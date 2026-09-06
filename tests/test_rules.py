"""rules.py の単体テスト（TC-022: yaml.safe_load使用の確認を含む）。"""

from pathlib import Path

import pytest

from scene_doctor.rules import RuleFileError, load_naming_rules


def _write_yaml(tmp_path: Path, name: str, content: str) -> Path:
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return path


def test_load_naming_rules_parses_patterns(tmp_path: Path) -> None:
    path = _write_yaml(
        tmp_path,
        "default.yaml",
        """
        schema_version: 1
        project_type: generic
        naming_rules:
          - pattern: '^geo_[a-z0-9_]+$'
            applies_to: geo
            description: "Geometryノードはgeo_で始まるsnake_case"
            rename_template: "geo_{seq:03d}"
        """,
    )

    rules = load_naming_rules(path)

    assert len(rules) == 1
    assert rules[0].applies_to == "geo"
    assert rules[0].rename_template == "geo_{seq:03d}"
    assert rules[0].pattern.match("geo_hero")


def test_load_naming_rules_missing_required_key_raises(tmp_path: Path) -> None:
    path = _write_yaml(
        tmp_path,
        "broken.yaml",
        """
        schema_version: 1
        project_type: generic
        """,
    )

    with pytest.raises(RuleFileError, match="naming_rules"):
        load_naming_rules(path)


def test_load_naming_rules_invalid_yaml_raises(tmp_path: Path) -> None:
    path = _write_yaml(tmp_path, "syntax_error.yaml", "key: [unclosed")

    with pytest.raises(RuleFileError):
        load_naming_rules(path)


def test_load_naming_rules_uses_safe_load(tmp_path: Path) -> None:
    """TC-022: yaml.safe_load が使われていることをソース上で確認する（静的チェック相当）。"""
    source = Path("scene_doctor/rules.py").read_text(encoding="utf-8")

    assert "yaml.safe_load(" in source
    assert "yaml.load(" not in source
