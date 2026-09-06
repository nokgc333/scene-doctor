"""命名規則YAMLの読込・検証（SEC-001: yaml.safe_load のみ使用）。"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from scene_doctor.checks.naming import NamingRule

REQUIRED_KEYS = {"schema_version", "project_type", "naming_rules"}


class RuleFileError(Exception):
    """命名規則YAMLの読込・検証エラー（E004に対応）。"""


def load_naming_rules(path: Path) -> list[NamingRule]:
    try:
        raw: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise RuleFileError(f"{path} contains invalid YAML: {exc}") from exc

    if not isinstance(raw, dict):
        raise RuleFileError(f"{path} must be a YAML mapping at the top level")

    missing = REQUIRED_KEYS - raw.keys()
    if missing:
        raise RuleFileError(f"{path} is missing required key(s): {', '.join(sorted(missing))}")

    return [
        NamingRule(
            pattern=re.compile(entry["pattern"]),
            applies_to=entry["applies_to"],
            description=entry["description"],
            rename_template=entry.get("rename_template"),
        )
        for entry in raw["naming_rules"]
    ]
