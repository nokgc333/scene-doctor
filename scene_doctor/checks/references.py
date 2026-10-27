"""ファイル参照(キャッシュのパス)と HDA の版の検出(SD-04)。hou には依存しない。"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any

from scene_doctor.interfaces import NodeLike
from scene_doctor.report import Severity, Violation

PathExists = Callable[[str], bool]


def _iter_nodes(network: NodeLike, recurse: bool) -> Iterator[NodeLike]:
    for child in network.children():
        yield child
        if recurse:
            yield from _iter_nodes(child, recurse)


def _is_variable_based(raw: str) -> bool:
    """`$HIP/cache/x.bgeo`・`` `chs(...)` ``・`op:/...` のように、場所を変数や参照で表しているか。"""
    return raw.startswith(("$", "op:", "opdef:", "`")) or "$" in raw.split("/")[0]


def _is_absolute(path: str) -> bool:
    return path.startswith(("/", "\\")) or (len(path) > 2 and path[1] == ":" and path[2] in "/\\")


def check_cache_paths(
    network: NodeLike, path_exists: PathExists, recurse: bool = True
) -> list[Violation]:
    """ファイルを参照するパラメーターの、存在しないパス(error)と、変数を使わない絶対パス(warning)。"""
    violations: list[Violation] = []
    for node in _iter_nodes(network, recurse):
        file_paths = getattr(node, "file_paths", None)
        if file_paths is None:
            continue
        for parm_name, raw, expanded in file_paths():
            if not raw or raw.startswith(("op:", "opdef:")):
                continue
            target = f"{node.path()}/{parm_name}"
            if not path_exists(expanded):
                violations.append(
                    Violation(
                        "missing_file",
                        target,
                        f"'{raw}' does not exist (resolved to '{expanded}')",
                        Severity.ERROR,
                    )
                )
            if not _is_variable_based(raw) and _is_absolute(raw):
                violations.append(
                    Violation(
                        "hardcoded_path",
                        target,
                        f"'{raw}' is an absolute path; use $HIP, $JOB or another variable",
                        Severity.WARNING,
                    )
                )
    return violations


def check_hda_versions(network: NodeLike, recurse: bool = True) -> list[Violation]:
    """読み込まれている最新の版より古い HDA を使っているノードを、警告する。"""
    violations: list[Violation] = []
    for node in _iter_nodes(network, recurse):
        hda_version: Any = getattr(node, "hda_version", None)
        info = hda_version() if hda_version is not None else None
        if info is None:
            continue
        name, used, latest = info
        if used != latest:
            violations.append(
                Violation(
                    "outdated_hda",
                    node.path(),
                    f"'{node.name()}' uses {name} version {used}; the latest loaded is {latest}",
                    Severity.WARNING,
                )
            )
    return violations
