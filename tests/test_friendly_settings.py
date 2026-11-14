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


def test_triage_recent_old_fixed_and_score():
    from datetime import datetime, timedelta, timezone

    from crashlens.triage import ago, score_label, triage

    now = datetime(2026, 11, 12, 12, 0, tzinfo=timezone.utc)

    def ev(fid, days, sev=Severity.HIGH):
        return Finding(fid, fid, sev, Category.CRASH, "s", last_seen=now - timedelta(days=days))

    recent = ev("bsod-9f", 1)
    old = ev("unexpected-restart", 20)
    fixed = ev("gpu-tdr", 3, Severity.MEDIUM)
    came_back = ev("app-crash-x", 0.5, Severity.LOW)
    state = Finding("disk-space-c", "full", Severity.HIGH, Category.STORAGE, "s")
    resolved = {
        "gpu-tdr": (now - timedelta(days=1)).isoformat(),  # last seen before -> fixed
        "app-crash-x": (now - timedelta(days=2)).isoformat(),  # happened again after
        "disk-space-c": now.isoformat(),  # state findings can't be hidden
    }
    t = triage([recent, old, fixed, came_back, state], resolved, now)
    assert {f.id for f in t.active} == {"bsod-9f", "app-crash-x", "disk-space-c"}
    assert [f.id for f in t.old] == ["unexpected-restart"]
    assert [f.id for f in t.fixed] == ["gpu-tdr"]
    assert t.score == round(100 * 0.82 * 0.98 * 0.82)
    assert score_label(t.score) == "Fair" and score_label(90) == "Good"
    assert score_label(10) == "Poor"
    assert ago(now - timedelta(days=3), now) == "3 days ago"
    assert ago(now - timedelta(hours=2), now) == "2 hours ago"


def test_settings_resolved_is_cleaned(tmp_path):
    p = tmp_path / "s.json"
    p.write_text(json.dumps({"resolved": {"bsod-9f": "2026-11-01T00:00:00+00:00", "x": ""}}))
    assert Settings.load(p).resolved == {"bsod-9f": "2026-11-01T00:00:00+00:00"}
    p.write_text(json.dumps({"resolved": ["not", "a", "dict"]}))
    assert Settings.load(p).resolved == {}


def test_fix_plan_picks_real_fixes_and_restore_point_first():
    from crashlens.fixplan import build_plan
    from crashlens.repairs.catalog import RepairKind
    from crashlens.triage import triage

    report = Scanner(demo_runner(), demo_system(), demo=True).run()
    plan = build_plan(triage(report.findings))
    ids = plan.repair_ids
    assert ids[0] == "restore_point"
    assert "clean_temp" in ids and "reset_windows_update" in ids
    assert len(ids) == len(set(ids))  # merged duplicates
    for rid in ids:
        assert REPAIRS[rid].kind is not RepairKind.OPEN
        assert rid != "memory_diagnostic"
    assert any(f.id == "reboot-pending" for f in plan.manual)


def test_fix_plan_empty_when_healthy():
    from crashlens.fixplan import build_plan
    from crashlens.triage import triage

    plan = build_plan(triage([F("reboot-pending", sev=Severity.MEDIUM)]))
    assert not plan and [f.id for f in plan.manual] == ["reboot-pending"]
