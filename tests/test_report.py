"""report.py の単体テスト（TC-024: CSV/JSON整合性）。"""

import json

from scene_doctor.report import (
    SceneReport,
    Severity,
    Violation,
    report_to_csv_rows,
    report_to_json,
)


def _sample_report() -> SceneReport:
    return SceneReport(
        hip_path="/tmp/bad_scene_01.hip",
        generated_at="2026-09-07T00:00:00Z",
        violations=[
            Violation(
                check_type="nonmanifold",
                target_path="edge(1, 2)",
                message="edge (1, 2) is shared by 3 face(s) (expected 2)",
                severity=Severity.ERROR,
            ),
            Violation(
                check_type="naming",
                target_path="/obj/geo1/box1",
                message="'box1' does not match naming rule",
                severity=Severity.WARNING,
                rename_candidate="geo_001",
            ),
        ],
    )


def test_violation_count_reflects_list_length() -> None:
    report = _sample_report()
    assert report.violation_count == 2


def test_empty_report_has_zero_violation_count() -> None:
    report = SceneReport(hip_path="/tmp/good.hip", generated_at="2026-09-07T00:00:00Z")
    assert report.violation_count == 0


def test_report_to_json_matches_schema() -> None:
    """TC-024: JSON出力が仕様書§4.4のスキーマ（必須キー・severity値）に一致する。"""
    payload = json.loads(report_to_json(_sample_report()))

    assert payload["hip_path"] == "/tmp/bad_scene_01.hip"
    assert payload["violation_count"] == 2
    assert payload["violations"][0]["severity"] == "error"
    assert payload["violations"][1]["rename_candidate"] == "geo_001"
    assert payload["violations"][0]["rename_candidate"] is None


def test_report_to_csv_rows_flattens_violations() -> None:
    """CSVはviolations配列を6列にフラット化する（hip_path/check_type/target_path/message/
    severity/rename_candidate）。"""
    rows = report_to_csv_rows(_sample_report())

    assert rows[0] == [
        "hip_path",
        "check_type",
        "target_path",
        "message",
        "severity",
        "rename_candidate",
    ]
    assert rows[1][0] == "/tmp/bad_scene_01.hip"
    assert rows[1][1] == "nonmanifold"
    assert rows[2][5] == "geo_001"
