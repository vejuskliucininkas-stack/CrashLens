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
    assert window.scan_btn.text() == "Check my computer"
    assert not window.save_btn.isEnabled()
    assert window.windowTitle().endswith("demo")
    # Details page hidden for normal users
    assert window.nav.item(4).isHidden()


def test_scan_shows_plain_verdict_and_cards(qtbot, window):
    report = scan(qtbot, window)
    assert window.report is report
    assert window.verdict_card.isVisible()
    assert "problems to fix" in window.verdict_title.text()
    assert window.cards, "problem cards were not created"
    first = window.cards[0]
    texts = " ".join(lab.text() for lab in first.findChildren(QLabel))
    assert "blue screen" in texts and "START HERE" in texts
    assert window.small_toggle is not None and not window.small_holder.isVisible()
    window.small_toggle.click()
    assert window.small_holder.isVisibleTo(window)
    assert window.scan_btn.text() == "Check again" and window.scan_btn.isEnabled()
    assert window.save_btn.isEnabled()
    assert all(r.status != CheckStatus.ERROR for r in report.results)


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
