"""検出結果のデータモデルとCSV/JSON出力（仕様書§4.3, §4.4）。"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum


class Severity(str, Enum):
    ERROR = "error"
    WARNING = "warning"


@dataclass(frozen=True)
class Violation:
    check_type: str  # "nonmanifold" | "ngon" | "zero_area" | "unconnected_node" | "naming"
    target_path: str  # プリミティブ番号 or ノードパス
    message: str
    severity: Severity
    rename_candidate: str | None = None  # naming違反のみ使用


@dataclass
class SceneReport:
    hip_path: str
    generated_at: str
    violations: list[Violation] = field(default_factory=list)

    @property
    def violation_count(self) -> int:
        return len(self.violations)


def report_to_json(report: SceneReport) -> str:
    payload = {
        "hip_path": report.hip_path,
        "generated_at": report.generated_at,
        "violation_count": report.violation_count,
        "violations": [
            {
                "check_type": v.check_type,
                "target_path": v.target_path,
                "message": v.message,
                "severity": v.severity.value,
                "rename_candidate": v.rename_candidate,
            }
            for v in report.violations
        ],
    }
    return json.dumps(payload, ensure_ascii=False)


CSV_HEADER = ["hip_path", "check_type", "target_path", "message", "severity", "rename_candidate"]


def report_to_csv_rows(report: SceneReport) -> list[list[str]]:
    """violations配列を6列にフラット化したCSV行（ヘッダ含む）を返す。"""
    rows: list[list[str]] = [CSV_HEADER]
    for v in report.violations:
        rows.append(
            [
                report.hip_path,
                v.check_type,
                v.target_path,
                v.message,
                v.severity.value,
                v.rename_candidate or "",
            ]
        )
    return rows
