"""Read the header of Windows kernel crash dumps (C:\\Windows\\Minidump\\*.dmp).

Only the fixed-size header is read (a few hundred bytes), so this is fast and
never loads a large dump into memory. Files are opened read-only.

64-bit kernel dump header layout (DUMP_HEADER64):
    0x00  'PAGE'            signature
    0x04  'DU64'            valid dump
    0x38  uint32            bug check code
    0x40  uint64 x 4        bug check parameters 1-4
32-bit kernel dumps use 'PAGE' + 'DUMP' with the code at 0x20 and four
uint32 parameters at 0x24.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

HEADER_BYTES = 0x80
MAX_FILES = 50


@dataclass(frozen=True)
class DumpInfo:
    path: Path
    kind: str  # "kernel64", "kernel32", "user", "unknown"
    bugcheck: int | None
    params: tuple[int, ...]
    modified: datetime | None
    size: int


def parse_header(data: bytes) -> tuple[str, int | None, tuple[int, ...]]:
    if len(data) >= 0x60 and data[0:4] == b"PAGE" and data[4:8] == b"DU64":
        code = struct.unpack_from("<I", data, 0x38)[0]
        params = struct.unpack_from("<4Q", data, 0x40)
        return "kernel64", code, tuple(params)
    if len(data) >= 0x34 and data[0:4] == b"PAGE" and data[4:8] == b"DUMP":
        code = struct.unpack_from("<I", data, 0x20)[0]
        params = struct.unpack_from("<4I", data, 0x24)
        return "kernel32", code, tuple(params)
    if data[0:4] == b"MDMP":
        return "user", None, ()
    return "unknown", None, ()


def read_dump(path: Path) -> DumpInfo:
    with path.open("rb") as fh:  # read-only
        head = fh.read(HEADER_BYTES)
    kind, code, params = parse_header(head)
    st = path.stat()
    return DumpInfo(
        path=path,
        kind=kind,
        bugcheck=code,
        params=params,
        modified=datetime.fromtimestamp(st.st_mtime, tz=timezone.utc),
        size=st.st_size,
    )


def scan_dir(folder: Path | None) -> tuple[list[DumpInfo], str]:
    """Return (dumps newest first, note). Never raises for missing/denied folders."""
    if folder is None:
        return [], ""
    try:
        if not folder.is_dir():
            return [], f"No crash dump folder at {folder}."
        files = sorted(
            (p for p in folder.iterdir() if p.suffix.lower() == ".dmp" and p.is_file()),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )[:MAX_FILES]
    except PermissionError:
        return [], "Crash dumps need administrator rights to read (run CrashLens as administrator)."
    except OSError as exc:
        return [], f"Could not list crash dumps: {exc}"
    dumps: list[DumpInfo] = []
    denied = 0
    for f in files:
        try:
            dumps.append(read_dump(f))
        except PermissionError:
            denied += 1
        except OSError:
            continue
    note = ""
    if denied:
        note = f"{denied} dump file(s) need administrator rights to read."
    return dumps, note
