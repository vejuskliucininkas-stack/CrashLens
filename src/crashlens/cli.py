"""Command-line interface.

crashlens                    open the desktop app
crashlens scan [--json]      run all checks and print the results
crashlens report FILE        save a shareable report (.html / .md / .json)
crashlens repairs            list available repairs
crashlens repair ID          run one repair after you type RUN to approve it
crashlens audit              show the repair history
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import TextIO

from crashlens import __version__
from crashlens.core.models import CheckStatus, ScanReport, Severity
from crashlens.environment import Environment, build_environment
from crashlens.repairs.catalog import REPAIRS
from crashlens.repairs.executor import ApprovalError, NotSupportedError
from crashlens.report import write_report
from crashlens.report.export import report_data

APPROVAL_WORD = "RUN"

_STATUS_MARK = {
    CheckStatus.OK: "ok  ",
    CheckStatus.ISSUES: "!!  ",
    CheckStatus.UNAVAILABLE: "--  ",
    CheckStatus.ERROR: "ERR ",
}


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="crashlens", description="Windows 11 troubleshooting.")
    p.add_argument("--version", action="version", version=f"CrashLens {__version__}")
    p.add_argument("--demo", action="store_true", help="use sample data instead of this PC")
    sub = p.add_subparsers(dest="cmd")

    s = sub.add_parser("scan", help="run all checks")
    s.add_argument("--days", type=int, default=30, help="how far back to look (1-365)")
    s.add_argument("--json", action="store_true", help="print JSON (personal details removed)")
    s.add_argument("--no-redact", action="store_true", help="keep personal details in --json")

    r = sub.add_parser("report", help="save a shareable report")
    r.add_argument("output", type=Path, help="file name ending in .html, .md or .json")
    r.add_argument("--days", type=int, default=30)
    r.add_argument("--no-redact", action="store_true", help="keep personal details")
    r.add_argument("--force", action="store_true", help="replace the file if it exists")

    sub.add_parser("repairs", help="list available repairs")

    rp = sub.add_parser("repair", help="run one repair (asks for approval)")
    rp.add_argument("repair_id", choices=sorted(REPAIRS))
    rp.add_argument("--dry-run", action="store_true", help="show what would run, run nothing")

    sub.add_parser("audit", help="show the repair history")
    sub.add_parser("gui", help="open the desktop app")
    return p


def _scan(env: Environment, days: int, out: TextIO, quiet: bool = False) -> ScanReport:
    def progress(i: int, total: int, name: str) -> None:
        if not quiet and name != "Done":
            print(f"  [{i + 1}/{total}] {name}...", file=sys.stderr)

    return env.scanner(days).run(progress=progress)


def print_report(report: ScanReport, out: TextIO) -> None:
    sysi = report.system
    print(f"CrashLens {__version__} - {sysi.os_name} {sysi.os_version}".rstrip(), file=out)
    if report.demo:
        print("DEMO DATA - not this PC", file=out)
    if sysi.is_windows and not sysi.is_admin:
        print("Tip: run as administrator to read crash dumps and disk details.", file=out)
    print("", file=out)
    for r in report.results:
        print(f"{_STATUS_MARK[r.status]}{r.name}: {r.message}", file=out)
    print("", file=out)
    findings = [f for f in report.findings if f.severity > Severity.INFO]
    if not findings:
        print("No problems found.", file=out)
    for f in findings:
        print(f"[{f.severity.label.upper():8}] {f.title}", file=out)
        print(f"           {f.summary}", file=out)
        for rec in f.recommendations[:3]:
            print(f"           - {rec}", file=out)
    repairs = report.recommended_repairs()
    if repairs:
        print("\nSuggested repairs (each asks for your approval):", file=out)
        for rid in repairs:
            print(f"  crashlens repair {rid:24} {REPAIRS[rid].title}", file=out)


def _cmd_repairs(out: TextIO) -> int:
    for r in REPAIRS.values():
        flags = []
        if r.needs_admin:
            flags.append("admin")
        if r.changes_system:
            flags.append("changes system files")
        if r.needs_restart:
            flags.append("restart")
        extra = f" ({', '.join(flags)})" if flags else ""
        print(f"{r.id:26} {r.title}{extra}", file=out)
    return 0


def _cmd_repair(
    env: Environment, rid: str, dry_run: bool, out: TextIO, ask: Callable[[str], str]
) -> int:
    repair = REPAIRS[rid]
    argv, elevate = env.executor.plan(repair)
    print(f"{repair.title}\n", file=out)
    print(f"What happens: {repair.what_happens}", file=out)
    print(f"Command:      {' '.join(repair.argv)}", file=out)
    print(f"Takes:        {repair.duration}", file=out)
    if elevate:
        print("Windows will ask for administrator permission.", file=out)
    if repair.caution:
        print(f"Caution:      {repair.caution}", file=out)
    if dry_run:
        env.executor.dry_run = True
    try:
        answer = ask(f"\nType {APPROVAL_WORD} to approve, anything else to cancel: ")
    except (EOFError, KeyboardInterrupt):
        answer = ""
    if answer.strip() != APPROVAL_WORD:
        print("Cancelled. Nothing was run.", file=out)
        return 1
    approval = env.executor.approvals.grant(rid, approved_by="cli")
    try:
        outcome = env.executor.execute(rid, approval)
    except (ApprovalError, NotSupportedError) as exc:
        print(f"Not run: {exc}", file=out)
        return 2
    print(f"\n{outcome.status.upper()}: {outcome.message}", file=out)
    for step in outcome.follow_up:
        print(f"Next: {step}", file=out)
    if outcome.output and not outcome.elevated_window:
        print("\n--- tool output ---", file=out)
        print(outcome.output.strip()[-4000:], file=out)
    return 0 if outcome.status in ("success", "launched", "simulated") else 1


def _cmd_audit(env: Environment, out: TextIO) -> int:
    rows = env.audit.read()
    if not rows:
        print("No repairs have been run yet.", file=out)
    for row in rows:
        detail = row.get("status") or row.get("approved_by") or row.get("reason") or ""
        print(
            f"{row.get('time', '?')[:19]}  {row.get('event', '?'):16} "
            f"{row.get('repair_id', ''):24} {detail}",
            file=out,
        )
    return 0


def _launch_gui(demo: bool) -> int:
    try:
        from crashlens.gui.app import main as gui_main
    except ImportError as exc:  # PySide6 missing
        print(f"The desktop app needs PySide6: pip install PySide6-Essentials ({exc})")
        return 2
    return gui_main(["--demo"] if demo else [])


def main(
    argv: list[str] | None = None,
    out: TextIO | None = None,
    ask: Callable[[str], str] = input,
    env: Environment | None = None,
) -> int:
    out = out or sys.stdout
    args = _parser().parse_args(argv)
    if args.cmd in (None, "gui"):
        return _launch_gui(args.demo)
    if args.cmd == "repairs":
        return _cmd_repairs(out)
    env = env or build_environment(demo=args.demo)

    if args.cmd == "scan":
        if not 1 <= args.days <= 365:
            print("--days must be between 1 and 365", file=sys.stderr)
            return 2
        report = _scan(env, args.days, out, quiet=args.json)
        if args.json:
            print(json.dumps(report_data(report, redact=not args.no_redact), indent=2), file=out)
        else:
            print_report(report, out)
        return 0
    if args.cmd == "report":
        if not 1 <= args.days <= 365:
            print("--days must be between 1 and 365", file=sys.stderr)
            return 2
        if args.output.exists() and not args.force:
            print(f"{args.output} already exists. Use --force to replace it.", file=out)
            return 1
        report = _scan(env, args.days, out)
        try:
            path = write_report(
                report, args.output, redact=not args.no_redact, overwrite=args.force
            )
        except FileExistsError:
            print(f"{args.output} already exists. Use --force to replace it.", file=out)
            return 1
        except ValueError as exc:
            print(str(exc), file=out)
            return 2
        print(f"Report saved: {path}", file=out)
        return 0
    if args.cmd == "repair":
        return _cmd_repair(env, args.repair_id, args.dry_run, out, ask)
    if args.cmd == "audit":
        return _cmd_audit(env, out)
    return 2


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
