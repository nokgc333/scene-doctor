"""SceneDoctor HDAのPythonModuleセクション本体。

hou.phm()経由でパラメータのボタンコールバックから呼ばれる。
実処理は scene_doctor パッケージ（hou非依存のcheck関数群）に委譲し、
このモジュール自身は「hou.Node -> HouGeometryAdapter/HouNodeAdapter に変換して
build_reportを呼ぶ」薄いグルーコードに徹する（Ports & Adapters, ADR-0001）。
"""

import glob
import os
import sys

SCENE_DOCTOR_REPO = "/Users/naokikaneko/3dcg-dev/scene_doctor"


def _ensure_importable():
    if SCENE_DOCTOR_REPO not in sys.path:
        sys.path.insert(0, SCENE_DOCTOR_REPO)

    # scene_doctorパッケージ本体はHDA開発中に頻繁に更新されるため、
    # Houdiniプロセス側にキャッシュされた古いモジュールを毎回破棄してから
    # 再import する（本番運用では省略してよいが、開発中の事故を避けるため既定で有効にする）。
    for name in list(sys.modules):
        if name == "scene_doctor" or name.startswith("scene_doctor.") or name == "scene_doctor_cli":
            del sys.modules[name]

    # hython同梱のPythonにはPyYAMLが入っていないことが多い。
    # 本来はデプロイ時に `hython -m pip install pyyaml` 等で解決すべきだが、
    # 開発環境ではリポジトリの.venvのsite-packagesをフォールバックとして使う。
    try:
        import yaml  # noqa: F401
    except ImportError:
        candidates = glob.glob(
            os.path.join(SCENE_DOCTOR_REPO, ".venv", "lib", "python3.*", "site-packages")
        )
        for c in candidates:
            if c not in sys.path:
                sys.path.insert(0, c)


def _load_naming_rules(node):
    from pathlib import Path

    import hou as _hou

    from scene_doctor.rules import RuleFileError, load_naming_rules

    rules_path = node.evalParm("rules_path")
    if not rules_path:
        return []
    try:
        return load_naming_rules(Path(_hou.expandString(rules_path)))
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
        enable_geometry=node.evalParm("enable_geometry"),
        enable_nodes=node.evalParm("enable_nodes"),
        enable_naming=node.evalParm("enable_naming"),
        ngon_threshold=node.evalParm("ngon_threshold"),
        zero_area_epsilon=node.evalParm("zero_area_epsilon"),
        recurse_into_subnets=node.evalParm("recurse_subnets"),
    )
    return report


def run_checks(node):
    """Run All Checks ボタン: 検証を実行し、violation_count/resultsパラメータへ反映する。"""
    import hou as _hou

    try:
        report = _build(node)
    except Exception as exc:  # noqa: BLE001 - UIへ確実に伝えるため意図的に広く捕捉
        _hou.ui.displayMessage(f"Scene Doctor error: {exc}", severity=_hou.severityType.Error)
        return

    node.parm("violation_count").set(report.violation_count)
    lines = [f"{report.violation_count} violation(s) found in {report.hip_path}", ""]
    for v in report.violations:
        suffix = f" -> rename to '{v.rename_candidate}'" if v.rename_candidate else ""
        lines.append(f"[{v.check_type}] {v.target_path}: {v.message}{suffix}")
    node.parm("results").set("\n".join(lines))


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

    applied = 0
    for v in report.violations:
        if v.check_type != "naming" or not v.rename_candidate:
            continue
        target = _hou.node(v.target_path)
        if target is not None:
            target.setName(v.rename_candidate, unique_name=True)
            applied += 1

    _hou.ui.displayMessage(
        f"{applied}件のノード名を変更しました。再度 Run All Checks を推奨します。"
    )
