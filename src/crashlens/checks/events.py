"""Reading the Windows Event Log through fixed, read-only PowerShell queries."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from crashlens.core.runner import CommandRunner, PsQuery, run_ps_json


@dataclass(frozen=True)
class EventRecord:
    id: int
    provider: str
    time: datetime | None
    level: int
    message: str
    data: tuple[str, ...]

    def datum(self, index: int, default: str = "") -> str:
        return self.data[index] if 0 <= index < len(self.data) else default


_SELECT = (
    "Select-Object "
    "@{n='Id';e={$_.Id}},"
    "@{n='Provider';e={$_.ProviderName}},"
    "@{n='Time';e={$_.TimeCreated.ToUniversalTime().ToString('o')}},"
    "@{n='Level';e={[int]$_.Level}},"
    "@{n='Message';e={$_.Message}},"
    "@{n='Data';e={@($_.Properties | ForEach-Object { [string]$_.Value })}}"
)


def _event_query(qid: str, filter_ps: str, max_events: int = 300, timeout: float = 90) -> PsQuery:
    script = (
        f"Get-WinEvent -FilterHashtable {filter_ps} -MaxEvents {int(max_events)} "
        f"-ErrorAction SilentlyContinue | {_SELECT}"
    )
    return PsQuery(qid, script, timeout)


def _since(days: int) -> str:
    return f"StartTime=(Get-Date).AddDays(-{int(days)})"


def system_crash_query(days: int) -> PsQuery:
    """Bug checks (1001), Kernel-Power 41, unexpected shutdown (6008), display TDR (4101)."""
    return _event_query(
        "events.system_crash",
        "@{LogName='System';Id=41,1001,6008,4101;" + _since(days) + "}",
    )


def whea_query(days: int) -> PsQuery:
    return _event_query(
        "events.whea",
        "@{LogName='System';ProviderName='Microsoft-Windows-WHEA-Logger';" + _since(days) + "}",
        max_events=200,
    )


def app_crash_query(days: int) -> PsQuery:
    return _event_query(
        "events.app_crash",
        "@{LogName='Application';ProviderName='Application Error','Application Hang';"
        "Id=1000,1002;" + _since(days) + "}",
        max_events=500,
    )


def storage_event_query(days: int) -> PsQuery:
    return _event_query(
        "events.storage",
        "@{LogName='System';"
        "ProviderName='disk','Ntfs','Microsoft-Windows-Ntfs','stornvme','storahci';"
        "Id=7,11,51,55,98,129,153;" + _since(days) + "}",
        max_events=300,
    )


def parse_time(value: Any) -> datetime | None:
    """Parse PowerShell 'o' format (7 fractional digits) and similar ISO strings."""
    if not value or not isinstance(value, str):
        return None
    s = value.strip()
    m = re.match(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(\.\d+)?(Z|[+-]\d{2}:\d{2})?$", s)
    if not m:
        # /Date(1700000000000)/ - older ConvertTo-Json date format
        d = re.match(r"^/Date\((-?\d+)\)/$", s)
        if d:
            return datetime.fromtimestamp(int(d.group(1)) / 1000, tz=timezone.utc)
        return None
    base, frac, tz = m.groups()
    frac = "." + frac[1:7] if frac else ""  # Python accepts at most 6 digits
    tzs = "+00:00" if tz in (None, "Z") else tz
    try:
        return datetime.fromisoformat(f"{base}{frac}{tzs}").astimezone(timezone.utc)
    except ValueError:
        return None


def to_record(raw: dict[str, Any]) -> EventRecord | None:
    try:
        eid = int(raw.get("Id"))
    except (TypeError, ValueError):
        return None
    data = raw.get("Data") or []
    if not isinstance(data, list):
        data = [data]
    level = raw.get("Level")
    try:
        level_i = int(level) if level is not None else 0
    except (TypeError, ValueError):
        level_i = 0
    return EventRecord(
        id=eid,
        provider=str(raw.get("Provider") or ""),
        time=parse_time(raw.get("Time")),
        level=level_i,
        message=str(raw.get("Message") or ""),
        data=tuple("" if d is None else str(d) for d in data),
    )


def fetch(runner: CommandRunner, query: PsQuery) -> list[EventRecord]:
    records = []
    for raw in run_ps_json(runner, query):
        if isinstance(raw, dict):
            rec = to_record(raw)
            if rec is not None:
                records.append(rec)
    return records
