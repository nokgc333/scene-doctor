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
        # "measuredarea"はアトリビュートではなくintrinsic（計算プロパティ）。
        # 実機検証(spiderweb_v1.hip)で attribValue("measuredarea") が
        # hou.OperationFailed になることを確認し、intrinsicValueに修正した。
        return float(self._prim.intrinsicValue("measuredarea"))


class HouGeometryAdapter:
    """hou.Geometry を GeometryLike に適合させる薄いラッパー。"""

    def __init__(self, geometry: "hou.Geometry") -> None:
        self._geometry = geometry

    def prims(self) -> Sequence[PrimLike]:
        return [HouPrimAdapter(p) for p in self._geometry.prims()]


class HouNodeAdapter:
    """hou.Node を NodeLike に適合させる薄いラッパー。

    boundary_category: 走査対象として許容するノードカテゴリ名（例: "Sop"）。
    未指定の場合はこのノード自身の子カテゴリ（childTypeCategory）を境界として確定し、
    生成する子アダプタすべてに同じ境界を引き継がせる。これにより、
    ルート直下の通常のカテゴリ遷移（例: Object配下のSopノード群）は正しく辿りつつ、
    DOP Network SOPのように異なるグラフの世界（Dop等）を内包するノードに出会った際は
    その内部には踏み込まない（実機検証 tornado_00.hiplc で判明した無限再帰的ハングへの対処）。
    """

    def __init__(self, node: "hou.Node", boundary_category: str | None = None) -> None:
        self._node = node
        self._boundary_category: str | None
        if boundary_category is not None:
            self._boundary_category = boundary_category
        else:
            child_category = node.childTypeCategory()
            self._boundary_category = child_category.name() if child_category else None

    def path(self) -> str:
        return str(self._node.path())

    def name(self) -> str:
        return str(self._node.name())

    def type_name(self) -> str:
        return str(self._node.type().name())

    def output_connections(self) -> Sequence["NodeLike"]:
        # 実機検証(spiderweb_v1.hip)で判明: outputConnections()の要素のoutputNode()が
        # Noneを返すケースが存在する（サブネット出力への接続等）。
        # Noneのままアダプタ化するとchildTypeCategory()呼び出しでクラッシュするため除外する。
        return [
            HouNodeAdapter(n, self._boundary_category)
            for c in self._node.outputConnections()
            if (n := c.outputNode()) is not None
        ]

    def is_display_flag_set(self) -> bool:
        # SOPネットワーク内にDOP Network SOP等が存在すると、再帰走査がDOPNode等の
        # 異なるノードカテゴリに踏み込むことがある。isDisplayFlagSet等のフラグ系メソッドは
        # SOP/OBJ固有でDopNodeには存在しないため、実機検証(tornado_00.hiplc, TC-023)で
        # AttributeErrorを確認済み。フラグを持たないノード種別は「フラグなし」として
        # 安全側（誤検出よりクラッシュしないことを優先）にFalseを返す。
        method = getattr(self._node, "isDisplayFlagSet", None)
        return bool(method()) if method is not None else False

    def is_render_flag_set(self) -> bool:
        method = getattr(self._node, "isRenderFlagSet", None)
        return bool(method()) if method is not None else False

    def is_bypassed(self) -> bool:
        method = getattr(self._node, "isBypassed", None)
        return bool(method()) if method is not None else False

    def children(self) -> Sequence["NodeLike"]:
        # boundary_categoryと異なるカテゴリの子（DOP Network SOP配下のDopNode等）は
        # 除外する。境界はルート生成時に一度だけ確定し、子孫アダプタへ引き継がれるため、
        # ルート直下の通常のカテゴリ遷移（Object配下のSop群等）は正しく含まれる。
        children = self._node.children()
        if self._boundary_category is None:
            return [HouNodeAdapter(c, self._boundary_category) for c in children]
        return [
            HouNodeAdapter(c, self._boundary_category)
            for c in children
            if c.type().category().name() == self._boundary_category
        ]

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
