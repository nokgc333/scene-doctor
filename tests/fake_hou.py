"""`hou` の呼び出しを記録する偽のモジュール(実 Houdini の無い CI で、アダプタの契約を確かめる)。

契約の根拠は、実機(Houdini 22.0.429 / 22.0.466)での検証で分かった挙動:
- `measuredarea` は属性ではなくイントリンシック(`intrinsicValue`)
- `outputConnections()` の要素の `outputNode()` は、`None` を返すことがある
- DOP などのカテゴリの違うノードは、フラグ系のメソッドを持たない
"""

from __future__ import annotations

import importlib
import sys
import types
from typing import Any


class FakeCategory:
    def __init__(self, name: str) -> None:
        self._name = name

    def name(self) -> str:
        return self._name


class FakeNodeType:
    def __init__(self, name: str, category: str) -> None:
        self._name = name
        self._category = FakeCategory(category)

    def name(self) -> str:
        return self._name

    def category(self) -> FakeCategory:
        return self._category


class FakeConnection:
    def __init__(self, node: Any) -> None:
        self._node = node

    def outputNode(self) -> Any:  # noqa: N802 - hou と同じ名前
        return self._node


class FakeHouNode:
    """hou.Node の最小限の偽物。`flags=None` は、フラグ系のメソッドを持たないカテゴリ(DOP など)。"""

    def __init__(
        self,
        path: str,
        type_name: str = "geo",
        category: str = "Object",
        child_category: str | None = "Sop",
        flags: dict[str, bool] | None = None,
        children: list[FakeHouNode] | None = None,
        outputs: list[Any] | None = None,
    ) -> None:
        self._path = path
        self._type = FakeNodeType(type_name, category)
        self._child_category = FakeCategory(child_category) if child_category else None
        self._children = children or []
        self._outputs = outputs or []
        self.calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []
        self.display_node: Any = None
        if flags is not None:
            self.isDisplayFlagSet = lambda: flags.get("display", False)  # noqa: N815
            self.isRenderFlagSet = lambda: flags.get("render", False)  # noqa: N815
            self.isBypassed = lambda: flags.get("bypass", False)  # noqa: N815

    def path(self) -> str:
        return self._path

    def name(self) -> str:
        return self._path.rsplit("/", 1)[-1]

    def type(self) -> FakeNodeType:
        return self._type

    def childTypeCategory(self) -> FakeCategory | None:  # noqa: N802
        return self._child_category

    def children(self) -> list[FakeHouNode]:
        return self._children

    def outputConnections(self) -> list[Any]:  # noqa: N802
        return self._outputs

    def displayNode(self) -> Any:  # noqa: N802
        return self.display_node

    def setName(self, new_name: str, unique_name: bool = False) -> None:  # noqa: N802
        self.calls.append(("setName", (new_name,), {"unique_name": unique_name}))


class FakePoint:
    def __init__(self, number: int) -> None:
        self._number = number

    def number(self) -> int:
        return self._number


class FakeVertex:
    def __init__(self, point_number: int) -> None:
        self._point = FakePoint(point_number)

    def point(self) -> FakePoint:
        return self._point


class FakeHouPrim:
    def __init__(self, point_numbers: list[int], area: float = 1.0) -> None:
        self._vertices = [FakeVertex(n) for n in point_numbers]
        self._area = area
        self.intrinsic_requests: list[str] = []

    def vertices(self) -> list[FakeVertex]:
        return self._vertices

    def intrinsicValue(self, name: str) -> float:  # noqa: N802
        self.intrinsic_requests.append(name)
        if name != "measuredarea":
            raise KeyError(name)
        return self._area

    def attribValue(self, name: str) -> float:  # noqa: N802
        raise AttributeError("measuredarea is an intrinsic, not an attribute")


class FakeHouGeometry:
    def __init__(self, prims: list[FakeHouPrim] | None = None) -> None:
        self._prims = prims or []

    def prims(self) -> list[FakeHouPrim]:
        return self._prims


class FakeHipFile:
    def __init__(self) -> None:
        self.loads: list[tuple[str, dict[str, Any]]] = []
        self.current_path = "/tmp/current.hip"

    def load(self, path: str, **kwargs: Any) -> None:
        self.loads.append((path, kwargs))

    def path(self) -> str:
        return self.current_path


def make_fake_hou(nodes: dict[str, FakeHouNode] | None = None) -> types.ModuleType:
    hou = types.ModuleType("hou")
    registry = nodes or {}
    hou.hipFile = FakeHipFile()  # type: ignore[attr-defined]
    hou.node = lambda path: registry.get(path)  # type: ignore[attr-defined]
    hou.Geometry = FakeHouGeometry  # type: ignore[attr-defined]
    hou.Prim = FakeHouPrim  # type: ignore[attr-defined]
    hou.Node = FakeHouNode  # type: ignore[attr-defined]
    return hou


def load_adapter_with_fake_hou(
    module: str, nodes: dict[str, FakeHouNode] | None = None
) -> tuple[types.ModuleType, types.ModuleType]:
    """偽の hou を差し込んで、アダプタのモジュールを読み込み直す。(アダプタ, 偽の hou)を返す。"""
    hou = make_fake_hou(nodes)
    sys.modules["hou"] = hou
    for name in [m for m in sys.modules if m.startswith("scene_doctor.adapters")]:
        del sys.modules[name]
    return importlib.import_module(module), hou
