"""Running repairs - only with an explicit, single-use approval, and always audited."""

from __future__ import annotations

import base64
import contextlib
import json
import os
import secrets
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path, PureWindowsPath
from typing import Any

from crashlens.core.runner import POWERSHELL, CommandRunner, _decode
from crashlens.repairs import cleanup
from crashlens.repairs.catalog import REPAIRS, Repair, RepairKind

APPROVAL_TTL = timedelta(minutes=10)
MAX_OUTPUT = 20_000


class ApprovalError(PermissionError):
    """Raised when a repair is attempted without a valid approval."""


class NotSupportedError(RuntimeError):
    pass


@dataclass(frozen=True)
class Approval:
    repair_id: str
    token: str
    granted_at: datetime
    approved_by: str  # "gui" / "cli"


class ApprovalRegistry:
    """Issues single-use approvals that expire. Thread-safe."""

    def __init__(self, ttl: timedelta = APPROVAL_TTL) -> None:
        self._ttl = ttl
        self._open: dict[str, Approval] = {}
        self._lock = threading.Lock()

    def grant(self, repair_id: str, approved_by: str, now: datetime | None = None) -> Approval:
        if repair_id not in REPAIRS:
            raise KeyError(repair_id)
        approval = Approval(
            repair_id=repair_id,
            token=secrets.token_hex(16),
            granted_at=now or datetime.now(timezone.utc),
            approved_by=approved_by,
        )
        with self._lock:
            self._open[approval.token] = approval
        return approval

    def consume(
        self, approval: Approval | None, repair_id: str, now: datetime | None = None
    ) -> None:
        if approval is None:
            raise ApprovalError("This repair needs your approval first.")
        now = now or datetime.now(timezone.utc)
        with self._lock:
            stored = self._open.pop(approval.token, None)
        if stored is None or stored != approval:
            raise ApprovalError("This approval is not valid or was already used.")
        if stored.repair_id != repair_id:
            raise ApprovalError("This approval was given for a different repair.")
        if now - stored.granted_at > self._ttl:
            raise ApprovalError("This approval has expired. Please approve the repair again.")


class AuditLog:
    """Append-only JSON-lines log of every repair attempt."""

    def __init__(self, path: Path | None) -> None:
        self.path = path
        self._lock = threading.Lock()

    def write(self, event: str, **fields: Any) -> None:
        if self.path is None:
            return
        record = {"time": datetime.now(timezone.utc).isoformat(), "event": event, **fields}
        line = json.dumps(record, ensure_ascii=False, default=str)
        with self._lock:
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                with self.path.open("a", encoding="utf-8") as fh:
                    fh.write(line + "\n")
            except OSError:
                pass  # auditing must never crash a repair

    def read(self, limit: int = 200) -> list[dict[str, Any]]:
        if self.path is None or not self.path.exists():
            return []
        out = []
        try:
            lines = self.path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            return []
        for line in lines[-limit:]:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return out


@dataclass
class RepairOutcome:
    repair_id: str
    status: str  # success / failed / cancelled / launched / simulated
    message: str
    returncode: int | None = None
    output: str = ""
    elevated_window: bool = False
    follow_up: list[str] = field(default_factory=list)


def _cmdline(argv: tuple[str, ...]) -> str:
    parts = []
    for a in argv:
        parts.append(f'"{a}"' if (" " in a and not a.startswith('"')) else a)
    return " ".join(parts)


def default_output_dir() -> Path:
    """Where elevated fixes write their output. ProgramData paths never contain quotes."""
    return Path(os.environ.get("ProgramData") or r"C:\ProgramData") / "CrashLens"


def _ps_quote(value: str) -> str:
    """Single-quoted PowerShell string literal (quotes doubled)."""
    return "'" + value.replace("'", "''") + "'"


EXIT_MARKER = "CRASHLENS-EXIT="


def elevated_batch_argv(items: list[tuple[Repair, Path]]) -> tuple[str, ...]:
    """Run one or more admin repairs hidden, with ONE Windows permission prompt.

    The commands come only from the repair catalog. They are put in a small
    PowerShell script, passed Base64-encoded (-EncodedCommand), so no quoting can
    break out. Each repair writes its output and exit code to its own log file,
    which CrashLens reads back and explains. Exit code 1223 = the person said No.
    """
    if not items:
        raise ValueError("nothing to run")
    lines = ["$ErrorActionPreference = 'Continue'", "$orig = [Console]::OutputEncoding"]
    folders = []
    for repair, log_path in items:
        log = str(log_path)
        if not (log_path.is_absolute() or PureWindowsPath(log).is_absolute()):
            raise ValueError("log path must be absolute")
        if repair.kind is not RepairKind.TOOL or not repair.argv:
            raise ValueError(f"{repair.id} cannot run elevated")
        folder = str(log_path.parent)
        if folder not in folders:
            folders.append(folder)
            lines.append(
                f"New-Item -ItemType Directory -Force -Path {_ps_quote(folder)} | Out-Null"
            )
        # sfc.exe writes UTF-16; everything else uses the console code page.
        enc = "[Text.Encoding]::Unicode" if repair.argv[0].lower() == "sfc.exe" else "$orig"
        args = " ".join(_ps_quote(a) for a in repair.argv)
        q = _ps_quote(log)
        lines += [
            f"[Console]::OutputEncoding = {enc}",
            f"& {args} *>&1 | Out-File -FilePath {q} -Encoding utf8",
            f'"{EXIT_MARKER}$LASTEXITCODE" | Out-File -FilePath {q} -Encoding utf8 -Append',
        ]
    lines.append("exit 0")
    encoded = base64.b64encode("\n".join(lines).encode("utf-16-le")).decode("ascii")
    outer = (
        "$ErrorActionPreference='Stop';"
        "try { "
        "$p = Start-Process -FilePath 'powershell.exe' -ArgumentList "
        f"'-NoProfile -NonInteractive -WindowStyle Hidden -EncodedCommand {encoded}' "
        "-Verb RunAs -WindowStyle Hidden -PassThru -Wait; exit $p.ExitCode"
        " } catch { exit 1223 }"
    )
    return (POWERSHELL, "-NoProfile", "-NonInteractive", "-Command", outer)


def elevated_argv(repair: Repair, log_path: Path) -> tuple[str, ...]:
    return elevated_batch_argv([(repair, log_path)])


def split_exit(output: str) -> tuple[int | None, str]:
    """Take the exit code CrashLens appended to a log, and return it with the rest."""
    code = None
    kept = []
    for line in output.splitlines():
        stripped = line.strip().lstrip("\ufeff")
        if stripped.startswith(EXIT_MARKER):
            try:
                code = int(stripped[len(EXIT_MARKER) :] or 0)
            except ValueError:
                code = None
        else:
            kept.append(line)
    return code, "\n".join(kept)


class RepairExecutor:
    def __init__(
        self,
        runner: CommandRunner,
        approvals: ApprovalRegistry,
        audit: AuditLog,
        *,
        is_windows: bool,
        is_admin: bool,
        dry_run: bool = False,
        output_dir: Path | None = None,
        temp_roots: list[Path] | None = None,
    ) -> None:
        self.runner = runner
        self.approvals = approvals
        self.audit = audit
        self.is_windows = is_windows
        self.is_admin = is_admin
        self.dry_run = dry_run
        self.output_dir = output_dir or default_output_dir()
        self.temp_roots = temp_roots  # None = the real temporary folders

    def plan(self, repair: Repair, log_path: Path | None = None) -> tuple[tuple[str, ...], bool]:
        """Return (argv, will_elevate) without running anything."""
        if repair.kind is RepairKind.TOOL and repair.needs_admin and not self.is_admin:
            log_path = log_path or self.output_dir / "fix-preview.txt"
            return elevated_argv(repair, log_path), True
        return repair.argv, False

    def execute(self, repair_id: str, approval: Approval | None) -> RepairOutcome:
        return self.execute_many([(repair_id, approval)])[0]

    def execute_many(
        self,
        items: list[tuple[str, Approval | None]],
        progress: Callable[[int, int, str], None] | None = None,
    ) -> list[RepairOutcome]:
        """Run several approved repairs. Every approval is checked BEFORE anything runs.
        Admin repairs are grouped so Windows asks for permission only once."""
        for rid, _ in items:
            if rid not in REPAIRS:
                raise KeyError(f"Unknown repair '{rid}'")
        for rid, approval in items:
            self.approvals.consume(approval, rid)  # raises ApprovalError
        plans = []
        for rid, approval in items:
            if approval is None:  # pragma: no cover - consume() already rejected it
                raise ApprovalError("This repair needs your approval first.")
            repair = REPAIRS[rid]
            log_path = self.output_dir / f"fix-{rid}-{approval.token[:8]}.txt"
            _, elevate = self.plan(repair, log_path)
            self.audit.write(
                "repair.approved",
                repair_id=rid,
                approved_by=approval.approved_by,
                approval=approval.token[:8],
                argv=list(repair.argv),
                elevated=elevate,
                dry_run=self.dry_run,
            )
            plans.append((repair, log_path, elevate))

        outcomes: dict[int, RepairOutcome] = {}
        total = len(plans)
        if self.dry_run:
            for i, (repair, _, _) in enumerate(plans):
                outcomes[i] = RepairOutcome(
                    repair.id, "simulated", f"Dry run - would run: {_cmdline(repair.argv)}"
                )
        elif not self.is_windows:
            for repair, _, _ in plans:
                self.audit.write("repair.refused", repair_id=repair.id, reason="not windows")
            raise NotSupportedError("Repairs can only run on Windows.")
        else:
            elevated = [(i, r, log) for i, (r, log, e) in enumerate(plans) if e]
            done = 0
            if elevated:
                if progress:
                    names = ", ".join(r.title for _, r, _ in elevated)
                    progress(done, total, names)
                for i, outcome in zip(
                    [i for i, _, _ in elevated], self._run_elevated(elevated), strict=True
                ):
                    outcomes[i] = outcome
                done += len(elevated)
            for i, (repair, _, elevate) in enumerate(plans):
                if elevate:
                    continue
                if progress:
                    progress(done, total, repair.title)
                outcomes[i] = self._run_one(repair)
                done += 1
        result = [outcomes[i] for i in range(total)]
        for o in result:
            self.audit.write(
                "repair.finished", repair_id=o.repair_id, status=o.status, returncode=o.returncode
            )
        return result

    def _run_elevated(self, items: list[tuple[int, Repair, Path]]) -> list[RepairOutcome]:
        argv = elevated_batch_argv([(r, log) for _, r, log in items])
        timeout = sum(r.timeout_s for _, r, _ in items) + 120
        res = self.runner.run(argv, timeout=timeout)
        out = []
        for _, repair, log in items:
            code, output = split_exit(self._read_log(log))
            if res.returncode == 1223:
                out.append(
                    RepairOutcome(
                        repair.id, "cancelled", "Administrator permission was not given.", 1223
                    )
                )
            elif res.not_found:
                out.append(RepairOutcome(repair.id, "failed", "Could not start the repair."))
            elif res.timed_out and code is None:
                out.append(
                    RepairOutcome(repair.id, "failed", "The repair timed out.", None, output)
                )
            elif code is None and not output.strip():
                out.append(RepairOutcome(repair.id, "failed", "The repair did not run."))
            else:
                out.append(interpret(repair, code if code is not None else 0, output))
        return out

    def _run_one(self, repair: Repair) -> RepairOutcome:
        rid = repair.id
        if repair.kind is RepairKind.BUILTIN:
            return self._builtin(repair)
        if repair.kind is RepairKind.OPEN:
            res = self.runner.open(repair.argv[0], " ".join(repair.argv[1:]))
            if res.returncode == 1223:
                return RepairOutcome(
                    rid, "cancelled", "Administrator permission was not given.", 1223
                )
            if not res.ok:
                return RepairOutcome(
                    rid, "failed", f"Could not open it: {res.stderr}", res.returncode
                )
            return RepairOutcome(rid, "launched", f"Opened: {repair.title}.")
        res = self.runner.run(repair.argv, timeout=repair.timeout_s)
        output = (res.stdout + ("\n" + res.stderr if res.stderr else ""))[-MAX_OUTPUT:]
        if res.timed_out:
            return RepairOutcome(rid, "failed", "The repair timed out.", None, output)
        if res.not_found:
            return RepairOutcome(rid, "failed", "The Windows tool was not found.")
        return interpret(repair, res.returncode, output)

    def _read_log(self, path: Path) -> str:
        """Read and then remove CrashLens' own output file for an elevated fix."""
        try:
            data = path.read_bytes()
        except OSError:
            return ""
        with contextlib.suppress(OSError):
            path.unlink()
        return _decode(data)[-MAX_OUTPUT:]

    def _builtin(self, repair: Repair) -> RepairOutcome:
        if repair.id == "clean_temp":
            roots = self.temp_roots
            if roots is None:
                roots = cleanup.temp_folders(self.is_admin)
            try:
                res = cleanup.clean_temp(roots)
            except cleanup.UnsafeFolderError as exc:
                return RepairOutcome(repair.id, "failed", f"Not cleaned: {exc}")
            if res.files_deleted == 0:
                msg = "There were no old temporary files to remove."
            else:
                msg = (
                    f"Freed {res.freed_text} by removing {res.files_deleted} old temporary file(s)."
                )
            if res.skipped:
                msg += f" {res.skipped} item(s) in use were left alone."
            follow = []
            if not self.is_admin:
                follow.append("To clean more, also use 'Free up space' (Windows Storage settings).")
            return RepairOutcome(repair.id, "success", msg, 0, follow_up=follow)
        return RepairOutcome(repair.id, "failed", "Unknown built-in fix.")


def interpret(repair: Repair, returncode: int, output: str) -> RepairOutcome:
    """Turn tool output into a plain-language result."""
    text = output.lower()
    rid = repair.id
    if rid == "sfc_scan":
        if "did not find any integrity violations" in text:
            return RepairOutcome(
                rid, "success", "No damaged system files were found.", returncode, output
            )
        if "successfully repaired" in text:
            return RepairOutcome(
                rid,
                "success",
                "Damaged system files were found and repaired. Restart the PC.",
                returncode,
                output,
                follow_up=["Restart the PC to finish the repair."],
            )
        if "unable to fix" in text:
            return RepairOutcome(
                rid,
                "failed",
                "Damaged files were found but could not all be repaired.",
                returncode,
                output,
                follow_up=["Run 'Repair the Windows component store (DISM)', then SFC again."],
            )
        if "pending system repair" in text:
            return RepairOutcome(
                rid,
                "failed",
                "A previous repair is waiting for a restart. Restart, then run SFC again.",
                returncode,
                output,
            )
    if rid.startswith("dism_"):
        if "no component store corruption detected" in text:
            return RepairOutcome(
                rid, "success", "The Windows component store is healthy.", returncode, output
            )
        if "the restore operation completed successfully" in text:
            return RepairOutcome(
                rid,
                "success",
                "The component store was repaired.",
                returncode,
                output,
                follow_up=["Run SFC again to repair system files from the fixed store."],
            )
        if "repairable" in text:
            return RepairOutcome(
                rid,
                "success",
                "Damage was found that can be repaired.",
                returncode,
                output,
                follow_up=["Run 'Repair the Windows component store (DISM)'."],
            )
    if rid == "chkdsk_scan":
        if "found no problems" in text:
            return RepairOutcome(
                rid, "success", "No file-system problems were found.", returncode, output
            )
        if "found problems" in text or "errors found" in text:
            return RepairOutcome(
                rid,
                "failed",
                "File-system problems were found.",
                returncode,
                output,
                follow_up=[
                    "Back up important files, then repair the drive from its Properties > "
                    "Tools > Check, or run 'chkdsk /spotfix' as administrator."
                ],
            )
    if rid == "windows_update_scan" and returncode == 0:
        return RepairOutcome(
            rid,
            "success",
            "Windows Update is now checking for updates. They download and install in the "
            "background.",
            returncode,
            output,
            follow_up=["Open Windows Update later to see progress and restart if asked."],
        )
    if rid == "reset_windows_update":
        if "crashlens-reset-complete" in text:
            return RepairOutcome(
                rid,
                "success",
                "Windows Update was reset.",
                returncode,
                output,
                follow_up=["Restart the PC, then check for updates again."],
            )
        return RepairOutcome(
            rid, "failed", "Windows Update could not be reset.", returncode, output
        )
    if rid == "rescan_devices" and returncode == 0:
        return RepairOutcome(
            rid,
            "success",
            "Windows looked for hardware again.",
            returncode,
            output,
            follow_up=["If a device still doesn't work, check for Windows updates."],
        )
    if rid == "update_defender":
        if "crashlens-defender-updated" in text:
            return RepairOutcome(
                rid, "success", "Virus protection is up to date.", returncode, output
            )
        return RepairOutcome(
            rid,
            "failed",
            "Virus protection could not be updated. If you use another "
            "antivirus, update it in that program.",
            returncode,
            output,
        )
    if rid == "quick_virus_scan":
        if "crashlens-scan-complete" in text:
            return RepairOutcome(
                rid,
                "success",
                "Quick scan finished. Windows Security shows anything it found.",
                returncode,
                output,
            )
        return RepairOutcome(rid, "failed", "The virus scan did not run.", returncode, output)
    if returncode == 0:
        return RepairOutcome(rid, "success", "Finished successfully.", returncode, output)
    return RepairOutcome(
        rid, "failed", f"Finished with exit code {returncode}.", returncode, output
    )
