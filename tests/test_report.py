import json

import pytest

from crashlens.core.models import (
    Category,
    CheckResult,
    CheckStatus,
    Finding,
    ScanReport,
    Severity,
    SystemInfo,
)
from crashlens.demo import demo_runner, demo_system
from crashlens.report import Redactor, render, write_report
from crashlens.scanner import Scanner

SYS = SystemInfo(os_name="Windows 11", computer_name="PAULIUS-PC", user_name="paulius")


def _report(*findings):
    r = ScanReport(system=SYS)
    r.results.append(CheckResult("x", "X check", CheckStatus.ISSUES, list(findings), "msg"))
    return r


def test_redactor():
    red = Redactor(SYS)
    s = (
        r"Dump C:\Users\Paulius\AppData\x.dmp by paulius on PAULIUS-PC, mail a.b@ex.lt, "
        "MAC 00:1A:2B:3C:4D:5E, Serial Number: ABC123, driver 31.0.15.5222"
    )
    out = red.text(s)
    assert r"C:\Users\<user>\AppData" in out
    assert "paulius" not in out.lower()
    assert "<computer>" in out and "<email>" in out and "<mac>" in out and "<serial>" in out
    assert "31.0.15.5222" in out  # versions untouched


def test_redactor_ignores_generic_names():
    red = Redactor(SystemInfo(user_name="user", computer_name="PC"))
    assert red.text("the user opened the PC") == "the user opened the PC"


def test_redactor_partial_words_untouched():
    red = Redactor(SystemInfo(user_name="ann"))
    assert red.text("annual report by Ann") == "annual report by <user>"


def test_html_escapes_everything():
    evil = Finding(
        "x",
        "<script>alert(1)</script>",
        Severity.HIGH,
        Category.APP,
        summary="<img src=x onerror=alert(1)>",
        evidence=("\"'><b>",),
    )
    html = render(_report(evil), "html", redact=False)
    assert "<script>" not in html and "<img" not in html and "<b>" not in html
    assert "&lt;script&gt;" in html
    assert "default-src 'none'" in html


def test_markdown_escapes_and_has_sections():
    f = Finding(
        "x",
        "A | B *bold*",
        Severity.LOW,
        Category.APP,
        "line1\nline2",
        recommendations=("do [this](http://x)",),
    )
    md = render(_report(f), "md", redact=False)
    assert "A \\| B \\*bold\\*" in md
    assert "\\[this\\]" in md
    assert "## Summary" in md and "## Checks" in md


def test_json_round_trip_and_redaction():
    data = json.loads(render(_report(), "json"))
    assert data["redacted"] is True
    assert data["system"]["computer_name"] == "<computer>"
    assert data["system"]["user_name"] == "<user>"
    raw = json.loads(render(_report(), "json", redact=False))
    assert raw["system"]["computer_name"] == "PAULIUS-PC"


def test_unknown_format():
    with pytest.raises(ValueError):
        render(_report(), "pdf")


def test_write_report_refuses_overwrite(tmp_path):
    p = write_report(_report(), tmp_path / "r.html")
    assert p.read_text(encoding="utf-8").startswith("<!doctype html>")
    with pytest.raises(FileExistsError):
        write_report(_report(), p)
    write_report(_report(), p, overwrite=True)
    assert not (tmp_path / "r.html.tmp").exists()


def test_full_demo_report_all_formats(tmp_path):
    report = Scanner(demo_runner(), demo_system(), demo=True).run()
    for ext in ("html", "md", "json"):
        out = write_report(report, tmp_path / f"demo.{ext}")
        text = out.read_text(encoding="utf-8").replace("\\_", "_")  # markdown escapes
        assert "DRIVER_POWER_STATE_FAILURE" in text
        assert "DEMO-PC" not in text
