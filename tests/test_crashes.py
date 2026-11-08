import struct

from conftest import evt

from crashlens.checks import events as ev
from crashlens.checks.crashes import (
    AppCrashCheck,
    BlueScreenCheck,
    GraphicsDriverCheck,
    HardwareErrorCheck,
    ReliabilityCheck,
    build_incidents,
)
from crashlens.core.models import CheckStatus, Severity
from crashlens.core.runner import CommandResult

WER = "Microsoft-Windows-WER-SystemErrorReporting"
KP = "Microsoft-Windows-Kernel-Power"


def bugcheck_event(time, code="0x0000009f", params="0x3, 0xffffd0, 0xfffff8, 0xffffb2"):
    msg = (
        f"The computer has rebooted from a bugcheck.  The bugcheck was: {code} ({params}). "
        "A dump was saved in: C:\\Windows\\Minidump\\110126-10000-01.dmp. Report Id: abc."
    )
    return evt(1001, WER, time, msg, [f"{code} ({params})", "", "C:\\Windows\\Minidump\\x.dmp"])


def kp41(time, code_dec="0", power_button="0"):
    return evt(
        41,
        KP,
        time,
        "The system has rebooted without cleanly shutting down first.",
        [code_dec, "0", "0", "0", "0", "0", power_button],
        level=1,
    )


def test_bluescreen_groups_by_code_and_merges_kp41(ctx, fake):
    fake.queries["events.system_crash"] = [
        bugcheck_event("2026-11-07T08:00:05.0000000Z"),
        kp41("2026-11-07T08:00:00.0000000Z", "159"),  # same incident, decimal 0x9F
        bugcheck_event("2026-11-03T08:00:05.0000000Z"),
        bugcheck_event("2026-11-01T08:00:05.0000000Z"),
        bugcheck_event("2026-10-30T08:00:05Z", code="0x00000124", params="0x0, 0x1, 0x2, 0x3"),
    ]
    result = BlueScreenCheck().run(ctx)
    assert result.status == CheckStatus.ISSUES
    by_id = {f.id: f for f in result.findings}
    dpsf = by_id["bsod-9f"]
    assert dpsf.occurrences == 3
    assert dpsf.severity == Severity.HIGH
    assert "DRIVER_POWER_STATE_FAILURE" in dpsf.title
    assert any("Kernel-Power 41" in e for e in dpsf.evidence)
    assert any("Minidump\\110126" in e for e in dpsf.evidence)
    assert "open_device_manager" in dpsf.repair_ids
    assert by_id["bsod-124"].severity == Severity.MEDIUM
    assert "unexpected-restart" not in by_id
    assert "3 blue screen" not in result.message  # 4 total
    assert result.message.startswith("4 blue screen")


def test_power_loss_without_bugcheck(ctx, fake):
    fake.queries["events.system_crash"] = [
        kp41("2026-11-06T20:00:00Z", "0", power_button="132456789"),
        evt(
            6008, "EventLog", "2026-11-06T20:00:30Z", "The previous system shutdown was unexpected."
        ),
        kp41("2026-11-02T20:00:00Z"),
        evt(6008, "EventLog", "2026-10-25T20:00:30Z", "unexpected"),
    ]
    result = BlueScreenCheck().run(ctx)
    [f] = result.findings
    assert f.id == "unexpected-restart"
    assert f.occurrences == 3  # first 6008 merged into the KP41 next to it
    assert f.severity == Severity.HIGH
    assert "power button" in f.summary
    assert any("forced power-off" in e for e in f.evidence)


def test_no_crashes_is_ok(ctx):
    result = BlueScreenCheck().run(ctx)
    assert result.status == CheckStatus.OK and result.findings == []
    assert "No blue screens" in result.message


def test_minidump_without_event_creates_incident(ctx, tmp_path):
    data = bytearray(0x80)
    data[0:8] = b"PAGEDU64"
    struct.pack_into("<I", data, 0x38, 0x50)
    (tmp_path / "a.dmp").write_bytes(bytes(data))
    ctx.minidump_dir = tmp_path
    ctx.now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
    result = BlueScreenCheck().run(ctx)
    [f] = result.findings
    assert f.id == "bsod-50"
    assert "Minidump" in f.evidence[0]


def test_build_incidents_ignores_unrelated_1001():
    other = ev.EventRecord(1001, "Some-Other-Provider", None, 4, "Fault bucket stuff", ())
    assert build_incidents([other], []) == []


def test_check_is_unavailable_off_windows(ctx):
    ctx.is_windows = False
    result = BlueScreenCheck().run(ctx)
    assert result.status == CheckStatus.UNAVAILABLE


def test_query_failure_becomes_error_not_crash(ctx, fake):
    fake.queries["events.system_crash"] = CommandResult(("x",), -1, "", timed_out=True)
    result = BlueScreenCheck().run(ctx)
    assert result.status == CheckStatus.ERROR
    assert "timed out" in result.message
    # the cached failure is reused by the next check without re-running
    calls = len(fake.calls)
    assert GraphicsDriverCheck().run(ctx).status == CheckStatus.ERROR
    assert len(fake.calls) == calls


def test_graphics_tdr(ctx, fake):
    msg = "Display driver nvlddmkm stopped responding and has successfully recovered."
    fake.queries["events.system_crash"] = [
        evt(4101, "Display", f"2026-11-0{d}T10:00:00Z", msg, level=3) for d in (1, 2, 3)
    ]
    [f] = GraphicsDriverCheck().run(ctx).findings
    assert f.severity == Severity.MEDIUM and "nvlddmkm" in f.summary


def test_whea_fatal_and_corrected(ctx, fake):
    fake.queries["events.whea"] = [
        evt(18, "Microsoft-Windows-WHEA-Logger", "2026-11-05T10:00:00Z", level=1),
        *[evt(17, "Microsoft-Windows-WHEA-Logger", "2026-11-05T10:00:00Z") for _ in range(12)],
    ]
    res = HardwareErrorCheck().run(ctx)
    by_id = {f.id: f for f in res.findings}
    assert by_id["whea-fatal"].severity == Severity.HIGH
    # only PCIe corrected errors -> stays low even when many
    assert by_id["whea-corrected"].severity == Severity.LOW


def test_app_crashes_grouped_with_hints(ctx, fake):
    def crash(app, module, code="c0000005", t="2026-11-04T10:00:00Z"):
        return evt(
            1000,
            "Application Error",
            t,
            "",
            [app, "1.2.3", "0", module, "4.5", "0", code, "0x1234"],
        )

    fake.queries["events.app_crash"] = [
        *[crash("game.exe", "nvwgf2umx.dll") for _ in range(4)],
        crash("notepad.exe", "ntdll.dll", "c0000374"),
        evt(1002, "Application Hang", "2026-11-04T11:00:00Z", "", ["explorer.exe", "10.0"]),
    ]
    res = AppCrashCheck().run(ctx)
    by_id = {f.id: f for f in res.findings}
    game = by_id["app-crash-game.exe-nvwgf2umx.dll"]
    assert game.occurrences == 4 and game.severity == Severity.LOW
    assert "NVIDIA graphics driver" in game.summary
    assert "access violation" in game.details
    assert game.repair_ids == ("open_device_manager",)
    assert by_id["app-crash-notepad.exe-ntdll.dll"].severity == Severity.INFO
    assert "heap corruption" in by_id["app-crash-notepad.exe-ntdll.dll"].details
    assert "app-hang-explorer.exe" in by_id
    assert res.message == "5 program crash(es), 1 freeze(s)."


def test_reliability_index(ctx, fake):
    fake.queries["cim.reliability"] = {"Index": 4.2, "Time": "2026-11-08T00:00:00Z"}
    [f] = ReliabilityCheck().run(ctx).findings
    assert f.severity == Severity.MEDIUM and "4.2" in f.title
    fake.queries["cim.reliability"] = []
    assert ReliabilityCheck().run(ctx).status == CheckStatus.UNAVAILABLE
