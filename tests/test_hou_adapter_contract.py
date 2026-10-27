"""adapters/hou_adapter.py の契約テスト(偽の hou で、呼び出しの引数・境界・失敗時の挙動を固定する)。"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from tests.fake_hou import (
    FakeConnection,
    FakeHouGeometry,
    FakeHouNode,
    FakeHouPrim,
    load_adapter_with_fake_hou,
    make_fake_hou,
)

import sys  # isort: skip


@pytest.fixture(autouse=True)
def _restore_hou() -> Iterator[None]:
    saved = sys.modules.get("hou")
    yield
    if saved is None:
        sys.modules.pop("hou", None)
    else:
        sys.modules["hou"] = saved
    for name in [m for m in sys.modules if m.startswith("scene_doctor.adapters")]:
        del sys.modules[name]


def _adapter(nodes: dict[str, FakeHouNode] | None = None):  # type: ignore[no-untyped-def]
    module, hou = load_adapter_with_fake_hou("scene_doctor.adapters.hou_adapter", nodes)
    return module, hou


class TestPrimAdapter:
    def test_the_vertices_become_their_point_numbers_in_order(self) -> None:
        module, _ = _adapter()

        ids = module.HouPrimAdapter(FakeHouPrim([4, 2, 7])).vertex_point_ids()

        assert list(ids) == [4, 2, 7]

    def test_the_area_is_read_from_the_intrinsic_not_the_attribute(self) -> None:
        module, _ = _adapter()
        prim = FakeHouPrim([0, 1, 2], area=2.5)

        area = module.HouPrimAdapter(prim).measured_area()

        assert area == 2.5
        assert prim.intrinsic_requests == ["measuredarea"]

    def test_the_area_is_a_float(self) -> None:
        module, _ = _adapter()

        assert isinstance(module.HouPrimAdapter(FakeHouPrim([0], area=3)).measured_area(), float)


class TestGeometryAdapter:
    def test_every_prim_is_wrapped(self) -> None:
        module, _ = _adapter()
        geometry = FakeHouGeometry([FakeHouPrim([0, 1, 2]), FakeHouPrim([1, 2, 3])])

        prims = module.HouGeometryAdapter(geometry).prims()

        assert [list(p.vertex_point_ids()) for p in prims] == [[0, 1, 2], [1, 2, 3]]

    def test_an_empty_geometry_has_no_prims(self) -> None:
        module, _ = _adapter()

        assert list(module.HouGeometryAdapter(FakeHouGeometry()).prims()) == []


class TestNodeAdapter:
    def test_basic_properties_come_from_the_node_and_its_type(self) -> None:
        module, _ = _adapter()
        node = FakeHouNode("/obj/geo1", type_name="geo")

        adapter = module.HouNodeAdapter(node)

        assert (adapter.path(), adapter.name(), adapter.type_name()) == ("/obj/geo1", "geo1", "geo")

    def test_the_flags_are_read_when_the_node_has_them(self) -> None:
        module, _ = _adapter()
        node = FakeHouNode("/obj/geo1", flags={"display": True, "render": False, "bypass": True})

        adapter = module.HouNodeAdapter(node)

        assert (
            adapter.is_display_flag_set(),
            adapter.is_render_flag_set(),
            adapter.is_bypassed(),
        ) == (True, False, True)

    def test_a_node_without_flag_methods_is_treated_as_having_no_flags(self) -> None:
        """実機(tornado_00.hiplc)で、DOP ノードが AttributeError になった経緯の回帰テスト。"""
        module, _ = _adapter()
        dop = FakeHouNode("/obj/geo1/dopnet1/solver", category="Dop", flags=None)

        adapter = module.HouNodeAdapter(dop)

        assert (
            adapter.is_display_flag_set(),
            adapter.is_render_flag_set(),
            adapter.is_bypassed(),
        ) == (False, False, False)

    def test_a_connection_whose_output_node_is_none_is_skipped(self) -> None:
        """実機(spiderweb_v1.hip)で、サブネット出力への接続が None になった経緯の回帰テスト。"""
        module, _ = _adapter()
        target = FakeHouNode("/obj/geo1/merge1", category="Sop", child_category=None)
        node = FakeHouNode(
            "/obj/geo1/box1",
            category="Sop",
            outputs=[FakeConnection(None), FakeConnection(target)],
        )

        outputs = module.HouNodeAdapter(node, "Sop").output_connections()

        assert [o.path() for o in outputs] == ["/obj/geo1/merge1"]

    def test_children_of_another_category_are_not_entered(self) -> None:
        """DOP Network SOP の中(Dop カテゴリ)に踏み込まない、という境界の契約。"""
        module, _ = _adapter()
        sop_child = FakeHouNode("/obj/geo1/box1", category="Sop")
        dop_child = FakeHouNode("/obj/geo1/dopnet1", category="Dop")
        parent = FakeHouNode(
            "/obj/geo1", category="Object", child_category="Sop", children=[sop_child, dop_child]
        )

        children = module.HouNodeAdapter(parent).children()

        assert [c.path() for c in children] == ["/obj/geo1/box1"]

    def test_the_boundary_is_decided_once_at_the_root_and_inherited(self) -> None:
        module, _ = _adapter()
        grandchild = FakeHouNode("/obj/geo1/subnet1/box1", category="Sop")
        subnet = FakeHouNode(
            "/obj/geo1/subnet1", category="Sop", child_category="Dop", children=[grandchild]
        )
        root = FakeHouNode("/obj/geo1", category="Object", child_category="Sop", children=[subnet])

        sub_adapter = module.HouNodeAdapter(root).children()[0]

        assert [c.path() for c in sub_adapter.children()] == ["/obj/geo1/subnet1/box1"]

    def test_without_any_child_category_every_child_is_returned(self) -> None:
        module, _ = _adapter()
        child = FakeHouNode("/x/a", category="Whatever")
        parent = FakeHouNode("/x", child_category=None, children=[child])

        assert len(module.HouNodeAdapter(parent).children()) == 1

    def test_renaming_asks_houdini_for_a_unique_name(self) -> None:
        module, _ = _adapter()
        node = FakeHouNode("/obj/geo1/box1", category="Sop")

        module.HouNodeAdapter(node, "Sop").set_name("geo_box_001")

        assert node.calls == [("setName", ("geo_box_001",), {"unique_name": True})]


class TestLoadScene:
    def _geo(self, name: str, display: bool, with_display_node: bool = True) -> FakeHouNode:
        node = FakeHouNode(f"/obj/{name}", type_name="geo", flags={"display": display})
        if with_display_node:
            geometry = FakeHouGeometry([FakeHouPrim([0, 1, 2])])
            node.display_node = type("Sop", (), {"geometry": lambda self: geometry})()
        return node

    def _load(  # type: ignore[no-untyped-def]
        self, geos: list[FakeHouNode], extra: list[FakeHouNode] | None = None
    ):
        obj = FakeHouNode("/obj", type_name="obj", children=[*(extra or []), *geos])
        module, hou = _adapter({"/obj": obj})
        return module, hou

    def test_the_hip_file_is_loaded_without_a_save_prompt(self) -> None:
        module, hou = self._load([self._geo("a", True)])

        module.load_scene(Path("/proj/scene.hip"))

        assert hou.hipFile.loads == [("/proj/scene.hip", {"suppress_save_prompt": True})]

    def test_the_geo_node_with_the_display_flag_is_chosen(self) -> None:
        module, _ = self._load([self._geo("a", False), self._geo("b", True)])

        _, network = module.load_scene(Path("x.hip"))

        assert network.path() == "/obj/b"

    def test_without_a_display_flag_the_first_geo_node_is_used(self) -> None:
        module, _ = self._load([self._geo("a", False), self._geo("b", False)])

        _, network = module.load_scene(Path("x.hip"))

        assert network.path() == "/obj/a"

    def test_non_geo_nodes_under_obj_are_ignored(self) -> None:
        cam = FakeHouNode("/obj/cam1", type_name="cam", flags={"display": True})
        module, _ = self._load([self._geo("a", False)], extra=[cam])

        _, network = module.load_scene(Path("x.hip"))

        assert network.path() == "/obj/a"

    def test_the_geometry_comes_from_the_display_node(self) -> None:
        module, _ = self._load([self._geo("a", True)])

        geometry, _ = module.load_scene(Path("x.hip"))

        assert len(geometry.prims()) == 1

    def test_a_geo_node_without_a_display_node_gets_empty_geometry(self) -> None:
        module, _ = self._load([self._geo("a", True, with_display_node=False)])

        geometry, _ = module.load_scene(Path("x.hip"))

        assert list(geometry.prims()) == []

    def test_a_scene_without_geo_nodes_is_refused_with_the_path_in_the_message(self) -> None:
        module, _ = self._load([])

        with pytest.raises(ValueError, match="x.hip.*no /obj geo nodes"):
            module.load_scene(Path("x.hip"))


def test_the_fake_has_the_attributes_the_adapter_module_needs() -> None:
    hou = make_fake_hou()

    for name in ("hipFile", "node", "Geometry"):
        assert hasattr(hou, name)


class TestExtendedAdapterMethods:
    def test_a_prim_has_uvs_when_either_the_vertex_or_the_point_attribute_exists(self) -> None:
        module, _ = _adapter()

        def adapt(**kw):  # type: ignore[no-untyped-def]
            return module.HouPrimAdapter(FakeHouPrim([0, 1, 2], **kw)).has_uv()

        assert adapt(vertex_uv=True) is True
        assert adapt(point_uv=True) is True
        assert adapt() is False

    def test_the_normal_is_returned_as_three_floats(self) -> None:
        module, _ = _adapter()

        normal = module.HouPrimAdapter(FakeHouPrim([0, 1, 2], normal=(0.0, 1.0, 0.0))).normal()

        assert tuple(normal) == (0.0, 1.0, 0.0)

    def test_the_centroid_is_the_average_of_the_vertex_positions(self) -> None:
        module, _ = _adapter()
        prim = FakeHouPrim([0, 1, 2], positions=[(0.0, 0.0, 0.0), (3.0, 0.0, 0.0), (0.0, 3.0, 0.0)])

        assert module.HouPrimAdapter(prim).centroid() == (1.0, 1.0, 0.0)

    def test_the_centroid_of_a_prim_without_vertices_does_not_divide_by_zero(self) -> None:
        module, _ = _adapter()

        assert module.HouPrimAdapter(FakeHouPrim([])).centroid() == (0.0, 0.0, 0.0)

    def test_the_geometry_lists_its_point_positions(self) -> None:
        from tests.fake_hou import FakePoint

        module, _ = _adapter()
        geometry = FakeHouGeometry(
            points=[FakePoint(0, (1.0, 2.0, 3.0)), FakePoint(1, (0.0, 0.0, 0.0))]
        )

        assert module.HouGeometryAdapter(geometry).point_positions() == [
            (1.0, 2.0, 3.0),
            (0.0, 0.0, 0.0),
        ]

    def test_only_file_reference_string_parms_are_reported_with_raw_and_expanded_values(
        self,
    ) -> None:
        from tests.fake_hou import FakeParm

        module, _ = _adapter()
        node = FakeHouNode(
            "/obj/geo1/file1",
            parms=[
                FakeParm("file", "$HIP/a.bgeo", "/proj/a.bgeo"),
                FakeParm("label", "hello", "hello", string_type="Regular"),
                FakeParm("count", "3", "3", kind="Int", string_type=None),
            ],
        )

        paths = module.HouNodeAdapter(node, "Sop").file_paths()

        assert list(paths) == [("file", "$HIP/a.bgeo", "/proj/a.bgeo")]

    def test_a_node_that_is_not_an_hda_has_no_version(self) -> None:
        module, _ = _adapter()

        assert module.HouNodeAdapter(FakeHouNode("/obj/geo1/box1")).hda_version() is None

    def test_an_hda_reports_its_version_and_the_latest_loaded_one(self) -> None:
        from tests.fake_hou import FakeCategory, FakeNodeType

        module, _ = _adapter()
        old = FakeNodeType("studio::Tool::1.0", "Sop", ("", "studio", "Tool", "1.0"), is_hda=True)
        new = FakeNodeType("studio::Tool::2.10", "Sop", ("", "studio", "Tool", "2.10"), is_hda=True)
        other = FakeNodeType(
            "studio::Other::9.0", "Sop", ("", "studio", "Other", "9.0"), is_hda=True
        )
        category = FakeCategory("Sop", {t.name(): t for t in (old, new, other)})
        old._category = category
        node = FakeHouNode("/obj/geo1/tool1", node_type=old)

        info = module.HouNodeAdapter(node).hda_version()

        assert info == ("studio::Tool", "1.0", "2.10")

    def test_versions_are_compared_as_numbers_not_text(self) -> None:
        module, _ = _adapter()

        assert module.latest_version(["2.9", "2.10", "1.0"]) == "2.10"
        assert module.latest_version([]) == ""
