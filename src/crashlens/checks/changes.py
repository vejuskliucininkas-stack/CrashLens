"""What changed on the PC: driver installs, Windows updates, program installs.

Two uses:
* Windows updates that keep failing are reported on their own.
* When blue screens or unexpected restarts happened, changes made in the days
  before the FIRST one are listed - "crashes started right after this driver
  update" is often the most useful clue there is.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta

from crashlens.checks import events as ev
from crashlens.checks.base import Check, CheckContext
from crashlens.checks.crashes import build_incidents
from crashlens.core.models import Category, Finding, Severity
from crashlens.core.runner import PsQuery, QueryError, run_ps_json

BEFORE_WINDOW = timedelta(days=7)
MAX_LINES = 10

UPDATE_HISTORY_QUERY = PsQuery(
    "updates.history",
    "$q=(New-Object -ComObject Microsoft.Update.Session).CreateUpdateSearcher(); "
    "$n=$q.GetTotalHistoryCount(); if ($n -gt 0) { $q.QueryHistory(0,[Math]::Min($n,200)) "
    "| Where-Object { $_.Operation -eq 1 -and $_.Title -notmatch "
    "'Security Intelligence|Definition Update|antimalware platform' } "
    "| Select-Object Title,ResultCode,HResult,"
    "@{n='Date';e={[datetime]::SpecifyKind($_.Date,'Utc').ToString('o')}} }",
    timeout=120,
)


def driver_install_query(days: int) -> PsQuery:
    return PsQuery(
        "events.driver_installs",
        "Get-WinEvent -FilterHashtable @{LogName='System';"
        "ProviderName='Microsoft-Windows-UserPnp';Id=20001,20003;"
        f"StartTime=(Get-Date).AddDays(-{int(days)})}} -MaxEvents 300 "
        "-ErrorAction SilentlyContinue | Select-Object "
        "@{n='Id';e={$_.Id}},@{n='Provider';e={$_.ProviderName}},"
        "@{n='Time';e={$_.TimeCreated.ToUniversalTime().ToString('o')}},"
        "@{n='Level';e={[int]$_.Level}},@{n='Message';e={$_.Message}},"
        "@{n='Data';e={@($_.Properties | ForEach-Object { [string]$_.Value })}}",
        timeout=90,
    )


def app_install_query(days: int) -> PsQuery:
    return PsQuery(
        "events.app_installs",
        "Get-WinEvent -FilterHashtable @{LogName='Application';ProviderName='MsiInstaller';"
        f"Id=11707,11724;StartTime=(Get-Date).AddDays(-{int(days)})}} -MaxEvents 300 "
        "-ErrorAction SilentlyContinue | Select-Object "
        "@{n='Id';e={$_.Id}},@{n='Provider';e={$_.ProviderName}},"
        "@{n='Time';e={$_.TimeCreated.ToUniversalTime().ToString('o')}},"
        "@{n='Level';e={[int]$_.Level}},@{n='Message';e={$_.Message}},"
        "@{n='Data';e={@($_.Properties | ForEach-Object { [string]$_.Value })}}",
        timeout=90,
    )


@dataclass(frozen=True)
class Change:
    time: datetime
    kind: str  # "driver" / "update" / "program"
    text: str


_INF = re.compile(r"([\w.-]+\.inf)(?:_[\w]+)?", re.I)
_PRODUCT = re.compile(r"Product:\s*(.+?)\s*--", re.I)


def _driver_change(e: ev.EventRecord) -> Change | None:
    if e.time is None:
        return None
    blob = " ".join([*e.data, e.message])
    m = _INF.search(blob)
    name = m.group(1) if m else "a device driver"
    verb = "removed" if e.id == 20003 else "installed"
    device = next((d for d in e.data if "\\" in d and not d.lower().endswith(".inf")), "")
    detail = f" for {device.split(chr(92))[0]} device" if device else ""
    return Change(e.time, "driver", f"Driver {name} {verb}{detail}")


def _app_change(e: ev.EventRecord) -> Change | None:
    if e.time is None:
        return None
    blob = " ".join([*e.data, e.message])
    m = _PRODUCT.search(blob)
    name = m.group(1) if m else (e.datum(0)[:80] or "a program")
    verb = "removed" if e.id == 11724 else "installed"
    return Change(e.time, "program", f"Program {name} {verb}")


def _n(n: int, word: str) -> str:
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def _short(title: str) -> str:
    title = " ".join(title.split())
    return title if len(title) <= 110 else title[:107] + "..."


class ChangesCheck(Check):
    id = "crash.changes"
    name = "Recent changes and update failures"

    def collect(self, ctx: CheckContext) -> tuple[list[Finding], str]:
        findings: list[Finding] = []
        changes: list[Change] = []
        notes: list[str] = []
        cutoff = ctx.now - timedelta(days=ctx.lookback_days) - BEFORE_WINDOW

        # Windows Update history: changes + failures
        try:
            history = run_ps_json(ctx.runner, UPDATE_HISTORY_QUERY)
        except QueryError:
            history = []
            notes.append("Windows Update history unavailable.")
        failed: list[tuple[datetime, str, str]] = []
        for h in history:
            t = ev.parse_time(h.get("Date"))
            if t is None or t < cutoff:
                continue
            title = _short(str(h.get("Title") or "Windows update"))
            code = h.get("ResultCode")
            if code in (2, 3):  # succeeded / succeeded with errors
                changes.append(Change(t, "update", f"Update installed: {title}"))
            elif code in (4, 5):  # failed / aborted
                hr = h.get("HResult")
                hr_s = f"0x{int(hr) & 0xFFFFFFFF:08X}" if isinstance(hr, int) and hr else ""
                failed.append((t, title, hr_s))

        recent_failed = [f for f in failed if f[0] >= ctx.now - timedelta(days=ctx.lookback_days)]
        if recent_failed:
            titles = {f[1] for f in recent_failed}
            findings.append(
                Finding(
                    id="updates-failing",
                    title="Windows updates are failing to install",
                    severity=Severity.MEDIUM if len(recent_failed) >= 2 else Severity.LOW,
                    category=Category.UPDATES,
                    summary=(
                        f"{_n(len(recent_failed), 'update installation')} failed in the last "
                        f"{ctx.lookback_days} days"
                        + (
                            f" ({len(titles)} different updates)."
                            if len(titles) > 1
                            else " - the same update kept failing."
                        )
                    ),
                    evidence=tuple(
                        f"{t:%Y-%m-%d} - {title}" + (f" - error {hr}" if hr else "")
                        for t, title, hr in sorted(recent_failed, reverse=True)[:MAX_LINES]
                    ),
                    recommendations=(
                        "Restart the PC, then open Windows Update and try again.",
                        "Make sure there is at least 20 GB free on drive C:.",
                        "Search Microsoft Support for the error code shown here.",
                        "If it keeps failing, run the DISM repair and System File Checker.",
                    ),
                    repair_ids=("reset_windows_update", "dism_restore", "sfc_scan"),
                    occurrences=len(recent_failed),
                    last_seen=max(f[0] for f in recent_failed),
                )
            )

        # Driver and program installs
        days = ctx.lookback_days + BEFORE_WINDOW.days
        for qid, query, parse in (
            ("events.driver_installs", driver_install_query(days), _driver_change),
            ("events.app_installs", app_install_query(days), _app_change),
        ):
            try:
                for e in ctx.cached(qid, lambda q=query: ev.fetch(ctx.runner, q)):
                    c = parse(e)
                    if c:
                        changes.append(c)
            except QueryError:
                notes.append(f"{qid.split('.')[1].replace('_', ' ')} unavailable.")

        # Correlate with the first crash
        try:
            system_events = ctx.cached(
                "events.system_crash",
                lambda: ev.fetch(ctx.runner, ev.system_crash_query(ctx.lookback_days)),
            )
        except QueryError:
            system_events = []
        incidents = [i for i in build_incidents(system_events, []) if i.time]
        if incidents:
            first = min(i.time for i in incidents if i.time)
            before = sorted(
                (c for c in changes if first - BEFORE_WINDOW <= c.time <= first),
                key=lambda c: c.time,
                reverse=True,
            )
            if before:
                drivers = sum(1 for c in before if c.kind == "driver")
                findings.append(
                    Finding(
                        id="changes-before-crashes",
                        title="Changes made just before the crashes started",
                        severity=Severity.LOW,
                        category=Category.CRASH,
                        summary=(
                            f"The first crash or unexpected restart in this period was on "
                            f"{first:%Y-%m-%d}. In the 7 days before it, "
                            f"{_n(len(before), 'change')} {'was' if len(before) == 1 else 'were'} "
                            "made"
                            + (f", including {_n(drivers, 'driver change')}" if drivers else "")
                            + ". If the problems began right after one of these, it is a likely "
                            "cause."
                        ),
                        evidence=tuple(
                            f"{c.time:%Y-%m-%d %H:%M} - {c.text}" for c in before[:MAX_LINES]
                        )
                        + (
                            (f"... and {len(before) - MAX_LINES} more",)
                            if len(before) > MAX_LINES
                            else ()
                        ),
                        recommendations=(
                            "For a driver installed just before: Device Manager > the device > "
                            "Properties > Driver > Roll Back Driver.",
                            "For a Windows update: Settings > Windows Update > Update history > "
                            "Uninstall updates.",
                            "For a program: uninstall it and see whether the crashes stop.",
                        ),
                        repair_ids=("open_device_manager", "open_windows_update"),
                        occurrences=len(before),
                        last_seen=before[0].time,
                    )
                )
        msg = f"{len(changes)} change(s) found"
        if recent_failed:
            msg += f", {len(recent_failed)} failed update(s)"
        msg += "."
        if notes:
            msg += " " + " ".join(notes)
        return findings, msg
