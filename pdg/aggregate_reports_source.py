"""PDG Python Script TOP: aggregate_reports（仕様書§10.1）。

各ワークアイテムが書き出した個別JSONレポートを読み込み、統合レポート
(aggregate_report.json / .csv)を同じフォルダに生成する。
Wait For All の後段で「Once per Batch」として1回だけ実行される。

出力先は、run_scene_doctor と同じ(環境変数 SCENE_DOCTOR_REPORTS、既定は $HIP/scene_doctor_reports)。
"""

import glob
import json
import os
from pathlib import Path

import hou

from scene_doctor.pdg_support import aggregate_csv, aggregate_reports

out_dir = Path(
    os.environ.get("SCENE_DOCTOR_REPORTS") or hou.text.expandString("$HIP/scene_doctor_reports")
)

sources = sorted(
    p for p in glob.glob(str(out_dir / "*_report.json")) if "aggregate_report" not in p
)
loaded = []
for path in sources:
    with open(path, "r", encoding="utf-8") as f:
        loaded.append((path, json.load(f)))

aggregate = aggregate_reports(loaded)

(out_dir / "aggregate_report.json").write_text(
    json.dumps(aggregate, ensure_ascii=False, indent=2), encoding="utf-8"
)
(out_dir / "aggregate_report.csv").write_text(
    aggregate_csv(aggregate), encoding="utf-8", newline=""
)

work_item.addOutputFile(str(out_dir / "aggregate_report.json"), tag="file/json")
work_item.addOutputFile(str(out_dir / "aggregate_report.csv"), tag="file/csv")
print(f"Aggregated {len(sources)} reports, {aggregate['total_violation_count']} total violations")
