"""Houdini本体へ`SceneDoctorPanel`を実際にドッキング・起動するアダプタ（ADR-0007）。

このモジュールは Houdini 同梱の Python（hython、または Houdini UIプロセス内のPython
Shell/Shelf Tool経由）でのみ import 可能。`hou` / `hou.qt` に依存するため、
`scene_doctor/adapters/hou_adapter.py`と同様の理由でpytest（venv）環境には存在せず、
CIの単体テスト・カバレッジ計測・mypyの対象からも除外している
（pyproject.tomlの`[tool.coverage.run] omit` / `[tool.mypy] exclude`参照）。

--- 実機での検証について ---
本ファイルの正しさは、この開発環境（Houdiniなし）では検証できない。
このセッションでは実機Houdini上での動作確認を行っていない（別セッションで実施予定）。
README「既知の制限事項」参照。
"""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

import hou  # type: ignore[import-not-found]

from scene_doctor.adapters.hou_adapter import HouGeometryAdapter, HouNodeAdapter
from scene_doctor.interfaces import PrimLike
from scene_doctor.report import SceneReport, report_to_csv_rows, report_to_json
from scene_doctor.rules import NamingRule, RuleFileError, load_naming_rules
from scene_doctor.ui.panel import SceneDoctorPanel
from scene_doctor_cli import build_report


class _EmptyGeometry:
    """表示SOPが取得できない場合に使う空のGeometryLikeフォールバック。"""

    def prims(self) -> Sequence[PrimLike]:
        return []


def _find_target_geo_node() -> "hou.Node | None":
    """/obj配下で表示フラグが立っている最初のgeoノードを検証対象とする。

    hou_adapter.load_scene()と同じ探索方針（v1の単純化した実装、README参照）だが、
    こちらは既に開いている現在のシーンに対して動作するため hou.hipFile.load() は行わない。
    """
    obj_level = hou.node("/obj")
    if obj_level is None:
        return None
    geo_nodes = [n for n in obj_level.children() if n.type().name() == "geo"]
    if not geo_nodes:
        return None
    return next((n for n in geo_nodes if n.isDisplayFlagSet()), geo_nodes[0])


def _default_rules_path() -> Path:
    """パネル起動元リポジトリ直下の rules/default.yaml を既定の命名規則ファイルとする。"""
    return Path(__file__).resolve().parents[2] / "rules" / "default.yaml"


def _load_naming_rules_safe() -> list[NamingRule]:
    rules_path = _default_rules_path()
    if not rules_path.exists():
        return []
    try:
        return load_naming_rules(rules_path)
    except RuleFileError as exc:
        hou.ui.displayMessage(f"Naming rules error: {exc}", severity=hou.severityType.Error)
        return []


def _run_checks() -> SceneReport:
    """SceneDoctorPanelの「Run Checks」ボタンから呼ばれる本番のcallback実装。"""
    target = _find_target_geo_node()
    if target is None:
        return SceneReport(
            hip_path=hou.hipFile.path(),
            generated_at="",
            violations=[],
        )

    display_sop = target.displayNode()
    geometry = display_sop.geometry() if display_sop is not None else None
    geo_adapter = HouGeometryAdapter(geometry) if geometry is not None else _EmptyGeometry()
    network_adapter = HouNodeAdapter(target)

    return build_report(
        hou.hipFile.path(),
        geo_adapter,
        network_adapter,
        _load_naming_rules_safe(),
    )


def _select_node(node_path: str) -> None:
    """SceneDoctorPanelの行クリックから呼ばれる本番のcallback実装。

    対象ノードを選択・カレント化し、ネットワークエディタでフレーミングする。
    """
    node = hou.node(node_path)
    if node is None:
        return

    node.setSelected(True, clear_all_selected=True)
    node.setCurrent(True, clear_all_selected=True)

    network_editor = hou.ui.paneTabOfType(hou.paneTabType.NetworkEditor)
    if network_editor is not None:
        network_editor.setCurrentNode(node)
        network_editor.homeToSelection()


def _export(fmt: str, out_path: str) -> None:
    """SceneDoctorPanelのExportボタンから呼ばれる本番のcallback実装。"""
    report = _run_checks()

    if not out_path:
        out_path = str(Path(hou.expandString("$HIP")) / "scene_doctor_report")

    path = Path(out_path)
    if fmt == "csv":
        import csv

        with path.with_suffix(".csv").open("w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerows(report_to_csv_rows(report))
    elif fmt == "json":
        path.with_suffix(".json").write_text(report_to_json(report), encoding="utf-8")
    else:
        raise ValueError(f"unsupported export format: {fmt!r}")


def launch_panel() -> SceneDoctorPanel:
    """SceneDoctorPanelを生成し、Houdiniメインウィンドウを親にして表示する。

    Houdiniの Python Shell または shelf tool から次のように呼び出す想定:

        from scene_doctor.adapters.houdini_panel_launch import launch_panel
        panel = launch_panel()

    `hou.qt.mainWindow()`をQDockWidgetのparentに渡し、独立したフローティングパネルとして
    表示する（Houdiniデスクトップへの正式なタブドッキングAPIは`hou.ui.curDesktop()`経由で
    バージョン差異があるため、hou.qt APIの正確な挙動は実機検証が必要。README参照）。
    """
    panel = SceneDoctorPanel(
        run_checks_callback=_run_checks,
        select_node_callback=_select_node,
        export_callback=_export,
        parent=hou.qt.mainWindow(),
    )
    panel.setFloating(True)
    panel.show()
    return panel
