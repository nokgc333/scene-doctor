"""命名規則の検証とリネーム候補生成（FR-003）。hou には依存せず NodeLike のみに依存する。"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass

from scene_doctor.interfaces import NodeLike
from scene_doctor.report import Severity, Violation


@dataclass(frozen=True)
class NamingRule:
    pattern: re.Pattern[str]
    applies_to: str
    description: str
    rename_template: str | None = None


def _iter_nodes(network: NodeLike, recurse: bool) -> Iterator[NodeLike]:
    for child in network.children():
        yield child
        if recurse:
            yield from _iter_nodes(child, recurse)


def check_naming(
    network: NodeLike, rules: list[NamingRule], recurse: bool = True
) -> list[Violation]:
    """命名規則に違反するノードを検出し、rename_templateがあればリネーム候補を付与する。"""
    violations: list[Violation] = []
    existing_names = {node.name() for node in _iter_nodes(network, recurse)}

    for node in _iter_nodes(network, recurse):
        applicable = [
            rule
            for rule in rules
            if rule.applies_to == "all" or rule.applies_to == node.type_name()
        ]
        for rule in applicable:
            if rule.pattern.match(node.name()):
                continue
            rename_candidate = None
            if rule.rename_template is not None:
                rename_candidate = generate_rename_candidate(node, rule, existing_names)
            violations.append(
                Violation(
                    check_type="naming",
                    target_path=node.path(),
                    message=f"'{node.name()}' does not match naming rule: {rule.description}",
                    severity=Severity.WARNING,
                    rename_candidate=rename_candidate,
                )
            )
    return violations


def generate_rename_candidate(node: NodeLike, rule: NamingRule, existing_names: set[str]) -> str:
    """rename_templateから候補名を生成し、existing_namesと衝突する場合は連番サフィックスで回避する。"""
    if rule.rename_template is None:
        raise ValueError("rule.rename_template must be set to generate a rename candidate")

    seq = 1
    while True:
        candidate = rule.rename_template.format(seq=seq)
        if candidate not in existing_names and candidate != node.name():
            return candidate
        seq += 1
