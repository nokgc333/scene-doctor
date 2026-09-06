"""Scene Doctor CLIエントリポイント（hythonから起動）。

使い方:
  hython scene_doctor_cli.py --hip <path> [--rules <path>] [--out <path>]
                              [--format {csv,json,both}]

実hou呼び出し（.hipファイルを開く、対象ノードを取得する等）は
scene_doctor.adapters.hou_adapter にのみ存在させ、本モジュールの他の関数は
hou非依存の GeometryLike/NodeLike のみに依存する（Ports & Adapters, ADR-0001）。
そのため本モジュールの純粋ロジック部分（build_report等）は
Houdiniなしでpytestから直接検証できる。
"""

from __future__ import annotations

import argparse
import csv
import datetime
import sys
from dataclasses import dataclass
from pathlib import Path

from scene_doctor.checks.geometry import (
    DEFAULT_NGON_THRESHOLD,
    DEFAULT_ZERO_AREA_EPSILON,
    check_ngons,
    check_nonmanifold,
    check_zero_area,
)
from scene_doctor.checks.naming import NamingRule, check_naming
from scene_doctor.checks.nodes import (
    check_unconnected_nodes,
    check_unused_bypassed_nodes,
)
from scene_doctor.interfaces import GeometryLike, NodeLike
from scene_doctor.report import SceneReport, report_to_csv_rows, report_to_json
from scene_doctor.rules import RuleFileError, load_naming_rules

# exit code規約（仕様書§5.6）
EXIT_NO_VIOLATIONS = 0
EXIT_VIOLATIONS_FOUND = 1
EXIT_HIP_NOT_FOUND = 10
EXIT_INVALID_PARAMETER = 11
EXIT_INVALID_TARGET_NODE = 12
EXIT_RULE_FILE_ERROR = 13
EXIT_OUTPUT_NOT_WRITABLE = 14

SOP_NETWORK_TYPE_NAMES = {"geo"}


class InvalidTargetNodeError(Exception):
    """target_node が SOP ネットワークでない場合に送出（E003）。"""


def validate_target_is_sop_network(node: NodeLike) -> None:
    """target_node が SOP（geo）ネットワークであることを検証する。"""
    if node.type_name() not in SOP_NETWORK_TYPE_NAMES:
        raise InvalidTargetNodeError(
            f"'{node.path()}' is a '{node.type_name()}' node; "
            f"expected one of {sorted(SOP_NETWORK_TYPE_NAMES)} (SOP network)"
        )


@dataclass(frozen=True)
class CheckOptions:
    enable_geometry: bool = True
    enable_nodes: bool = True
    enable_naming: bool = True
    ngon_threshold: int = DEFAULT_NGON_THRESHOLD
    zero_area_epsilon: float = DEFAULT_ZERO_AREA_EPSILON
    recurse_into_subnets: bool = True


def build_report(
    hip_path: str,
    geo: GeometryLike,
    network: NodeLike,
    naming_rules: list[NamingRule],
    enable_geometry: bool = True,
    enable_nodes: bool = True,
    enable_naming: bool = True,
    ngon_threshold: int = DEFAULT_NGON_THRESHOLD,
    zero_area_epsilon: float = DEFAULT_ZERO_AREA_EPSILON,
    recurse_into_subnets: bool = True,
) -> SceneReport:
    """有効化されたチェックを実行し、結果を1つのSceneReportに集約する。

    hou には依存せず、GeometryLike/NodeLikeを満たすオブジェクトを受け取るだけなので、
    実Houdiniなしでもフェイクオブジェクトを渡して検証できる。
    """
    report = SceneReport(
        hip_path=hip_path,
        generated_at=datetime.datetime.now(datetime.timezone.utc)
        .isoformat()
        .replace("+00:00", "Z"),
    )

    if enable_geometry:
        report.violations.extend(check_nonmanifold(geo))
        report.violations.extend(check_ngons(geo, threshold=ngon_threshold))
        report.violations.extend(check_zero_area(geo, epsilon=zero_area_epsilon))

    if enable_nodes:
        report.violations.extend(
            check_unconnected_nodes(network, recurse_into_subnets=recurse_into_subnets)
        )
        report.violations.extend(
            check_unused_bypassed_nodes(network, recurse_into_subnets=recurse_into_subnets)
        )

    if enable_naming:
        report.violations.extend(check_naming(network, naming_rules, recurse=recurse_into_subnets))

    return report


def write_report(report: SceneReport, out_path: Path, output_format: str) -> None:
    """レポートを指定形式で書き出す（既定は json/csv 両方）。"""
    if output_format in ("json", "both"):
        out_path.with_suffix(".json").write_text(report_to_json(report), encoding="utf-8")
    if output_format in ("csv", "both"):
        with out_path.with_suffix(".csv").open("w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerows(report_to_csv_rows(report))


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Scene Doctor: Houdiniシーン検証ツール")
    parser.add_argument("--hip", required=True, help="検証対象の.hipファイルパス")
    parser.add_argument("--rules", default="rules/default.yaml", help="命名規則YAMLのパス")
    parser.add_argument("--out", default=None, help="出力先パス（既定: <hipのstem>_report）")
    parser.add_argument(
        "--format", choices=["csv", "json", "both"], default="both", help="出力形式"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """hython上で実行する本番エントリポイント。

    実hou呼び出し（.hipを開く・対象ノードを取得する）はここでのみ行い、
    scene_doctor.adapters.hou_adapter に処理を委譲する。
    このモジュールはHoudini本体がない環境ではimport時にエラーになるため、
    実機（hython）でのみ実行・検証できる（README「実機での検証手順」参照）。
    """
    args = _build_arg_parser().parse_args(argv)
    hip_path = Path(args.hip)

    if not hip_path.exists():
        print(f"Error: '{hip_path}' does not exist", file=sys.stderr)
        return EXIT_HIP_NOT_FOUND

    try:
        naming_rules = load_naming_rules(Path(args.rules))
    except RuleFileError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return EXIT_RULE_FILE_ERROR

    try:
        # hou への依存はこの1行に閉じ込める（実機でのみ実行可能）。
        from scene_doctor.adapters.hou_adapter import load_scene  # noqa: PLC0415

        geo, network = load_scene(hip_path)
        validate_target_is_sop_network(network)
    except InvalidTargetNodeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return EXIT_INVALID_TARGET_NODE

    try:
        report = build_report(str(hip_path), geo, network, naming_rules)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return EXIT_INVALID_PARAMETER

    out_path = Path(args.out) if args.out else hip_path.with_name(f"{hip_path.stem}_report")
    try:
        write_report(report, out_path, args.format)
    except OSError as exc:
        print(f"Error: cannot write to '{out_path}': {exc}", file=sys.stderr)
        return EXIT_OUTPUT_NOT_WRITABLE

    print(f"{report.violation_count} violation(s) found.")
    return EXIT_VIOLATIONS_FOUND if report.violation_count else EXIT_NO_VIOLATIONS


if __name__ == "__main__":
    sys.exit(main())
