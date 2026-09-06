"""ジオメトリ欠陥検出（FR-001）。hou には依存せず GeometryLike のみに依存する。"""

from __future__ import annotations

from scene_doctor.interfaces import GeometryLike
from scene_doctor.report import Severity, Violation

DEFAULT_NGON_THRESHOLD = 5
DEFAULT_ZERO_AREA_EPSILON = 1e-6


def check_nonmanifold(geo: GeometryLike) -> list[Violation]:
    """3枚以上の面が共有するエッジを非多様体として検出する。

    1枚のみに共有されるエッジ（境界/オープンエッジ）は開いたサーフェスとして正常な状態であり、
    非多様体ではない。非多様体とみなすのは3枚以上が同一エッジを共有する場合のみとする
    （CGの標準用語に合わせた判定。TC-001で境界エッジを誤検出しないことを確認済み）。

    エッジは (min(point_a, point_b), max(point_a, point_b)) のタプルで正規化し、
    エッジ -> 隣接プリミティブ数のハッシュマップを構築することで O(総頂点数) で判定する
    （業務ロジック§8.1参照。10万ポリゴン規模でもNFR-001の目標を満たす設計）。
    """
    edge_face_count: dict[tuple[int, int], int] = {}
    for prim in geo.prims():
        pts = prim.vertex_point_ids()
        n = len(pts)
        for i in range(n):
            a, b = pts[i], pts[(i + 1) % n]
            edge = (min(a, b), max(a, b))
            edge_face_count[edge] = edge_face_count.get(edge, 0) + 1

    violations: list[Violation] = []
    for edge, count in edge_face_count.items():
        if count > 2:
            violations.append(
                Violation(
                    check_type="nonmanifold",
                    target_path=f"edge{edge}",
                    message=f"edge {edge} is shared by {count} face(s) (expected at most 2)",
                    severity=Severity.ERROR,
                )
            )
    return violations


def check_ngons(geo: GeometryLike, threshold: int = DEFAULT_NGON_THRESHOLD) -> list[Violation]:
    if threshold < 3:
        raise ValueError("ngon_threshold must be >= 3")
    violations: list[Violation] = []
    for i, prim in enumerate(geo.prims()):
        n = len(prim.vertex_point_ids())
        if n >= threshold:
            violations.append(
                Violation(
                    check_type="ngon",
                    target_path=f"prim{i}",
                    message=f"primitive has {n} sides (threshold={threshold})",
                    severity=Severity.WARNING,
                )
            )
    return violations


def check_zero_area(
    geo: GeometryLike, epsilon: float = DEFAULT_ZERO_AREA_EPSILON
) -> list[Violation]:
    if epsilon <= 0:
        raise ValueError("zero_area_epsilon must be > 0")
    violations: list[Violation] = []
    for i, prim in enumerate(geo.prims()):
        area = prim.measured_area()
        if area < epsilon:
            violations.append(
                Violation(
                    check_type="zero_area",
                    target_path=f"prim{i}",
                    message=f"primitive area {area:.8f} is below epsilon={epsilon}",
                    severity=Severity.ERROR,
                )
            )
    return violations
