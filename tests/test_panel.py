"""panel.py の単体テスト（本物のPySide6ウィジェット + pytest-qtのqtbotで検証）。

`QT_QPA_PLATFORM=offscreen`（tests/conftest.py）によりヘッドレス環境で実ウィジェットを
生成・操作する。houは一切importしないため、Houdiniなしで完全に検証できる。
"""

from __future__ import annotations

from PySide6.QtCore import Qt

from scene_doctor.report import SceneReport, Severity, Violation
from scene_doctor.ui.panel import SceneDoctorPanel


def _sample_report(hip_path: str = "/tmp/bad_scene_01.hip") -> SceneReport:
    return SceneReport(
        hip_path=hip_path,
        generated_at="2026-09-07T00:00:00Z",
        violations=[
            Violation(
                check_type="nonmanifold",
                target_path="/obj/geo1/box1",
                message="edge (1, 2) is shared by 3 face(s) (expected 2)",
                severity=Severity.ERROR,
            ),
            Violation(
                check_type="naming",
                target_path="/obj/geo1/box2",
                message="'box2' does not match naming rule",
                severity=Severity.WARNING,
                rename_candidate="geo_002",
            ),
        ],
    )


def _make_panel(qtbot, run_checks=None, select_node=None, export=None) -> SceneDoctorPanel:
    panel = SceneDoctorPanel(
        run_checks_callback=run_checks or (lambda: _sample_report()),
        select_node_callback=select_node or (lambda path: None),
        export_callback=export or (lambda fmt, path: None),
    )
    qtbot.addWidget(panel)
    panel.show()
    return panel


class TestSceneDoctorPanelConstruction:
    def test_panel_constructs_with_empty_tree(self, qtbot) -> None:
        panel = _make_panel(qtbot)
        assert panel.tree.topLevelItemCount() == 0

    def test_panel_status_bar_shows_zero_violations_initially(self, qtbot) -> None:
        panel = _make_panel(qtbot)
        assert "0" in panel.status_label.text()


class TestRunChecksButton:
    def test_run_checks_button_invokes_callback(self, qtbot) -> None:
        calls: list[bool] = []

        def run_checks() -> SceneReport:
            calls.append(True)
            return _sample_report()

        panel = _make_panel(qtbot, run_checks=run_checks)
        qtbot.mouseClick(panel.run_checks_button, Qt.MouseButton.LeftButton)

        assert calls == [True]

    def test_run_checks_button_populates_tree(self, qtbot) -> None:
        panel = _make_panel(qtbot)
        panel.run_checks_button.click()

        assert panel.tree.topLevelItemCount() == 2

    def test_run_checks_button_updates_status_label(self, qtbot) -> None:
        panel = _make_panel(qtbot)
        panel.run_checks_button.click()

        assert "2" in panel.status_label.text()

    def test_run_checks_rebuilds_tree_clearing_previous_rows(self, qtbot) -> None:
        reports = [_sample_report(), SceneReport(hip_path="/tmp/x.hip", generated_at="t")]
        call_index = {"i": 0}

        def run_checks() -> SceneReport:
            report = reports[call_index["i"]]
            call_index["i"] += 1
            return report

        panel = _make_panel(qtbot, run_checks=run_checks)
        panel.run_checks_button.click()
        assert panel.tree.topLevelItemCount() == 2

        panel.run_checks_button.click()
        assert panel.tree.topLevelItemCount() == 0


class TestRowSelection:
    def test_clicking_row_invokes_select_node_callback_with_node_path(self, qtbot) -> None:
        selected: list[str] = []
        panel = _make_panel(qtbot, select_node=lambda path: selected.append(path))
        panel.run_checks_button.click()

        first_item = panel.tree.topLevelItem(0)
        panel.tree.setCurrentItem(first_item)

        assert selected == ["/obj/geo1/box1"]

    def test_clicking_second_row_selects_its_node_path(self, qtbot) -> None:
        selected: list[str] = []
        panel = _make_panel(qtbot, select_node=lambda path: selected.append(path))
        panel.run_checks_button.click()

        second_item = panel.tree.topLevelItem(1)
        panel.tree.setCurrentItem(second_item)

        assert selected == ["/obj/geo1/box2"]

    def test_clearing_current_item_does_not_invoke_select_node_callback(self, qtbot) -> None:
        selected: list[str] = []
        panel = _make_panel(qtbot, select_node=lambda path: selected.append(path))
        panel.run_checks_button.click()
        panel.tree.setCurrentItem(panel.tree.topLevelItem(0))
        selected.clear()

        panel.tree.setCurrentItem(None)

        assert selected == []


class TestFiltering:
    def test_severity_filter_hides_non_matching_rows(self, qtbot) -> None:
        panel = _make_panel(qtbot)
        panel.run_checks_button.click()
        assert panel.tree.topLevelItemCount() == 2

        panel.severity_filter.setCurrentText(Severity.ERROR.value)

        assert panel.tree.topLevelItemCount() == 1

    def test_category_filter_hides_non_matching_rows(self, qtbot) -> None:
        panel = _make_panel(qtbot)
        panel.run_checks_button.click()

        panel.category_filter.setCurrentText("naming")

        assert panel.tree.topLevelItemCount() == 1

    def test_resetting_filter_to_all_restores_full_list(self, qtbot) -> None:
        panel = _make_panel(qtbot)
        panel.run_checks_button.click()

        panel.severity_filter.setCurrentText(Severity.ERROR.value)
        assert panel.tree.topLevelItemCount() == 1

        panel.severity_filter.setCurrentText(panel.FILTER_ALL)
        assert panel.tree.topLevelItemCount() == 2


class TestExportButtons:
    def test_export_csv_button_invokes_callback_with_csv_format(self, qtbot) -> None:
        calls: list[tuple[str, str]] = []
        panel = _make_panel(qtbot, export=lambda fmt, path: calls.append((fmt, path)))
        panel.run_checks_button.click()

        panel.export_csv_button.click()

        assert calls[0][0] == "csv"

    def test_export_json_button_invokes_callback_with_json_format(self, qtbot) -> None:
        calls: list[tuple[str, str]] = []
        panel = _make_panel(qtbot, export=lambda fmt, path: calls.append((fmt, path)))
        panel.run_checks_button.click()

        panel.export_json_button.click()

        assert calls[0][0] == "json"
