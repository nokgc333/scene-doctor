"""checks/nodes.py の単体テスト（TC-010〜014）。"""

from scene_doctor.checks.nodes import (
    check_unconnected_nodes,
    check_unused_bypassed_nodes,
)
from tests.fakes import FakeNode


class TestCheckUnconnectedNodes:
    def test_terminal_node_with_display_flag_is_not_flagged(self) -> None:
        """TC-010: 出力接続0だがDisplayフラグが立つ末端ノードは誤検出されない。"""
        network = FakeNode(
            "/obj/geo1", "geo1", _children=[FakeNode("/obj/geo1/out1", "out1", _display_flag=True)]
        )

        assert check_unconnected_nodes(network) == []

    def test_terminal_node_without_flags_is_detected(self) -> None:
        """TC-011: 出力接続0かつDisplay/Renderフラグなしの中間ノードは検出される。"""
        network = FakeNode("/obj/geo1", "geo1", _children=[FakeNode("/obj/geo1/box1", "box1")])

        violations = check_unconnected_nodes(network)

        assert len(violations) == 1
        assert violations[0].target_path == "/obj/geo1/box1"
        assert violations[0].check_type == "unconnected_node"

    def test_node_with_output_connection_is_not_flagged(self) -> None:
        downstream = FakeNode("/obj/geo1/box2", "box2", _display_flag=True)
        upstream = FakeNode("/obj/geo1/box1", "box1", _output_connections=[downstream])
        network = FakeNode("/obj/geo1", "geo1", _children=[upstream, downstream])

        assert check_unconnected_nodes(network) == []

    def test_recurses_into_subnetworks_by_default(self) -> None:
        """TC-013: Subnetwork内部の未接続ノードも既定では再帰的に検出される。"""
        inner = FakeNode("/obj/geo1/sub1/box1", "box1")
        subnet = FakeNode("/obj/geo1/sub1", "sub1", _children=[inner])
        network = FakeNode("/obj/geo1", "geo1", _children=[subnet])

        violations = check_unconnected_nodes(network)

        assert any(v.target_path == "/obj/geo1/sub1/box1" for v in violations)

    def test_does_not_recurse_when_disabled(self) -> None:
        """TC-014: recurse_into_subnets=False の場合、Subnetwork内部は走査されない。"""
        inner = FakeNode("/obj/geo1/sub1/box1", "box1")
        subnet = FakeNode("/obj/geo1/sub1", "sub1", _children=[inner])
        network = FakeNode("/obj/geo1", "geo1", _children=[subnet])

        violations = check_unconnected_nodes(network, recurse_into_subnets=False)

        assert not any(v.target_path == "/obj/geo1/sub1/box1" for v in violations)


class TestCheckUnusedBypassedNodes:
    def test_bypassed_node_is_detected_as_unused(self) -> None:
        """TC-012: バイパス済みノードは「未使用（バイパス）」として区別して検出される。"""
        network = FakeNode(
            "/obj/geo1", "geo1", _children=[FakeNode("/obj/geo1/box1", "box1", _bypassed=True)]
        )

        violations = check_unused_bypassed_nodes(network)

        assert len(violations) == 1
        assert violations[0].check_type == "unused_bypassed"

    def test_non_bypassed_node_is_not_flagged(self) -> None:
        network = FakeNode(
            "/obj/geo1", "geo1", _children=[FakeNode("/obj/geo1/box1", "box1", _display_flag=True)]
        )

        assert check_unused_bypassed_nodes(network) == []
