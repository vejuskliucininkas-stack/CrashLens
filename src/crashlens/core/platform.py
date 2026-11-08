"""Platform detection and basic system information (no external commands)."""

from __future__ import annotations

import getpass
import os
import platform
import socket
import sys
from pathlib import Path

from crashlens.core.models import SystemInfo


def is_windows() -> bool:
    return sys.platform == "win32"


def is_admin() -> bool:
    """True when running elevated. Never raises."""
    if not is_windows():
        try:
            return os.geteuid() == 0  # type: ignore[attr-defined]
        except AttributeError:
            return False
    try:
        import ctypes

        return bool(ctypes.windll.shell32.IsUserAnAdmin())  # type: ignore[attr-defined]
    except Exception:
        return False


def system_info() -> SystemInfo:
    win = is_windows()
    os_name = "Windows" if win else platform.system()
    version = platform.version()
    build = ""
    if win:
        # platform.release() says "10" on Windows 11; the build number tells them apart.
        try:
            build = version.split(".")[2]
            os_name = "Windows 11" if int(build) >= 22000 else f"Windows {platform.release()}"
        except (IndexError, ValueError):
            pass
    try:
        user = getpass.getuser()
    except Exception:
        user = ""
    return SystemInfo(
        os_name=os_name,
        os_version=version,
        os_build=build,
        computer_name=os.environ.get("COMPUTERNAME") or socket.gethostname(),
        user_name=user,
        is_admin=is_admin(),
        is_windows=win,
    )


def relaunch_as_admin() -> bool:
    """Start a new elevated copy of CrashLens through Windows' UAC prompt.

    Returns True if Windows accepted the request (the user still decides in the
    UAC dialog). Only CrashLens itself is relaunched, with its original arguments.
    """
    if not is_windows():
        return False
    try:
        import ctypes
        import subprocess

        if getattr(sys, "frozen", False):
            exe, args = sys.executable, sys.argv[1:]
        else:
            exe, args = sys.executable, ["-m", "crashlens", *sys.argv[1:]]
        params = subprocess.list2cmdline(args)
        rc = ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, params, None, 1)  # type: ignore[attr-defined]
        return int(rc) > 32
    except Exception:
        return False


def app_data_dir() -> Path:
    """Per-user folder for CrashLens' own files (audit log, settings)."""
    base = os.environ.get("LOCALAPPDATA")
    path = Path(base) / "CrashLens" if base else Path.home() / ".crashlens"
    return path


def windows_dir() -> Path:
    return Path(os.environ.get("SystemRoot") or os.environ.get("WINDIR") or r"C:\Windows")
