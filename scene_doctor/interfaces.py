"""hou本体への依存を切り離すためのProtocol定義（Ports & Adapters, ADR-0001）。

checks/配下はここで定義した構造的部分型のみに依存し、hou を直接importしない
（CI上の静的チェックでも担保する。要件定義書 FR-006 / TC-021）。
"""

from __future__ import annotations

from typing import Protocol, Sequence


class PrimLike(Protocol):
    def vertex_point_ids(self) -> Sequence[int]:
        """プリミティブを構成する頂点が指す点IDの並び（多角形の周を表す）。"""
        ...

    def measured_area(self) -> float:
        """プリミティブの実測面積。"""
        ...


class GeometryLike(Protocol):
    def prims(self) -> Sequence[PrimLike]:
        """ジオメトリに含まれる全プリミティブ。"""
        ...


class NodeLike(Protocol):
    def path(self) -> str: ...
    def name(self) -> str: ...
    def type_name(self) -> str: ...
    def output_connections(self) -> Sequence["NodeLike"]: ...
    def is_display_flag_set(self) -> bool: ...
    def is_render_flag_set(self) -> bool: ...
    def is_bypassed(self) -> bool: ...
    def children(self) -> Sequence["NodeLike"]: ...
    def set_name(self, new_name: str) -> None: ...


class UvPrimLike(Protocol):
    def has_uv(self) -> bool:
        """プリミティブの頂点(または点)に UV(`uv` 属性)があるか。"""
        ...


class NormalPrimLike(Protocol):
    def normal(self) -> tuple[float, float, float]:
        """面の法線(長さは問わない)。"""
        ...

    def centroid(self) -> tuple[float, float, float]:
        """面の重心。"""
        ...


class PointGeometryLike(Protocol):
    def point_positions(self) -> Sequence[tuple[float, float, float]]:
        """全ての点の位置。"""
        ...


class FileNodeLike(Protocol):
    def file_paths(self) -> Sequence[tuple[str, str, str]]:
        """ファイルを参照するパラメーターの(パラメーター名, 書かれた文字列, 変数を展開した実際のパス)。"""
        ...


class HdaNodeLike(Protocol):
    def hda_version(self) -> tuple[str, str, str] | None:
        """HDA のインスタンスなら(HDA 名, 使っている版, 読み込まれている最新の版)。HDA でなければ None。"""
        ...
