"""PDG Python Script TOP: run_scene_doctor（仕様書§10.1）。

ワークアイテムごとに hython scene_doctor_cli.py を固定引数のサブプロセスとして起動する。
ワークアイテム由来の文字列（filename）は subprocess.run のリスト引数としてのみ渡し、
exec/eval には一切渡さない（SEC-002、CI静的チェック対象）。
"""

import subprocess
from pathlib import Path

HYTHON = (
    "/Users/naokikaneko/Library/Application Support/Steam/steamapps/common/"
    "Houdini Indie/Frameworks/Houdini.framework/Versions/22.0/Resources/bin/hython"
)
SCENE_DOCTOR_DIR = "/Users/naokikaneko/3dcg-dev/scene_doctor"
OUT_DIR = f"{SCENE_DOCTOR_DIR}/pdg/reports"

hip_path = str(Path(work_item.attribValue("directory")) / work_item.attribValue("filename"))
# stemだけだと同名で拡張子違い(.hip/.hiplc)が衝突するため、拡張子も出力名に含める。
out_path = f"{OUT_DIR}/{Path(hip_path).name.replace('.', '_')}_report"

result = subprocess.run(
    [
        HYTHON,
        f"{SCENE_DOCTOR_DIR}/scene_doctor_cli.py",
        "--hip",
        hip_path,
        "--rules",
        f"{SCENE_DOCTOR_DIR}/rules/default.yaml",
        "--out",
        out_path,
        "--format",
        "json",
    ],
    capture_output=True,
    text=True,
    timeout=60,
)

work_item.setStringAttrib("scd_stdout", 0, result.stdout[-2000:])
work_item.setStringAttrib("scd_stderr", 0, result.stderr[-2000:])
work_item.setIntAttrib("scd_exitcode", 0, result.returncode)

# exit code規約(仕様書§5.6): 0=違反なし / 1=違反あり は正常終了。10番台はエラー。
if result.returncode not in (0, 1):
    raise RuntimeError(
        f"scene_doctor_cli failed for '{hip_path}' (exit={result.returncode}): "
        f"{result.stderr[-500:]}"
    )

work_item.addOutputFile(out_path + ".json", tag="file/json")
