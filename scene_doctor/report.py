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


FAIL_ON_CHOICES = ("warning", "error", "never")
COMMON_SCHEMA_VERSION = "1"
TOOL_NAME = "scene-doctor"


def exceeds_threshold(report: SceneReport, fail_on: str) -> bool:
    """`--fail-on` の基準を超える違反があるか。`warning`: 1 件でも / `error`: error だけ / `never`: 常に False。"""
    if fail_on == "never":
        return False
    if fail_on == "error":
        return any(v.severity == Severity.ERROR for v in report.violations)
    return report.violation_count > 0


def report_to_common_json(report: SceneReport) -> str:
    """ツール間で共通のレポート形式(docs/schema/common-report.schema.json)。unibridge と同じ形。

    リネーム候補(naming のみ)は、共通の形に項目が無いため、メッセージの末尾に添える。
    """
    findings = [
        {
            "rule": v.check_type,
            "severity": v.severity.value,
            "target": v.target_path,
            "message": (
                f"{v.message} (rename candidate: {v.rename_candidate})"
                if v.rename_candidate
                else v.message
            ),
        }
        for v in report.violations
    ]
    payload = {
        "schema_version": COMMON_SCHEMA_VERSION,
        "tool": TOOL_NAME,
        "generated_at": report.generated_at,
        "subject": report.hip_path,
        "has_errors": any(v.severity == Severity.ERROR for v in report.violations),
        "findings": findings,
    }
    return json.dumps(payload, ensure_ascii=False)


def redact_home(text: str, home: str) -> str:
    """利用者のホームフォルダの名前(利用者名を含む)を `~` に置き換える。区切りは、`/` と `\\` の両方を扱う。"""
    if not home:
        return text
    variants = {home, home.replace("\\", "/"), home.replace("/", "\\")}
    for variant in sorted(variants, key=len, reverse=True):
        text = text.replace(variant, "~")
    return text


def redacted(report: SceneReport, home: str) -> SceneReport:
    """パスに含まれるホームフォルダを `~` にした、新しいレポート。元のレポートは変えない。"""
    return SceneReport(
        hip_path=redact_home(report.hip_path, home),
        generated_at=report.generated_at,
        violations=[
            Violation(
                check_type=v.check_type,
                target_path=redact_home(v.target_path, home),
                message=redact_home(v.message, home),
                severity=v.severity,
                rename_candidate=v.rename_candidate,
            )
            for v in report.violations
        ],
    )
