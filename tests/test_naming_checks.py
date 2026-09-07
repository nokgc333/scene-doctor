"""checks/naming.py の単体テスト（TC-015〜017）。"""

import re

from scene_doctor.checks.naming import (
    NamingRule,
    check_naming,
    generate_rename_candidate,
)
from tests.fakes import FakeNode


def _rule(pattern: str, applies_to: str = "geo", rename_template: str | None = None) -> NamingRule:
    return NamingRule(
        pattern=re.compile(pattern),
        applies_to=applies_to,
        description=f"must match {pattern}",
        rename_template=rename_template,
    )


class TestCheckNaming:
    def test_conforming_name_is_not_flagged(self) -> None:
        """TC-015: 命名規則を満たすノード名は違反として検出されない。"""
        network = FakeNode(
            "/obj", "obj", _children=[FakeNode("/obj/geo_hero", "geo_hero", _type_name="geo")]
        )
        rules = [_rule(r"^geo_[a-z0-9_]+$")]

        assert check_naming(network, rules) == []

    def test_violating_name_is_detected_with_rename_candidate(self) -> None:
        """TC-016: 命名規則違反は検出され、rename_templateがあればリネーム候補が生成される。"""
        network = FakeNode(
            "/obj", "obj", _children=[FakeNode("/obj/box1", "box1", _type_name="geo")]
        )
        rules = [_rule(r"^geo_[a-z0-9_]+$", rename_template="geo_{seq:03d}")]

        violations = check_naming(network, rules)

        assert len(violations) == 1
        assert violations[0].check_type == "naming"
        assert violations[0].rename_candidate == "geo_001"

    def test_rules_do_not_apply_to_other_node_types(self) -> None:
        network = FakeNode(
            "/obj", "obj", _children=[FakeNode("/obj/box1", "box1", _type_name="xform")]
        )
        rules = [_rule(r"^geo_[a-z0-9_]+$", applies_to="geo")]

        assert check_naming(network, rules) == []

    def test_multiple_violations_in_same_batch_get_distinct_rename_candidates(self) -> None:
        """実機検証(Houdini)で発見: 同一バッチ内の複数違反が同じ候補名(geo_001)を
        重複提案していた。2件目以降は1件目の提案済み候補を避けなければならない。
        """
        network = FakeNode(
            "/obj",
            "obj",
            _children=[
                FakeNode("/obj/box1", "box1", _type_name="geo"),
                FakeNode("/obj/box2", "box2", _type_name="geo"),
            ],
        )
        rules = [_rule(r"^geo_[a-z0-9_]+$", rename_template="geo_{seq:03d}")]

        violations = check_naming(network, rules)

        candidates = [v.rename_candidate for v in violations]
        assert candidates == ["geo_001", "geo_002"]
        assert len(set(candidates)) == len(candidates)


class TestGenerateRenameCandidate:
    def test_first_candidate_has_no_suffix_collision(self) -> None:
        node = FakeNode("/obj/box1", "box1")
        rule = _rule(r"^geo_", rename_template="geo_{seq:03d}")

        candidate = generate_rename_candidate(node, rule, existing_names=set())

        assert candidate == "geo_001"

    def test_colliding_candidate_gets_next_sequence(self) -> None:
        """TC-017: リネーム候補が既存ノード名と衝突する場合、連番サフィックス付き候補が生成される。"""
        node = FakeNode("/obj/box1", "box1")
        rule = _rule(r"^geo_", rename_template="geo_{seq:03d}")

        candidate = generate_rename_candidate(node, rule, existing_names={"geo_001", "geo_002"})

        assert candidate == "geo_003"
