"""Read-only checks against the real system. Runs only on Windows."""

import sys

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="needs Windows")


def test_full_scan_on_this_pc():
    from crashlens.core.models import CheckStatus
    from crashlens.core.platform import system_info
    from crashlens.core.runner import SubprocessRunner
    from crashlens.scanner import Scanner

    report = Scanner(SubprocessRunner(), system_info(), lookback_days=7).run()
    by_id = {r.check_id: r for r in report.results}
    errors = {r.check_id: r.message for r in report.results if r.status == CheckStatus.ERROR}
    assert not errors, errors
    # These exist on every Windows install.
    assert by_id["health.disk_space"].status in (CheckStatus.OK, CheckStatus.ISSUES)
    assert by_id["health.system"].status in (CheckStatus.OK, CheckStatus.ISSUES)
    assert "build" in by_id["health.system"].message


def test_powershell_json_roundtrip():
    from crashlens.core.runner import PsQuery, SubprocessRunner, run_ps_json

    rows = run_ps_json(SubprocessRunner(), PsQuery("t", "[pscustomobject]@{A=1;B='ä'}"))
    assert rows == [{"A": 1, "B": "ä"}]
