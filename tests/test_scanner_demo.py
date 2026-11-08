import pytest

from crashlens.checks.base import Check
from crashlens.core.models import CheckStatus, Severity, SystemInfo
from crashlens.core.runner import FakeRunner
from crashlens.demo import demo_runner, demo_system
from crashlens.repairs.catalog import REPAIRS
from crashlens.scanner import Scanner, default_checks


def test_demo_scan_produces_rich_report():
    report = Scanner(demo_runner(), demo_system(), demo=True).run()
    statuses = {r.check_id: r.status for r in report.results}
    assert all(s != CheckStatus.ERROR for s in statuses.values()), statuses
    ids = {f.id for f in report.findings}
    for expected in (
        "bsod-9f",
        "bsod-d1",
        "unexpected-restart",
        "gpu-tdr",
        "reliability-index",
        "disk-space-c",
        "reboot-pending",
        "updates-old",
        "startup-many",
    ):
        assert expected in ids
    counts = report.counts()
    assert counts[Severity.HIGH] >= 2
    # findings sorted most severe first
    sev = [int(f.severity) for f in report.findings]
    assert sev == sorted(sev, reverse=True)
    for rid in report.recommended_repairs():
        assert rid in REPAIRS
    data = report.to_dict()
    assert data["demo"] is True and data["summary"]["HIGH"] == counts[Severity.HIGH]


def test_scan_off_windows_marks_checks_unavailable():
    sysinfo = SystemInfo(is_windows=False)
    report = Scanner(FakeRunner(), sysinfo).run()
    assert {r.status for r in report.results} == {CheckStatus.UNAVAILABLE}


def test_progress_and_cancel():
    seen = []
    calls = {"n": 0}

    def cancelled():
        calls["n"] += 1
        return calls["n"] > 2

    report = Scanner(demo_runner(), demo_system(), demo=True).run(
        progress=lambda i, t, name: seen.append((i, t, name)), cancelled=cancelled
    )
    assert seen[-1][2] == "Done"
    assert sum(r.message == "Cancelled." for r in report.results) == len(default_checks()) - 2


def test_one_exploding_check_does_not_break_scan():
    class Boom(Check):
        id = "x.boom"
        name = "Boom"
        windows_only = False

        def collect(self, ctx):
            raise ZeroDivisionError("bad")

    report = Scanner(FakeRunner(), SystemInfo(is_windows=True), checks=[Boom()]).run()
    [r] = report.results
    assert r.status == CheckStatus.ERROR and "ZeroDivisionError" in r.message


def test_lookback_validated():
    with pytest.raises(ValueError):
        Scanner(FakeRunner(), SystemInfo(), lookback_days=0)
