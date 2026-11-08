import json
from datetime import datetime, timedelta, timezone

import pytest

from crashlens.core.runner import CommandResult, FakeRunner, _decode
from crashlens.repairs.catalog import REPAIRS, RepairKind, get
from crashlens.repairs.executor import (
    ApprovalError,
    ApprovalRegistry,
    AuditLog,
    NotSupportedError,
    RepairExecutor,
    elevated_argv,
    interpret,
)

# Commands/flags that must never appear in a CrashLens repair.
FORBIDDEN_WORDS = [
    "erase",
    "rmdir",
    "format",
    "remove-item",
    "clear-",
    "diskpart",
    "set-mppreference",
    "disable",
    "bcdedit",
    "netsh",
    "vssadmin",
    "cleanmgr",
    "resetbase",
    "startcomponentcleanup",
    "shutdown",
    "restart-computer",
    "uninstall",
    "cipher",
    "takeown",
    "icacls",
]
FORBIDDEN_TOKENS = {"del", "rd", "reg", "/f", "/r", "/x", "/b", "/spotfix", "/offlinescanandfix"}


def make_executor(runner=None, *, windows=True, admin=True, dry=False, tmp_path=None):
    return RepairExecutor(
        runner or FakeRunner(),
        ApprovalRegistry(),
        AuditLog(tmp_path / "audit.log" if tmp_path else None),
        is_windows=windows,
        is_admin=admin,
        dry_run=dry,
    )


# --------------------------------------------------------------------------- catalog safety


@pytest.mark.parametrize("repair", list(REPAIRS.values()), ids=list(REPAIRS))
def test_catalog_commands_are_safe(repair):
    joined = " ".join(repair.argv).lower()
    for bad in FORBIDDEN_WORDS:
        assert bad not in joined, f"{repair.id} contains forbidden '{bad}'"
    tokens = set(joined.split())
    assert not tokens & FORBIDDEN_TOKENS, f"{repair.id} uses {tokens & FORBIDDEN_TOKENS}"
    assert "'" not in joined  # required by elevated_argv quoting
    assert repair.what_happens and repair.title
    if repair.kind is RepairKind.OPEN:
        assert not repair.changes_system


def test_catalog_lookup():
    assert get("sfc_scan").argv == ("sfc.exe", "/scannow")
    with pytest.raises(KeyError):
        get("format_c")


# --------------------------------------------------------------------------- approvals


def test_repair_without_approval_is_refused(tmp_path):
    runner = FakeRunner()
    ex = make_executor(runner, tmp_path=tmp_path)
    with pytest.raises(ApprovalError):
        ex.execute("sfc_scan", None)
    assert runner.calls == []


def test_approval_is_single_use_and_specific(tmp_path):
    runner = FakeRunner(commands={"sfc.exe": CommandResult(("sfc.exe",), 0, "ok")})
    ex = make_executor(runner, tmp_path=tmp_path)
    a = ex.approvals.grant("sfc_scan", "test")
    ex.execute("sfc_scan", a)
    with pytest.raises(ApprovalError, match="already used"):
        ex.execute("sfc_scan", a)
    b = ex.approvals.grant("dism_check", "test")
    with pytest.raises(ApprovalError, match="different repair"):
        ex.execute("sfc_scan", b)
    assert len(runner.calls) == 1


def test_forged_and_expired_approvals_rejected():
    reg = ApprovalRegistry(ttl=timedelta(minutes=10))
    from crashlens.repairs.executor import Approval

    forged = Approval("sfc_scan", "0" * 32, datetime.now(timezone.utc), "x")
    with pytest.raises(ApprovalError):
        reg.consume(forged, "sfc_scan")
    old = reg.grant("sfc_scan", "x", now=datetime.now(timezone.utc) - timedelta(minutes=11))
    with pytest.raises(ApprovalError, match="expired"):
        reg.consume(old, "sfc_scan")
    with pytest.raises(KeyError):
        reg.grant("not_a_repair", "x")


# --------------------------------------------------------------------------- execution


def test_runs_tool_and_interprets_sfc_output(tmp_path):
    out = "Windows Resource Protection did not find any integrity violations."
    runner = FakeRunner(commands={"sfc.exe": CommandResult(("sfc.exe",), 0, out)})
    ex = make_executor(runner, tmp_path=tmp_path)
    res = ex.execute("sfc_scan", ex.approvals.grant("sfc_scan", "gui"))
    assert res.status == "success" and "No damaged" in res.message
    assert runner.calls == [("sfc.exe", "/scannow")]
    log = [json.loads(line) for line in (tmp_path / "audit.log").read_text().splitlines()]
    assert [e["event"] for e in log] == ["repair.approved", "repair.finished"]
    assert log[0]["approved_by"] == "gui" and log[1]["status"] == "success"
    assert len(log[0]["approval"]) == 8  # only a prefix of the token is logged


def test_non_admin_uses_uac_window(tmp_path):
    runner = FakeRunner(commands={"powershell.exe": CommandResult(("p",), 0, "")})
    ex = make_executor(runner, admin=False, tmp_path=tmp_path)
    res = ex.execute("sfc_scan", ex.approvals.grant("sfc_scan", "gui"))
    assert res.status == "launched" and res.elevated_window
    script = runner.calls[0][-1]
    assert "-Verb RunAs" in script and "'/k sfc.exe /scannow'" in script


def test_uac_declined_is_cancelled(tmp_path):
    runner = FakeRunner(commands={"powershell.exe": CommandResult(("p",), 1223, "")})
    ex = make_executor(runner, admin=False, tmp_path=tmp_path)
    res = ex.execute("dism_check", ex.approvals.grant("dism_check", "gui"))
    assert res.status == "cancelled"


def test_open_kind_uses_shell_open(tmp_path):
    runner = FakeRunner()
    ex = make_executor(runner, admin=False, tmp_path=tmp_path)
    res = ex.execute("open_windows_update", ex.approvals.grant("open_windows_update", "gui"))
    assert res.status == "launched"
    assert runner.calls == [("open", "ms-settings:windowsupdate")]
    res = ex.execute(
        "open_reliability_monitor", ex.approvals.grant("open_reliability_monitor", "x")
    )
    assert runner.calls[-1] == ("open", "perfmon.exe", "/rel")


def test_open_kind_uac_cancel_and_failure(tmp_path):
    runner = FakeRunner(commands={"open": CommandResult(("mdsched.exe",), 1223, "", "cancelled")})
    ex = make_executor(runner, admin=False, tmp_path=tmp_path)
    res = ex.execute("memory_diagnostic", ex.approvals.grant("memory_diagnostic", "gui"))
    assert res.status == "cancelled"
    runner.commands["open"] = CommandResult(("x",), 2, "", "not found", not_found=True)
    res = ex.execute("open_device_manager", ex.approvals.grant("open_device_manager", "gui"))
    assert res.status == "failed" and "not found" in res.message


def test_dry_run_never_executes(tmp_path):
    runner = FakeRunner()
    ex = make_executor(runner, dry=True, windows=False, tmp_path=tmp_path)
    res = ex.execute("dism_restore", ex.approvals.grant("dism_restore", "cli"))
    assert res.status == "simulated" and runner.calls == []


def test_refuses_off_windows(tmp_path):
    ex = make_executor(windows=False, tmp_path=tmp_path)
    with pytest.raises(NotSupportedError):
        ex.execute("sfc_scan", ex.approvals.grant("sfc_scan", "cli"))


def test_timeout_and_missing_tool(tmp_path):
    runner = FakeRunner(
        commands={"sfc.exe": CommandResult(("sfc.exe",), -1, "partial", timed_out=True)}
    )
    ex = make_executor(runner, tmp_path=tmp_path)
    assert ex.execute("sfc_scan", ex.approvals.grant("sfc_scan", "x")).status == "failed"
    ex = make_executor(FakeRunner(), tmp_path=tmp_path)
    res = ex.execute("chkdsk_scan", ex.approvals.grant("chkdsk_scan", "x"))
    assert res.status == "failed" and "not found" in res.message


def test_elevated_argv_rejects_quotes():
    from dataclasses import replace

    bad = replace(REPAIRS["sfc_scan"], argv=("sfc.exe", "x'; Remove-Item C:\\ '"))
    with pytest.raises(ValueError):
        elevated_argv(bad)


@pytest.mark.parametrize(
    "rid,text,status,follow",
    [
        ("sfc_scan", "found corrupt files and successfully repaired them", "success", True),
        ("sfc_scan", "found corrupt files but was unable to fix some of them", "failed", True),
        ("dism_scan", "The component store is repairable.", "success", True),
        ("dism_restore", "The restore operation completed successfully.", "success", True),
        ("dism_check", "No component store corruption detected.", "success", False),
        (
            "chkdsk_scan",
            "Windows has scanned the file system and found no problems.",
            "success",
            False,
        ),
        ("chkdsk_scan", "Windows has scanned the file system and found problems.", "failed", True),
        ("restore_point", "", "success", False),
    ],
)
def test_interpret(rid, text, status, follow):
    res = interpret(REPAIRS[rid], 0, text)
    assert res.status == status
    assert bool(res.follow_up) == follow


def test_utf16_output_decoded():
    raw = "Verification 100% complete.".encode("utf-16-le")
    assert _decode(raw) == "Verification 100% complete."


def test_audit_log_read_skips_garbage(tmp_path):
    log = AuditLog(tmp_path / "a.log")
    log.write("x", a=1)
    (tmp_path / "a.log").open("a").write("not json\n")
    log.write("y")
    assert [e["event"] for e in log.read()] == ["x", "y"]
    assert AuditLog(None).read() == []
