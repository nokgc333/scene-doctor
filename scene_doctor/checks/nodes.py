"""ノード構造の欠陥検出（FR-002）。hou には依存せず NodeLike のみに依存する。"""

from __future__ import annotations

from collections.abc import Iterator

from scene_doctor.interfaces import NodeLike
from scene_doctor.report import Severity, Violation


def _iter_nodes(network: NodeLike, recurse_into_subnets: bool) -> Iterator[NodeLike]:
    for child in network.children():
        yield child
        if recurse_into_subnets:
            yield from _iter_nodes(child, recurse_into_subnets)


def check_unconnected_nodes(
    network: NodeLike, recurse_into_subnets: bool = True
) -> list[Violation]:
    """出力接続0かつDisplay/Renderフラグが立っていないノードを未接続として検出する。

    バイパス済みノードは check_unused_bypassed_nodes 側で別カテゴリとして扱うため、
    ここでは対象から除外する。
    """
    violations: list[Violation] = []
    for node in _iter_nodes(network, recurse_into_subnets):
        if node.is_bypassed():
            continue
        has_output = len(node.output_connections()) > 0
        is_terminal_output = node.is_display_flag_set() or node.is_render_flag_set()
        if not has_output and not is_terminal_output:
            violations.append(
                Violation(
                    check_type="unconnected_node",
                    target_path=node.path(),
                    message=f"'{node.name()}' has no output connections and is not "
                    "flagged for display/render",
                    severity=Severity.WARNING,
                )
            )
    return violations


def check_unused_bypassed_nodes(
    network: NodeLike, recurse_into_subnets: bool = True
) -> list[Violation]:
    """isBypassed()がTrueのノードを「未使用（バイパス）」として検出する。"""
    violations: list[Violation] = []
    for node in _iter_nodes(network, recurse_into_subnets):
        if node.is_bypassed():
            violations.append(
                Violation(
                    check_type="unused_bypassed",
                    target_path=node.path(),
                    message=f"'{node.name()}' is bypassed",
                    severity=Severity.WARNING,
                )
            )
    return violations
