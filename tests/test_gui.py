import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QLabel  # noqa: E402

from crashlens.core.models import CheckStatus  # noqa: E402
from crashlens.core.settings import Settings  # noqa: E402
from crashlens.environment import build_environment  # noqa: E402
from crashlens.gui import style as theme  # noqa: E402
from crashlens.gui.dialogs import ConfirmRepairDialog  # noqa: E402
from crashlens.gui.main_window import (  # noqa: E402
    P_DETAILS,
    P_HELP,
    P_HOME,
    P_SETTINGS,
    P_WELCOME,
    MainWindow,
)


@pytest.fixture
def env(tmp_path):
    return build_environment(
        demo=True, audit_path=tmp_path / "audit.log", settings_path=tmp_path / "settings.json"
    )


@pytest.fixture
def window(qtbot, env):
    w = MainWindow(env, Settings(welcomed=True))
    qtbot.addWidget(w)
    w.show()
    return w


def scan(qtbot, w):
    with qtbot.waitSignal(w.scan_completed, timeout=10000) as blocker:
        w.start_scan()
    return blocker.args[0]


def test_first_start_shows_welcome_then_home(qtbot, env):
    w = MainWindow(env, Settings())
    qtbot.addWidget(w)
    assert w.stack.currentIndex() == P_WELCOME
    assert not w.sidebar.isVisibleTo(w)
    w.welcome_button.click()
    assert w.stack.currentIndex() == P_HOME
    assert Settings.load(env.settings_path).welcomed is True


def test_starts_on_home_without_report(window):
    assert window.stack.currentIndex() == P_HOME
    assert window.report is None
    assert window.scan_btn.text() == "Scan now"
    assert not window.save_btn.isEnabled()
    assert window.windowTitle().endswith("demo")
    # Details page hidden for normal users
    assert window.nav.item(4).isHidden()


def test_scan_shows_dashboard_verdict_and_cards(qtbot, window):
    report = scan(qtbot, window)
    assert window.report is report
    assert window.ring.score is not None and 0 <= window.ring.score < 85
    assert "need attention" in window.verdict_title.text()
    assert window.tiles_grid.count() >= 6  # Windows, memory, drives, updates...
    assert window.cards, "problem cards were not created"
    first = window.cards[0]
    texts = " ".join(lab.text() for lab in first.findChildren(QLabel))
    assert "blue screen" in texts and "START HERE" in texts and "Last time" in texts
    # minor issues and old problems are folded away
    assert window.minor_toggle is not None and not window.minor_holder.isVisible()
    assert window.old_toggle is not None and not window.old_holder.isVisible()
    window.old_toggle.click()
    assert window.old_holder.isVisibleTo(window)
    assert window.scan_btn.text() == "Scan again" and window.scan_btn.isEnabled()
    assert window.save_btn.isEnabled()
    assert all(r.status != CheckStatus.ERROR for r in report.results)


def test_mark_fixed_hides_until_it_happens_again(qtbot, window, env):
    scan(qtbot, window)
    fid = window.cards[0].property("finding_id")
    assert fid.startswith("bsod-")
    window.mark_fixed(fid)
    assert fid in Settings.load(env.settings_path).resolved
    active_ids = [
        c.property("finding_id") for c in window.cards if c.parent() is not window.fixed_holder
    ]
    assert fid not in active_ids
    assert window.fixed_toggle is not None
    window.unmark_fixed(fid)
    assert window.cards[0].property("finding_id") == fid


def test_fix_from_card_marks_fixed_and_rechecks(qtbot, window, monkeypatch):
    monkeypatch.setattr(
        ConfirmRepairDialog, "exec", lambda self: ConfirmRepairDialog.DialogCode.Accepted
    )
    scan(qtbot, window)
    f = next(f for f in window.report.findings if f.id == "gpu-tdr")
    with qtbot.waitSignal(window.scan_completed, timeout=10000):
        window.request_repair(f.repair_ids[0], f.id)
    assert "gpu-tdr" in window.settings.resolved
    assert window.fixed_banner.isVisibleTo(window)
    banner = window.fixed_banner.findChild(QLabel).text()
    assert "fixed" in banner and "screen" in banner


def test_theme_switch_applies_and_saves(window, env):
    app = QApplication.instance()
    window._set_theme("dark")
    assert theme.mode() == "dark"
    assert "#121418" in app.styleSheet()
    assert Settings.load(env.settings_path).theme == "dark"
    window._set_theme("light")
    assert theme.mode() == "light"
    assert Settings.load(env.settings_path).theme == "light"
    assert window.theme_choice[2]["light"].isChecked()


def test_text_size_and_lookback(window, env):
    window._set_text_size("xlarge")
    assert theme.base_pt() == theme.SIZES["xlarge"]
    window.lookback.setCurrentIndex(2)
    assert window.settings.lookback_days == 90
    saved = Settings.load(env.settings_path)
    assert saved.text_size == "xlarge" and saved.lookback_days == 90
    window._set_text_size("normal")


def test_expert_details_toggle(qtbot, window):
    scan(qtbot, window)
    window.details_box.setChecked(True)
    assert not window.nav.item(4).isHidden()
    window.go(P_DETAILS)
    assert window.problem_list.count() == len(window.report.findings)
    assert window.check_table.rowCount() == len(window.report.results)
    window.details_box.setChecked(False)
    assert window.nav.item(4).isHidden()
    assert window.stack.currentIndex() == P_SETTINGS


def test_confirm_dialog_defaults_to_no(window, qtbot):
    dlg = window.approval_dialog("sfc_scan")
    qtbot.addWidget(dlg)
    assert dlg.no_button.isDefault() and not dlg.yes_button.isDefault()
    texts = " ".join(lab.text() for lab in dlg.findChildren(QLabel))
    assert "Repair Windows files" in texts
    assert "sfc.exe /scannow" in texts  # technical details available
    assert "practice" in texts  # demo notice


def test_saying_no_runs_nothing(window, monkeypatch):
    monkeypatch.setattr(
        ConfirmRepairDialog, "exec", lambda self: ConfirmRepairDialog.DialogCode.Rejected
    )
    window.request_repair("sfc_scan")
    assert window.env.audit.read() == []
    assert not window._repair_running


def test_saying_yes_runs_simulated_fix(qtbot, window, monkeypatch):
    monkeypatch.setattr(
        ConfirmRepairDialog, "exec", lambda self: ConfirmRepairDialog.DialogCode.Accepted
    )
    with qtbot.waitSignal(window.repair_completed, timeout=5000) as blocker:
        window.request_repair("dism_restore")
    assert blocker.args[0].status == "simulated"
    assert not window.last_result.isHidden()  # shown on the Fix tools page (+ popup)
    assert window.history.rowCount() == 2  # approved + finished
    assert not window.busy.isVisibleTo(window)


def test_tell_me_more_offers_fixes(qtbot, window):
    scan(qtbot, window)
    dlg = window.finding_dialog(window.report.findings[0].id)
    qtbot.addWidget(dlg)
    assert dlg.fix_buttons
    asked = []
    dlg.fix_requested.disconnect()
    dlg.fix_requested.connect(asked.append)
    dlg.fix_buttons[0].click()
    assert asked == [window.report.findings[0].repair_ids[0]]


def test_save_and_copy_report(qtbot, window, tmp_path):
    window.go(P_HELP)
    assert window.help_needs_scan.isVisibleTo(window)
    scan(qtbot, window)
    assert not window.help_needs_scan.isVisibleTo(window)
    out = window.save_report(str(tmp_path / "report"))
    assert out.suffix == ".html" and out.exists()
    assert "DEMO-PC" not in out.read_text(encoding="utf-8")
    window.copy_summary()
    from PySide6.QtGui import QGuiApplication

    assert "CrashLens report" in QGuiApplication.clipboard().text()


def test_cancel_scan(qtbot, window):
    with qtbot.waitSignal(window.scan_completed, timeout=10000) as blocker:
        window.start_scan()
        window.cancel_scan()
    assert blocker.args[0] is window.report


def test_fix_everything_dialog_defaults_to_cancel(qtbot, window):
    from crashlens.gui.dialogs import FixAllDialog  # noqa: F401

    scan(qtbot, window)
    assert window.fix_all_btn.isVisibleTo(window)
    assert window.fix_all_btn.text().startswith("Fix everything (")
    dlg = window.fix_all_dialog()
    qtbot.addWidget(dlg)
    assert dlg.cancel_button.isDefault() and not dlg.start_button.isDefault()
    assert dlg.selected_ids() == window.plan.repair_ids
    dlg.boxes["clean_temp"].setChecked(False)
    assert "clean_temp" not in dlg.selected_ids()
    for box in dlg.boxes.values():
        box.setChecked(False)
    assert not dlg.start_button.isEnabled()
    texts = " ".join(lab.text() for lab in dlg.findChildren(QLabel))
    assert "do these yourself" in texts and "restart" in texts.lower()


def test_fix_everything_cancel_runs_nothing(qtbot, window, monkeypatch):
    from crashlens.gui.dialogs import FixAllDialog

    scan(qtbot, window)
    monkeypatch.setattr(FixAllDialog, "exec", lambda self: FixAllDialog.DialogCode.Rejected)
    window.fix_everything()
    assert window.env.audit.read() == []


def test_fix_everything_runs_marks_fixed_and_rechecks(qtbot, window, monkeypatch):
    from crashlens.gui.dialogs import FixAllDialog

    scan(qtbot, window)
    monkeypatch.setattr(FixAllDialog, "exec", lambda self: FixAllDialog.DialogCode.Accepted)
    expected = list(window.plan.repair_ids)
    with qtbot.waitSignal(window.scan_completed, timeout=15000):
        window.fix_everything()
    finished = [e["repair_id"] for e in window.env.audit.read() if e["event"] == "repair.finished"]
    assert finished == expected
    # event problems fixed by these fixes are marked (gpu-tdr via 'check for updates')
    assert "gpu-tdr" in window.settings.resolved
    assert window.fixed_banner.isVisibleTo(window)
    assert "fixed" in window.fixed_banner.findChild(QLabel).text()
    assert not window._repair_running
