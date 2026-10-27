"""HDA の PythonModule から呼ぶ、hou に依存しない部分(結果の整形・リネーム対象・パラメーターの変換)。

HDA の中のコード(hda/python_module_source.py)は、hou のノードとのやり取りだけを行う薄い糊にして、
ここに置いた関数を呼ぶ。ここは、Houdini なしで、pytest から検証できる。
"""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from scene_doctor.report import SceneReport

HOME_VARIABLE = "SCENE_DOCTOR_HOME"

PARM_OPTIONS: tuple[tuple[str, str, Callable[[Any], Any]], ...] = (
    ("enable_geometry", "enable_geometry", bool),
    ("enable_nodes", "enable_nodes", bool),
    ("enable_naming", "enable_naming", bool),
    ("ngon_threshold", "ngon_threshold", int),
    ("zero_area_epsilon", "zero_area_epsilon", float),
    ("recurse_subnets", "recurse_into_subnets", bool),
)


def scene_doctor_home(env: Mapping[str, str], fallback: Path) -> Path:
    """配布物のルート。環境変数 `SCENE_DOCTOR_HOME`(Houdini の package ファイルが設定する)> 実行中のコードの場所。"""
    configured = env.get(HOME_VARIABLE)
    return Path(configured) if configured else fallback


def options_from_parms(eval_parm: Callable[[str], Any]) -> dict[str, Any]:
    """HDA のパラメーター(`evalParm`)から、`build_report` の引数を作る。値は、型を揃える。"""
    return {option: convert(eval_parm(parm)) for parm, option, convert in PARM_OPTIONS}


def format_results(report: SceneReport) -> str:
    """`results` パラメーターに出す、人が読むための複数行の文。"""
    lines = [f"{report.violation_count} violation(s) found in {report.hip_path}", ""]
    for violation in report.violations:
        suffix = (
            f" -> rename to '{violation.rename_candidate}'" if violation.rename_candidate else ""
        )
        lines.append(
            f"[{violation.check_type}] {violation.target_path}: {violation.message}{suffix}"
        )
    return "\n".join(lines)


def rename_targets(report: SceneReport) -> list[tuple[str, str]]:
    """リネーム候補を持つ naming 違反の(ノードのパス, 新しい名前)。候補のない違反は含まない。"""
    return [
        (v.target_path, v.rename_candidate)
        for v in report.violations
        if v.check_type == "naming" and v.rename_candidate
    ]


def rules_path_from_parm(raw: str, expand: Callable[[str], str]) -> Path | None:
    """`rules_path` パラメーターの文字列を、実際のパスにする。空なら None。"""
    return Path(expand(raw)) if raw else None


def default_home() -> Path:
    return Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
