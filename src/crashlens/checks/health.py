"""System health checks. All read-only."""

from __future__ import annotations

import re
import zlib
from datetime import timedelta

from crashlens.checks import events as ev
from crashlens.checks.base import Check, CheckContext, Unavailable
from crashlens.core.models import Category, Finding, Severity
from crashlens.core.runner import PsQuery, run_ps_json

GB = 1024**3


def _num(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _fmt_gb(n_bytes: float) -> str:
    return f"{n_bytes / GB:.1f} GB"


# --------------------------------------------------------------------------- #
# Disk space
# --------------------------------------------------------------------------- #

DISK_SPACE_QUERY = PsQuery(
    "cim.logical_disks",
    "Get-CimInstance -ClassName Win32_LogicalDisk -Filter 'DriveType=3' "
    "| Select-Object DeviceID,VolumeName,Size,FreeSpace",
)


class DiskSpaceCheck(Check):
    id = "health.disk_space"
    name = "Free disk space"

    def collect(self, ctx: CheckContext) -> tuple[list[Finding], str]:
        rows = run_ps_json(ctx.runner, DISK_SPACE_QUERY)
        if not rows:
            raise Unavailable("No local drives were reported.")
        findings = []
        parts = []
        for r in rows:
            dev = str(r.get("DeviceID") or "?")
            size, free = _num(r.get("Size")), _num(r.get("FreeSpace"))
            if size <= 0:
                continue
            pct = free / size * 100
            parts.append(f"{dev} {_fmt_gb(free)} free ({pct:.0f}%)")
            ctx.metrics.setdefault("drives", []).append(
                {"drive": dev, "label": str(r.get("VolumeName") or ""), "size": size, "free": free}
            )
            system = dev.upper() == "C:"
            if pct < 5 or free < 5 * GB:
                sev = Severity.HIGH if system else Severity.MEDIUM
            elif pct < 10 or free < 15 * GB:
                sev = Severity.MEDIUM if system else Severity.LOW
            else:
                continue
            findings.append(
                Finding(
                    id=f"disk-space-{dev.rstrip(':').lower()}",
                    title=f"Drive {dev} is nearly full",
                    severity=sev,
                    category=Category.STORAGE,
                    summary=(
                        f"Only {_fmt_gb(free)} of {_fmt_gb(size)} is free ({pct:.0f}%)."
                        + (
                            " Windows needs free space on C: for updates, the page file and "
                            "crash dumps; a full system drive causes slowdowns and failed updates."
                            if system
                            else ""
                        )
                    ),
                    recommendations=(
                        "Open Storage settings to see what is using space and review the cleanup "
                        "suggestions.",
                        "Move large personal files (videos, downloads) to another drive or cloud "
                        "storage.",
                        "Uninstall programs and games you no longer use.",
                    ),
                    repair_ids=("clean_temp", "open_storage_settings"),
                )
            )
        return findings, "; ".join(parts) or "No drives with a known size."


# --------------------------------------------------------------------------- #
# Physical disk health
# --------------------------------------------------------------------------- #

DISK_HEALTH_QUERY = PsQuery(
    "storage.physical_disks",
    "Get-PhysicalDisk | ForEach-Object { $c = $_ | Get-StorageReliabilityCounter; "
    "[pscustomobject]@{ Name=$_.FriendlyName; Media=[string]$_.MediaType; "
    "Bus=[string]$_.BusType; Health=[string]$_.HealthStatus; "
    "Status=[string]($_.OperationalStatus -join ','); "
    "Temperature=$c.Temperature; Wear=$c.Wear; "
    "ReadErrors=$c.ReadErrorsUncorrected; WriteErrors=$c.WriteErrorsUncorrected } }",
    timeout=90,
)


class DiskHealthCheck(Check):
    id = "health.disk_health"
    name = "Disk health"

    def collect(self, ctx: CheckContext) -> tuple[list[Finding], str]:
        rows = run_ps_json(ctx.runner, DISK_HEALTH_QUERY)
        if not rows:
            raise Unavailable("Disk health information is not available.")
        findings = []
        parts = []
        for i, r in enumerate(rows):
            name = str(r.get("Name") or f"Disk {i}")
            health = str(r.get("Health") or "Unknown")
            status = str(r.get("Status") or "")
            parts.append(f"{name}: {health}")
            wear = r.get("Wear")
            temp = r.get("Temperature")
            uncorrected = int(_num(r.get("ReadErrors"))) + int(_num(r.get("WriteErrors")))
            evidence = [f"Health: {health}", f"Status: {status or 'unknown'}"]
            if wear not in (None, ""):
                evidence.append(f"Wear: {int(_num(wear))}%")
            if temp not in (None, "", 0):
                evidence.append(f"Temperature: {int(_num(temp))} C")
            if uncorrected:
                evidence.append(f"Uncorrected read/write errors: {uncorrected}")

            sev = None
            summary = ""
            if health.lower() == "unhealthy":
                sev = Severity.CRITICAL
                summary = "Windows reports this disk as UNHEALTHY. It may fail soon."
            elif health.lower() == "warning" or uncorrected > 0:
                sev = Severity.HIGH
                summary = "Windows reports warnings for this disk."
            elif wear not in (None, "") and _num(wear) >= 90:
                sev = Severity.HIGH
                summary = f"This SSD has used {int(_num(wear))}% of its rated life."
            elif wear not in (None, "") and _num(wear) >= 70:
                sev = Severity.LOW
                summary = f"This SSD has used {int(_num(wear))}% of its rated life."
            elif temp not in (None, "") and _num(temp) >= 70:
                sev = Severity.MEDIUM
                summary = f"This disk is running hot ({int(_num(temp))} C)."
            if sev is None:
                continue
            findings.append(
                Finding(
                    id=f"disk-health-{i}",
                    title=f"Disk problem: {name}",
                    severity=sev,
                    category=Category.STORAGE,
                    summary=summary,
                    evidence=tuple(evidence),
                    recommendations=(
                        "Back up important files now.",
                        "Run a file-system scan of the drive.",
                        "Check the maker's tool (Samsung Magician, WD Dashboard, etc.) for "
                        "firmware updates and a detailed health report.",
                    ),
                    repair_ids=("chkdsk_scan",),
                )
            )
        return findings, "; ".join(parts)


# --------------------------------------------------------------------------- #
# Storage errors in the event log
# --------------------------------------------------------------------------- #

_STORAGE_MEANING = {
    7: "bad block found on the disk",
    11: "controller error",
    51: "error during a paging operation",
    55: "file-system structure is corrupt",
    98: "volume needs a file-system repair",
    129: "storage driver had to reset the device",
    153: "disk I/O had to be retried",
}


class StorageEventsCheck(Check):
    id = "health.storage_events"
    name = "Disk errors in the event log"

    def collect(self, ctx: CheckContext) -> tuple[list[Finding], str]:
        events = ctx.cached(
            "events.storage",
            lambda: ev.fetch(ctx.runner, ev.storage_event_query(ctx.lookback_days)),
        )
        if not events:
            return [], "No disk errors recorded."
        by_id: dict[int, list[ev.EventRecord]] = {}
        for e in events:
            by_id.setdefault(e.id, []).append(e)
        serious = {7, 11, 51, 55}
        n = len(events)
        sev = Severity.HIGH if any(i in serious for i in by_id) else Severity.MEDIUM
        if sev == Severity.MEDIUM and n < 5:
            sev = Severity.LOW
        evidence = tuple(
            f"{len(v)} x {_STORAGE_MEANING.get(k, f'event {k}')} ({v[0].provider} {k})"
            for k, v in sorted(by_id.items(), key=lambda kv: -len(kv[1]))
        )
        finding = Finding(
            id="storage-errors",
            title="Disk or file-system errors recorded",
            severity=sev,
            category=Category.STORAGE,
            summary=(
                f"Windows recorded {n} disk-related error(s) in the last {ctx.lookback_days} "
                "days. Disk errors can cause freezes, crashes and lost files."
            ),
            evidence=evidence,
            recommendations=(
                "Back up important files.",
                "Check disk health and run a file-system scan.",
                "Check or reseat the disk's cable/connector; update storage drivers and SSD "
                "firmware.",
            ),
            repair_ids=("chkdsk_scan",),
            occurrences=n,
            last_seen=max((e.time for e in events if e.time), default=None),
        )
        return [finding], f"{n} disk-related event(s)."


# --------------------------------------------------------------------------- #
# Devices with problems
# --------------------------------------------------------------------------- #

PROBLEM_DEVICES_QUERY = PsQuery(
    "cim.problem_devices",
    "Get-CimInstance -ClassName Win32_PnPEntity "
    "| Where-Object { $_.ConfigManagerErrorCode -ne 0 } "
    "| Select-Object Name,PNPClass,ConfigManagerErrorCode,Present",
)

DEVICE_ERRORS = {
    1: "is not configured correctly",
    3: "has a driver that may be damaged",
    10: "cannot start",
    12: "cannot find enough free resources",
    14: "needs a restart to work",
    18: "needs its driver reinstalled",
    19: "has damaged registry settings",
    22: "is disabled",
    24: "is not present or not working",
    28: "has no driver installed",
    31: "is not working because Windows cannot load its driver",
    39: "has a missing or damaged driver",
    43: "was stopped by Windows because it reported problems",
    45: "is not connected",
    52: "has a driver without a valid digital signature",
}


class ProblemDevicesCheck(Check):
    id = "health.devices"
    name = "Devices and drivers"

    def collect(self, ctx: CheckContext) -> tuple[list[Finding], str]:
        rows = run_ps_json(ctx.runner, PROBLEM_DEVICES_QUERY)
        findings = []
        for r in rows:
            code = int(_num(r.get("ConfigManagerErrorCode")))
            if code in (22, 45):  # disabled on purpose / unplugged
                continue
            if r.get("Present") is False:
                continue
            name = str(r.get("Name") or "Unknown device")
            cls = str(r.get("PNPClass") or "")
            meaning = DEVICE_ERRORS.get(code, f"has a problem (code {code})")
            sev = Severity.MEDIUM
            if code == 14:
                sev = Severity.LOW
            if cls.lower() in ("display", "diskdrive", "scsiadapter", "hdc", "net", "system"):
                sev = Severity.HIGH if code != 14 else Severity.LOW
            findings.append(
                Finding(
                    id=f"device-{zlib.crc32(f'{name}|{code}'.encode()):08x}",
                    title=f"{name} {meaning}",
                    severity=sev,
                    category=Category.DRIVERS,
                    summary=f"Device Manager reports error code {code} for this device.",
                    evidence=(f"Class: {cls or 'unknown'}", f"Error code: {code}"),
                    recommendations=(
                        ("Restart the PC.",)
                        if code == 14
                        else (
                            "Open Device Manager, right-click the device and choose Update driver.",
                            "Download the driver from the device or PC maker's website.",
                            "If it broke after an update, use Roll Back Driver.",
                        )
                    ),
                    repair_ids=(
                        ("rescan_devices",)
                        if code == 14
                        else ("rescan_devices", "windows_update_scan", "open_device_manager")
                    ),
                )
            )
        msg = f"{len(findings)} device(s) with problems." if findings else "All devices working."
        return findings, msg


# --------------------------------------------------------------------------- #
# OS: uptime, memory, pending reboot
# --------------------------------------------------------------------------- #

OS_QUERY = PsQuery(
    "cim.os",
    "$o = Get-CimInstance -ClassName Win32_OperatingSystem; "
    "$rp = (Test-Path 'HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Component Based "
    "Servicing\\RebootPending') -or (Test-Path 'HKLM:\\SOFTWARE\\Microsoft\\Windows\\"
    "CurrentVersion\\WindowsUpdate\\Auto Update\\RebootRequired'); "
    "[pscustomobject]@{ Caption=$o.Caption; Version=$o.Version; Build=$o.BuildNumber; "
    "LastBoot=$o.LastBootUpTime.ToUniversalTime().ToString('o'); "
    "TotalKB=$o.TotalVisibleMemorySize; FreeKB=$o.FreePhysicalMemory; RebootPending=$rp }",
)


class SystemStateCheck(Check):
    id = "health.system"
    name = "Uptime, memory and pending restarts"

    def collect(self, ctx: CheckContext) -> tuple[list[Finding], str]:
        rows = run_ps_json(ctx.runner, OS_QUERY)
        if not rows:
            raise Unavailable("Operating system information is not available.")
        r = rows[0]
        findings = []
        boot = ev.parse_time(r.get("LastBoot"))
        uptime = (ctx.now - boot) if boot else None
        total, free = _num(r.get("TotalKB")), _num(r.get("FreeKB"))
        used_pct = (1 - free / total) * 100 if total > 0 else None
        ctx.metrics["os"] = {
            "caption": str(r.get("Caption") or "Windows").replace("Microsoft ", "").strip(),
            "build": str(r.get("Build") or ""),
            "uptime_hours": round(uptime.total_seconds() / 3600, 1) if uptime else None,
            "ram_total_gb": round(total / 1024 / 1024, 1) if total > 0 else None,
            "ram_used_pct": round(used_pct) if used_pct is not None else None,
            "reboot_pending": r.get("RebootPending") is True,
        }

        if r.get("RebootPending") is True:
            findings.append(
                Finding(
                    id="reboot-pending",
                    title="A restart is waiting to finish updates",
                    severity=Severity.MEDIUM,
                    category=Category.UPDATES,
                    summary="Windows has installed updates or changes that only complete after "
                    "a restart. Until then, some fixes are not active.",
                    recommendations=("Save your work and restart the PC.",),
                )
            )
        if uptime and uptime > timedelta(days=14):
            findings.append(
                Finding(
                    id="long-uptime",
                    title=f"Not restarted for {uptime.days} days",
                    severity=Severity.LOW,
                    category=Category.PERFORMANCE,
                    summary="Long periods without a restart can leave updates unfinished and "
                    "let memory leaks build up. (Shut down with Fast Startup on does not count "
                    "as a restart.)",
                    recommendations=("Use Start > Power > Restart now and then.",),
                )
            )
        if used_pct is not None and used_pct >= 90:
            findings.append(
                Finding(
                    id="memory-pressure",
                    title=f"Memory is {used_pct:.0f}% used",
                    severity=Severity.MEDIUM,
                    category=Category.PERFORMANCE,
                    summary=f"Only {free / 1024 / 1024:.1f} GB of {total / 1024 / 1024:.1f} GB "
                    "RAM is free right now. The PC may feel slow and programs may crash.",
                    recommendations=(
                        "Close programs and browser tabs you are not using.",
                        "Check Task Manager > Processes, sorted by Memory.",
                        "Turn off programs you do not need at startup.",
                    ),
                    repair_ids=("open_startup_apps",),
                )
            )
        parts = [str(r.get("Caption") or "Windows").strip()]
        if r.get("Build"):
            parts.append(f"build {r['Build']}")
        if uptime is not None:
            parts.append(f"up {uptime.days}d {uptime.seconds // 3600}h")
        if used_pct is not None:
            parts.append(f"RAM {used_pct:.0f}% used")
        return findings, ", ".join(parts)


# --------------------------------------------------------------------------- #
# Updates
# --------------------------------------------------------------------------- #

# Last successful update install. Windows Update history first (dates are UTC);
# Defender definition / platform updates and the Malicious Software Removal Tool are
# ignored because they keep arriving even when Windows updates are stuck. Falls back
# to Get-HotFix (local time) when the Windows Update API is unavailable.
LAST_UPDATE_QUERY = PsQuery(
    "updates.last_install",
    "$d=$null; $t=$null; $src='WindowsUpdate'; "
    "try { $q=(New-Object -ComObject Microsoft.Update.Session).CreateUpdateSearcher(); "
    "$n=$q.GetTotalHistoryCount(); if ($n -gt 0) { "
    "$h=$q.QueryHistory(0,[Math]::Min($n,300)) | Where-Object { $_.ResultCode -eq 2 -and "
    "$_.Operation -eq 1 -and $_.Title -notmatch "
    "'Security Intelligence|Definition Update|antimalware platform|Malicious Software' } "
    "| Sort-Object Date -Descending | Select-Object -First 1; "
    "if ($h) { $d=[datetime]::SpecifyKind($h.Date,'Utc'); $t=$h.Title } } } catch {} "
    "if (-not $d) { $src='HotFix'; $h=Get-HotFix | Where-Object { $_.InstalledOn } "
    "| Sort-Object InstalledOn -Descending | Select-Object -First 1; "
    "if ($h) { $d=([datetime]$h.InstalledOn).ToUniversalTime(); $t=$h.HotFixID } } "
    "if ($d) { [pscustomobject]@{ Title=$t; InstalledOn=$d.ToString('o'); Source=$src } }",
    timeout=120,
)


def _short_update_name(title: str) -> str:
    """'2026-10 Cumulative Update for Windows 11 ... (KB5043178)' -> 'KB5043178'."""
    m = re.search(r"\bKB\d{6,8}\b", title)
    return m.group(0) if m else (title[:60] + "..." if len(title) > 60 else title)


class UpdatesCheck(Check):
    id = "health.updates"
    name = "Windows updates"

    def collect(self, ctx: CheckContext) -> tuple[list[Finding], str]:
        rows = run_ps_json(ctx.runner, LAST_UPDATE_QUERY)
        if not rows:
            raise Unavailable("Update history is not available.")
        last = ev.parse_time(rows[0].get("InstalledOn"))
        kb = _short_update_name(str(rows[0].get("Title") or "update"))
        if last is None:
            raise Unavailable("The date of the last update is unknown.")
        age = (ctx.now - last).days
        ctx.metrics["updates"] = {"days": age, "name": kb}
        msg = f"Last update {kb} installed {age} day(s) ago."
        if age < 45:
            return [], msg
        finding = Finding(
            id="updates-old",
            title=f"No Windows updates for {age} days",
            severity=Severity.HIGH if age >= 90 else Severity.MEDIUM,
            category=Category.UPDATES,
            summary="Windows updates include fixes for crashes, drivers and security problems. "
            "Updates may be paused or failing.",
            evidence=(f"Most recent: {kb} on {last.date().isoformat()}",),
            recommendations=(
                "Open Windows Update and select 'Check for updates'.",
                "If updates fail, note the error code shown there.",
            ),
            repair_ids=("windows_update_scan", "reset_windows_update", "open_windows_update"),
        )
        return [finding], msg


# --------------------------------------------------------------------------- #
# Antivirus status (read-only - CrashLens never changes security settings)
# --------------------------------------------------------------------------- #

AV_QUERY = PsQuery(
    "cim.antivirus",
    "Get-CimInstance -Namespace root/SecurityCenter2 -ClassName AntiVirusProduct "
    "| Select-Object displayName,productState",
)


def decode_product_state(state: int) -> tuple[bool, bool]:
    """Return (enabled, up_to_date) from SecurityCenter2 productState."""
    scanner = (state >> 8) & 0xFF
    defs = state & 0xFF
    return scanner in (0x10, 0x11), defs == 0x00


class AntivirusCheck(Check):
    id = "health.antivirus"
    name = "Virus protection"

    def collect(self, ctx: CheckContext) -> tuple[list[Finding], str]:
        rows = run_ps_json(ctx.runner, AV_QUERY)
        if not rows:
            raise Unavailable("Security Center information is not available.")
        products = []
        for r in rows:
            try:
                state = int(r.get("productState"))
            except (TypeError, ValueError):
                continue
            enabled, current = decode_product_state(state)
            products.append((str(r.get("displayName") or "Antivirus"), enabled, current))
        if not products:
            raise Unavailable("No antivirus status could be read.")
        active = [p for p in products if p[1]]
        ctx.metrics["protection"] = [
            {"name": n, "enabled": e, "up_to_date": c} for n, e, c in products
        ]
        summary = ", ".join(
            f"{n} ({'on' if e else 'off'}{', definitions out of date' if e and not c else ''})"
            for n, e, c in products
        )
        if not active:
            return [
                Finding(
                    id="av-off",
                    title="No active virus protection",
                    severity=Severity.HIGH,
                    category=Category.SECURITY,
                    summary="Windows reports that no antivirus is currently turned on.",
                    evidence=tuple(n for n, _, _ in products),
                    recommendations=(
                        "Open Windows Security and turn real-time protection back on, or check "
                        "your antivirus program.",
                    ),
                    repair_ids=("open_windows_security",),
                )
            ], summary
        if all(not c for _, _, c in active):
            return [
                Finding(
                    id="av-outdated",
                    title="Antivirus definitions are out of date",
                    severity=Severity.MEDIUM,
                    category=Category.SECURITY,
                    summary="Your antivirus is on but its virus definitions are not current.",
                    recommendations=("Open Windows Security (or your antivirus) and update.",),
                    repair_ids=("update_defender", "open_windows_security"),
                )
            ], summary
        return [], summary


# --------------------------------------------------------------------------- #
# Startup programs
# --------------------------------------------------------------------------- #

STARTUP_QUERY = PsQuery(
    "cim.startup",
    "Get-CimInstance -ClassName Win32_StartupCommand | Select-Object Name,Location",
)


class StartupAppsCheck(Check):
    id = "health.startup"
    name = "Startup programs"

    def collect(self, ctx: CheckContext) -> tuple[list[Finding], str]:
        rows = run_ps_json(ctx.runner, STARTUP_QUERY)
        names = sorted({str(r.get("Name") or "").strip() for r in rows} - {""}, key=str.lower)
        ctx.metrics["startup_count"] = len(names)
        msg = f"{len(names)} program(s) start with Windows."
        if len(names) < 12:
            return [], msg
        return [
            Finding(
                id="startup-many",
                title=f"{len(names)} programs start with Windows",
                severity=Severity.LOW,
                category=Category.PERFORMANCE,
                summary="Many startup programs slow down sign-in and use memory in the background.",
                evidence=tuple(names[:20])
                + ((f"... and {len(names) - 20} more",) if len(names) > 20 else ()),
                recommendations=("Turn off startup programs you do not need right away.",),
                repair_ids=("open_startup_apps",),
            )
        ], msg


ALL_HEALTH_CHECKS = (
    DiskSpaceCheck,
    DiskHealthCheck,
    StorageEventsCheck,
    ProblemDevicesCheck,
    SystemStateCheck,
    UpdatesCheck,
    AntivirusCheck,
    StartupAppsCheck,
)
