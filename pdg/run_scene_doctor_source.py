"""PDG Python Script TOP: run_scene_doctor（仕様書§10.1）。

ワークアイテムごとに hython scene_doctor_cli.py を固定引数のサブプロセスとして起動する。
ワークアイテム由来の文字列（filename）は subprocess.run のリスト引数としてのみ渡し、
exec/eval には一切渡さない（SEC-002、CI静的チェック対象）。

場所は、環境変数で決める(利用者のパスを書かない):
  SCENE_DOCTOR_HOME     配布物のルート(Houdini の package ファイルが設定する)
  SCENE_DOCTOR_REPORTS  レポートの出力先(既定: $HIP/scene_doctor_reports)
hython は、実行中の Houdini の `$HFS/bin/hython`。
"""

import os
import subprocess
from pathlib import Path

import hou

from scene_doctor.pdg_support import (
    build_cli_command,
    is_failure,
    report_base_name,
)

home = Path(os.environ["SCENE_DOCTOR_HOME"])
hython = os.path.join(hou.text.expandString("$HFS"), "bin", "hython")
reports_dir = Path(
    os.environ.get("SCENE_DOCTOR_REPORTS") or hou.text.expandString("$HIP/scene_doctor_reports")
)
reports_dir.mkdir(parents=True, exist_ok=True)

hip_path = str(Path(work_item.attribValue("directory")) / work_item.attribValue("filename"))
out_path = str(reports_dir / report_base_name(hip_path))

result = subprocess.run(
    build_cli_command(hython, home, hip_path, home / "rules" / "default.yaml", out_path),
    capture_output=True,
    text=True,
    timeout=60,
)

work_item.setStringAttrib("scd_stdout", 0, result.stdout[-2000:])
work_item.setStringAttrib("scd_stderr", 0, result.stderr[-2000:])
work_item.setIntAttrib("scd_exitcode", 0, result.returncode)

# exit code規約(仕様書§5.6): 0=違反なし / 1=違反あり は正常終了。10番台はエラー。
if is_failure(result.returncode):
    raise RuntimeError(
        f"scene_doctor_cli failed for '{hip_path}' (exit={result.returncode}): "
        f"{result.stderr[-500:]}"
    )

work_item.addOutputFile(out_path + ".json", tag="file/json")
