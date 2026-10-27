"""Houdini 実機の検証。`hython scripts/verify_houdini.py` で実行する。

結果は 1 行 1 項目の `CHECK <名前> <PASS|FAIL> <詳細>`。記録は docs/verification/ に、版ごとに残す。
検証するもの: アダプタ(実 hou)・CLI・HDA の PythonModule・共通レポート形式。
"""

import json
import os
import sys
import tempfile
from pathlib import Path

import hou

ROOT = Path(__file__).resolve().parent.parent
os.environ["SCENE_DOCTOR_HOME"] = str(ROOT)
sys.path.insert(0, str(ROOT))


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"CHECK {name} {'PASS' if ok else 'FAIL'} {detail}")


def build_scene(hip_path: Path) -> None:
    hou.hipFile.clear(suppress_save_prompt=True)
    geo = hou.node("/obj").createNode("geo", "BadGeoName")
    box = geo.createNode("box", "box1")
    circle = geo.createNode("circle", "ngon1")
    circle.parm("type").set(1)
    circle.parm("divs").set(8)
    merge = geo.createNode("merge", "geo_merge")
    merge.setInput(0, box)
    merge.setInput(1, circle)
    merge.setDisplayFlag(True)
    merge.setRenderFlag(True)
    geo.createNode("null", "orphan_null")
    geo.createNode("xform", "TransformBad")
    hou.hipFile.save(str(hip_path))


def main() -> None:
    print(f"HOUDINI_VERSION {hou.applicationVersionString()}")
    print(f"PYTHON_VERSION {sys.version.split()[0]}")
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        hip = work / "scene.hip"
        build_scene(hip)

        import scene_doctor_cli

        code = scene_doctor_cli.main(
            ["--hip", str(hip), "--out", str(work / "r"), "--format", "all"]
        )
        check("cli_exits_with_violations_found", code == 1, f"exit={code}")
        payload = json.loads((work / "r.json").read_text(encoding="utf-8"))
        kinds = {v["check_type"] for v in payload["violations"]}
        check("ngon_is_detected", "ngon" in kinds, str(sorted(kinds)))
        check("unconnected_node_is_detected", "unconnected_node" in kinds, "")
        check(
            "naming_violation_has_a_rename_candidate",
            any(
                v["check_type"] == "naming" and v["rename_candidate"] for v in payload["violations"]
            ),
            "",
        )
        common = json.loads((work / "r.common.json").read_text(encoding="utf-8"))
        check(
            "common_report_has_the_shared_shape",
            common["schema_version"] == "1"
            and common["tool"] == "scene-doctor"
            and isinstance(common["findings"], list),
            common["subject"],
        )

        again = scene_doctor_cli.main(["--hip", str(hip), "--out", str(work / "r")])
        check("existing_report_is_not_overwritten_without_force", again == 16, f"exit={again}")

        hou.hipFile.load(str(hip), suppress_save_prompt=True)
        hou.hda.installFile(str(ROOT / "hda" / "SceneDoctor.hdalc"))
        geo = hou.node("/obj/BadGeoName")
        sop_types = hou.sopNodeTypeCategory().nodeTypes()
        type_name = next(n for n in sop_types if "scenedoctor" in n.lower())
        print(f"HDA_TYPE {type_name}")
        doctor = geo.createNode(type_name, "scene_doctor1")
        report = doctor.hdaModule()._build(doctor)
        print(f"HDA_REPORT violations={report.violation_count}")
        doctor.hdaModule().run_checks(doctor)
        count = doctor.parm("violation_count").eval()
        results = doctor.parm("results").eval()
        check("hda_run_checks_fills_the_count", count >= 2, f"count={count}")
        check("hda_results_text_lists_violations", "[ngon]" in results, results.splitlines()[0])
        check(
            "hda_has_no_hardcoded_user_path",
            "/Users/"
            not in hou.hda.definitionsInFile(str(ROOT / "hda" / "SceneDoctor.hdalc"))[0]
            .sections()["PythonModule"]
            .contents(),
            "",
        )


main()
