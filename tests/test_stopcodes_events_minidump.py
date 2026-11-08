import struct
from datetime import timezone

from crashlens.checks import events as ev
from crashlens.checks import minidump
from crashlens.checks.stopcodes import STOP_CODES, describe, format_code, parse_code
from crashlens.repairs.catalog import REPAIRS


def test_parse_code_variants():
    assert parse_code("0x0000009f") == 0x9F
    assert parse_code("159") == 0x9F  # Kernel-Power 41 stores decimal
    assert parse_code("9f") == 0x9F
    assert parse_code("") is None
    assert parse_code(None) is None
    assert parse_code("zz") is None
    assert format_code(0x124) == "0x00000124"


def test_knowledge_base_is_consistent():
    assert len(STOP_CODES) >= 30
    for code, sc in STOP_CODES.items():
        assert sc.code == code
        assert sc.meaning and sc.steps
        for rid in sc.repairs:
            assert rid in REPAIRS, f"{sc.name} references unknown repair {rid}"


def test_describe_unknown_code_has_fallback():
    sc = describe(0xDEAD)
    assert sc.name == "UNKNOWN_STOP_CODE"
    assert "0x0000DEAD" in sc.steps[0]


def test_parse_time_formats():
    t = ev.parse_time("2026-11-01T10:20:30.1234567Z")
    assert t and t.tzinfo == timezone.utc and t.microsecond == 123456
    t2 = ev.parse_time("2026-11-01T12:20:30+02:00")
    assert t2.hour == 10
    assert ev.parse_time("/Date(1700000000000)/").year == 2023
    assert ev.parse_time("garbage") is None
    assert ev.parse_time(None) is None


def test_to_record_handles_odd_shapes():
    r = ev.to_record({"Id": "41", "Provider": None, "Data": "5", "Level": None})
    assert r.id == 41 and r.data == ("5",) and r.provider == "" and r.level == 0
    assert ev.to_record({"Id": "x"}) is None
    assert r.datum(9, "d") == "d"


def test_queries_are_fixed_and_bounded():
    q = ev.system_crash_query(30)
    script = q.argv()[-1]
    assert "-MaxEvents 300" in script
    assert "AddDays(-30)" in script
    assert "Remove-" not in script and "Set-" not in script


def _dump64(code, params):
    data = bytearray(0x80)
    data[0:8] = b"PAGEDU64"
    struct.pack_into("<I", data, 0x38, code)
    struct.pack_into("<4Q", data, 0x40, *params)
    return bytes(data)


def test_minidump_header_64_and_32_and_user():
    kind, code, params = minidump.parse_header(_dump64(0x9F, (3, 0xFFFF, 0xAA, 0xBB)))
    assert kind == "kernel64" and code == 0x9F and params == (3, 0xFFFF, 0xAA, 0xBB)
    d32 = bytearray(0x40)
    d32[0:8] = b"PAGEDUMP"
    struct.pack_into("<I", d32, 0x20, 0x50)
    struct.pack_into("<4I", d32, 0x24, 1, 2, 3, 4)
    assert minidump.parse_header(bytes(d32)) == ("kernel32", 0x50, (1, 2, 3, 4))
    assert minidump.parse_header(b"MDMP" + b"\0" * 60)[0] == "user"
    assert minidump.parse_header(b"junk")[0] == "unknown"
    assert minidump.parse_header(b"")[0] == "unknown"


def test_minidump_scan_dir(tmp_path):
    (tmp_path / "110826-1.dmp").write_bytes(_dump64(0x124, (0, 1, 2, 3)))
    (tmp_path / "notes.txt").write_text("x")
    dumps, note = minidump.scan_dir(tmp_path)
    assert len(dumps) == 1 and dumps[0].bugcheck == 0x124 and note == ""
    assert minidump.scan_dir(tmp_path / "missing")[0] == []
    assert minidump.scan_dir(None) == ([], "")
