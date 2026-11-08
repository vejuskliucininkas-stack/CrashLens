"""Demo mode: a realistic, fictional PC with problems, for trying CrashLens anywhere.

Nothing here touches the real system. Repairs in demo mode are always dry runs.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from crashlens.core.models import SystemInfo
from crashlens.core.runner import FakeRunner


def _t(now: datetime, days: float, hours: float = 0) -> str:
    return (now - timedelta(days=days, hours=hours)).strftime("%Y-%m-%dT%H:%M:%S.0000000Z")


def _ev(eid, provider, time, message="", data=(), level=2):
    return {
        "Id": eid,
        "Provider": provider,
        "Time": time,
        "Level": level,
        "Message": message,
        "Data": list(data),
    }


def demo_system() -> SystemInfo:
    return SystemInfo(
        os_name="Windows 11 (demo)",
        os_version="10.0.26100",
        os_build="26100",
        computer_name="DEMO-PC",
        user_name="demo",
        is_admin=False,
        is_windows=False,
    )


def demo_runner(now: datetime | None = None) -> FakeRunner:
    now = now or datetime.now(timezone.utc)
    wer = "Microsoft-Windows-WER-SystemErrorReporting"

    def bugcheck(days, code, params, dump):
        msg = (
            "The computer has rebooted from a bugcheck.  The bugcheck was: "
            f"{code} ({params}). A dump was saved in: C:\\Windows\\Minidump\\{dump}. "
            "Report Id: 00000000-0000-0000-0000-000000000000."
        )
        return _ev(1001, wer, _t(now, days), msg, [f"{code} ({params})"])

    def kp41(days, code_dec, button="0"):
        return _ev(
            41,
            "Microsoft-Windows-Kernel-Power",
            _t(now, days, 0.002),
            "The system has rebooted without cleanly shutting down first.",
            [code_dec, "0", "0", "0", "0", "0", button],
            level=1,
        )

    dpsf = "0x00000003, 0xffffd88e4c2a1060, 0xfffff8065d6a7850, 0xffffd88e52e1a010"
    system_crash = [
        bugcheck(1.2, "0x0000009f", dpsf, "110726-11234-01.dmp"),
        kp41(1.2, "159"),
        bugcheck(4.5, "0x0000009f", dpsf, "110426-10984-01.dmp"),
        kp41(4.5, "159"),
        bugcheck(9.1, "0x0000009f", dpsf, "103026-10421-01.dmp"),
        bugcheck(15.3, "0x000000d1", "0x0, 0x2, 0x0, 0xfffff8066a7c1234", "102426-9876-01.dmp"),
        kp41(21.0, "0", button="133751234567890000"),
        _ev(6008, "EventLog", _t(now, 21.0, -0.01), "The previous system shutdown was unexpected."),
        *[
            _ev(
                4101,
                "Display",
                _t(now, d),
                "Display driver nvlddmkm stopped responding and has successfully recovered.",
                level=3,
            )
            for d in (2.0, 2.1, 6.4, 11.0)
        ],
    ]

    def crash(days, app, ver, module, code):
        return _ev(
            1000,
            "Application Error",
            _t(now, days),
            "",
            [app, ver, "65a1b2c3", module, "31.0.15.5222", "0", code, "0x00000000000a1b2c"],
        )

    app_crash = [
        *[crash(d, "Game.exe", "2.4.1.0", "nvwgf2umx.dll", "c0000005") for d in (1, 2, 2.1, 5, 6)],
        crash(3, "PhotoEditor.exe", "8.1.0.0", "ucrtbase.dll", "c0000409"),
        _ev(1002, "Application Hang", _t(now, 0.5), "", ["Teams.exe", "25.1.0"]),
        _ev(1002, "Application Hang", _t(now, 7), "", ["Teams.exe", "25.1.0"]),
    ]

    whea = [_ev(17, "Microsoft-Windows-WHEA-Logger", _t(now, d), "", level=3) for d in (3, 8)]

    storage = [_ev(153, "disk", _t(now, d), "", level=3) for d in (2, 9, 12)]

    return FakeRunner(
        queries={
            "events.system_crash": system_crash,
            "events.app_crash": app_crash,
            "events.whea": whea,
            "events.storage": storage,
            "cim.reliability": {"Index": 3.6, "Time": _t(now, 0)},
            "cim.logical_disks": [
                {"DeviceID": "C:", "VolumeName": "Windows", "Size": 255e9, "FreeSpace": 11.2e9},
                {"DeviceID": "D:", "VolumeName": "Data", "Size": 1000e9, "FreeSpace": 412e9},
            ],
            "storage.physical_disks": [
                {
                    "Name": "Samsung SSD 970 EVO 250GB",
                    "Media": "SSD",
                    "Bus": "NVMe",
                    "Health": "Healthy",
                    "Status": "OK",
                    "Temperature": 41,
                    "Wear": 74,
                    "ReadErrors": 0,
                    "WriteErrors": 0,
                },
                {
                    "Name": "WDC WD10EZEX-08WN4A0",
                    "Media": "HDD",
                    "Bus": "SATA",
                    "Health": "Healthy",
                    "Status": "OK",
                    "Temperature": 35,
                    "Wear": None,
                    "ReadErrors": 0,
                    "WriteErrors": 0,
                },
            ],
            "cim.problem_devices": [
                {
                    "Name": "Intel(R) Wi-Fi 6 AX201 160MHz",
                    "PNPClass": "Net",
                    "ConfigManagerErrorCode": 10,
                    "Present": True,
                },
            ],
            "cim.os": {
                "Caption": "Microsoft Windows 11 Home",
                "Version": "10.0.26100",
                "Build": "26100",
                "LastBoot": _t(now, 19, 3),
                "TotalKB": 16 * 1024 * 1024,
                "FreeKB": 5.5 * 1024 * 1024,
                "RebootPending": True,
            },
            "updates.last_install": {
                "Title": "2026-09 Cumulative Update for Windows 11 Version 24H2 for "
                "x64-based Systems (KB5043178)",
                "InstalledOn": _t(now, 52),
            },
            "cim.antivirus": {
                "displayName": "Microsoft Defender Antivirus",
                "productState": 397568,
            },
            "cim.startup": [
                {"Name": n, "Location": "HKU\\...\\Run"}
                for n in (
                    "OneDrive",
                    "Teams",
                    "Spotify",
                    "Discord",
                    "Steam",
                    "EpicGamesLauncher",
                    "Adobe Creative Cloud",
                    "Logitech G HUB",
                    "NVIDIA Broadcast",
                    "Razer Synapse",
                    "Zoom",
                    "Dropbox",
                    "SecurityHealth",
                    "RtkAudUService",
                )
            ],
        }
    )
