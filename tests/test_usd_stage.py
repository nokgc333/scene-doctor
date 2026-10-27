"""Solaris(LOPs)の USD ステージの検査のテスト(usd-core が無ければ飛ばす)。"""

from __future__ import annotations

from pathlib import Path

import pytest

pxr = pytest.importorskip("pxr")

from pxr import Sdf, Usd, UsdGeom, UsdShade  # noqa: E402

from scene_doctor.checks.usd_stage import check_usd_stage, open_stage  # noqa: E402
from scene_doctor.report import Severity  # noqa: E402


def _stage() -> Usd.Stage:
    return Usd.Stage.CreateInMemory()


def _kinds(stage: Usd.Stage) -> list[str]:
    return [v.check_type for v in check_usd_stage(stage)]


def _good_mesh(stage: Usd.Stage, path: str = "/root/m") -> None:
    mesh = UsdGeom.Mesh.Define(stage, path)
    UsdShade.MaterialBindingAPI.Apply(mesh.GetPrim()).Bind(UsdShade.Material.Define(stage, "/mat"))
    pv = UsdGeom.PrimvarsAPI(mesh.GetPrim()).CreatePrimvar(
        "st", Sdf.ValueTypeNames.TexCoord2fArray, "vertex"
    )
    pv.Set([(0.0, 0.0)])


def test_a_clean_stage_has_no_violation() -> None:
    stage = _stage()
    _good_mesh(stage)
    stage.SetDefaultPrim(stage.GetPrimAtPath("/root"))

    assert check_usd_stage(stage) == []


def test_an_empty_stage_has_no_violation() -> None:
    assert check_usd_stage(_stage()) == []


def test_prims_without_a_default_prim_are_a_warning_on_the_stage() -> None:
    stage = _stage()
    UsdGeom.Xform.Define(stage, "/root")

    violations = check_usd_stage(stage)

    assert [(v.check_type, v.target_path, v.severity) for v in violations] == [
        ("usd_default_prim", "(stage)", Severity.WARNING)
    ]


def test_a_mesh_without_material_and_uv_gives_two_warnings_on_the_mesh() -> None:
    stage = _stage()
    UsdGeom.Mesh.Define(stage, "/root/m")
    stage.SetDefaultPrim(stage.GetPrimAtPath("/root"))

    violations = check_usd_stage(stage)

    assert sorted((v.check_type, v.target_path) for v in violations) == [
        ("usd_no_material", "/root/m"),
        ("usd_no_uv", "/root/m"),
    ]


def test_a_binding_on_the_parent_counts_for_its_meshes() -> None:
    stage = _stage()
    group = UsdGeom.Xform.Define(stage, "/root")
    stage.SetDefaultPrim(group.GetPrim())
    UsdShade.MaterialBindingAPI.Apply(group.GetPrim()).Bind(UsdShade.Material.Define(stage, "/mat"))
    mesh = UsdGeom.Mesh.Define(stage, "/root/m")
    UsdGeom.PrimvarsAPI(mesh.GetPrim()).CreatePrimvar(
        "st", Sdf.ValueTypeNames.TexCoord2fArray, "vertex"
    ).Set([(0.0, 0.0)])

    assert check_usd_stage(stage) == []


def test_an_unresolved_reference_is_an_error(tmp_path: Path) -> None:
    path = tmp_path / "scene.usda"
    stage = Usd.Stage.CreateNew(str(path))
    root = stage.DefinePrim("/root")
    stage.SetDefaultPrim(root)
    root.GetReferences().AddReference("./missing.usda")
    stage.GetRootLayer().Save()

    violations = check_usd_stage(Usd.Stage.Open(str(path)))

    errors = [v for v in violations if v.check_type == "usd_unresolved_reference"]
    assert len(errors) == 1
    assert errors[0].severity == Severity.ERROR
    assert "missing.usda" in errors[0].message


def test_open_stage_opens_a_file_and_refuses_a_broken_one(tmp_path: Path) -> None:
    good = tmp_path / "a.usda"
    stage = Usd.Stage.CreateNew(str(good))
    stage.GetRootLayer().Save()
    broken = tmp_path / "b.usda"
    broken.write_text("not usd at all")

    assert open_stage(str(good)) is not None
    with pytest.raises(
        Exception
    ):  # noqa: B017 - pxr は、壊れたファイルで Tf.ErrorException を送出する
        open_stage(str(broken))


def test_a_default_prim_that_does_not_exist_is_reported() -> None:
    stage = _stage()
    UsdGeom.Xform.Define(stage, "/World")
    stage.GetRootLayer().defaultPrim = "Missing"

    violations = check_usd_stage(stage)

    assert [
        (v.check_type, v.severity) for v in violations if v.check_type == "usd_default_prim"
    ] == [("usd_default_prim", Severity.WARNING)]
    assert "Missing" in next(v.message for v in violations if v.check_type == "usd_default_prim")
