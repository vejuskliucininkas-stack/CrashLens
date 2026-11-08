import io
import json

from crashlens.cli import main
from crashlens.core.models import SystemInfo
from crashlens.core.runner import CommandResult, FakeRunner
from crashlens.environment import Environment, build_environment
from crashlens.repairs.executor import ApprovalRegistry, AuditLog, RepairExecutor


def run(argv, answer="", env=None):
    out = io.StringIO()
    code = main(argv, out=out, ask=lambda _prompt: answer, env=env)
    return code, out.getvalue()


def windows_env(tmp_path, runner):
    system = SystemInfo(os_name="Windows 11", is_windows=True, is_admin=True)
    audit = AuditLog(tmp_path / "audit.log")
    ex = RepairExecutor(runner, ApprovalRegistry(), audit, is_windows=True, is_admin=True)
    return Environment(runner, system, False, ex, audit)


def test_scan_demo_text():
    code, out = run(["--demo", "scan"])
    assert code == 0
    assert "DEMO DATA" in out
    assert "DRIVER_POWER_STATE_FAILURE" in out
    assert "crashlens repair sfc_scan" in out or "crashlens repair open_device_manager" in out


def test_scan_demo_json_redacted():
    code, out = run(["--demo", "scan", "--json"])
    data = json.loads(out)
    assert code == 0 and data["redacted"] and data["system"]["computer_name"] == "<computer>"


def test_scan_rejects_bad_days():
    assert run(["--demo", "scan", "--days", "0"])[0] == 2


def test_report_and_overwrite_protection(tmp_path):
    target = tmp_path / "r.html"
    code, out = run(["--demo", "report", str(target)])
    assert code == 0 and target.exists()
    env = build_environment(demo=True, audit_path=tmp_path / "a.log")
    calls_before = len(env.runner.calls)
    code, out = run(["--demo", "report", str(target)], env=env)
    assert code == 1 and "already exists" in out
    assert len(env.runner.calls) == calls_before  # refused before scanning
    assert run(["--demo", "report", str(tmp_path / "r.pdf")])[0] == 2


def test_repairs_list():
    code, out = run(["repairs"])
    assert code == 0 and "sfc_scan" in out and "admin" in out


def test_repair_cancelled_without_exact_word(tmp_path):
    runner = FakeRunner(commands={"sfc.exe": CommandResult(("sfc.exe",), 0, "")})
    env = windows_env(tmp_path, runner)
    for answer in ("", "yes", "run", "RUN please"):
        code, out = run(["repair", "sfc_scan"], answer=answer, env=env)
        assert code == 1 and "Nothing was run" in out
    assert runner.calls == []


def test_repair_runs_after_approval(tmp_path):
    msg = "Windows Resource Protection did not find any integrity violations."
    runner = FakeRunner(commands={"sfc.exe": CommandResult(("sfc.exe",), 0, msg)})
    env = windows_env(tmp_path, runner)
    code, out = run(["repair", "sfc_scan"], answer="RUN", env=env)
    assert code == 0 and "SUCCESS" in out and runner.calls == [("sfc.exe", "/scannow")]
    code, out = run(["audit"], env=env)
    assert "repair.finished" in out and "sfc_scan" in out


def test_repair_dry_run(tmp_path):
    runner = FakeRunner()
    env = windows_env(tmp_path, runner)
    code, out = run(["repair", "dism_restore", "--dry-run"], answer="RUN", env=env)
    assert code == 0 and "SIMULATED" in out and runner.calls == []


def test_demo_repair_is_always_simulated(tmp_path):
    env = build_environment(demo=True, audit_path=tmp_path / "a.log")
    code, out = run(["repair", "sfc_scan"], answer="RUN", env=env)
    assert code == 0 and "SIMULATED" in out


def test_audit_empty(tmp_path):
    env = windows_env(tmp_path, FakeRunner())
    assert "No repairs" in run(["audit"], env=env)[1]
