import json
import sys

import pytest

from crashlens.core.runner import (
    CommandResult,
    FakeRunner,
    PsQuery,
    QueryError,
    SubprocessRunner,
    query_id_from_argv,
    run_ps_json,
)


def test_ps_query_argv_is_list_without_shell_and_tagged():
    q = PsQuery("x.y", "Get-Date")
    argv = q.argv()
    assert argv[0] == "powershell.exe"
    assert "-NoProfile" in argv and "-NonInteractive" in argv
    assert query_id_from_argv(argv) == "x.y"
    assert "ConvertTo-Json" in argv[-1]
    # never touches the execution policy
    assert "ExecutionPolicy" not in " ".join(argv)


def test_run_ps_json_normalises_single_object_and_empty():
    r = FakeRunner(queries={"a": {"k": 1}, "b": [{"k": 1}, {"k": 2}]})
    assert run_ps_json(r, PsQuery("a", "x")) == [{"k": 1}]
    assert run_ps_json(r, PsQuery("b", "x")) == [{"k": 1}, {"k": 2}]
    assert run_ps_json(r, PsQuery("missing", "x")) == []


def test_run_ps_json_errors():
    q = PsQuery("bad", "x")
    r = FakeRunner(queries={"bad": CommandResult(("p",), 0, "{not json")})
    with pytest.raises(QueryError):
        run_ps_json(r, q)
    r = FakeRunner(queries={"bad": CommandResult(("p",), -1, "", timed_out=True)})
    with pytest.raises(QueryError, match="timed out"):
        run_ps_json(r, q)
    r = FakeRunner(queries={"bad": CommandResult(("p",), -1, "", not_found=True)})
    with pytest.raises(QueryError, match="not available"):
        run_ps_json(r, q)


def test_fake_runner_unknown_command_is_not_found():
    res = FakeRunner().run(["nothing.exe"])
    assert res.not_found and not res.ok


def test_subprocess_runner_real_process_and_timeout():
    r = SubprocessRunner()
    res = r.run([sys.executable, "-c", "print('hi')"])
    assert res.ok and res.stdout.strip() == "hi"
    res = r.run([sys.executable, "-c", "import time; time.sleep(5)"], timeout=0.5)
    assert res.timed_out and not res.ok
    res = r.run(["definitely-not-a-real-binary-xyz"])
    assert res.not_found


def test_subprocess_runner_does_not_interpret_shell_metacharacters(tmp_path):
    marker = tmp_path / "pwned"
    r = SubprocessRunner()
    res = r.run([sys.executable, "-c", "import sys; print(sys.argv[1])", f"x; touch {marker}"])
    assert res.ok
    assert not marker.exists()
    assert json.dumps(res.stdout)  # decoded as text


def test_subprocess_runner_rejects_empty():
    with pytest.raises(ValueError):
        SubprocessRunner().run([])


def test_subprocess_runner_open_off_windows():
    if sys.platform == "win32":
        pytest.skip("would really open something")
    res = SubprocessRunner().open("ms-settings:windowsupdate")
    assert res.not_found and not res.ok
