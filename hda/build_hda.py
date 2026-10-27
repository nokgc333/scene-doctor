"""SceneDoctor.hdalc を、パラメータとボタンつきで、一から作る。

使い方: `hython hda/build_hda.py`

HDA(.hdalc)はバイナリで、差分が読めないため、中身を作るこのスクリプトと、PythonModule の
ソース(hda/python_module_source.py)を正本とする(ADR-0005: ベースは subnet)。
パラメーター: enable_geometry / enable_nodes / enable_naming / ngon_threshold /
zero_area_epsilon / recurse_subnets / rules_path と、ボタン(Run / Export / Apply Rename)、
結果(violation_count / results)。
"""

from pathlib import Path

import hou

HERE = Path(__file__).resolve().parent
HDA_PATH = HERE / "SceneDoctor.hdalc"
SOURCE_PATH = HERE / "python_module_source.py"
OPERATOR = "scene_doctor::SceneDoctor::1.0"
LABEL = "Scene Doctor"
DEFAULT_RULES = "$SCENE_DOCTOR_HOME/rules/default.yaml"


def callback(function: str) -> str:
    return f"hou.phm().{function}(kwargs['node'])"


def parm_templates() -> hou.ParmTemplateGroup:
    group = hou.ParmTemplateGroup()
    group.append(hou.ToggleParmTemplate("enable_geometry", "Geometry Checks", default_value=True))
    group.append(hou.ToggleParmTemplate("enable_nodes", "Node Checks", default_value=True))
    group.append(hou.ToggleParmTemplate("enable_naming", "Naming Checks", default_value=True))
    group.append(
        hou.IntParmTemplate(
            "ngon_threshold", "N-gon Threshold", 1, default_value=(5,), min=3, max=64
        )
    )
    group.append(
        hou.FloatParmTemplate(
            "zero_area_epsilon", "Zero Area Epsilon", 1, default_value=(1e-6,), min=0.0, max=1.0
        )
    )
    group.append(
        hou.ToggleParmTemplate("recurse_subnets", "Recurse Into Subnets", default_value=True)
    )
    group.append(
        hou.StringParmTemplate(
            "rules_path",
            "Naming Rules",
            1,
            default_value=(DEFAULT_RULES,),
            string_type=hou.stringParmType.FileReference,
        )
    )
    for name, label, function in (
        ("run_checks", "Run All Checks", "run_checks"),
        ("export_report", "Export CSV/JSON", "export_report"),
        ("apply_rename", "Apply Rename Candidates", "apply_rename"),
    ):
        button = hou.ButtonParmTemplate(name, label)
        button.setScriptCallback(callback(function))
        button.setScriptCallbackLanguage(hou.scriptLanguage.Python)
        group.append(button)
    count = hou.IntParmTemplate("violation_count", "Violations", 1, default_value=(0,))
    count.setConditional(hou.parmCondType.DisableWhen, "{ violation_count >= 0 }")
    group.append(count)
    results = hou.StringParmTemplate("results", "Results", 1)
    results.setTags({"editor": "1", "editorlines": "12"})
    group.append(results)
    return group


def main() -> None:
    hou.hipFile.clear(suppress_save_prompt=True)
    geo = hou.node("/obj").createNode("geo", "hda_builder")
    subnet = geo.createNode("subnet", "scene_doctor")
    definition = (
        subnet.createDigitalAsset(
            name=OPERATOR,
            hda_file_name=str(HDA_PATH),
            description=LABEL,
            min_num_inputs=0,
            max_num_inputs=0,
            ignore_external_references=True,
        )
        .type()
        .definition()
    )
    definition.setParmTemplateGroup(parm_templates())
    definition.addSection("PythonModule", SOURCE_PATH.read_text(encoding="utf-8"))
    definition.setExtraFileOption("PythonModule/IsPython", True)
    definition.save(str(HDA_PATH))
    print(f"built {OPERATOR} -> {HDA_PATH}")


main()
