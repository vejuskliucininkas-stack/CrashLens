"""Crash, blue-screen and stability analysis."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from crashlens.checks import events as ev
from crashlens.checks import minidump
from crashlens.checks.base import Check, CheckContext, Unavailable
from crashlens.checks.stopcodes import describe, format_code, parse_code
from crashlens.core.models import Category, Finding, Severity
from crashlens.core.runner import PsQuery, run_ps_json

MATCH_WINDOW = timedelta(minutes=15)
_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
MAX_EVIDENCE = 6

_BUGCHECK_RE = re.compile(r"bug ?check was:?\s*(0x[0-9a-fA-F]+)\s*(?:\(([^)]*)\))?", re.I)
_DUMP_RE = re.compile(r"dump was saved in:?\s*(\S.*?\.dmp)", re.I)


def times(n: int) -> str:
    return {1: "once", 2: "twice"}.get(n, f"{n} times")


def _fmt_time(t: datetime | None) -> str:
    return t.strftime("%Y-%m-%d %H:%M UTC") if t else "unknown time"


# --------------------------------------------------------------------------- #
# Blue screens and unexpected restarts
# --------------------------------------------------------------------------- #


@dataclass
class Incident:
    time: datetime | None
    code: int | None  # None = no stop code (power loss / hard freeze)
    params: str = ""
    sources: set[str] = field(default_factory=set)
    dump: str | None = None
    forced_power_off: bool = False


def _close(a: datetime | None, b: datetime | None) -> bool:
    return a is not None and b is not None and abs(a - b) <= MATCH_WINDOW


def _parse_bugcheck_event(e: ev.EventRecord) -> Incident | None:
    text = " ".join([e.message, *e.data])
    m = _BUGCHECK_RE.search(text)
    code = parse_code(m.group(1)) if m else None
    if code is None:
        # data[0] is usually "0x0000009f (0x..., 0x..., ...)" or just the code
        first = e.datum(0).split("(")[0].strip()
        code = parse_code(first) if first.lower().startswith("0x") else None
    if code is None:
        return None
    dm = _DUMP_RE.search(text)
    dump = dm.group(1).strip() if dm else None
    if dump is None:
        # Localised Windows: the message text is translated, but the event data is not.
        dump = next((d.strip() for d in e.data[1:3] if d.strip().lower().endswith(".dmp")), None)
    params = (m.group(2) or "").strip() if m else ""
    if not params:
        pm = re.search(r"\(([^)]*)\)", e.datum(0))
        params = pm.group(1).strip() if pm else ""
    return Incident(
        time=e.time,
        code=code,
        params=params,
        sources={"Event 1001 (BugCheck)"},
        dump=dump,
    )


def build_incidents(
    system_events: list[ev.EventRecord], dumps: list[minidump.DumpInfo]
) -> list[Incident]:
    incidents: list[Incident] = []

    for e in system_events:
        if e.id == 1001 and (
            "systemerrorreporting" in e.provider.lower() or _BUGCHECK_RE.search(e.message)
        ):
            inc = _parse_bugcheck_event(e)
            if inc:
                incidents.append(inc)

    for e in system_events:
        if e.id != 41 or "kernel-power" not in e.provider.lower():
            continue
        code = parse_code(e.datum(0)) or None  # 0 means "no bug check"
        forced = e.datum(6) not in ("", "0")
        match = next(
            (i for i in incidents if _close(i.time, e.time) and (code is None or i.code == code)),
            None,
        )
        if match:
            match.sources.add("Kernel-Power 41")
            match.forced_power_off = match.forced_power_off or forced
        else:
            incidents.append(
                Incident(e.time, code, sources={"Kernel-Power 41"}, forced_power_off=forced)
            )

    for e in system_events:
        if e.id != 6008:
            continue
        match = next((i for i in incidents if _close(i.time, e.time)), None)
        if match:
            match.sources.add("Event 6008")
        else:
            incidents.append(Incident(e.time, None, sources={"Event 6008"}))

    for d in dumps:
        if d.bugcheck is None:
            continue
        match = next(
            (i for i in incidents if i.code == d.bugcheck and _close(i.time, d.modified)), None
        )
        if match:
            match.sources.add("Minidump")
            match.dump = match.dump or str(d.path)
        else:
            params = ", ".join(f"0x{p:X}" for p in d.params)
            incidents.append(
                Incident(d.modified, d.bugcheck, params, {"Minidump"}, dump=str(d.path))
            )

    incidents.sort(key=lambda i: i.time or _EPOCH, reverse=True)
    return incidents


def _count_severity(n: int, high_at: int = 3, critical_at: int = 6) -> Severity:
    if n >= critical_at:
        return Severity.CRITICAL
    if n >= high_at:
        return Severity.HIGH
    return Severity.MEDIUM


def incidents_to_findings(incidents: list[Incident], days: int) -> list[Finding]:
    findings: list[Finding] = []
    by_code: dict[int, list[Incident]] = defaultdict(list)
    no_code: list[Incident] = []
    for inc in incidents:
        (by_code[inc.code] if inc.code else no_code).append(inc)

    for code, items in sorted(by_code.items(), key=lambda kv: -len(kv[1])):
        kb = describe(code)
        n = len(items)
        evidence = []
        for inc in items[:MAX_EVIDENCE]:
            line = f"{_fmt_time(inc.time)} - {', '.join(sorted(inc.sources))}"
            if inc.params:
                line += f" - parameters: {inc.params}"
            if inc.dump:
                line += f" - dump: {inc.dump}"
            evidence.append(line)
        if n > MAX_EVIDENCE:
            evidence.append(f"... and {n - MAX_EVIDENCE} more")
        findings.append(
            Finding(
                id=f"bsod-{code:x}",
                title=f"Blue screen: {kb.name} ({format_code(code)})",
                severity=_count_severity(n),
                category=Category.CRASH,
                summary=(
                    f"Windows crashed with this stop code {times(n)} in the last {days} days. "
                    f"{kb.meaning}"
                ),
                details="Likely causes: " + "; ".join(kb.likely_causes) + ".",
                evidence=tuple(evidence),
                recommendations=kb.steps,
                repair_ids=kb.repairs,
                occurrences=n,
                last_seen=items[0].time,
            )
        )

    if no_code:
        n = len(no_code)
        forced = sum(1 for i in no_code if i.forced_power_off)
        summary = (
            f"The PC restarted or switched off without shutting down properly {times(n)} in "
            f"the last {days} days, and no blue screen was recorded. That usually means a "
            "sudden power loss, a complete freeze, or the power button being held down."
        )
        if forced:
            summary += f" The power button was used to force it off {times(forced)}."
        findings.append(
            Finding(
                id="unexpected-restart",
                title="Unexpected restarts or shutdowns",
                severity=_count_severity(n, high_at=3, critical_at=10),
                category=Category.HARDWARE if n >= 3 else Category.SYSTEM,
                summary=summary,
                details=(
                    "If you held the power button because the PC froze, the freeze is the real "
                    "problem - often a driver, overheating or unstable hardware."
                ),
                evidence=tuple(
                    f"{_fmt_time(i.time)} - {', '.join(sorted(i.sources))}"
                    + (" - forced power-off" if i.forced_power_off else "")
                    for i in no_code[:MAX_EVIDENCE]
                ),
                recommendations=(
                    "Check the power cable, power strip / UPS, and on laptops the charger and "
                    "battery.",
                    "Make sure the PC is not overheating: clean dust from vents and fans.",
                    "If the PC froze first, update graphics, chipset and storage drivers.",
                    "Remove any CPU/RAM/GPU overclock and test the memory.",
                ),
                repair_ids=("memory_diagnostic", "open_reliability_monitor"),
                occurrences=n,
                last_seen=no_code[0].time,
            )
        )
    return findings


class BlueScreenCheck(Check):
    id = "crash.bluescreen"
    name = "Blue screens & unexpected restarts"

    def collect(self, ctx: CheckContext) -> tuple[list[Finding], str]:
        system_events = ctx.cached(
            "events.system_crash",
            lambda: ev.fetch(ctx.runner, ev.system_crash_query(ctx.lookback_days)),
        )
        dumps, dump_note = minidump.scan_dir(ctx.minidump_dir)
        cutoff = ctx.now - timedelta(days=ctx.lookback_days)
        dumps = [d for d in dumps if d.modified is None or d.modified >= cutoff]
        incidents = build_incidents(system_events, dumps)
        findings = incidents_to_findings(incidents, ctx.lookback_days)
        if not findings:
            msg = f"No blue screens or unexpected restarts in the last {ctx.lookback_days} days."
        else:
            bsods = sum(f.occurrences for f in findings if f.id.startswith("bsod-"))
            others = sum(f.occurrences for f in findings if f.id == "unexpected-restart")
            msg = f"{bsods} blue screen(s), {others} other unexpected restart(s)."
        if dump_note:
            msg += " " + dump_note
        return findings, msg


# --------------------------------------------------------------------------- #
# Graphics driver timeouts (TDR)
# --------------------------------------------------------------------------- #


def _tdr_driver(e: ev.EventRecord) -> str:
    m = re.search(r"driver\s+(\S+)\s+stopped", e.message, re.I)
    if m:
        return m.group(1)
    # Localised Windows: the driver name is the event's first insertion string.
    first = e.datum(0).strip()
    return first if re.fullmatch(r"[\w.-]{2,64}", first) else ""


class GraphicsDriverCheck(Check):
    id = "crash.graphics"
    name = "Graphics driver resets"

    def collect(self, ctx: CheckContext) -> tuple[list[Finding], str]:
        system_events = ctx.cached(
            "events.system_crash",
            lambda: ev.fetch(ctx.runner, ev.system_crash_query(ctx.lookback_days)),
        )
        tdrs = [e for e in system_events if e.id == 4101]
        if not tdrs:
            return [], "No graphics driver resets."
        n = len(tdrs)
        drivers = Counter(_tdr_driver(e) for e in tdrs)
        drivers.pop("", None)
        names = ", ".join(d for d, _ in drivers.most_common(3)) or "the display driver"
        latest = max((e.time for e in tdrs if e.time), default=None)
        finding = Finding(
            id="gpu-tdr",
            title="Graphics driver stopped responding (and recovered)",
            severity=Severity.MEDIUM if n >= 3 else Severity.LOW,
            category=Category.DRIVERS,
            summary=(
                f"{names} stopped responding and was restarted by Windows {times(n)} in the "
                f"last {ctx.lookback_days} days. You may have seen the screen go black briefly."
            ),
            evidence=tuple(_fmt_time(e.time) for e in tdrs[:MAX_EVIDENCE]),
            recommendations=(
                "Install the newest graphics driver from NVIDIA, AMD or Intel.",
                "Remove any graphics-card overclock.",
                "Check graphics-card temperatures and that its power cables are secure.",
            ),
            repair_ids=("windows_update_scan", "open_device_manager"),
            occurrences=n,
            last_seen=latest,
        )
        return [finding], f"{n} graphics driver reset(s)."


# --------------------------------------------------------------------------- #
# Hardware errors (WHEA)
# --------------------------------------------------------------------------- #

_WHEA_FATAL = {1, 18, 20}
_WHEA_KIND = {
    17: "corrected PCI Express error",
    19: "corrected processor (machine check) error",
    47: "corrected memory error",
}


class HardwareErrorCheck(Check):
    id = "crash.hardware"
    name = "Hardware error reports"

    def collect(self, ctx: CheckContext) -> tuple[list[Finding], str]:
        events = ctx.cached(
            "events.whea", lambda: ev.fetch(ctx.runner, ev.whea_query(ctx.lookback_days))
        )
        if not events:
            return [], "No hardware errors reported."
        fatal = [e for e in events if e.id in _WHEA_FATAL]
        corrected = [e for e in events if e.id not in _WHEA_FATAL]
        findings: list[Finding] = []
        if fatal:
            findings.append(
                Finding(
                    id="whea-fatal",
                    title="Fatal hardware errors",
                    severity=Severity.HIGH,
                    category=Category.HARDWARE,
                    summary=(
                        f"The hardware reported {len(fatal)} error(s) it could not correct. "
                        "These usually cause a blue screen (WHEA_UNCORRECTABLE_ERROR) or a "
                        "sudden restart."
                    ),
                    evidence=tuple(
                        f"{_fmt_time(e.time)} - event {e.id}" for e in fatal[:MAX_EVIDENCE]
                    ),
                    recommendations=(
                        "Return CPU, memory and graphics card to default (non-overclocked) "
                        "settings.",
                        "Check temperatures and clean dust from fans and heatsinks.",
                        "Update the BIOS/UEFI from the PC or motherboard maker.",
                        "Test the memory with Windows Memory Diagnostic.",
                    ),
                    repair_ids=("memory_diagnostic",),
                    occurrences=len(fatal),
                    last_seen=max((e.time for e in fatal if e.time), default=None),
                )
            )
        if corrected:
            kinds = Counter(_WHEA_KIND.get(e.id, f"hardware event {e.id}") for e in corrected)
            only_pcie = set(kinds) == {_WHEA_KIND[17]}
            n = len(corrected)
            sev = Severity.LOW if only_pcie or n < 10 else Severity.MEDIUM
            findings.append(
                Finding(
                    id="whea-corrected",
                    title="Corrected hardware errors",
                    severity=sev,
                    category=Category.HARDWARE,
                    summary=(
                        f"The hardware fixed {n} error(s) by itself: "
                        + ", ".join(f"{c} x {k}" for k, c in kinds.most_common())
                        + ". A few are normal; a steady stream can be an early warning."
                    ),
                    details=(
                        "Corrected PCI Express errors are often caused by power-saving settings "
                        "and are usually harmless."
                        if only_pcie
                        else "Repeated corrected processor or memory errors can precede crashes."
                    ),
                    evidence=tuple(
                        f"{_fmt_time(e.time)} - {_WHEA_KIND.get(e.id, f'event {e.id}')}"
                        for e in corrected[:MAX_EVIDENCE]
                    ),
                    recommendations=(
                        "Update the BIOS/UEFI and chipset drivers.",
                        "If errors keep growing, test memory and check cooling.",
                    ),
                    repair_ids=("memory_diagnostic",) if not only_pcie else (),
                    occurrences=n,
                    last_seen=max((e.time for e in corrected if e.time), default=None),
                )
            )
        return findings, f"{len(fatal)} fatal, {len(corrected)} corrected hardware error(s)."


# --------------------------------------------------------------------------- #
# Application crashes and hangs
# --------------------------------------------------------------------------- #

EXCEPTION_NAMES = {
    0xC0000005: "access violation (the program read or wrote invalid memory)",
    0xC0000409: "stack buffer overrun / fail-fast (the program stopped itself after "
    "detecting a problem)",
    0xC0000374: "heap corruption",
    0xC00000FD: "stack overflow",
    0xE0434352: ".NET exception that was not handled",
    0xE06D7363: "C++ exception that was not handled",
    0x80000003: "breakpoint (debug code left in the program)",
    0xC0000142: "the program failed to start (DLL initialisation failed)",
    0xC000041D: "an unhandled error inside a user callback",
    0xC0000602: "fail-fast exception",
}

MODULE_HINTS = {
    "nvwgf2umx.dll": "NVIDIA graphics driver",
    "nvd3dumx.dll": "NVIDIA graphics driver",
    "nvoglv64.dll": "NVIDIA graphics driver",
    "atidxx64.dll": "AMD graphics driver",
    "amdxx64.dll": "AMD graphics driver",
    "atio6axx.dll": "AMD graphics driver",
    "igd10iumd64.dll": "Intel graphics driver",
    "igd12umd64.dll": "Intel graphics driver",
    "igc64.dll": "Intel graphics driver",
    "coreclr.dll": ".NET runtime",
    "clr.dll": ".NET Framework runtime",
    "kernelbase.dll": "Windows (the program raised an error Windows reported)",
    "ntdll.dll": "Windows core library (often memory corruption inside the program)",
    "ucrtbase.dll": "C runtime library",
    "msvcp140.dll": "Visual C++ runtime",
    "vcruntime140.dll": "Visual C++ runtime",
    "d3d11.dll": "Direct3D graphics",
    "d3d12.dll": "Direct3D graphics",
    "dxgi.dll": "DirectX graphics",
}

MAX_APP_FINDINGS = 8


def parse_exception_code(code_s: str) -> int | None:
    """Application Error stores the code as hex text ('c0000005'), but some systems
    deliver it as a decimal number ('3221225477'). Error codes are >= 0x80000000,
    which is always 10 decimal digits, while the hex form is at most 8 characters."""
    s = (code_s or "").strip()
    if s.isdigit() and len(s) == 10:
        return int(s, 10)
    return parse_code(s if s.lower().startswith("0x") else f"0x{s}") if s else None


def _exc_text(code_s: str) -> str:
    code = parse_exception_code(code_s)
    if code is None:
        return code_s or "unknown error"
    return f"{format_code(code)} - {EXCEPTION_NAMES.get(code, 'error')}"


class AppCrashCheck(Check):
    id = "crash.apps"
    name = "Program crashes & freezes"

    def collect(self, ctx: CheckContext) -> tuple[list[Finding], str]:
        events = ctx.cached(
            "events.app_crash", lambda: ev.fetch(ctx.runner, ev.app_crash_query(ctx.lookback_days))
        )
        crashes: dict[tuple[str, str], list[ev.EventRecord]] = defaultdict(list)
        hangs: dict[str, list[ev.EventRecord]] = defaultdict(list)
        for e in events:
            app = e.datum(0).strip()
            if not app:
                continue
            if e.id == 1000:
                crashes[(app.lower(), e.datum(3).strip().lower())].append(e)
            elif e.id == 1002:
                hangs[app.lower()].append(e)

        findings: list[Finding] = []
        for (_, module), items in sorted(crashes.items(), key=lambda kv: -len(kv[1]))[
            :MAX_APP_FINDINGS
        ]:
            n = len(items)
            first = items[0]
            app = first.datum(0)
            module_name = first.datum(3) or "unknown module"
            hint = MODULE_HINTS.get(module)
            sev = Severity.MEDIUM if n >= 10 else Severity.LOW if n >= 3 else Severity.INFO
            recs = [
                f"Update {app} to its latest version, or repair/reinstall it.",
            ]
            repairs: tuple[str, ...] = ()
            if hint and "graphics" in hint.lower():
                recs.insert(0, "The crash happened inside the graphics driver - update it.")
                repairs = ("open_device_manager",)
            elif hint and "runtime" in hint.lower():
                recs.append(f"Repair or update the {hint}.")
            if n >= 3:
                recs.append("If it started recently, check what changed (updates, add-ons, mods).")
            findings.append(
                Finding(
                    id=f"app-crash-{app.lower()}-{module}",
                    title=f"{app} crashed" + (f" {n} times" if n > 1 else ""),
                    severity=sev,
                    category=Category.APP,
                    summary=(
                        f"{app} closed unexpectedly {times(n)}. The fault was in "
                        f"{module_name}" + (f" ({hint})" if hint else "") + "."
                    ),
                    details="Error: " + _exc_text(first.datum(6)),
                    evidence=tuple(
                        f"{_fmt_time(e.time)} - version {e.datum(1) or '?'}"
                        for e in items[:MAX_EVIDENCE]
                    ),
                    recommendations=tuple(recs),
                    repair_ids=repairs,
                    occurrences=n,
                    last_seen=max((e.time for e in items if e.time), default=None),
                )
            )
        for _, items in sorted(hangs.items(), key=lambda kv: -len(kv[1]))[:MAX_APP_FINDINGS]:
            n = len(items)
            app = items[0].datum(0)
            findings.append(
                Finding(
                    id=f"app-hang-{app.lower()}",
                    title=f"{app} stopped responding" + (f" {n} times" if n > 1 else ""),
                    severity=Severity.LOW if n >= 5 else Severity.INFO,
                    category=Category.APP,
                    summary=f"{app} froze and had to be closed {times(n)}.",
                    evidence=tuple(_fmt_time(e.time) for e in items[:MAX_EVIDENCE]),
                    recommendations=(
                        f"Update {app}.",
                        "Check free disk space and memory use while it runs.",
                    ),
                    occurrences=n,
                    last_seen=max((e.time for e in items if e.time), default=None),
                )
            )
        total_c = sum(len(v) for v in crashes.values())
        total_h = sum(len(v) for v in hangs.values())
        return findings, f"{total_c} program crash(es), {total_h} freeze(s)."


# --------------------------------------------------------------------------- #
# Reliability index
# --------------------------------------------------------------------------- #

RELIABILITY_QUERY = PsQuery(
    "cim.reliability",
    "Get-CimInstance -ClassName Win32_ReliabilityStabilityMetrics "
    "| Sort-Object TimeGenerated -Descending | Select-Object -First 1 "
    "@{n='Index';e={[double]$_.SystemStabilityIndex}},"
    "@{n='Time';e={$_.TimeGenerated.ToUniversalTime().ToString('o')}}",
    timeout=90,
)


class ReliabilityCheck(Check):
    id = "crash.reliability"
    name = "Windows reliability index"

    def collect(self, ctx: CheckContext) -> tuple[list[Finding], str]:
        rows = run_ps_json(ctx.runner, RELIABILITY_QUERY)
        if not rows or not isinstance(rows[0], dict) or rows[0].get("Index") is None:
            raise Unavailable("Windows is not collecting reliability data on this PC.")
        try:
            index = float(rows[0]["Index"])
        except (TypeError, ValueError) as exc:
            raise Unavailable("Reliability data could not be read.") from exc
        # Shown on the dashboard; it summarises the crashes already reported, so it is
        # information only and does not count as a problem of its own.
        sev = Severity.INFO
        ctx.metrics["reliability"] = round(index, 1)
        finding = Finding(
            id="reliability-index",
            title=f"Reliability index: {index:.1f} / 10",
            severity=sev,
            category=Category.SYSTEM,
            summary=(
                "Windows rates its own stability from 1 (very unstable) to 10 (stable), based "
                "on recent crashes and failures."
            ),
            recommendations=("Open Reliability Monitor to see failures day by day.",),
            repair_ids=("open_reliability_monitor",),
            last_seen=ev.parse_time(rows[0].get("Time")),
        )
        return [finding], f"Stability index {index:.1f}/10."
