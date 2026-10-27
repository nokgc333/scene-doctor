"""大規模シーン(偽の hou)での、検査の所要時間とメモリの計測。`python scripts/benchmark.py` で実行する。

実 hou のジオメトリ取得は含まない(偽のオブジェクトを使うため、検査ロジックだけの値)。
"""

import sys
import time
import tracemalloc
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import scene_doctor_cli  # noqa: E402
from tests.fakes import FakeGeometry, FakeNode, FakePrim  # noqa: E402

SIZES = ((1_000, 20_000), (5_000, 100_000), (10_000, 200_000))


def build(nodes: int, prims: int) -> tuple[FakeGeometry, FakeNode]:
    geo = FakeGeometry([FakePrim([i, i + 1, i + 2]) for i in range(prims)])
    network = FakeNode("/obj/geo1", "geo1", _type_name="geo", _display_flag=True)
    network._children = [
        FakeNode(f"/obj/geo1/node_{i}", f"node_{i}", _type_name="null") for i in range(nodes)
    ]
    return geo, network


def main() -> None:
    print("| ノード数 | プリミティブ数 | 時間 (s) | ピークメモリ (MB) |")
    print("| --- | --- | --- | --- |")
    for nodes, prims in SIZES:
        geo, network = build(nodes, prims)
        tracemalloc.start()
        started = time.perf_counter()
        scene_doctor_cli.build_report("bench.hip", geo, network, [])
        elapsed = time.perf_counter() - started
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        print(f"| {nodes:,} | {prims:,} | {elapsed:.2f} | {peak / 1_000_000:.0f} |")


main()
