"""The only place CrashLens starts external processes.

Rules enforced here (see docs/SECURITY.md):
* Arguments are always passed as a list - never through a shell string.
* Every call has a timeout.
* Output is decoded defensively (UTF-8, invalid bytes replaced).
* Nothing user-supplied is ever spliced into a PowerShell script. Queries are
  fixed strings defined in the source code.
"""

from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

DEFAULT_TIMEOUT = 60.0

POWERSHELL = "powershell.exe"
PS_BASE_ARGS = ("-NoProfile", "-NonInteractive", "-Command")
PS_PRELUDE = (
    "$ErrorActionPreference='SilentlyContinue';"
    "$ProgressPreference='SilentlyContinue';"
    "[Console]::OutputEncoding=[System.Text.Encoding]::UTF8;"
)
QUERY_MARKER = "#crashlens-query:"


@dataclass(frozen=True)
class CommandResult:
    args: tuple[str, ...]
    returncode: int
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False
    not_found: bool = False

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and not self.timed_out and not self.not_found


class CommandRunner(Protocol):
    def run(self, args: Sequence[str], timeout: float = DEFAULT_TIMEOUT) -> CommandResult: ...


class SubprocessRunner:
    """Real runner used on Windows."""

    def run(self, args: Sequence[str], timeout: float = DEFAULT_TIMEOUT) -> CommandResult:
        argv = tuple(str(a) for a in args)
        if not argv:
            raise ValueError("empty command")
        kwargs: dict[str, Any] = {}
        if sys.platform == "win32":
            # Do not flash console windows over the GUI.
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            proc = subprocess.run(
                argv,
                shell=False,
                capture_output=True,
                timeout=timeout,
                check=False,
                stdin=subprocess.DEVNULL,
                **kwargs,
            )
        except subprocess.TimeoutExpired as exc:
            return CommandResult(argv, -1, _decode(exc.stdout), _decode(exc.stderr), timed_out=True)
        except (FileNotFoundError, PermissionError, OSError) as exc:
            return CommandResult(argv, -1, "", str(exc), not_found=True)
        return CommandResult(argv, proc.returncode, _decode(proc.stdout), _decode(proc.stderr))


def _decode(data: bytes | str | None) -> str:
    if data is None:
        return ""
    if isinstance(data, str):
        return data
    # Some Windows tools (sfc.exe) write UTF-16 LE when their output is piped.
    if data.startswith(b"\xff\xfe") or (len(data) >= 4 and data[1::2].count(0) > len(data) // 4):
        return data.decode("utf-16-le", errors="replace").lstrip("﻿").replace("\x00", "")
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("utf-8", errors="replace")


# --------------------------------------------------------------------------- #
# PowerShell JSON queries
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class PsQuery:
    """A fixed, read-only PowerShell query whose output is converted to JSON."""

    id: str
    script: str
    timeout: float = DEFAULT_TIMEOUT

    def argv(self) -> tuple[str, ...]:
        body = (
            f"{QUERY_MARKER}{self.id}\n{PS_PRELUDE}"
            f"$r = & {{ {self.script} }}; "
            "if ($null -ne $r) { ConvertTo-Json -InputObject @($r) -Depth 5 -Compress }"
        )
        return (POWERSHELL, *PS_BASE_ARGS, body)


class QueryError(RuntimeError):
    pass


def run_ps_json(runner: CommandRunner, query: PsQuery) -> list[Any]:
    """Run a query and return a list of records (empty list when nothing matched)."""
    res = runner.run(query.argv(), timeout=query.timeout)
    if res.not_found:
        raise QueryError("PowerShell is not available on this system")
    if res.timed_out:
        raise QueryError(f"query '{query.id}' timed out after {query.timeout:.0f}s")
    text = res.stdout.strip()
    if not text:
        if res.returncode not in (0, 1):
            raise QueryError(f"query '{query.id}' failed: {res.stderr.strip()[:300]}")
        return []
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise QueryError(f"query '{query.id}' returned invalid JSON: {exc}") from exc
    if data is None:
        return []
    if isinstance(data, list):
        return [d for d in data if d is not None]
    return [data]


# --------------------------------------------------------------------------- #
# Test / demo runner
# --------------------------------------------------------------------------- #


@dataclass
class FakeRunner:
    """Runner that returns canned output. Used by tests and demo mode.

    * ``queries`` maps a PsQuery id to the Python object it should return
      (serialised to JSON as PowerShell would) or to a CommandResult.
    * ``commands`` maps the first argv element (lower-cased exe name) to a
      CommandResult or a callable producing one.
    """

    queries: dict[str, Any] = field(default_factory=dict)
    commands: dict[str, CommandResult | Callable[[tuple[str, ...]], CommandResult]] = field(
        default_factory=dict
    )
    calls: list[tuple[str, ...]] = field(default_factory=list)

    def run(self, args: Sequence[str], timeout: float = DEFAULT_TIMEOUT) -> CommandResult:
        argv = tuple(str(a) for a in args)
        self.calls.append(argv)
        qid = query_id_from_argv(argv)
        if qid is not None:
            if qid not in self.queries:
                return CommandResult(argv, 0, "")
            value = self.queries[qid]
            if isinstance(value, CommandResult):
                return value
            return CommandResult(argv, 0, json.dumps(value))
        exe = argv[0].lower().rsplit("\\", 1)[-1]
        handler = self.commands.get(exe)
        if handler is None:
            return CommandResult(argv, -1, "", f"{exe}: not found (fake)", not_found=True)
        return handler(argv) if callable(handler) else handler


def query_id_from_argv(argv: Sequence[str]) -> str | None:
    if not argv or not argv[0].lower().endswith("powershell.exe"):
        return None
    script = argv[-1]
    if not script.startswith(QUERY_MARKER):
        return None
    return script[len(QUERY_MARKER) :].split("\n", 1)[0].strip()
