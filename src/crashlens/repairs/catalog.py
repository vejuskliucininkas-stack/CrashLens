"""The fixed list of repairs CrashLens can offer.

Design rules (enforced by tests in tests/test_repairs.py):
* Every command is a constant defined here - no user input is ever added.
* No repair deletes user files, changes security settings, or disables
  Windows protection features.
* Repairs either run a built-in Windows repair/diagnostic tool, or simply open
  a Windows settings page / tool so the user can act themselves.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from enum import Enum


class RepairKind(str, Enum):
    TOOL = "tool"  # runs a built-in Windows repair or diagnostic tool
    BUILTIN = "builtin"  # done by CrashLens itself (see repairs/cleanup.py)
    OPEN = "open"  # opens a Windows page or tool; the user decides what to do there
    # OPEN entries are started with ShellExecute (like double-clicking): argv[0] is the
    # document, URI or program and argv[1:] are its arguments.


@dataclass(frozen=True)
class Repair:
    id: str
    title: str
    description: str
    what_happens: str
    kind: RepairKind
    argv: tuple[str, ...]
    needs_admin: bool = False
    changes_system: bool = False
    needs_restart: bool = False
    duration: str = "a few seconds"
    timeout_s: float = 60.0
    caution: str = ""


def _system_drive() -> str:
    drive = os.environ.get("SystemDrive", "C:").strip().upper()
    return drive if re.fullmatch(r"[A-Z]:", drive) else "C:"


def _build() -> dict[str, Repair]:
    drive = _system_drive()
    items = [
        Repair(
            id="sfc_scan",
            title="Check and repair Windows system files (SFC)",
            description="Runs System File Checker, which compares Windows' own files against "
            "known-good copies and restores any that are damaged.",
            what_happens="Runs 'sfc /scannow'. Only Windows system files are checked and, if "
            "damaged, replaced with Windows' own cached copies. Your documents, programs and "
            "settings are not touched.",
            kind=RepairKind.TOOL,
            argv=("sfc.exe", "/scannow"),
            needs_admin=True,
            changes_system=True,
            duration="10-30 minutes",
            timeout_s=3600,
        ),
        Repair(
            id="dism_check",
            title="Quick check of the Windows component store (DISM)",
            description="Asks DISM whether the Windows image has already been flagged as "
            "damaged. Read-only and quick.",
            what_happens="Runs 'DISM /Online /Cleanup-Image /CheckHealth'. Nothing is changed.",
            kind=RepairKind.TOOL,
            argv=("DISM.exe", "/Online", "/Cleanup-Image", "/CheckHealth"),
            needs_admin=True,
            duration="under a minute",
            timeout_s=600,
        ),
        Repair(
            id="dism_scan",
            title="Deep scan of the Windows component store (DISM)",
            description="Scans the Windows image for damage. Read-only.",
            what_happens="Runs 'DISM /Online /Cleanup-Image /ScanHealth'. Nothing is changed.",
            kind=RepairKind.TOOL,
            argv=("DISM.exe", "/Online", "/Cleanup-Image", "/ScanHealth"),
            needs_admin=True,
            duration="5-15 minutes",
            timeout_s=3600,
        ),
        Repair(
            id="dism_restore",
            title="Repair the Windows component store (DISM)",
            description="Repairs the Windows image that SFC uses as its source of good files. "
            "Run this when SFC reports files it cannot fix, then run SFC again.",
            what_happens="Runs 'DISM /Online /Cleanup-Image /RestoreHealth'. Damaged Windows "
            "components are replaced with clean copies downloaded from Windows Update. Your "
            "files and programs are not touched.",
            kind=RepairKind.TOOL,
            argv=("DISM.exe", "/Online", "/Cleanup-Image", "/RestoreHealth"),
            needs_admin=True,
            changes_system=True,
            duration="10-30 minutes (needs internet)",
            timeout_s=5400,
        ),
        Repair(
            id="chkdsk_scan",
            title=f"Scan drive {drive} for file-system errors",
            description="Runs an online, read-only scan of the system drive while Windows keeps "
            "running.",
            what_happens=f"Runs 'chkdsk {drive} /scan'. The drive is checked and problems are "
            "reported. Nothing is repaired or deleted by this scan.",
            kind=RepairKind.TOOL,
            argv=("chkdsk.exe", drive, "/scan"),
            needs_admin=True,
            duration="a few minutes",
            timeout_s=3600,
        ),
        Repair(
            id="restore_point",
            title="Create a system restore point",
            description="Saves a restore point so Windows settings, drivers and system files "
            "can be rolled back later. A good first step before other repairs.",
            what_happens="Runs 'Checkpoint-Computer'. A new restore point is added; nothing is "
            "removed. System Protection must be turned on for the system drive, and Windows "
            "allows only one new restore point per 24 hours by default.",
            kind=RepairKind.TOOL,
            argv=(
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                "Checkpoint-Computer -Description CrashLens -RestorePointType MODIFY_SETTINGS",
            ),
            needs_admin=True,
            changes_system=True,
            duration="1-3 minutes",
            timeout_s=900,
        ),
        Repair(
            id="clean_temp",
            title="Clean up temporary files",
            description="Deletes leftover temporary files that programs and Windows no longer "
            "need, to free up space on drive C:.",
            what_happens="Deletes files older than 2 days from the temporary-files folders "
            "(%TEMP%, and C:\\Windows\\Temp when CrashLens runs as administrator). Files in use "
            "are skipped. Documents, pictures, downloads, the desktop and the Recycle Bin are "
            "never touched.",
            kind=RepairKind.BUILTIN,
            argv=(),
            changes_system=True,
            duration="under a minute",
            timeout_s=600,
        ),
        Repair(
            id="windows_update_scan",
            title="Check for Windows updates now",
            description="Tells Windows Update to look for updates (including driver updates) "
            "right away. Updates then download and install as usual.",
            what_happens="Runs 'UsoClient StartInteractiveScan', the same as clicking 'Check for "
            "updates' in Settings.",
            kind=RepairKind.TOOL,
            argv=("UsoClient.exe", "StartInteractiveScan"),
            duration="starts straight away; updates install in the background",
            timeout_s=120,
        ),
        Repair(
            id="reset_windows_update",
            title="Reset Windows Update",
            description="Fixes Windows Update when updates keep failing: stops the update "
            "services, sets the old download cache aside, and starts the services again.",
            what_happens="Stops the Windows Update and BITS services, renames the folder "
            "C:\\Windows\\SoftwareDistribution to SoftwareDistribution.old-<number> (nothing is "
            "deleted), then starts the services again. Windows downloads the updates fresh.",
            kind=RepairKind.TOOL,
            argv=(
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                "Stop-Service -Name wuauserv,bits -Force -ErrorAction Stop; "
                "Rename-Item -Path $env:windir\\SoftwareDistribution -NewName "
                "SoftwareDistribution.old-$((Get-Date).Ticks) -ErrorAction "
                "Continue; Start-Service -Name bits,wuauserv; "
                "Write-Output CrashLens-reset-complete",
            ),
            needs_admin=True,
            changes_system=True,
            duration="under a minute",
            timeout_s=300,
        ),
        Repair(
            id="rescan_devices",
            title="Re-detect devices",
            description="Makes Windows look for hardware again and reinstall drivers it "
            "already has. Often brings a device that stopped working back.",
            what_happens="Runs 'pnputil /scan-devices', the same as 'Scan for hardware changes' "
            "in Device Manager.",
            kind=RepairKind.TOOL,
            argv=("pnputil.exe", "/scan-devices"),
            needs_admin=True,
            duration="a few seconds",
            timeout_s=300,
        ),
        Repair(
            id="update_defender",
            title="Update virus protection",
            description="Downloads the newest virus definitions for Microsoft Defender.",
            what_happens="Runs 'Update-MpSignature'. Only works when Microsoft Defender is your "
            "antivirus.",
            kind=RepairKind.TOOL,
            argv=(
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                "Update-MpSignature -ErrorAction Stop; Write-Output CrashLens-defender-updated",
            ),
            needs_admin=True,
            duration="under a minute (needs internet)",
            timeout_s=600,
        ),
        Repair(
            id="quick_virus_scan",
            title="Quick virus scan",
            description="Runs a Microsoft Defender quick scan of the places viruses usually hide.",
            what_happens="Runs 'Start-MpScan -ScanType QuickScan'. Defender handles anything it "
            "finds as usual.",
            kind=RepairKind.TOOL,
            argv=(
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                "Start-MpScan -ScanType QuickScan -ErrorAction Stop; "
                "Write-Output CrashLens-scan-complete",
            ),
            needs_admin=True,
            duration="5-15 minutes",
            timeout_s=3600,
        ),
        Repair(
            id="memory_diagnostic",
            title="Test the memory (Windows Memory Diagnostic)",
            description="Opens Windows Memory Diagnostic. It tests RAM during a restart.",
            what_happens="Opens 'mdsched.exe'. Windows asks whether to restart now or test at "
            "the next restart - you choose there. Save your work before restarting.",
            kind=RepairKind.OPEN,
            argv=("mdsched.exe",),
            needs_restart=True,
            duration="opens instantly; the test takes 10-20 minutes during restart",
            timeout_s=30,
            caution="Choosing 'Restart now' in the Windows dialog restarts the PC immediately.",
        ),
        Repair(
            id="open_device_manager",
            title="Open Device Manager",
            description="Shows every device and its driver. Update or roll back drivers here.",
            what_happens="Opens Device Manager. Nothing is changed unless you change it.",
            kind=RepairKind.OPEN,
            argv=("devmgmt.msc",),
        ),
        Repair(
            id="open_windows_update",
            title="Open Windows Update",
            description="Check for and install Windows and driver updates.",
            what_happens="Opens Settings > Windows Update. Nothing is installed automatically "
            "by CrashLens.",
            kind=RepairKind.OPEN,
            argv=("ms-settings:windowsupdate",),
        ),
        Repair(
            id="open_windows_security",
            title="Open Windows Security",
            description="Check virus protection and run a scan.",
            what_happens="Opens the Windows Security app. CrashLens never changes security "
            "settings.",
            kind=RepairKind.OPEN,
            argv=("windowsdefender:",),
        ),
        Repair(
            id="open_reliability_monitor",
            title="Open Reliability Monitor",
            description="Day-by-day history of crashes, failures and installs.",
            what_happens="Opens Reliability Monitor. Read-only.",
            kind=RepairKind.OPEN,
            argv=("perfmon.exe", "/rel"),
        ),
        Repair(
            id="open_startup_apps",
            title="Open Startup apps settings",
            description="Choose which programs start with Windows.",
            what_happens="Opens Settings > Apps > Startup. You decide what to turn off.",
            kind=RepairKind.OPEN,
            argv=("ms-settings:startupapps",),
        ),
        Repair(
            id="open_storage_settings",
            title="Open Storage settings",
            description="See what uses disk space and review cleanup suggestions.",
            what_happens="Opens Settings > System > Storage. Nothing is deleted unless you "
            "choose to delete it there.",
            kind=RepairKind.OPEN,
            argv=("ms-settings:storagesense",),
        ),
    ]
    return {r.id: r for r in items}


REPAIRS: dict[str, Repair] = _build()


def get(repair_id: str) -> Repair:
    try:
        return REPAIRS[repair_id]
    except KeyError:
        raise KeyError(f"Unknown repair '{repair_id}'") from None
