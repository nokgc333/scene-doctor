"""Scene Doctor CLIエントリポイント（hythonから起動）。

使い方:
  hython scene_doctor_cli.py --hip <path> [--rules <path>] [--out <path>]
                              [--format {csv,json,common,both,all}] [--fail-on ...]
  python scene_doctor_cli.py --list-rules   (Houdini 不要)

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
from scene_doctor.report import (
    FAIL_ON_CHOICES,
    SceneReport,
    exceeds_threshold,
    redacted,
    report_to_common_json,
    report_to_csv_rows,
    report_to_json,
)
from scene_doctor.rules import RuleFileError, load_naming_rules

# exit code規約（仕様書§5.6）
EXIT_NO_VIOLATIONS = 0
EXIT_VIOLATIONS_FOUND = 1
EXIT_HIP_NOT_FOUND = 10
EXIT_INVALID_PARAMETER = 11
EXIT_INVALID_TARGET_NODE = 12
EXIT_RULE_FILE_ERROR = 13
EXIT_OUTPUT_NOT_WRITABLE = 14
EXIT_HOU_UNAVAILABLE = 15
EXIT_OUTPUT_EXISTS = 16

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


FORMAT_CHOICES = ["csv", "json", "common", "both", "all"]
OUTPUT_SUFFIXES = {"json": ".json", "csv": ".csv", "common": ".common.json"}
FORMATS_WRITTEN = {
    "csv": ("csv",),
    "json": ("json",),
    "common": ("common",),
    "both": ("json", "csv"),
    "all": ("json", "csv", "common"),
}


def output_files(out_path: Path, output_format: str) -> list[Path]:
    """この形式で書き出すファイルの一覧。"""
    return [
        (
            out_path.with_name(out_path.name + OUTPUT_SUFFIXES[kind])
            if kind == "common"
            else out_path.with_suffix(OUTPUT_SUFFIXES[kind])
        )
        for kind in FORMATS_WRITTEN[output_format]
    ]


def write_report(report: SceneReport, out_path: Path, output_format: str) -> None:
    """レポートを指定形式で書き出す（既定は json/csv 両方）。"""
    kinds = FORMATS_WRITTEN[output_format]
    paths = dict(zip(kinds, output_files(out_path, output_format)))
    if "json" in paths:
        paths["json"].write_text(report_to_json(report), encoding="utf-8")
    if "csv" in paths:
        with paths["csv"].open("w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerows(report_to_csv_rows(report))
    if "common" in paths:
        paths["common"].write_text(report_to_common_json(report), encoding="utf-8")


EXIT_CODE_TABLE = (
    (EXIT_NO_VIOLATIONS, "no violations (or none at the --fail-on level)"),
    (EXIT_VIOLATIONS_FOUND, "violations found"),
    (EXIT_HIP_NOT_FOUND, "the .hip file does not exist"),
    (EXIT_INVALID_PARAMETER, "invalid parameter (for example a scene with no geo node)"),
    (EXIT_INVALID_TARGET_NODE, "the target node is not a SOP network"),
    (EXIT_RULE_FILE_ERROR, "the naming rule file is missing or invalid"),
    (EXIT_OUTPUT_NOT_WRITABLE, "cannot write the report"),
    (EXIT_HOU_UNAVAILABLE, "Houdini's hou module is not available: run with hython"),
    (EXIT_OUTPUT_EXISTS, "the report already exists (use --force to overwrite)"),
)


def exit_code_help() -> str:
    return "exit codes:\n" + "\n".join(f"  {code:>2}  {text}" for code, text in EXIT_CODE_TABLE)


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Scene Doctor: Houdiniシーン検証ツール",
        epilog=exit_code_help(),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--hip", help="検証対象の.hipファイルパス")
    parser.add_argument(
        "--rules", default=None, help="命名規則YAMLのパス(既定: 配布物の rules/default.yaml)"
    )
    parser.add_argument("--out", default=None, help="出力先パス（既定: <hipのstem>_report）")
    parser.add_argument("--format", choices=FORMAT_CHOICES, default="both", help="出力形式")
    parser.add_argument(
        "--fail-on",
        choices=FAIL_ON_CHOICES,
        default="warning",
        help="終了コード 1 にする違反の重さ(warning: 1 件でも / error: error だけ / never: 常に 0)",
    )
    parser.add_argument("--force", action="store_true", help="既存のレポートを上書きする")
    parser.add_argument(
        "--redact-home",
        action="store_true",
        help="レポートのパスに含まれるホームフォルダ(利用者名)を ~ にする(共有するレポート向け)",
    )
    parser.add_argument(
        "--list-rules", action="store_true", help="命名規則の一覧を表示して終わる(Houdini 不要)"
    )
    verbosity = parser.add_mutually_exclusive_group()
    verbosity.add_argument("--quiet", "-q", action="store_true", help="標準出力を抑える")
    verbosity.add_argument("--verbose", "-v", action="store_true", help="進捗を標準エラーに出す")
    return parser


def default_rules_path() -> Path:
    return Path(__file__).resolve().parent / "rules" / "default.yaml"


def _list_rules(rules_path: Path) -> int:
    try:
        rules = load_naming_rules(rules_path)
    except RuleFileError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return EXIT_RULE_FILE_ERROR
    print(f"{len(rules)} naming rule(s) in {rules_path}")
    for rule in rules:
        template = f" -> {rule.rename_template}" if rule.rename_template else ""
        print(f"  [{rule.applies_to}] {rule.pattern.pattern}  {rule.description}{template}")
    return EXIT_NO_VIOLATIONS


def _hou_unavailable_message() -> str:
    return (
        "Error: Houdini's 'hou' module is not available in this Python. "
        "Scene Doctor needs Houdini to open a .hip file: run it with Houdini's Python, "
        "for example `hython scene_doctor_cli.py --hip scene.hip`. "
        "(`--list-rules` works without Houdini.)"
    )


def _load(hip_path: Path) -> tuple[GeometryLike, NodeLike] | int:
    """hou を使って .hip を開く。hou が無い・対象が違うときは、メッセージを出して終了コードを返す。"""
    try:
        # hou への依存はこの 1 行に閉じ込める（実機でのみ実行可能）。
        from scene_doctor.adapters.hou_adapter import load_scene  # noqa: PLC0415

        geo, network = load_scene(hip_path)
        validate_target_is_sop_network(network)
    except ModuleNotFoundError as exc:
        if exc.name != "hou":
            raise
        print(_hou_unavailable_message(), file=sys.stderr)
        return EXIT_HOU_UNAVAILABLE
    except InvalidTargetNodeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return EXIT_INVALID_TARGET_NODE
    return geo, network


def main(argv: list[str] | None = None) -> int:
    """hython上で実行する本番エントリポイント。

    実hou呼び出し（.hipを開く・対象ノードを取得する）は scene_doctor.adapters.hou_adapter に委譲する。
    Houdini の外で実行しても、スタックトレースではなく、案内つきの終了コード 15 で終わる。
    """
    args = _build_arg_parser().parse_args(argv)
    rules_path = Path(args.rules) if args.rules else default_rules_path()
    say = (lambda text: None) if args.quiet else print

    def note(text: str) -> None:
        if args.verbose:
            print(text, file=sys.stderr)

    if args.list_rules:
        return _list_rules(rules_path)
    if not args.hip:
        print("Error: --hip is required (or use --list-rules)", file=sys.stderr)
        return EXIT_INVALID_PARAMETER

    hip_path = Path(args.hip)
    if not hip_path.exists():
        print(f"Error: '{hip_path}' does not exist", file=sys.stderr)
        return EXIT_HIP_NOT_FOUND

    try:
        naming_rules = load_naming_rules(rules_path)
    except RuleFileError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return EXIT_RULE_FILE_ERROR
    note(f"loaded {len(naming_rules)} naming rule(s) from {rules_path}")

    out_path = Path(args.out) if args.out else hip_path.with_name(f"{hip_path.stem}_report")
    existing = [p for p in output_files(out_path, args.format) if p.exists()]
    if existing and not args.force:
        print(f"Error: '{existing[0]}' already exists (use --force to overwrite)", file=sys.stderr)
        return EXIT_OUTPUT_EXISTS

    note(f"opening {hip_path}")
    loaded = _load(hip_path)
    if isinstance(loaded, int):
        return loaded
    geo, network = loaded

    note("running checks")
    try:
        report = build_report(str(hip_path), geo, network, naming_rules)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return EXIT_INVALID_PARAMETER

    if args.redact_home:
        report = redacted(report, str(Path.home()))

    try:
        write_report(report, out_path, args.format)
    except OSError as exc:
        print(f"Error: cannot write to '{out_path}': {exc}", file=sys.stderr)
        return EXIT_OUTPUT_NOT_WRITABLE

    say(f"{report.violation_count} violation(s) found.")
    return EXIT_VIOLATIONS_FOUND if exceeds_threshold(report, args.fail_on) else EXIT_NO_VIOLATIONS


if __name__ == "__main__":
    sys.exit(main())
