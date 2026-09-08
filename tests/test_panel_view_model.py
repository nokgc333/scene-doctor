"""panel_view_model.py の単体テスト（DCC非依存、PySide6/houに依存しない純粋関数）。"""

from scene_doctor.report import SceneReport, Severity, Violation
from scene_doctor.ui.panel_view_model import (
    ViolationRow,
    build_rows,
    filter_rows,
    sort_rows,
)


def _sample_report() -> SceneReport:
    return SceneReport(
        hip_path="/tmp/bad_scene_01.hip",
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
            Violation(
                check_type="zero_area",
                target_path="/obj/geo1/box1",
                message="prim 5 has zero area",
                severity=Severity.ERROR,
            ),
        ],
    )


class TestBuildRows:
    def test_empty_report_yields_no_rows(self) -> None:
        report = SceneReport(hip_path="/tmp/good.hip", generated_at="2026-09-07T00:00:00Z")
        assert build_rows(report) == []

    def test_build_rows_converts_all_violations(self) -> None:
        rows = build_rows(_sample_report())
        assert len(rows) == 3
        assert all(isinstance(row, ViolationRow) for row in rows)

    def test_build_rows_preserves_field_values(self) -> None:
        rows = build_rows(_sample_report())
        first = rows[0]
        assert first.severity == Severity.ERROR
        assert first.category == "nonmanifold"
        assert first.target_path == "/obj/geo1/box1"
        assert first.message == "edge (1, 2) is shared by 3 face(s) (expected 2)"
        assert first.node_path == "/obj/geo1/box1"

    def test_build_rows_carries_rename_candidate(self) -> None:
        rows = build_rows(_sample_report())
        naming_row = next(r for r in rows if r.category == "naming")
        assert naming_row.rename_candidate == "geo_002"

    def test_build_rows_none_rename_candidate_when_absent(self) -> None:
        rows = build_rows(_sample_report())
        non_naming_row = next(r for r in rows if r.category == "nonmanifold")
        assert non_naming_row.rename_candidate is None

    def test_build_rows_preserves_input_order(self) -> None:
        rows = build_rows(_sample_report())
        assert [r.category for r in rows] == ["nonmanifold", "naming", "zero_area"]

    def test_node_path_falls_back_to_target_path_for_non_node_targets(self) -> None:
        report = SceneReport(
            hip_path="/tmp/x.hip",
            generated_at="2026-09-07T00:00:00Z",
            violations=[
                Violation(
                    check_type="nonmanifold",
                    target_path="edge(1, 2)",
                    message="msg",
                    severity=Severity.ERROR,
                )
            ],
        )
        rows = build_rows(report)
        assert rows[0].node_path == "edge(1, 2)"


class TestFilterRows:
    def test_no_filter_returns_all_rows(self) -> None:
        rows = build_rows(_sample_report())
        assert filter_rows(rows) == rows

    def test_filter_by_severity(self) -> None:
        rows = build_rows(_sample_report())
        filtered = filter_rows(rows, severity=Severity.ERROR)
        assert len(filtered) == 2
        assert all(r.severity == Severity.ERROR for r in filtered)

    def test_filter_by_category(self) -> None:
        rows = build_rows(_sample_report())
        filtered = filter_rows(rows, category="naming")
        assert len(filtered) == 1
        assert filtered[0].category == "naming"

    def test_filter_by_severity_and_category_combined(self) -> None:
        rows = build_rows(_sample_report())
        filtered = filter_rows(rows, severity=Severity.ERROR, category="zero_area")
        assert len(filtered) == 1
        assert filtered[0].target_path == "/obj/geo1/box1"
        assert filtered[0].category == "zero_area"

    def test_filter_with_no_matches_returns_empty_list(self) -> None:
        rows = build_rows(_sample_report())
        filtered = filter_rows(rows, category="ngon")
        assert filtered == []

    def test_filter_empty_rows_returns_empty_list(self) -> None:
        assert filter_rows([], severity=Severity.ERROR) == []


class TestSortRows:
    def test_sort_by_severity(self) -> None:
        rows = build_rows(_sample_report())
        sorted_rows = sort_rows(rows, key="severity")
        assert [r.severity for r in sorted_rows] == sorted(r.severity for r in rows)

    def test_sort_by_category_reverse(self) -> None:
        rows = build_rows(_sample_report())
        sorted_rows = sort_rows(rows, key="category", reverse=True)
        assert [r.category for r in sorted_rows] == sorted((r.category for r in rows), reverse=True)

    def test_sort_by_target_path(self) -> None:
        rows = build_rows(_sample_report())
        sorted_rows = sort_rows(rows, key="target_path")
        assert [r.target_path for r in sorted_rows] == sorted(r.target_path for r in rows)

    def test_sort_does_not_mutate_input(self) -> None:
        rows = build_rows(_sample_report())
        original_order = list(rows)
        sort_rows(rows, key="category", reverse=True)
        assert rows == original_order

    def test_sort_empty_rows_returns_empty_list(self) -> None:
        assert sort_rows([], key="category") == []
