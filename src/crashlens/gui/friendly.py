"""Plain words for people who have never used a PC tool.

Findings keep their precise technical text (used in reports and the expert
view). This module turns them into a short headline, one calm sentence, and a
simple name for each fix.
"""

from __future__ import annotations

import re

from crashlens.core.models import Finding, Severity

# --------------------------------------------------------------------------- fixes

# repair id -> (button / title text, what it does in one or two plain sentences)
REPAIR_WORDS: dict[str, tuple[str, str]] = {
    "clean_temp": (
        "Clean up temporary files",
        "Deletes leftover temporary files that Windows and programs no longer need. "
        "Your documents, photos, downloads and the Recycle Bin are not touched.",
    ),
    "windows_update_scan": (
        "Check for updates now",
        "Windows Update looks for new updates and drivers straight away and installs them "
        "in the background.",
    ),
    "reset_windows_update": (
        "Reset Windows Update",
        "Fixes updates that keep failing: Windows Update is restarted with a fresh download "
        "folder. Nothing is deleted.",
    ),
    "rescan_devices": (
        "Re-detect devices",
        "Windows looks for your hardware again and reinstalls drivers it already has. "
        "Often brings a device that stopped working back.",
    ),
    "update_defender": (
        "Update virus protection",
        "Downloads the newest virus definitions for Microsoft Defender.",
    ),
    "quick_virus_scan": (
        "Quick virus scan",
        "Microsoft Defender checks the places viruses usually hide. Takes 5-15 minutes.",
    ),
    "sfc_scan": (
        "Repair Windows files",
        "Windows checks its own files and fixes any that are broken. "
        "Your photos, documents and programs are not touched.",
    ),
    "dism_check": (
        "Quick check of Windows",
        "Windows quickly checks whether it is damaged. Nothing is changed.",
    ),
    "dism_scan": (
        "Full check of Windows",
        "Windows checks itself thoroughly for damage. Nothing is changed.",
    ),
    "dism_restore": (
        "Deep-repair Windows",
        "Windows downloads fresh copies of its damaged parts and repairs itself. "
        "It needs the internet. Your files are not touched.",
    ),
    "chkdsk_scan": (
        "Check the drive for errors",
        "Windows checks your main drive for errors and tells you what it finds. "
        "Nothing is changed or deleted.",
    ),
    "restore_point": (
        "Make a backup point",
        "Windows saves a snapshot of its settings, so changes can be undone later. "
        "Your files are not touched.",
    ),
    "memory_diagnostic": (
        "Test the memory",
        "Opens Windows' memory test. The test runs while the computer restarts, so "
        "save your work first. You choose when to restart.",
    ),
    "open_device_manager": (
        "Open driver settings",
        "Opens Device Manager, where drivers can be updated. Nothing changes unless you change it.",
    ),
    "open_windows_update": (
        "Open Windows Update",
        'Opens Windows Update. Click "Check for updates" there.',
    ),
    "open_windows_security": (
        "Open virus protection",
        "Opens Windows Security, where you can turn protection on and run a scan.",
    ),
    "open_reliability_monitor": (
        "See crash history",
        "Opens the calendar of crashes and problems that Windows keeps.",
    ),
    "open_startup_apps": (
        "Choose startup programs",
        "Opens the list of programs that start with your computer. "
        "Switch off the ones you don't need.",
    ),
    "open_storage_settings": (
        "Free up space",
        "Opens Storage settings, which shows what takes up space and suggests "
        "what to clean up. Nothing is deleted unless you choose it.",
    ),
}


def repair_name(repair_id: str) -> str:
    return REPAIR_WORDS.get(repair_id, (repair_id.replace("_", " ").capitalize(), ""))[0]


def repair_text(repair_id: str) -> str:
    return REPAIR_WORDS.get(repair_id, ("", ""))[1]


# --------------------------------------------------------------------------- findings

EXPLAIN: dict[str, str] = {
    "bsod-": "Windows hit a serious error and had to restart. This is usually caused by "
    "a driver (the small program that runs one part of your computer) or by faulty "
    "memory.",
    "unexpected-restart": "Your computer switched off without warning. This happens with "
    "power cuts, overheating, or when it froze and the power button was held down.",
    "gpu-tdr": "Your screen may have gone black for a second. Updating the graphics "
    "driver usually fixes this.",
    "whea-fatal": "A part inside your computer (like the processor or the memory) "
    "reported an error it could not fix.",
    "whea-corrected": "A few of these are normal. It's only a worry if there are many.",
    "app-crash-": "The program closed unexpectedly. Updating or reinstalling it usually helps.",
    "app-hang-": "The program stopped responding and had to be closed.",
    "reliability-index": "This score comes from Windows itself. 10 means very stable. "
    "Under 5 means there have been many problems lately.",
    "changes-before-crashes": "Something new - a driver, an update or a program - right "
    "before the problems started is often the cause.",
    "updates-failing": "Updates fix problems and keep you safe, so it's worth getting "
    "them working again.",
    "disk-space-": "A full drive makes the computer slow and stops updates from installing.",
    "disk-health-": "Copy your photos and documents somewhere safe soon, in case this "
    "drive stops working.",
    "storage-errors": "Drive errors can cause freezing and lost files. Copy your "
    "important files somewhere safe.",
    "device-": "A part of your computer, or something plugged into it, has a driver problem.",
    "reboot-pending": "Save your work, then click Start, the power button, and Restart.",
    "long-uptime": "Restarting now and then clears out small problems and finishes updates.",
    "memory-pressure": "Close programs and browser tabs you aren't using.",
    "updates-old": "Updates fix problems and protect you from viruses.",
    "av-off": "Your computer is not protected against viruses right now.",
    "av-outdated": "Your virus protection needs an update to catch new viruses.",
    "startup-many": "They make your computer slower to start. You can switch off the "
    "ones you don't need.",
}


def times(n: int) -> str:
    return {1: "once", 2: "twice"}.get(n, f"{n} times")


def _key(finding_id: str) -> str | None:
    matches = [k for k in EXPLAIN if finding_id == k or finding_id.startswith(k)]
    return max(matches, key=len) if matches else None


def _program_name(title: str) -> str:
    name = re.split(r" (crashed|stopped responding)", title)[0].strip()
    return re.sub(r"\.exe$", "", name, flags=re.I) or "A program"


def headline(f: Finding) -> str:
    fid, n = f.id, f.occurrences
    if fid.startswith("bsod-"):
        return f"Your computer crashed with a blue screen {times(n)}"
    if fid == "unexpected-restart":
        return f"Your computer switched off or restarted by itself {times(n)}"
    if fid == "gpu-tdr":
        return f"Your screen's driver stopped working for a moment {times(n)}"
    if fid == "whea-fatal":
        return "Your computer's hardware reported serious errors"
    if fid == "whea-corrected":
        return "Your computer's hardware fixed some small errors by itself"
    if fid.startswith("app-crash-"):
        return f"The program “{_program_name(f.title)}” closed by itself {times(n)}"
    if fid.startswith("app-hang-"):
        return f"The program “{_program_name(f.title)}” froze {times(n)}"
    if fid == "reliability-index":
        m = re.search(r"([\d.]+)\s*/\s*10", f.title)
        score = m.group(1) if m else "?"
        return f"Windows gives your computer a stability score of {score} out of 10"
    if fid == "changes-before-crashes":
        return "Something was installed just before the problems started"
    if fid == "updates-failing":
        return "Windows updates keep failing"
    if fid.startswith("disk-space-"):
        drive = fid.rsplit("-", 1)[-1].upper()
        if drive == "C":
            return "Your main drive (C:) is almost full"
        return f"Drive {drive}: is almost full"
    if fid.startswith("disk-health-"):
        if f.severity >= Severity.CRITICAL:
            return "One of your drives may be about to fail"
        return "One of your drives needs attention"
    if fid == "storage-errors":
        return "Your drive reported errors"
    if fid.startswith("device-"):
        return "A device isn't working properly"
    if fid == "reboot-pending":
        return "Your computer needs a restart to finish updating"
    if fid == "long-uptime":
        m = re.search(r"(\d+) days", f.title)
        return f"Your computer hasn't been restarted for {m.group(1) if m else 'many'} days"
    if fid == "memory-pressure":
        return "Your computer's memory is almost full"
    if fid == "updates-old":
        m = re.search(r"(\d+) days", f.title)
        return f"Windows hasn't updated for {m.group(1) if m else 'a long time'} days"
    if fid == "av-off":
        return "Virus protection is switched off"
    if fid == "av-outdated":
        return "Virus protection is out of date"
    if fid == "startup-many":
        m = re.match(r"(\d+)", f.title)
        return f"{m.group(1) if m else 'Many'} programs start with your computer"
    return f.title


def explanation(f: Finding) -> str:
    key = _key(f.id)
    text = EXPLAIN[key] if key else f.summary
    if f.id.startswith("device-"):
        text = f"{f.title}. {text}"
    return text


def badge(f: Finding) -> str:
    if f.severity >= Severity.HIGH:
        return "Important"
    if f.severity == Severity.MEDIUM:
        return "Worth fixing"
    if f.severity == Severity.LOW:
        return "Small thing"
    return "Good to know"


def plural(n: int, word: str) -> str:
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def verdict(findings: list[Finding]) -> tuple[str, str, str]:
    """Return (mood, title, subtitle). mood is 'ok', 'warn' or 'bad'."""
    main = [f for f in findings if f.severity >= Severity.MEDIUM]
    small = [f for f in findings if f.severity == Severity.LOW]
    also = f" There are also {plural(len(small), 'small thing')} further down." if small else ""
    if not main and not small:
        return "ok", "Your computer looks healthy", "We didn't find anything that needs fixing."
    if not main:
        return (
            "warn",
            "Your computer is mostly fine",
            f"We found {plural(len(small), 'small thing')} you can improve.",
        )
    if any(f.severity >= Severity.HIGH for f in main):
        return (
            "bad",
            f"We found {plural(len(main), 'problem')} to fix",
            "Start with the first one - it's the most important." + also,
        )
    return (
        "warn",
        f"We found {plural(len(main), 'thing')} worth fixing",
        "Start with the first one." + also,
    )
