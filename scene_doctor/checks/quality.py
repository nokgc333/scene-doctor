"""ジオメトリの品質(UV の欠損・法線の向き・重複点)の検出(SD-04)。hou には依存しない。

対象は、必要なメソッドを持つオブジェクトだけ(`UvPrimLike` など。実機では hou_adapter が全て満たす)。
大量の違反でレポートが埋まらないよう、ジオメトリごとに 1 件へ集約し、該当の番号を先頭の数件だけ添える。
"""

from __future__ import annotations

from collections.abc import Sequence

from scene_doctor.interfaces import (
    GeometryLike,
    NormalPrimLike,
    PointGeometryLike,
    UvPrimLike,
)
from scene_doctor.report import Severity, Violation

DEFAULT_DUPLICATE_POINT_EPSILON = 1e-5
SAMPLE_SIZE = 10
MIN_PRIMS_FOR_NORMAL_CHECK = 4


def _sample(indexes: Sequence[int]) -> str:
    shown = ", ".join(str(i) for i in indexes[:SAMPLE_SIZE])
    more = f" (+{len(indexes) - SAMPLE_SIZE} more)" if len(indexes) > SAMPLE_SIZE else ""
    return f"{shown}{more}"


def check_missing_uvs(geo: GeometryLike) -> list[Violation]:
    """UV を持たないプリミティブがあれば、1 件にまとめて警告する。"""
    prims = list(geo.prims())
    missing = [i for i, p in enumerate(prims) if not _uv(p).has_uv()]
    if not missing:
        return []
    return [
        Violation(
            check_type="missing_uv",
            target_path="geometry",
            message=(
                f"{len(missing)} of {len(prims)} primitive(s) have no UVs: "
                f"prim {_sample(missing)}"
            ),
            severity=Severity.WARNING,
        )
    ]


def _uv(prim: object) -> UvPrimLike:
    return prim  # type: ignore[return-value]


def _dot(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def check_flipped_normals(geo: GeometryLike) -> list[Violation]:
    """閉じた形の外向きの面に混ざった、内向きの面(反転した法線)を検出する。

    ジオメトリの重心から面の重心へのベクトルと、法線の内積が負なら「内向き」。
    大多数が外向きで、少数が内向きのとき、その少数を反転とみなす(凹んだ形では、
    正しい面を内向きと判定しうるため、警告に留める)。面が少ない(4 未満)ときは判定しない。
    """
    prims = [p for p in geo.prims()]
    if len(prims) < MIN_PRIMS_FOR_NORMAL_CHECK:
        return []
    centroids = [_normal(p).centroid() for p in prims]
    count = len(centroids)
    center = (
        sum(c[0] for c in centroids) / count,
        sum(c[1] for c in centroids) / count,
        sum(c[2] for c in centroids) / count,
    )
    inward = []
    for index, prim in enumerate(prims):
        c = centroids[index]
        outward_vector = (c[0] - center[0], c[1] - center[1], c[2] - center[2])
        if _dot(_normal(prim).normal(), outward_vector) < 0:
            inward.append(index)
    if not inward or len(inward) * 2 >= count:
        return []
    return [
        Violation(
            check_type="flipped_normal",
            target_path="geometry",
            message=(
                f"{len(inward)} of {count} primitive(s) face the opposite way "
                f"from the rest: prim {_sample(inward)}"
            ),
            severity=Severity.WARNING,
        )
    ]


def _normal(prim: object) -> NormalPrimLike:
    return prim  # type: ignore[return-value]


def check_duplicate_points(
    geo: PointGeometryLike, epsilon: float = DEFAULT_DUPLICATE_POINT_EPSILON
) -> list[Violation]:
    """同じ位置(epsilon の格子で同じ)にある点を、重複として 1 件にまとめて警告する。"""
    if epsilon <= 0:
        raise ValueError("duplicate_point_epsilon must be > 0")
    seen: dict[tuple[int, int, int], int] = {}
    duplicates: list[int] = []
    for index, (x, y, z) in enumerate(geo.point_positions()):
        key = (round(x / epsilon), round(y / epsilon), round(z / epsilon))
        if key in seen:
            duplicates.append(index)
        else:
            seen[key] = index
    if not duplicates:
        return []
    return [
        Violation(
            check_type="duplicate_point",
            target_path="geometry",
            message=(
                f"{len(duplicates)} point(s) duplicate an earlier point: "
                f"point {_sample(duplicates)}"
            ),
            severity=Severity.WARNING,
        )
    ]
