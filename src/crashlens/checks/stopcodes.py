"""Plain-language knowledge base for Windows stop codes (bug checks).

Explanations are written for non-experts. ``repairs`` refer to ids in
``crashlens.repairs.catalog``.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StopCode:
    code: int
    name: str
    meaning: str
    likely_causes: tuple[str, ...]
    steps: tuple[str, ...]
    repairs: tuple[str, ...] = ()

    @property
    def hex(self) -> str:
        return format_code(self.code)


def format_code(code: int) -> str:
    return f"0x{code:08X}"


_DRIVER_STEPS = (
    "Update the driver for any recently added or changed device (graphics, network, audio).",
    "If the crashes started after a driver or Windows update, roll that driver back in "
    "Device Manager.",
    "Check that Windows Update is fully installed.",
)
_MEMORY_STEPS = (
    "Run Windows Memory Diagnostic to test the RAM.",
    "If you overclock or use an XMP/EXPO memory profile, return to default settings and test.",
    "Reseat memory modules (or test them one at a time) if crashes continue.",
)
_FILES_STEPS = (
    "Run System File Checker and DISM to repair Windows system files.",
    "Scan the system drive for file-system errors.",
)

_CODES: tuple[StopCode, ...] = (
    StopCode(
        0x0A,
        "IRQL_NOT_LESS_OR_EQUAL",
        "A driver touched memory it was not allowed to at that moment.",
        ("A faulty or outdated driver", "Defective RAM", "Incompatible security software"),
        _DRIVER_STEPS + _MEMORY_STEPS[:1],
        ("memory_diagnostic", "open_device_manager", "open_windows_update"),
    ),
    StopCode(
        0x1A,
        "MEMORY_MANAGEMENT",
        "Windows found its memory bookkeeping damaged.",
        ("Defective or unstable RAM", "A buggy driver", "Damaged system files"),
        _MEMORY_STEPS + _FILES_STEPS[:1],
        ("memory_diagnostic", "sfc_scan", "dism_restore"),
    ),
    StopCode(
        0x1E,
        "KMODE_EXCEPTION_NOT_HANDLED",
        "A program running inside the Windows kernel hit an error nobody caught.",
        ("A faulty driver", "Damaged system files", "Hardware problems"),
        _DRIVER_STEPS + _FILES_STEPS[:1],
        ("sfc_scan", "open_device_manager"),
    ),
    StopCode(
        0x24,
        "NTFS_FILE_SYSTEM",
        "The NTFS file system driver ran into a problem.",
        ("File-system corruption", "A failing disk", "Disk-related drivers or filter software"),
        _FILES_STEPS + ("Check the disk's health (CrashLens Health scan).",),
        ("chkdsk_scan", "sfc_scan"),
    ),
    StopCode(
        0x3B,
        "SYSTEM_SERVICE_EXCEPTION",
        "A system service crashed while switching between a program and the kernel.",
        ("Graphics or other drivers", "Antivirus or anti-cheat drivers", "Damaged system files"),
        _DRIVER_STEPS + _FILES_STEPS[:1],
        ("sfc_scan", "dism_restore", "open_device_manager"),
    ),
    StopCode(
        0x50,
        "PAGE_FAULT_IN_NONPAGED_AREA",
        "Windows looked for data in memory that should always be there and did not find it.",
        ("Defective RAM", "A faulty driver", "Antivirus software", "Disk or file-system errors"),
        _MEMORY_STEPS[:1] + _DRIVER_STEPS[:2] + _FILES_STEPS[1:],
        ("memory_diagnostic", "chkdsk_scan", "open_device_manager"),
    ),
    StopCode(
        0x7A,
        "KERNEL_DATA_INPAGE_ERROR",
        "Windows could not read needed data back from the disk (page file).",
        ("A failing disk or SSD", "Loose or faulty SATA/NVMe connection", "Bad RAM"),
        (
            "Back up important files now - this code often points at a failing disk.",
            "Check disk health and run a disk scan.",
            "Reseat the drive's cable / connector.",
        ),
        ("chkdsk_scan", "memory_diagnostic"),
    ),
    StopCode(
        0x7E,
        "SYSTEM_THREAD_EXCEPTION_NOT_HANDLED",
        "A Windows system thread crashed - usually because of a driver.",
        ("Outdated or incompatible driver (graphics drivers are common)",),
        _DRIVER_STEPS,
        ("open_device_manager", "open_windows_update"),
    ),
    StopCode(
        0x7F,
        "UNEXPECTED_KERNEL_MODE_TRAP",
        "The processor raised an error the kernel could not handle.",
        ("Hardware faults (RAM, CPU)", "Overheating", "Overclocking", "Drivers"),
        _MEMORY_STEPS + ("Check that the PC is not overheating; clean dust from fans.",),
        ("memory_diagnostic",),
    ),
    StopCode(
        0x9F,
        "DRIVER_POWER_STATE_FAILURE",
        "A driver did not respond while the PC was going to sleep, waking, or shutting down.",
        ("Network, USB, graphics or storage drivers", "Power-management settings"),
        _DRIVER_STEPS
        + ("Try disabling Fast Startup if the problem appears around shutdown or sleep.",),
        ("open_device_manager", "open_windows_update"),
    ),
    StopCode(
        0xC2,
        "BAD_POOL_CALLER",
        "A driver made an invalid memory request.",
        ("A faulty driver", "Security or VPN software"),
        _DRIVER_STEPS,
        ("open_device_manager",),
    ),
    StopCode(
        0xC5,
        "DRIVER_CORRUPTED_EXPOOL",
        "A driver damaged shared kernel memory.",
        ("A faulty driver",),
        _DRIVER_STEPS,
        ("open_device_manager",),
    ),
    StopCode(
        0xD1,
        "DRIVER_IRQL_NOT_LESS_OR_EQUAL",
        "A driver accessed memory incorrectly - very often a network or graphics driver.",
        ("Network (Wi-Fi/Ethernet) drivers", "Graphics drivers", "VPN or firewall drivers"),
        _DRIVER_STEPS,
        ("open_device_manager", "open_windows_update"),
    ),
    StopCode(
        0xEF,
        "CRITICAL_PROCESS_DIED",
        "A process Windows cannot live without stopped unexpectedly.",
        ("Damaged system files", "Disk errors", "Malware or aggressive security software"),
        _FILES_STEPS + ("Run a full antivirus scan in Windows Security.",),
        ("sfc_scan", "dism_restore", "chkdsk_scan", "open_windows_security"),
    ),
    StopCode(
        0xF4,
        "CRITICAL_OBJECT_TERMINATION",
        "A critical process or thread ended unexpectedly.",
        ("Failing storage", "Damaged system files"),
        _FILES_STEPS,
        ("chkdsk_scan", "sfc_scan"),
    ),
    StopCode(
        0x101,
        "CLOCK_WATCHDOG_TIMEOUT",
        "One processor core stopped responding.",
        ("CPU instability (overclocking, voltage)", "Outdated BIOS/UEFI", "Overheating"),
        (
            "Remove any CPU overclock / undervolt and test at default settings.",
            "Update the BIOS/UEFI from the PC or motherboard maker.",
            "Check temperatures and cooling.",
        ),
    ),
    StopCode(
        0x116,
        "VIDEO_TDR_FAILURE",
        "The graphics driver stopped responding and could not be restarted.",
        ("Graphics driver problems", "Overheated or overclocked graphics card", "Weak PSU"),
        (
            "Install the latest graphics driver from NVIDIA/AMD/Intel (a clean install helps).",
            "Remove any graphics-card overclock.",
            "Check graphics-card temperatures and power connectors.",
        ),
        ("open_device_manager",),
    ),
    StopCode(
        0x117,
        "VIDEO_TDR_TIMEOUT_DETECTED",
        "The graphics driver stopped responding in time.",
        ("Graphics driver problems", "Overheating graphics card"),
        ("Update or reinstall the graphics driver.", "Check graphics-card cooling."),
        ("open_device_manager",),
    ),
    StopCode(
        0x124,
        "WHEA_UNCORRECTABLE_ERROR",
        "The hardware itself reported an error it could not correct.",
        ("CPU or RAM instability", "Overclocking", "Overheating", "Power supply problems"),
        (
            "Return CPU, RAM and GPU to default (non-overclocked) settings.",
            "Check temperatures and clean dust from fans and heatsinks.",
            "Update the BIOS/UEFI.",
            "Run Windows Memory Diagnostic.",
        ),
        ("memory_diagnostic",),
    ),
    StopCode(
        0x133,
        "DPC_WATCHDOG_VIOLATION",
        "A driver took too long to finish its work.",
        ("Storage controller drivers or SSD firmware", "Other outdated drivers"),
        ("Update SSD firmware and storage/chipset drivers from the maker's website.",)
        + _DRIVER_STEPS[1:],
        ("open_device_manager", "open_windows_update"),
    ),
    StopCode(
        0x139,
        "KERNEL_SECURITY_CHECK_FAILURE",
        "Windows detected damaged internal data and stopped to stay safe.",
        ("Incompatible drivers", "Bad RAM", "Damaged system files"),
        _DRIVER_STEPS[:2] + _MEMORY_STEPS[:1] + _FILES_STEPS[:1],
        ("sfc_scan", "memory_diagnostic", "open_device_manager"),
    ),
    StopCode(
        0x13A,
        "KERNEL_MODE_HEAP_CORRUPTION",
        "Kernel memory was damaged, usually by a driver.",
        ("Graphics or other drivers",),
        _DRIVER_STEPS,
        ("open_device_manager",),
    ),
    StopCode(
        0x154,
        "UNEXPECTED_STORE_EXCEPTION",
        "Windows' memory store hit an unexpected error.",
        ("Failing or nearly full disk", "Storage drivers", "Damaged system files"),
        ("Check the disk's health and free space.",) + _FILES_STEPS,
        ("chkdsk_scan", "sfc_scan"),
    ),
    StopCode(
        0x15F,
        "CONNECTED_STANDBY_WATCHDOG_TIMEOUT_LIVEDUMP",
        "A device did not respond while the PC was in modern standby.",
        ("Device drivers that do not handle sleep well",),
        _DRIVER_STEPS,
        ("open_device_manager",),
    ),
    StopCode(
        0x18B,
        "SECURE_KERNEL_ERROR",
        "The secure kernel (virtualisation-based security) hit an error.",
        ("Drivers incompatible with Memory Integrity", "Firmware issues"),
        ("Update the BIOS/UEFI.",) + _DRIVER_STEPS[:2],
        ("open_device_manager",),
    ),
    StopCode(
        0x19,
        "BAD_POOL_HEADER",
        "A block of kernel memory was damaged.",
        ("A faulty driver", "Defective RAM", "Disk errors"),
        _DRIVER_STEPS[:2] + _MEMORY_STEPS[:1],
        ("memory_diagnostic", "open_device_manager"),
    ),
    StopCode(
        0x3D,
        "INTERRUPT_EXCEPTION_NOT_HANDLED",
        "A hardware interrupt caused an error nobody caught.",
        ("Drivers", "Hardware faults"),
        _DRIVER_STEPS,
        ("open_device_manager",),
    ),
    StopCode(
        0x4E,
        "PFN_LIST_CORRUPT",
        "Windows' list of physical memory pages was damaged.",
        ("Defective RAM", "A faulty driver"),
        _MEMORY_STEPS,
        ("memory_diagnostic",),
    ),
    StopCode(
        0x6B,
        "PROCESS1_INITIALIZATION_FAILED",
        "Windows failed while starting up its first processes.",
        ("Damaged system files", "Disk problems"),
        _FILES_STEPS,
        ("sfc_scan", "dism_restore", "chkdsk_scan"),
    ),
    StopCode(
        0x7B,
        "INACCESSIBLE_BOOT_DEVICE",
        "Windows lost access to the drive it boots from.",
        ("Storage controller mode changed in BIOS (AHCI/RAID)", "Failing disk", "Driver update"),
        (
            "If you changed BIOS storage settings, change them back.",
            "Check the disk's health.",
        ),
        ("chkdsk_scan",),
    ),
    StopCode(
        0xBE,
        "ATTEMPTED_WRITE_TO_READONLY_MEMORY",
        "A driver tried to write to memory that is read-only.",
        ("A faulty driver",),
        _DRIVER_STEPS,
        ("open_device_manager",),
    ),
    StopCode(
        0xC4,
        "DRIVER_VERIFIER_DETECTED_VIOLATION",
        "Driver Verifier caught a driver misbehaving.",
        ("A faulty driver (Driver Verifier is turned on)",),
        ("If you enabled Driver Verifier, note the driver it names, then turn Verifier off.",)
        + _DRIVER_STEPS[:1],
    ),
    StopCode(
        0xFC,
        "ATTEMPTED_EXECUTE_OF_NOEXECUTE_MEMORY",
        "Code tried to run from memory marked as data only.",
        ("A faulty driver", "Bad RAM"),
        _DRIVER_STEPS[:2] + _MEMORY_STEPS[:1],
        ("memory_diagnostic", "open_device_manager"),
    ),
    StopCode(
        0x1000007E,
        "SYSTEM_THREAD_EXCEPTION_NOT_HANDLED_M",
        "A Windows system thread crashed - usually because of a driver.",
        ("Outdated or incompatible driver",),
        _DRIVER_STEPS,
        ("open_device_manager",),
    ),
    StopCode(
        0x1000008E,
        "KERNEL_MODE_EXCEPTION_NOT_HANDLED_M",
        "A kernel-mode program hit an error nobody caught.",
        ("Drivers", "Bad RAM"),
        _DRIVER_STEPS[:2] + _MEMORY_STEPS[:1],
        ("memory_diagnostic", "open_device_manager"),
    ),
    StopCode(
        0x8E,
        "KERNEL_MODE_EXCEPTION_NOT_HANDLED",
        "A kernel-mode program hit an error nobody caught.",
        ("Drivers", "Bad RAM"),
        _DRIVER_STEPS[:2] + _MEMORY_STEPS[:1],
        ("memory_diagnostic", "open_device_manager"),
    ),
    StopCode(
        0x1D8,
        "ATTEMPTED_SWITCH_FROM_DPC",
        "A driver performed an illegal operation while handling a deferred call.",
        ("A faulty driver",),
        _DRIVER_STEPS,
        ("open_device_manager",),
    ),
)

STOP_CODES: dict[int, StopCode] = {}
for _sc in _CODES:
    STOP_CODES.setdefault(_sc.code, _sc)


def lookup(code: int) -> StopCode | None:
    return STOP_CODES.get(code)


def describe(code: int) -> StopCode:
    """Return the entry for a code, or a generic fallback entry."""
    found = lookup(code)
    if found:
        return found
    return StopCode(
        code,
        "UNKNOWN_STOP_CODE",
        "Windows stopped with a code CrashLens does not have a description for yet.",
        ("Drivers", "Hardware", "Damaged system files"),
        (
            f"Search Microsoft's 'Bug check code reference' for {format_code(code)}.",
            *_DRIVER_STEPS[:2],
            *_FILES_STEPS[:1],
        ),
        ("sfc_scan", "open_device_manager"),
    )


def parse_code(text: str | int | None) -> int | None:
    """Parse '0x0000009f', '9f', '159' (decimal from Kernel-Power 41) etc."""
    if text is None:
        return None
    if isinstance(text, int):
        return text
    s = str(text).strip()
    if not s:
        return None
    try:
        if s.lower().startswith("0x"):
            return int(s, 16)
        if s.isdigit():
            return int(s, 10)
        return int(s, 16)
    except ValueError:
        return None
