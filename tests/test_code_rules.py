"""コードの規則をテストで強制する(関数の長さ・シェルの不使用・exec/eval の不使用・個人のパスを書かない)。"""

from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAX_FUNCTION_LINES = 80
SOURCE_DIRS = ("scene_doctor", "hda", "pdg", "scripts")


def _sources() -> list[Path]:
    files = [ROOT / "scene_doctor_cli.py"]
    for directory in SOURCE_DIRS:
        files.extend(sorted((ROOT / directory).rglob("*.py")))
    return files


def test_no_function_is_longer_than_the_limit() -> None:
    too_long = []
    for path in _sources():
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                length = (node.end_lineno or node.lineno) - node.lineno + 1
                if length > MAX_FUNCTION_LINES:
                    too_long.append(f"{path.relative_to(ROOT)}:{node.name} ({length} lines)")

    assert too_long == []


def test_the_shell_is_never_used_to_start_a_process() -> None:
    pattern = re.compile(r"shell\s*=\s*True|os\.system\(|os\.popen\(")
    offenders = [
        str(p.relative_to(ROOT))
        for p in _sources()
        if pattern.search(p.read_text(encoding="utf-8"))
    ]

    assert offenders == []


def test_exec_and_eval_are_not_used() -> None:
    pattern = re.compile(r"(?<![A-Za-z_.])(exec|eval)\(")
    offenders = [
        str(p.relative_to(ROOT))
        for p in _sources()
        if pattern.search(p.read_text(encoding="utf-8"))
    ]

    assert offenders == []


def test_subprocess_calls_pass_a_list_not_a_string() -> None:
    for path in _sources():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in {"run", "Popen", "call", "check_call", "check_output"}
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "subprocess"
            ):
                first = node.args[0] if node.args else None
                assert not isinstance(first, (ast.Constant, ast.JoinedStr)), path.name
