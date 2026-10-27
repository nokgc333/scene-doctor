"""品質(UV・法線・重複点)とファイル参照・HDA の版の検査のテスト。"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from scene_doctor.checks.quality import (
    check_duplicate_points,
    check_flipped_normals,
    check_missing_uvs,
)
from scene_doctor.checks.references import check_cache_paths, check_hda_versions
from scene_doctor.report import Severity


@dataclass
class UvPrim:
    uv: bool

    def has_uv(self) -> bool:
        return self.uv


@dataclass
class NormalPrim:
    _normal: tuple[float, float, float]
    _centroid: tuple[float, float, float]

    def normal(self) -> tuple[float, float, float]:
        return self._normal

    def centroid(self) -> tuple[float, float, float]:
        return self._centroid


@dataclass
class Geo:
    _prims: list = field(default_factory=list)
    _points: list = field(default_factory=list)

    def prims(self) -> list:
        return self._prims

    def point_positions(self) -> list:
        return self._points


class TestMissingUvs:
    def test_prims_without_uvs_are_reported_once_with_the_count(self) -> None:
        geo = Geo([UvPrim(True), UvPrim(False), UvPrim(False)])

        violations = check_missing_uvs(geo)

        assert len(violations) == 1
        assert violations[0].check_type == "missing_uv"
        assert violations[0].severity == Severity.WARNING
        assert "2 of 3" in violations[0].message
        assert "prim 1, 2" in violations[0].message

    def test_all_prims_with_uvs_gives_nothing(self) -> None:
        assert check_missing_uvs(Geo([UvPrim(True)] * 3)) == []

    def test_no_prims_gives_nothing(self) -> None:
        assert check_missing_uvs(Geo([])) == []

    def test_a_long_list_is_shortened(self) -> None:
        violations = check_missing_uvs(Geo([UvPrim(False)] * 25))

        assert "(+15 more)" in violations[0].message
        assert "25 of 25" in violations[0].message


class TestFlippedNormals:
    def _cube_like(self, flipped: set[int]) -> Geo:
        # 6 面の箱: 中心(0,0,0)から見て、各面の重心は ±1 の軸方向
        directions = [(1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1)]
        prims = []
        for index, d in enumerate(directions):
            normal = tuple(-x if index in flipped else x for x in d)
            prims.append(NormalPrim(normal, tuple(float(x) for x in d)))
        return Geo(prims)

    def test_a_consistent_outward_mesh_has_no_violation(self) -> None:
        assert check_flipped_normals(self._cube_like(set())) == []

    def test_a_minority_of_inward_faces_is_reported_with_their_numbers(self) -> None:
        violations = check_flipped_normals(self._cube_like({2}))

        assert len(violations) == 1
        assert violations[0].check_type == "flipped_normal"
        assert "1 of 6" in violations[0].message
        assert "prim 2" in violations[0].message

    def test_a_fully_reversed_mesh_is_not_reported_because_there_is_no_reference(self) -> None:
        assert check_flipped_normals(self._cube_like({0, 1, 2, 3, 4, 5})) == []

    def test_exactly_half_inward_is_not_reported(self) -> None:
        assert check_flipped_normals(self._cube_like({0, 1, 2})) == []

    def test_fewer_than_four_prims_are_not_judged(self) -> None:
        geo = Geo([NormalPrim((1, 0, 0), (1, 0, 0)), NormalPrim((1, 0, 0), (-1, 0, 0))])

        assert check_flipped_normals(geo) == []

    def test_the_normal_length_does_not_matter(self) -> None:
        geo = self._cube_like(set())
        geo._prims[0] = NormalPrim((100, 0, 0), (1.0, 0.0, 0.0))

        assert check_flipped_normals(geo) == []


class TestDuplicatePoints:
    def test_points_at_the_same_position_are_reported_once(self) -> None:
        geo = Geo(_points=[(0, 0, 0), (1, 0, 0), (0, 0, 0), (1, 0, 0), (0, 0, 0)])

        violations = check_duplicate_points(geo)

        assert len(violations) == 1
        assert violations[0].check_type == "duplicate_point"
        assert "3 point(s)" in violations[0].message
        assert "point 2, 3, 4" in violations[0].message

    def test_points_closer_than_epsilon_count_as_duplicates(self) -> None:
        geo = Geo(_points=[(0, 0, 0), (1e-7, 0, 0)])

        assert len(check_duplicate_points(geo, epsilon=1e-5)) == 1

    def test_points_farther_than_epsilon_do_not(self) -> None:
        geo = Geo(_points=[(0, 0, 0), (1e-3, 0, 0)])

        assert check_duplicate_points(geo, epsilon=1e-5) == []

    def test_no_points_gives_nothing(self) -> None:
        assert check_duplicate_points(Geo()) == []

    @pytest.mark.parametrize("epsilon", [0, -1e-5])
    def test_a_non_positive_epsilon_is_refused(self, epsilon: float) -> None:
        with pytest.raises(ValueError, match="duplicate_point_epsilon"):
            check_duplicate_points(Geo(), epsilon=epsilon)


@dataclass
class RefNode:
    _path: str
    _files: list | None = None
    _hda: tuple | None = None
    _children: list = field(default_factory=list)

    def path(self) -> str:
        return self._path

    def name(self) -> str:
        return self._path.rsplit("/", 1)[-1]

    def children(self) -> list:
        return self._children

    def file_paths(self) -> list:
        return self._files or []

    def hda_version(self) -> tuple | None:
        return self._hda


class PlainNode:
    def __init__(self, path: str) -> None:
        self._path = path

    def path(self) -> str:
        return self._path

    def name(self) -> str:
        return self._path.rsplit("/", 1)[-1]

    def children(self) -> list:
        return []


def _net(*children) -> RefNode:
    return RefNode("/obj/geo1", _children=list(children))


class TestCachePaths:
    def test_a_missing_file_is_an_error_with_the_parameter_in_the_target(self) -> None:
        node = RefNode("/obj/geo1/file1", [("file", "$HIP/cache/a.bgeo", "/proj/cache/a.bgeo")])

        violations = check_cache_paths(_net(node), lambda p: False)

        assert [(v.check_type, v.severity) for v in violations] == [
            ("missing_file", Severity.ERROR)
        ]
        assert violations[0].target_path == "/obj/geo1/file1/file"
        assert "/proj/cache/a.bgeo" in violations[0].message

    def test_an_existing_variable_based_path_is_clean(self) -> None:
        node = RefNode("/obj/geo1/file1", [("file", "$HIP/a.bgeo", "/proj/a.bgeo")])

        assert check_cache_paths(_net(node), lambda p: True) == []

    def test_an_existing_hardcoded_absolute_path_is_a_warning(self) -> None:
        node = RefNode("/obj/geo1/file1", [("file", "/Users/x/a.bgeo", "/Users/x/a.bgeo")])

        violations = check_cache_paths(_net(node), lambda p: True)

        assert [(v.check_type, v.severity) for v in violations] == [
            ("hardcoded_path", Severity.WARNING)
        ]

    def test_a_missing_hardcoded_path_gives_both_findings(self) -> None:
        node = RefNode(
            "/obj/geo1/file1", [("file", "C:\\\\cache\\\\a.bgeo", "C:\\\\cache\\\\a.bgeo")]
        )

        kinds = [v.check_type for v in check_cache_paths(_net(node), lambda p: False)]

        assert kinds == ["missing_file", "hardcoded_path"]

    def test_a_relative_path_is_not_a_hardcoded_absolute_path(self) -> None:
        node = RefNode("/obj/geo1/file1", [("file", "cache/a.bgeo", "/proj/cache/a.bgeo")])

        assert check_cache_paths(_net(node), lambda p: True) == []

    def test_empty_and_operator_paths_are_skipped(self) -> None:
        node = RefNode(
            "/obj/geo1/n", [("file", "", ""), ("geo", "op:/obj/geo1/other", "op:/obj/geo1/other")]
        )

        assert check_cache_paths(_net(node), lambda p: False) == []

    def test_nodes_without_file_parameters_are_ignored(self) -> None:
        assert check_cache_paths(_net(PlainNode("/obj/geo1/box1")), lambda p: False) == []

    def test_subnets_are_searched_only_when_asked(self) -> None:
        inner = RefNode("/obj/geo1/sub/file1", [("file", "$HIP/a", "/p/a")])
        sub = RefNode("/obj/geo1/sub", _children=[inner])

        assert len(check_cache_paths(_net(sub), lambda p: False, recurse=True)) == 1
        assert check_cache_paths(_net(sub), lambda p: False, recurse=False) == []

    def test_each_parameter_of_a_node_is_checked(self) -> None:
        node = RefNode("/obj/geo1/n", [("a", "$HIP/a", "/p/a"), ("b", "$HIP/b", "/p/b")])

        targets = [v.target_path for v in check_cache_paths(_net(node), lambda p: False)]

        assert targets == ["/obj/geo1/n/a", "/obj/geo1/n/b"]


class TestHdaVersions:
    def test_an_older_version_than_the_latest_is_a_warning(self) -> None:
        node = RefNode("/obj/geo1/tool1", _hda=("studio::Tool", "1.0", "2.0"))

        violations = check_hda_versions(_net(node))

        assert len(violations) == 1
        assert violations[0].check_type == "outdated_hda"
        assert "1.0" in violations[0].message and "2.0" in violations[0].message

    def test_the_latest_version_is_clean(self) -> None:
        node = RefNode("/obj/geo1/tool1", _hda=("studio::Tool", "2.0", "2.0"))

        assert check_hda_versions(_net(node)) == []

    def test_nodes_that_are_not_hdas_are_ignored(self) -> None:
        assert check_hda_versions(_net(RefNode("/obj/geo1/box1"))) == []
        assert check_hda_versions(_net(PlainNode("/obj/geo1/box2"))) == []
