"""PDG Python Script TOP: aggregate_reports（仕様書§10.1）。

各ワークアイテムが pdg/reports/ に書き出した個別JSONレポートを読み込み、
統合レポート（pdg/reports/aggregate_report.json / .csv）を生成する。
Wait For All の後段で「Once per Batch」として1回だけ実行される。
"""

import csv
import glob
import json
from pathlib import Path

OUT_DIR = "/Users/naokikaneko/3dcg-dev/scene_doctor/pdg/reports"

individual_reports = sorted(glob.glob(f"{OUT_DIR}/*_report.json"))
individual_reports = [p for p in individual_reports if "aggregate_report" not in p]

all_violations = []
per_file_counts = {}
for path in individual_reports:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    hip_path = data["hip_path"]
    per_file_counts[hip_path] = data["violation_count"]
    for v in data["violations"]:
        all_violations.append({"hip_path": hip_path, **v})

aggregate = {
    "source_reports": individual_reports,
    "total_files": len(individual_reports),
    "total_violation_count": len(all_violations),
    "per_file_counts": per_file_counts,
    "violations": all_violations,
}

with open(f"{OUT_DIR}/aggregate_report.json", "w", encoding="utf-8") as f:
    json.dump(aggregate, f, ensure_ascii=False, indent=2)

with open(f"{OUT_DIR}/aggregate_report.csv", "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow(
        ["hip_path", "check_type", "target_path", "message", "severity", "rename_candidate"]
    )
    for v in all_violations:
        writer.writerow(
            [
                v["hip_path"],
                v["check_type"],
                v["target_path"],
                v["message"],
                v["severity"],
                v.get("rename_candidate") or "",
            ]
        )

work_item.addOutputFile(f"{OUT_DIR}/aggregate_report.json", tag="file/json")
work_item.addOutputFile(f"{OUT_DIR}/aggregate_report.csv", tag="file/csv")
print(f"Aggregated {len(individual_reports)} reports, {len(all_violations)} total violations")
