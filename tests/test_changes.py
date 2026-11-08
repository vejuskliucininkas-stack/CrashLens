from conftest import evt

from crashlens.checks.changes import ChangesCheck
from crashlens.core.models import CheckStatus, Severity
from crashlens.core.runner import CommandResult

KP = "Microsoft-Windows-Kernel-Power"


def kp41(t):
    return evt(41, KP, t, "", ["0", "0", "0", "0", "0", "0", "0"], level=1)


def driver(t, inf="nvlddmkm.inf_amd64_1", eid=20001):
    return evt(eid, "Microsoft-Windows-UserPnp", t, "", ["PCI\\VEN_10DE\\1", inf, "0x0"], 4)


def test_changes_before_first_crash(ctx, fake):
    fake.queries["events.system_crash"] = [
        kp41("2026-11-05T10:00:00Z"),
        kp41("2026-11-01T10:00:00Z"),
    ]
    fake.queries["events.driver_installs"] = [
        driver("2026-10-30T09:00:00Z"),  # 2 days before the first crash -> listed
        driver("2026-10-10T09:00:00Z"),  # too early -> not listed
        driver("2026-11-03T09:00:00Z", "oldaudio.inf", eid=20003),  # after first crash
    ]
    fake.queries["events.app_installs"] = [
        evt(
            11707,
            "MsiInstaller",
            "2026-10-31T12:00:00Z",
            "Product: Cool Tool -- Installation completed successfully.",
            [],
            4,
        )
    ]
    fake.queries["updates.history"] = [
        {"Title": "Cumulative Update (KB5000001)", "ResultCode": 2, "Date": "2026-10-29T08:00:00Z"}
    ]
    res = ChangesCheck().run(ctx)
    [f] = res.findings
    assert f.id == "changes-before-crashes" and f.severity == Severity.LOW
    assert "2026-11-01" in f.summary and "3 changes were made" in f.summary
    assert "1 driver change" in f.summary
    text = "\n".join(f.evidence)
    assert "Driver nvlddmkm.inf installed for PCI device" in text
    assert "Program Cool Tool installed" in text
    assert "KB5000001" in text
    assert "oldaudio" not in text
    # newest first
    assert f.evidence[0].startswith("2026-10-31")


def test_no_crashes_no_correlation(ctx, fake):
    fake.queries["events.driver_installs"] = [driver("2026-10-30T09:00:00Z")]
    res = ChangesCheck().run(ctx)
    assert res.findings == [] and res.status == CheckStatus.OK
    assert res.message.startswith("1 change")


def test_failing_updates(ctx, fake):
    fake.queries["updates.history"] = [
        {"Title": "KB1 update", "ResultCode": 4, "HResult": -2145124330, "Date": d}
        for d in ("2026-11-01T00:00:00Z", "2026-11-04T00:00:00Z")
    ] + [{"Title": "Old fail", "ResultCode": 4, "Date": "2026-08-01T00:00:00Z"}]
    [f] = ChangesCheck().run(ctx).findings
    assert f.id == "updates-failing" and f.severity == Severity.MEDIUM
    assert f.occurrences == 2
    assert "0x80240016" in f.evidence[0]
    assert "same update kept failing" in f.summary
    assert "dism_restore" in f.repair_ids


def test_unavailable_sources_are_noted_not_fatal(ctx, fake):
    fake.queries["updates.history"] = CommandResult(("p",), -1, "", timed_out=True)
    res = ChangesCheck().run(ctx)
    assert res.status == CheckStatus.OK
    assert "Windows Update history unavailable" in res.message
