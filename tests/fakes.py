"""interfaces.py の Protocol を満たす純粋Pythonフェイク（hou非依存でのテスト用）。"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class FakePrim:
    _point_ids: list[int]
    _area: float = 1.0

    def vertex_point_ids(self) -> list[int]:
        return self._point_ids

    def measured_area(self) -> float:
        return self._area


@dataclass
class FakeGeometry:
    _prims: list[FakePrim] = field(default_factory=list)

    def prims(self) -> list[FakePrim]:
        return self._prims


@dataclass
class FakeNode:
    _path: str
    _name: str
    _type_name: str = "geo"
    _output_connections: list["FakeNode"] = field(default_factory=list)
    _display_flag: bool = False
    _render_flag: bool = False
    _bypassed: bool = False
    _children: list["FakeNode"] = field(default_factory=list)

    def path(self) -> str:
        return self._path

    def name(self) -> str:
        return self._name

    def type_name(self) -> str:
        return self._type_name

    def output_connections(self) -> list["FakeNode"]:
        return self._output_connections

    def is_display_flag_set(self) -> bool:
        return self._display_flag

    def is_render_flag_set(self) -> bool:
        return self._render_flag

    def is_bypassed(self) -> bool:
        return self._bypassed

    def children(self) -> list["FakeNode"]:
        return self._children

    def set_name(self, new_name: str) -> None:
        self._name = new_name
