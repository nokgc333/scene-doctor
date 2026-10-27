"""SceneDoctor HDAのPythonModuleセクション本体。

hou.phm()経由でパラメータのボタンコールバックから呼ばれる。
実処理は scene_doctor パッケージ（hou非依存のcheck関数群）に委譲し、
このモジュール自身は「hou.Node -> HouGeometryAdapter/HouNodeAdapter に変換して
build_reportを呼ぶ」薄いグルーコードに徹する（Ports & Adapters, ADR-0001）。
"""

import os
import sys


def _ensure_importable():
    """配布物のルート($SCENE_DOCTOR_HOME。Houdini の package ファイルが設定する)を import パスに足す。"""
    home = os.environ.get("SCENE_DOCTOR_HOME")
    if not home:
        raise RuntimeError(
            "SCENE_DOCTOR_HOME is not set. Install the Scene Doctor Houdini package "
            "(see README: Houdini パッケージとしてのインストール)."
        )
    if home not in sys.path:
        sys.path.insert(0, home)

    # 開発中に scene_doctor を更新しても、Houdini が古いモジュールを持ち続けないよう、毎回破棄して再 import する。
    for name in list(sys.modules):
        if name == "scene_doctor" or name.startswith("scene_doctor.") or name == "scene_doctor_cli":
            del sys.modules[name]


def _load_naming_rules(node):
    import hou as _hou

    from scene_doctor.hda_support import rules_path_from_parm
    from scene_doctor.rules import RuleFileError, load_naming_rules

    rules_path = rules_path_from_parm(node.evalParm("rules_path"), _hou.expandString)
    if rules_path is None:
        return []
    try:
        return load_naming_rules(rules_path)
    except RuleFileError as exc:
        _hou.ui.displayMessage(f"Naming rules error: {exc}", severity=_hou.severityType.Error)
        return []


def _build(node):
    """現在のnode配下（親ネットワーク=兄弟ノード群）に対してレポートを構築する。"""
    _ensure_importable()
    # Python Module内では sys.modules['hou'] を経由せず、
    # 呼び出し時点で既にHoudini本体（hython/実プロセス）内で実行されているため
    # `import hou` がそのままネイティブに解決される（RPC越しの検証時とは異なる）。
    from scene_doctor.adapters.hou_adapter import HouGeometryAdapter, HouNodeAdapter
    from scene_doctor.hda_support import options_from_parms
    from scene_doctor_cli import build_report

    parent = node.parent()
    display_sop = parent.displayNode()
    geometry = display_sop.geometry() if display_sop is not None else None

    if geometry is not None:
        geo_adapter = HouGeometryAdapter(geometry)
    else:

        class _EmptyGeo:
            def prims(self):
                return []

        geo_adapter = _EmptyGeo()

    network_adapter = HouNodeAdapter(parent)
    naming_rules = _load_naming_rules(node)

    report = build_report(
        parent.path(),
        geo_adapter,
        network_adapter,
        naming_rules,
        **options_from_parms(node.evalParm),
    )
    return report


def run_checks(node):
    """Run All Checks ボタン: 検証を実行し、violation_count/resultsパラメータへ反映する。"""
    import hou as _hou

    try:
        report = _build(node)
        from scene_doctor.hda_support import format_results
    except Exception as exc:  # noqa: BLE001 - UIへ確実に伝えるため意図的に広く捕捉
        _hou.ui.displayMessage(f"Scene Doctor error: {exc}", severity=_hou.severityType.Error)
        return

    node.parm("violation_count").set(report.violation_count)
    node.parm("results").set(format_results(report))


def export_report(node):
    """Export CSV/JSON ボタン: 直近の検証結果を $HIP/report.csv, report.json に出力する。"""
    from pathlib import Path

    import hou as _hou

    from scene_doctor_cli import write_report

    try:
        report = _build(node)
    except Exception as exc:  # noqa: BLE001
        _hou.ui.displayMessage(f"Scene Doctor error: {exc}", severity=_hou.severityType.Error)
        return

    out_path = Path(_hou.expandString("$HIP/report"))
    write_report(report, out_path, "both")
    node.parm("violation_count").set(report.violation_count)
    _hou.ui.displayMessage(f"Exported: {out_path}.json / {out_path}.csv")


def apply_rename(node):
    """Apply Rename Candidates ボタン: naming違反のリネーム候補を実際に適用する（要確認、SEC-003/ADR-0003）。"""
    import hou as _hou

    confirmed = _hou.ui.displayConfirmation(
        "リネーム候補をノード名に適用します。この操作はUndo可能です。よろしいですか？",
        severity=_hou.severityType.Warning,
    )
    if not confirmed:
        return

    try:
        report = _build(node)
    except Exception as exc:  # noqa: BLE001
        _hou.ui.displayMessage(f"Scene Doctor error: {exc}", severity=_hou.severityType.Error)
        return

    from scene_doctor.hda_support import rename_targets

    applied = 0
    for node_path, new_name in rename_targets(report):
        target = _hou.node(node_path)
        if target is not None:
            target.setName(new_name, unique_name=True)
            applied += 1

    _hou.ui.displayMessage(
        f"{applied}件のノード名を変更しました。再度 Run All Checks を推奨します。"
    )
