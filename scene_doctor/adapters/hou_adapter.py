"""実 hou への依存をここに閉じ込めるアダプタ層（Ports & Adapters, ADR-0001）。

このモジュールは Houdini 同梱の Python（hython）でのみ import 可能。
pytest（venv）環境には `hou` が存在しないため、CI の型チェック・単体テストの対象から
意図的に除外している（pyproject.toml の [tool.mypy] exclude、CIの静的チェック参照）。

--- 実機での検証が必須な理由（README/Runbookにも明記） ---
本ファイルの正しさは、この開発環境（Houdiniなし）では検証できない。
仕様書§11.3 RB-002の手順に従い、実際のHoudini上で
`~/3dcg-dev/houdini_dev/tornado_00.hiplc` 等に対して動作確認すること
（要件定義書 TC-023, TC-024 の手動E2E）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

import hou  # type: ignore[import-not-found]

from scene_doctor.interfaces import GeometryLike, NodeLike, PrimLike


class HouPrimAdapter:
    """hou.Prim を PrimLike に適合させる薄いラッパー。"""

    def __init__(self, prim: "hou.Prim") -> None:
        self._prim = prim

    def vertex_point_ids(self) -> Sequence[int]:
        return [vertex.point().number() for vertex in self._prim.vertices()]

    def measured_area(self) -> float:
        return float(self._prim.attribValue("measuredarea"))


class HouGeometryAdapter:
    """hou.Geometry を GeometryLike に適合させる薄いラッパー。"""

    def __init__(self, geometry: "hou.Geometry") -> None:
        self._geometry = geometry

    def prims(self) -> Sequence[PrimLike]:
        return [HouPrimAdapter(p) for p in self._geometry.prims()]


class HouNodeAdapter:
    """hou.Node を NodeLike に適合させる薄いラッパー。"""

    def __init__(self, node: "hou.Node") -> None:
        self._node = node

    def path(self) -> str:
        return str(self._node.path())

    def name(self) -> str:
        return str(self._node.name())

    def type_name(self) -> str:
        return str(self._node.type().name())

    def output_connections(self) -> Sequence["NodeLike"]:
        return [HouNodeAdapter(c.outputNode()) for c in self._node.outputConnections()]

    def is_display_flag_set(self) -> bool:
        return bool(self._node.isDisplayFlagSet())

    def is_render_flag_set(self) -> bool:
        return bool(self._node.isRenderFlagSet())

    def is_bypassed(self) -> bool:
        return bool(self._node.isBypassed())

    def children(self) -> Sequence["NodeLike"]:
        return [HouNodeAdapter(c) for c in self._node.children()]

    def set_name(self, new_name: str) -> None:
        self._node.setName(new_name, unique_name=True)


def load_scene(hip_path: Path) -> tuple[GeometryLike, NodeLike]:
    """.hipファイルを開き、検証対象のジオメトリとノードネットワークを返す。

    v1では「表示フラグが立っている最初のgeoノード」を検証対象とする単純な方針を取る
    （複数geoノードを横断する集約はPDGバッチ側でファイル単位のワークアイテムとして
    扱うことでカバーする想定）。ノード探索戦略の妥当性は実機での検証（TC-023/024）が必要。
    """
    hou.hipFile.load(str(hip_path), suppress_save_prompt=True)

    obj_level = hou.node("/obj")
    geo_nodes = [n for n in obj_level.children() if n.type().name() == "geo"]
    if not geo_nodes:
        raise ValueError(f"'{hip_path}' contains no /obj geo nodes to validate")

    target = next((n for n in geo_nodes if n.isDisplayFlagSet()), geo_nodes[0])
    display_sop = target.displayNode()
    geometry = display_sop.geometry() if display_sop is not None else hou.Geometry()

    return HouGeometryAdapter(geometry), HouNodeAdapter(target)
