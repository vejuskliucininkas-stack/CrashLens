from conftest import evt

from crashlens.checks.health import (
    AntivirusCheck,
    DiskHealthCheck,
    DiskSpaceCheck,
    ProblemDevicesCheck,
    StartupAppsCheck,
    StorageEventsCheck,
    SystemStateCheck,
    UpdatesCheck,
    decode_product_state,
)
from crashlens.core.models import CheckStatus, Severity

GB = 1024**3


def test_disk_space_thresholds(ctx, fake):
    fake.queries["cim.logical_disks"] = [
        {"DeviceID": "C:", "Size": 256 * GB, "FreeSpace": 4 * GB},
        {"DeviceID": "D:", "Size": 1000 * GB, "FreeSpace": 80 * GB},
        {"DeviceID": "E:", "Size": 500 * GB, "FreeSpace": 300 * GB},
        {"DeviceID": "F:", "Size": None, "FreeSpace": None},
    ]
    res = DiskSpaceCheck().run(ctx)
    by_id = {f.id: f for f in res.findings}
    assert by_id["disk-space-c"].severity == Severity.HIGH
    assert by_id["disk-space-d"].severity == Severity.LOW
    assert "disk-space-e" not in by_id
    assert "C: 4.0 GB free" in res.message


def test_disk_space_no_drives_unavailable(ctx):
    assert DiskSpaceCheck().run(ctx).status == CheckStatus.UNAVAILABLE


def test_disk_health(ctx, fake):
    fake.queries["storage.physical_disks"] = [
        {"Name": "A", "Health": "Unhealthy", "Status": "Degraded"},
        {"Name": "B", "Health": "Healthy", "Wear": 92},
        {"Name": "C", "Health": "Healthy", "Wear": 10, "Temperature": 40},
        {"Name": "D", "Health": "Healthy", "ReadErrors": 3},
    ]
    findings = {f.title: f for f in DiskHealthCheck().run(ctx).findings}
    assert findings["Disk problem: A"].severity == Severity.CRITICAL
    assert findings["Disk problem: B"].severity == Severity.HIGH
    assert "Disk problem: C" not in findings
    assert findings["Disk problem: D"].severity == Severity.HIGH


def test_storage_events(ctx, fake):
    fake.queries["events.storage"] = [evt(7, "disk", "2026-11-01T00:00:00Z")] + [
        evt(153, "disk", "2026-11-02T00:00:00Z") for _ in range(2)
    ]
    [f] = StorageEventsCheck().run(ctx).findings
    assert f.severity == Severity.HIGH and f.occurrences == 3
    assert "bad block" in " ".join(f.evidence)


def test_storage_events_few_retries_low(ctx, fake):
    fake.queries["events.storage"] = [evt(153, "disk", "2026-11-02T00:00:00Z")]
    [f] = StorageEventsCheck().run(ctx).findings
    assert f.severity == Severity.LOW


def test_problem_devices_skip_disabled_and_rank_classes(ctx, fake):
    fake.queries["cim.problem_devices"] = [
        {"Name": "Wi-Fi", "PNPClass": "Net", "ConfigManagerErrorCode": 10, "Present": True},
        {"Name": "Old webcam", "PNPClass": "Camera", "ConfigManagerErrorCode": 28},
        {"Name": "Disabled thing", "PNPClass": "Net", "ConfigManagerErrorCode": 22},
        {"Name": "Ghost", "PNPClass": "USB", "ConfigManagerErrorCode": 43, "Present": False},
    ]
    res = ProblemDevicesCheck().run(ctx)
    titles = {f.title: f for f in res.findings}
    assert titles["Wi-Fi cannot start"].severity == Severity.HIGH
    assert titles["Old webcam has no driver installed"].severity == Severity.MEDIUM
    assert len(titles) == 2
    # ids are stable between runs
    assert res.findings[0].id == ProblemDevicesCheck().run(ctx).findings[0].id


def test_system_state(ctx, fake):
    fake.queries["cim.os"] = {
        "Caption": "Microsoft Windows 11 Pro",
        "Build": "26100",
        "LastBoot": "2026-10-20T00:00:00Z",
        "TotalKB": 8 * 1024 * 1024,
        "FreeKB": 0.5 * 1024 * 1024,
        "RebootPending": True,
    }
    res = SystemStateCheck().run(ctx)
    ids = {f.id for f in res.findings}
    assert ids == {"reboot-pending", "long-uptime", "memory-pressure"}
    assert "build 26100" in res.message


def test_updates_age(ctx, fake):
    fake.queries["cim.hotfix"] = {"HotFixID": "KB1", "InstalledOn": "2026-10-30T00:00:00Z"}
    assert UpdatesCheck().run(ctx).findings == []
    fake.queries["cim.hotfix"] = {"HotFixID": "KB1", "InstalledOn": "2026-07-01T00:00:00Z"}
    [f] = UpdatesCheck().run(ctx).findings
    assert f.severity == Severity.HIGH


def test_av_state_decoding():
    assert decode_product_state(397568) == (True, True)  # Defender on, up to date
    assert decode_product_state(393472) == (False, True)  # off
    assert decode_product_state(397584) == (True, False)  # on, outdated


def test_antivirus_check(ctx, fake):
    fake.queries["cim.antivirus"] = [{"displayName": "Defender", "productState": 393472}]
    [f] = AntivirusCheck().run(ctx).findings
    assert f.id == "av-off" and f.severity == Severity.HIGH
    fake.queries["cim.antivirus"] = [
        {"displayName": "Defender", "productState": 393472},
        {"displayName": "OtherAV", "productState": 266240},
    ]
    assert AntivirusCheck().run(ctx).findings == []


def test_startup_apps(ctx, fake):
    fake.queries["cim.startup"] = [{"Name": f"App{i}"} for i in range(5)]
    assert StartupAppsCheck().run(ctx).findings == []
    fake.queries["cim.startup"] = [{"Name": f"App{i}"} for i in range(25)]
    [f] = StartupAppsCheck().run(ctx).findings
    assert f.severity == Severity.LOW and f.evidence[-1] == "... and 5 more"
