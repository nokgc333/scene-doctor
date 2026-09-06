"""checks/geometry.py の単体テスト（TC-001〜008）。"""

import pytest

from scene_doctor.checks.geometry import check_ngons, check_nonmanifold, check_zero_area
from tests.fakes import FakeGeometry, FakePrim


def _quad(points: list[int]) -> FakePrim:
    return FakePrim(_point_ids=points)


class TestCheckNonmanifold:
    def test_all_manifold_quads_have_no_violations(self) -> None:
        """TC-001: 全プリミティブがmanifoldなフェイクジオメトリでは違反0件。

        2枚の四角形が辺(1,2)を共有する、通常のmanifoldメッシュを模す。
        """
        geo = FakeGeometry([_quad([0, 1, 2, 3]), _quad([1, 4, 5, 2])])

        assert check_nonmanifold(geo) == []

    def test_edge_shared_by_three_faces_is_detected(self) -> None:
        """TC-002: 3枚の面が1辺を共有する場合、非多様体として検出される。"""
        geo = FakeGeometry([_quad([0, 1, 2, 3]), _quad([1, 4, 5, 2]), _quad([1, 6, 7, 2])])

        violations = check_nonmanifold(geo)

        assert len(violations) == 1
        assert violations[0].check_type == "nonmanifold"
        assert "shared by 3 face(s)" in violations[0].message


class TestCheckNgons:
    def test_pentagon_is_detected_with_default_threshold(self) -> None:
        """TC-003: 五角形プリミティブ（既定閾値5）はN-gonとして検出される。"""
        geo = FakeGeometry([_quad([0, 1, 2, 3, 4])])

        violations = check_ngons(geo)

        assert len(violations) == 1
        assert violations[0].check_type == "ngon"

    def test_quad_only_geometry_has_no_ngon_with_default_threshold(self) -> None:
        """TC-004: 四角形のみ（既定閾値5）ではN-gonとして検出されない。"""
        geo = FakeGeometry([_quad([0, 1, 2, 3])])

        assert check_ngons(geo) == []

    def test_quad_is_detected_when_threshold_lowered_to_three(self) -> None:
        """TC-005: ngon_threshold=3 に変更すると四角形もN-gonとして検出される。"""
        geo = FakeGeometry([_quad([0, 1, 2, 3])])

        violations = check_ngons(geo, threshold=3)

        assert len(violations) == 1

    def test_threshold_below_three_raises(self) -> None:
        geo = FakeGeometry([])
        with pytest.raises(ValueError, match="ngon_threshold"):
            check_ngons(geo, threshold=2)


class TestCheckZeroArea:
    def test_degenerate_polygon_below_epsilon_is_detected(self) -> None:
        """TC-006: 面積がepsilon未満の縮退ポリゴンはゼロ面積として検出される。"""
        geo = FakeGeometry([FakePrim(_point_ids=[0, 1, 2], _area=1e-9)])

        violations = check_zero_area(geo)

        assert len(violations) == 1
        assert violations[0].check_type == "zero_area"

    def test_area_slightly_above_threshold_is_not_flagged(self) -> None:
        """TC-007: 面積が閾値をわずかに上回るポリゴンは誤検出されない。"""
        geo = FakeGeometry([FakePrim(_point_ids=[0, 1, 2], _area=2e-6)])

        assert check_zero_area(geo) == []

    def test_empty_geometry_returns_no_violations(self) -> None:
        """TC-008: 空のジオメトリ（0プリミティブ）はエラーにならず0件で正常終了する。"""
        geo = FakeGeometry([])

        assert check_nonmanifold(geo) == []
        assert check_ngons(geo) == []
        assert check_zero_area(geo) == []
