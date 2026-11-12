"""Clean up temporary files - the only CrashLens fix that deletes anything.

Strict limits (enforced here and by tests):
* Only folders that ARE temporary-file folders (the user's %TEMP%, and
  C:\\Windows\\Temp when running as administrator). Anything else is refused.
* Only files older than ``min_age_days`` (default 2), so files programs are
  using right now are left alone.
* Never follows symbolic links or junctions, so nothing outside the temp
  folder can be reached.
* Files that are locked or protected are skipped, never forced.
* Folders are only removed when empty.
"""

from __future__ import annotations

import os
import stat
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

from crashlens.core.platform import windows_dir

FILE_ATTRIBUTE_REPARSE_POINT = 0x400


@dataclass
class CleanupResult:
    files_deleted: int = 0
    bytes_freed: int = 0
    skipped: int = 0
    folders: list[str] = field(default_factory=list)

    @property
    def freed_text(self) -> str:
        b = self.bytes_freed
        if b >= 1024**3:
            return f"{b / 1024**3:.1f} GB"
        if b >= 1024**2:
            return f"{b / 1024**2:.0f} MB"
        return f"{b / 1024:.0f} KB"


class UnsafeFolderError(ValueError):
    pass


def temp_folders(is_admin: bool) -> list[Path]:
    folders = [Path(tempfile.gettempdir())]
    if is_admin and os.name == "nt":
        folders.append(windows_dir() / "Temp")
    out = []
    for f in folders:
        try:
            r = f.resolve()
        except OSError:
            continue
        if r.is_dir() and r not in out:
            out.append(r)
    return out


def check_safe_root(root: Path) -> Path:
    """Refuse anything that is not clearly a temporary-files folder."""
    r = Path(root).resolve()
    if r.name.lower() not in ("temp", "tmp"):
        raise UnsafeFolderError(f"{r} is not a temporary-files folder")
    if r.parent == r or r == Path.home().resolve() or len(r.parts) < 2:
        raise UnsafeFolderError(f"{r} is too broad")
    return r


def _is_link(entry: os.DirEntry) -> bool:
    try:
        if entry.is_symlink():
            return True
        st = entry.stat(follow_symlinks=False)
    except OSError:
        return True  # cannot inspect - treat as unsafe
    attrs = getattr(st, "st_file_attributes", 0)
    return bool(attrs & FILE_ATTRIBUTE_REPARSE_POINT)


def _clean_dir(path: Path, cutoff: float, res: CleanupResult, depth: int = 0) -> bool:
    """Delete old files below ``path``. Returns True if ``path`` ended up empty."""
    if depth > 32:
        return False
    empty = True
    try:
        entries = list(os.scandir(path))
    except OSError:
        res.skipped += 1
        return False
    for entry in entries:
        if _is_link(entry):
            empty = False
            res.skipped += 1
            continue
        try:
            st = entry.stat(follow_symlinks=False)
        except OSError:
            empty = False
            res.skipped += 1
            continue
        if stat.S_ISDIR(st.st_mode):
            sub_empty = _clean_dir(Path(entry.path), cutoff, res, depth + 1)
            if sub_empty and st.st_mtime < cutoff:
                try:
                    os.rmdir(entry.path)  # only succeeds if empty
                    continue
                except OSError:
                    pass
            empty = False
        elif stat.S_ISREG(st.st_mode) and st.st_mtime < cutoff:
            try:
                os.remove(entry.path)
                res.files_deleted += 1
                res.bytes_freed += st.st_size
            except OSError:
                empty = False
                res.skipped += 1
        else:
            empty = False
    return empty


def clean_temp(
    roots: list[Path], min_age_days: float = 2, now: float | None = None
) -> CleanupResult:
    cutoff = (now if now is not None else time.time()) - min_age_days * 86400
    res = CleanupResult()
    for root in roots:
        safe = check_safe_root(root)
        res.folders.append(str(safe))
        _clean_dir(safe, cutoff, res)
    return res


def measure_temp(roots: list[Path], min_age_days: float = 2) -> int:
    """How many bytes a cleanup would free (read-only)."""
    cutoff = time.time() - min_age_days * 86400
    total = 0
    for root in roots:
        try:
            safe = check_safe_root(root)
        except UnsafeFolderError:
            continue
        stack = [safe]
        while stack:
            d = stack.pop()
            try:
                for e in os.scandir(d):
                    if _is_link(e):
                        continue
                    st = e.stat(follow_symlinks=False)
                    if stat.S_ISDIR(st.st_mode):
                        stack.append(Path(e.path))
                    elif stat.S_ISREG(st.st_mode) and st.st_mtime < cutoff:
                        total += st.st_size
            except OSError:
                continue
    return total
