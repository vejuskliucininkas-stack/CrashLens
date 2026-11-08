import pytest

pytest.importorskip("PySide6")

from crashlens.core.models import CheckStatus  # noqa: E402
from crashlens.environment import build_environment  # noqa: E402
from crashlens.gui.dialogs import ApprovalDialog  # noqa: E402
from crashlens.gui.main_window import PAGES, MainWindow  # noqa: E402
from crashlens.repairs.catalog import REPAIRS  # noqa: E402


@pytest.fixture
def window(qtbot, tmp_path):
    env = build_environment(demo=True, audit_path=tmp_path / "audit.log")
    w = MainWindow(env)
    qtbot.addWidget(w)
    w.show()
    return w


def scan(qtbot, w):
    with qtbot.waitSignal(w.scan_completed, timeout=10000) as blocker:
        w.start_scan()
    return blocker.args[0]


def test_starts_without_report(window):
    assert window.report is None
    assert not window.save_btn.isEnabled()
    assert window.windowTitle().endswith("demo")
    assert window.repair_list.count() == len(REPAIRS)


def test_scan_fills_every_page(qtbot, window):
    report = scan(qtbot, window)
    assert window.report is report
    assert window.top_list.count() == 6
    assert window.problem_list.count() == len(report.findings)
    assert "Blue screen" in window.problem_view.toPlainText()
    assert window.check_table.rowCount() == len(report.results)
    assert window.save_btn.isEnabled()
    assert window.repair_list.item(0).text().startswith("Suggested - ")
    assert window.scan_btn.text() == "Scan again" and window.scan_btn.isEnabled()
    assert all(r.status != CheckStatus.ERROR for r in report.results)


def test_filters(qtbot, window):
    scan(qtbot, window)
    total = window.problem_list.count()
    window.filter.setCurrentIndex(1)
    crashes = window.problem_list.count()
    window.filter.setCurrentIndex(2)
    health = window.problem_list.count()
    assert crashes + health == total and crashes and health
    window.filter.setCurrentIndex(0)
    window.hide_info.setChecked(True)
    assert window.problem_list.count() < total


def test_open_top_item_navigates(qtbot, window):
    scan(qtbot, window)
    item = window.top_list.item(0)
    window._open_top_item(item)
    assert window.stack.currentIndex() == PAGES.index("Problems")
    assert window.problem_list.currentItem().text() == item.text()


def test_approval_dialog_requires_tick(window, qtbot):
    dlg = window.approval_dialog("sfc_scan")
    qtbot.addWidget(dlg)
    assert not dlg.run_button.isEnabled()
    dlg._accept_if_confirmed()
    assert dlg.result() != ApprovalDialog.DialogCode.Accepted
    dlg.confirm.setChecked(True)
    assert dlg.run_button.isEnabled()
    from PySide6.QtWidgets import QLabel

    texts = " ".join(lab.text() for lab in dlg.findChildren(QLabel))
    assert "sfc.exe /scannow" in texts and "Nothing will actually run" in texts


def test_rejected_dialog_runs_nothing(window, monkeypatch):
    monkeypatch.setattr(ApprovalDialog, "exec", lambda self: ApprovalDialog.DialogCode.Rejected)
    window.request_repair("sfc_scan")
    assert window.env.audit.read() == []
    assert not window._repair_running


def test_accepted_repair_runs_simulated(qtbot, window, monkeypatch):
    monkeypatch.setattr(ApprovalDialog, "exec", lambda self: ApprovalDialog.DialogCode.Accepted)
    with qtbot.waitSignal(window.repair_completed, timeout=5000) as blocker:
        window.request_repair("dism_restore")
    outcome = blocker.args[0]
    assert outcome.status == "simulated"
    assert "SIMULATED" in window.repair_output.toPlainText()
    assert window.history.rowCount() == 2  # approved + finished
    assert window.stack.currentIndex() == PAGES.index("Repairs")


def test_save_and_copy_report(qtbot, window, tmp_path):
    scan(qtbot, window)
    out = window.save_report(str(tmp_path / "report"))
    assert out.suffix == ".html" and out.exists()
    assert "DEMO-PC" not in out.read_text(encoding="utf-8")
    window.fmt_group.button(1).setChecked(True)
    out_md = window.save_report(str(tmp_path / "report.md"))
    assert out_md.read_text(encoding="utf-8").startswith("# CrashLens report")
    window.copy_summary()
    from PySide6.QtGui import QGuiApplication

    assert "CrashLens report" in QGuiApplication.clipboard().text()


def test_cancel_scan(qtbot, window):
    with qtbot.waitSignal(window.scan_completed, timeout=10000) as blocker:
        window.start_scan()
        window.cancel_scan()
    # Either finished before the cancel landed, or later checks were skipped.
    assert blocker.args[0] is window.report
