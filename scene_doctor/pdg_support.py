"""PDG の Python Script TOP から呼ぶ、hou に依存しない部分(コマンドの組み立て・レポートの集約)。

ワークアイテム由来の文字列は、`subprocess` のリスト引数としてのみ渡し、シェルを使わない(SEC-002)。
"""

from __future__ import annotations

import csv
import io
from collections.abc import Sequence
from pathlib import Path
from typing import Any

CSV_HEADER = ["hip_path", "check_type", "target_path", "message", "severity", "rename_candidate"]
OK_EXIT_CODES = (0, 1)


def report_base_name(hip_path: str) -> str:
    """個別レポートの名前。同名で拡張子違い(.hip / .hiplc)が衝突しないよう、拡張子も含める。"""
    return f"{Path(hip_path).name.replace('.', '_')}_report"


def build_cli_command(
    hython: str, home: Path, hip_path: str, rules: Path, out_path: str
) -> list[str]:
    return [
        hython,
        str(home / "scene_doctor_cli.py"),
        "--hip",
        hip_path,
        "--rules",
        str(rules),
        "--out",
        out_path,
        "--format",
        "json",
        "--force",
    ]


def is_failure(returncode: int) -> bool:
    """終了コード 0(違反なし)と 1(違反あり)は正常。それ以外はエラー。"""
    return returncode not in OK_EXIT_CODES


def aggregate_reports(reports: Sequence[tuple[str, dict[str, Any]]]) -> dict[str, Any]:
    """(元のファイル, 読み込んだ JSON)の並びから、統合レポートを作る。"""
    violations: list[dict[str, Any]] = []
    per_file: dict[str, int] = {}
    for _, data in reports:
        per_file[data["hip_path"]] = data["violation_count"]
        for violation in data["violations"]:
            violations.append({"hip_path": data["hip_path"], **violation})
    return {
        "source_reports": [source for source, _ in reports],
        "total_files": len(reports),
        "total_violation_count": len(violations),
        "per_file_counts": per_file,
        "violations": violations,
    }


def aggregate_csv(aggregate: dict[str, Any]) -> str:
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer)
    writer.writerow(CSV_HEADER)
    for violation in aggregate["violations"]:
        writer.writerow(
            [
                violation["hip_path"],
                violation["check_type"],
                violation["target_path"],
                violation["message"],
                violation["severity"],
                violation.get("rename_candidate") or "",
            ]
        )
    return buffer.getvalue()
