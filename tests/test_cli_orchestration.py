"""scene_doctor_cli.py の純粋ロジック部分の単体テスト（TC-009, オーケストレーション統合）。"""

import re

import pytest

from scene_doctor.checks.naming import NamingRule
from scene_doctor_cli import (
    InvalidTargetNodeError,
    build_report,
    validate_target_is_sop_network,
)
from tests.fakes import FakeGeometry, FakeNode, FakePrim


class TestValidateTargetIsSopNetwork:
    def test_sop_network_passes(self) -> None:
        node = FakeNode("/obj/geo1", "geo1", _type_name="geo")
        validate_target_is_sop_network(node)  # 例外を送出しなければ成功

    def test_non_sop_node_raises(self) -> None:
        """TC-009: SOPでないノードをtarget_nodeに指定するとE003相当の例外を送出する。"""
        node = FakeNode("/obj", "obj", _type_name="obj")

        with pytest.raises(InvalidTargetNodeError, match="geo"):
            validate_target_is_sop_network(node)


class TestBuildReport:
    def test_aggregates_violations_from_all_enabled_checks(self) -> None:
        geo = FakeGeometry([FakePrim(_point_ids=[0, 1, 2], _area=1e-9)])  # zero-area
        leaf = FakeNode("/obj/geo1/box1", "box1", _type_name="geo")  # unconnected + naming違反
        network = FakeNode("/obj/geo1", "geo1", _type_name="geo", _children=[leaf])
        rules = [
            NamingRule(
                pattern=re.compile(r"^geo_"),
                applies_to="geo",
                description="must start with geo_",
                rename_template="geo_{seq:03d}",
            )
        ]

        report = build_report(
            hip_path="/tmp/bad_scene_01.hip",
            geo=geo,
            network=network,
            naming_rules=rules,
        )

        check_types = {v.check_type for v in report.violations}
        assert "zero_area" in check_types
        assert "unconnected_node" in check_types
        assert "naming" in check_types
        assert report.violation_count == 3

    def test_disabling_a_check_excludes_its_violations(self) -> None:
        geo = FakeGeometry([FakePrim(_point_ids=[0, 1, 2], _area=1e-9)])
        network = FakeNode("/obj/geo1", "geo1", _type_name="geo")

        report = build_report(
            hip_path="/tmp/scene.hip",
            geo=geo,
            network=network,
            naming_rules=[],
            enable_geometry=False,
        )

        assert report.violation_count == 0

    def test_invalid_ngon_threshold_propagates_as_value_error(self) -> None:
        geo = FakeGeometry([])
        network = FakeNode("/obj/geo1", "geo1", _type_name="geo")

        with pytest.raises(ValueError, match="ngon_threshold"):
            build_report(
                hip_path="/tmp/scene.hip",
                geo=geo,
                network=network,
                naming_rules=[],
                ngon_threshold=2,
            )
