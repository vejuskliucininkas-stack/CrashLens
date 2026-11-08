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


def app_data_dir() -> Path:
    """Per-user folder for CrashLens' own files (audit log, settings)."""
    base = os.environ.get("LOCALAPPDATA")
    path = Path(base) / "CrashLens" if base else Path.home() / ".crashlens"
    return path


def windows_dir() -> Path:
    return Path(os.environ.get("SystemRoot") or os.environ.get("WINDIR") or r"C:\Windows")
