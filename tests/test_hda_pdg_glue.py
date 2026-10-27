"""HDA の PythonModule と PDG の Python Script TOP の糊のコードを、偽の hou / work_item で動かすテスト。"""

from __future__ import annotations

import importlib.util
import json
import runpy
import subprocess
import sys
import types
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from tests.fake_hou import FakeHouGeometry, FakeHouNode, FakeHouPrim, make_fake_hou

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _clean_modules() -> Iterator[None]:
    saved_hou = sys.modules.get("hou")
    saved_path = list(sys.path)
    yield
    sys.path[:] = saved_path
    if saved_hou is None:
        sys.modules.pop("hou", None)
    else:
        sys.modules["hou"] = saved_hou


class FakeParm:
    def __init__(self) -> None:
        self.value: Any = None

    def set(self, value: Any) -> None:
        self.value = value


class FakeHdaNode:
    def __init__(self, parent: FakeHouNode, values: dict[str, Any]) -> None:
        self._parent = parent
        self._values = values
        self.parms: dict[str, FakeParm] = {}

    def parent(self) -> FakeHouNode:
        return self._parent

    def evalParm(self, name: str) -> Any:  # noqa: N802
        return self._values[name]

    def parm(self, name: str) -> FakeParm:
        return self.parms.setdefault(name, FakeParm())


def _hou_with_ui() -> tuple[types.ModuleType, list[str]]:
    hou = make_fake_hou()
    messages: list[str] = []
    hou.ui = types.SimpleNamespace(  # type: ignore[attr-defined]
        displayMessage=lambda text, **kw: messages.append(text),
        displayConfirmation=lambda text, **kw: True,
    )
    severities = types.SimpleNamespace(Error="error", Warning="warning")
    hou.severityType = severities  # type: ignore[attr-defined]
    hou.expandString = lambda s: s.replace("$HIP", "/proj")  # type: ignore[attr-defined]
    hou.text = types.SimpleNamespace(expandString=hou.expandString)  # type: ignore[attr-defined]
    return hou, messages


def _load_hda_module() -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(
        "hda_source", ROOT / "hda" / "python_module_source.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _scene() -> tuple[FakeHouNode, dict[str, FakeHouNode]]:
    sop = FakeHouNode("/obj/geo1/BadName", type_name="box", category="Sop", flags={})
    sop.display_node = types.SimpleNamespace(
        geometry=lambda: FakeHouGeometry([FakeHouPrim([0, 1, 2, 3, 4, 5], area=1.0)])
    )
    parent = FakeHouNode(
        "/obj/geo1",
        category="Object",
        child_category="Sop",
        children=[sop],
        flags={"display": True},
    )
    parent.display_node = sop.display_node
    return parent, {"/obj/geo1": parent, "/obj/geo1/BadName": sop}


PARMS = {
    "enable_geometry": 1,
    "enable_nodes": 1,
    "enable_naming": 0,
    "ngon_threshold": 5,
    "zero_area_epsilon": 1e-6,
    "recurse_subnets": 1,
    "rules_path": "",
}


class TestHdaModule:
    def test_without_the_home_variable_the_error_says_how_to_install(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("SCENE_DOCTOR_HOME", raising=False)
        module = _load_hda_module()

        with pytest.raises(RuntimeError, match="SCENE_DOCTOR_HOME is not set"):
            module._ensure_importable()

    def test_the_home_is_put_on_the_import_path(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SCENE_DOCTOR_HOME", str(ROOT))
        module = _load_hda_module()

        module._ensure_importable()

        assert str(ROOT) in sys.path

    def test_run_checks_writes_the_count_and_the_result_text(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SCENE_DOCTOR_HOME", str(ROOT))
        hou, messages = _hou_with_ui()
        sys.modules["hou"] = hou
        parent, nodes = _scene()
        hou.node = lambda path: nodes.get(path)  # type: ignore[attr-defined]
        module = _load_hda_module()
        node = FakeHdaNode(parent, PARMS)

        module.run_checks(node)

        assert node.parms["violation_count"].value >= 1
        assert "[ngon]" in node.parms["results"].value
        assert messages == []

    def test_an_exception_is_shown_to_the_user_not_raised(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("SCENE_DOCTOR_HOME", raising=False)
        hou, messages = _hou_with_ui()
        sys.modules["hou"] = hou
        parent, _ = _scene()
        module = _load_hda_module()

        module.run_checks(FakeHdaNode(parent, PARMS))

        assert messages and "SCENE_DOCTOR_HOME" in messages[0]

    def test_export_writes_both_files_next_to_the_hip(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv("SCENE_DOCTOR_HOME", str(ROOT))
        hou, messages = _hou_with_ui()
        hou.expandString = lambda s: s.replace("$HIP", str(tmp_path))  # type: ignore[attr-defined]
        sys.modules["hou"] = hou
        parent, _ = _scene()
        module = _load_hda_module()

        module.export_report(FakeHdaNode(parent, PARMS))

        written = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
        assert written["violation_count"] >= 1
        assert (tmp_path / "report.csv").is_file()
        assert messages and "Exported" in messages[0]

    def test_apply_rename_renames_only_nodes_with_candidates(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SCENE_DOCTOR_HOME", str(ROOT))
        hou, messages = _hou_with_ui()
        sys.modules["hou"] = hou
        parent, nodes = _scene()
        hou.node = lambda path: nodes.get(path)  # type: ignore[attr-defined]
        module = _load_hda_module()
        values = {**PARMS, "enable_naming": 1, "enable_geometry": 0, "enable_nodes": 0}
        rules = ROOT / "rules" / "default.yaml"
        values["rules_path"] = str(rules)

        module.apply_rename(FakeHdaNode(parent, values))

        renamed = [c for c in nodes["/obj/geo1/BadName"].calls if c[0] == "setName"]
        assert all(c[2] == {"unique_name": True} for c in renamed)
        assert messages and "件のノード名を変更しました" in messages[0]

    def test_a_declined_confirmation_changes_nothing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SCENE_DOCTOR_HOME", str(ROOT))
        hou, messages = _hou_with_ui()
        hou.ui.displayConfirmation = lambda *a, **k: False
        sys.modules["hou"] = hou
        parent, nodes = _scene()
        module = _load_hda_module()

        module.apply_rename(FakeHdaNode(parent, PARMS))

        assert messages == []
        assert nodes["/obj/geo1/BadName"].calls == []


class FakeWorkItem:
    def __init__(self, directory: str, filename: str) -> None:
        self._attribs = {"directory": directory, "filename": filename}
        self.strings: dict[str, str] = {}
        self.ints: dict[str, int] = {}
        self.outputs: list[tuple[str, str]] = []

    def attribValue(self, name: str) -> str:  # noqa: N802
        return self._attribs[name]

    def setStringAttrib(self, name: str, index: int, value: str) -> None:  # noqa: N802
        self.strings[name] = value

    def setIntAttrib(self, name: str, index: int, value: int) -> None:  # noqa: N802
        self.ints[name] = value

    def addOutputFile(self, path: str, tag: str = "") -> None:  # noqa: N802
        self.outputs.append((path, tag))


def _run_pdg(name: str, work_item: Any) -> dict[str, Any]:
    return runpy.run_path(str(ROOT / "pdg" / name), init_globals={"work_item": work_item})


class TestPdgScripts:
    def test_the_run_script_launches_the_cli_without_a_shell_and_records_the_result(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        hou, _ = _hou_with_ui()
        hou.text.expandString = lambda s: (
            str(tmp_path / "hfs") if s == "$HFS" else str(tmp_path / "hip")
        )
        sys.modules["hou"] = hou
        monkeypatch.setenv("SCENE_DOCTOR_HOME", str(ROOT))
        monkeypatch.setenv("SCENE_DOCTOR_REPORTS", str(tmp_path / "reports"))
        sys.path.insert(0, str(ROOT))
        calls: list[dict[str, Any]] = []

        def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
            calls.append({"command": command, **kwargs})
            return subprocess.CompletedProcess(
                command, 1, stdout="2 violation(s) found.", stderr=""
            )

        monkeypatch.setattr(subprocess, "run", fake_run)
        item = FakeWorkItem("/shots", "a b.hip")

        _run_pdg("run_scene_doctor_source.py", item)

        assert Path(calls[0]["command"][0]).parts[-2:-1] == ("bin",)
        assert calls[0]["command"][calls[0]["command"].index("--hip") + 1] == str(
            Path("/shots") / "a b.hip"
        )
        assert "shell" not in calls[0] or calls[0]["shell"] is False
        assert item.ints["scd_exitcode"] == 1
        assert item.outputs == [(str(tmp_path / "reports" / "a b_hip_report.json"), "file/json")]
        assert (tmp_path / "reports").is_dir()

    def test_an_error_exit_code_fails_the_work_item(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        hou, _ = _hou_with_ui()
        sys.modules["hou"] = hou
        monkeypatch.setenv("SCENE_DOCTOR_HOME", str(ROOT))
        monkeypatch.setenv("SCENE_DOCTOR_REPORTS", str(tmp_path))
        sys.path.insert(0, str(ROOT))
        monkeypatch.setattr(
            subprocess, "run", lambda c, **k: subprocess.CompletedProcess(c, 12, "", "no hou")
        )

        with pytest.raises(RuntimeError, match="exit=12"):
            _run_pdg("run_scene_doctor_source.py", FakeWorkItem("/s", "a.hip"))

    def test_the_aggregate_script_writes_json_and_csv_from_the_individual_reports(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        hou, _ = _hou_with_ui()
        sys.modules["hou"] = hou
        monkeypatch.setenv("SCENE_DOCTOR_REPORTS", str(tmp_path))
        sys.path.insert(0, str(ROOT))
        for name, count in (("a_hip_report.json", 1), ("b_hip_report.json", 0)):
            (tmp_path / name).write_text(
                json.dumps(
                    {
                        "hip_path": name,
                        "violation_count": count,
                        "violations": [
                            {
                                "check_type": "ngon",
                                "target_path": "1",
                                "message": "m",
                                "severity": "warning",
                                "rename_candidate": None,
                            }
                        ][:count],
                    }
                ),
                encoding="utf-8",
            )
        item = FakeWorkItem("", "")

        _run_pdg("aggregate_reports_source.py", item)

        aggregate = json.loads((tmp_path / "aggregate_report.json").read_text(encoding="utf-8"))
        assert aggregate["total_files"] == 2
        assert aggregate["total_violation_count"] == 1
        assert (tmp_path / "aggregate_report.csv").is_file()
        assert [t for _, t in item.outputs] == ["file/json", "file/csv"]

    def test_a_previous_aggregate_is_not_counted_again(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        hou, _ = _hou_with_ui()
        sys.modules["hou"] = hou
        monkeypatch.setenv("SCENE_DOCTOR_REPORTS", str(tmp_path))
        sys.path.insert(0, str(ROOT))
        (tmp_path / "aggregate_report.json").write_text("{}", encoding="utf-8")

        _run_pdg("aggregate_reports_source.py", FakeWorkItem("", ""))

        aggregate = json.loads((tmp_path / "aggregate_report.json").read_text(encoding="utf-8"))
        assert aggregate["total_files"] == 0


def test_no_source_script_contains_a_personal_absolute_path() -> None:
    for relative in (
        "hda/python_module_source.py",
        "pdg/run_scene_doctor_source.py",
        "pdg/aggregate_reports_source.py",
        "scene_doctor/adapters/houdini_panel_launch.py",
    ):
        text = (ROOT / relative).read_text(encoding="utf-8")
        assert "/Users/" not in text, relative
