"""PySide6パネル用のDCC非依存ビューモデル層。

`hou`はもちろん`PySide6`にも依存しない純粋なdataclass・関数のみで構成する。
`SceneReport`（`scene_doctor/report.py`）を画面表示用の行データに変換し、
フィルタ・ソートといったUIロジックをHoudini/Qtなしでpytestから直接検証できるようにする
（Ports & Adapters, ADR-0001と同じ思想をGUI層にも適用したもの。ADR-0007参照）。
"""

from __future__ import annotations

from dataclasses import dataclass

from scene_doctor.report import SceneReport, Severity, Violation


@dataclass(frozen=True)
class ViolationRow:
    """パネルのツリーに表示する1違反分の行データ。"""

    severity: Severity
    category: str  # Violation.check_type
    target_path: str
    message: str
    node_path: str  # ノード選択ジャンプに使うパス（target_pathと同じ値を採用する）
    rename_candidate: str | None = None


def _violation_to_row(violation: Violation) -> ViolationRow:
    return ViolationRow(
        severity=violation.severity,
        category=violation.check_type,
        target_path=violation.target_path,
        message=violation.message,
        node_path=violation.target_path,
        rename_candidate=violation.rename_candidate,
    )


def build_rows(report: SceneReport) -> list[ViolationRow]:
    """SceneReportの各violationを表示用の行データに変換する（順序は入力を維持）。"""
    return [_violation_to_row(v) for v in report.violations]


def filter_rows(
    rows: list[ViolationRow],
    severity: Severity | None = None,
    category: str | None = None,
) -> list[ViolationRow]:
    """severity/categoryで行データを絞り込む純粋関数。両方Noneなら全件を返す。"""
    result = rows
    if severity is not None:
        result = [r for r in result if r.severity == severity]
    if category is not None:
        result = [r for r in result if r.category == category]
    return result


def sort_rows(rows: list[ViolationRow], key: str, reverse: bool = False) -> list[ViolationRow]:
    """指定フィールド名で行データをソートする純粋関数（入力リストは変更しない）。"""
    return sorted(rows, key=lambda r: getattr(r, key), reverse=reverse)
