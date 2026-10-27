"""Solaris(LOPs)の USD ステージの検査(SD-04)。`pxr`(usd-core、Houdini 同梱)だけに依存し、`hou` には依存しない。

unibridge の `integrity-check` と同じ観点の、小さな部分集合: 既定 Prim・解決できない参照・
マテリアルの割り当て・UV。違反は、他の検査と同じ `Violation` で返す(共通のレポート形式に載る)。
"""

from __future__ import annotations

from pxr import Usd, UsdGeom, UsdShade, UsdUtils

from scene_doctor.report import Severity, Violation

STAGE_TARGET = "(stage)"
UV_PRIMVAR = "st"


def _meshes(stage: Usd.Stage) -> list[Usd.Prim]:
    return [p for p in stage.Traverse() if p.IsA(UsdGeom.Mesh)]


def _has_inherited_binding(prim: Usd.Prim) -> bool:
    current: Usd.Prim | None = prim
    while current is not None and current.IsValid() and not current.IsPseudoRoot():
        rel = UsdShade.MaterialBindingAPI(current).GetDirectBindingRel()
        if rel and rel.GetTargets():
            return True
        current = current.GetParent()
    return False


def check_usd_stage(stage: Usd.Stage) -> list[Violation]:
    """USD ステージの、既定 Prim・参照・マテリアル・UV を検査する。"""
    violations: list[Violation] = []

    default_name = stage.GetRootLayer().defaultPrim
    if not default_name and any(True for _ in stage.Traverse()):
        violations.append(
            Violation(
                "usd_default_prim",
                STAGE_TARGET,
                "the stage has prims but no default prim",
                Severity.WARNING,
            )
        )
    elif default_name and not stage.GetDefaultPrim():
        violations.append(
            Violation(
                "usd_default_prim",
                STAGE_TARGET,
                f"the default prim '{default_name}' does not exist on the stage",
                Severity.WARNING,
            )
        )

    root = stage.GetRootLayer()
    if not root.anonymous:
        _, _, unresolved = UsdUtils.ComputeAllDependencies(root.identifier)
        violations.extend(
            Violation(
                "usd_unresolved_reference",
                STAGE_TARGET,
                f"unresolved dependency: {path}",
                Severity.ERROR,
            )
            for path in sorted(unresolved)
        )

    for prim in _meshes(stage):
        path = prim.GetPath().pathString
        if not _has_inherited_binding(prim):
            violations.append(
                Violation("usd_no_material", path, "mesh has no material binding", Severity.WARNING)
            )
        if not UsdGeom.PrimvarsAPI(prim).HasPrimvar(UV_PRIMVAR):
            violations.append(
                Violation("usd_no_uv", path, "mesh has no 'st' primvar (UV)", Severity.WARNING)
            )
    return violations


def open_stage(path: str) -> Usd.Stage:
    """ファイルから USD ステージを開く。開けなければ ValueError。"""
    stage = Usd.Stage.Open(path)
    if stage is None:
        raise ValueError(f"'{path}' could not be opened as a USD stage")
    return stage


__all__ = ["check_usd_stage", "open_stage"]
