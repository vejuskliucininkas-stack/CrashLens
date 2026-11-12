import json

from crashlens.core.models import Category, Finding, Severity
from crashlens.core.settings import Settings
from crashlens.demo import demo_runner, demo_system
from crashlens.gui import friendly
from crashlens.repairs.catalog import REPAIRS
from crashlens.scanner import Scanner


def F(fid, title="t", sev=Severity.MEDIUM, n=1):
    return Finding(fid, title, sev, Category.SYSTEM, "summary", occurrences=n)


def test_every_repair_has_plain_words():
    for rid in REPAIRS:
        name, text = friendly.REPAIR_WORDS[rid]
        assert name and text


def test_headlines_are_plain():
    assert (
        friendly.headline(F("bsod-9f", n=3)) == "Your computer crashed with a blue screen 3 times"
    )
    assert friendly.headline(F("app-crash-game.exe-x", "Game.exe crashed 5 times", n=5)) == (
        "The program “Game” closed by itself 5 times"
    )
    assert friendly.headline(F("disk-space-c")) == "Your main drive (C:) is almost full"
    assert friendly.headline(F("disk-space-d")) == "Drive D: is almost full"
    assert "3.6 out of 10" in friendly.headline(
        F("reliability-index", "Reliability index: 3.6 / 10")
    )
    assert friendly.headline(F("unknown-x", "Raw title")) == "Raw title"


def test_no_jargon_in_demo_headlines():
    report = Scanner(demo_runner(), demo_system(), demo=True).run()
    for f in report.findings:
        text = friendly.headline(f) + " " + friendly.explanation(f)
        for jargon in ("0x", "BSOD", "WHEA", "TDR", "IRQL", "Kernel", "HRESULT"):
            assert jargon not in text, (f.id, text)


def test_verdict():
    assert friendly.verdict([])[0] == "ok"
    assert friendly.verdict([F("a", sev=Severity.LOW)])[1] == "Your computer is mostly fine"
    mood, title, sub = friendly.verdict([F("a", sev=Severity.HIGH), F("b", sev=Severity.LOW)])
    assert mood == "bad" and title == "We found 1 problem to fix" and "1 small thing" in sub


def test_settings_roundtrip_and_bad_files(tmp_path):
    p = tmp_path / "s.json"
    assert Settings.load(p) == Settings()
    Settings(theme="dark", text_size="large", lookback_days=90, show_details=True).save(p)
    s = Settings.load(p)
    assert (s.theme, s.text_size, s.lookback_days, s.show_details) == ("dark", "large", 90, True)
    p.write_text("{broken")
    assert Settings.load(p) == Settings()
    p.write_text(json.dumps({"theme": "purple", "lookback_days": 5, "extra": 1}))
    s = Settings.load(p)
    assert s.theme == "system" and s.lookback_days == 30
    assert Settings().save(None) is False
