"""scene_doctor_cli.py の write_report / main() のテスト（hou非依存）。"""

import json
import sys
import types
from pathlib import Path

import pytest

import scene_doctor_cli
from scene_doctor.report import SceneReport, Severity, Violation
from tests.fakes import FakeGeometry, FakeNode


def test_write_report_writes_both_formats_by_default(tmp_path: Path) -> None:
    report = SceneReport(
        hip_path="/tmp/x.hip",
        generated_at="2026-09-07T00:00:00Z",
        violations=[
            Violation(
                check_type="naming",
                target_path="/obj/geo1/box1",
                message="bad name",
                severity=Severity.WARNING,
            )
        ],
    )
    out_base = tmp_path / "x_report"

    scene_doctor_cli.write_report(report, out_base, "both")

    json_payload = json.loads(out_base.with_suffix(".json").read_text(encoding="utf-8"))
    assert json_payload["violation_count"] == 1
    csv_text = out_base.with_suffix(".csv").read_text(encoding="utf-8")
    assert "naming" in csv_text


def test_write_report_json_only_does_not_create_csv(tmp_path: Path) -> None:
    report = SceneReport(hip_path="/tmp/x.hip", generated_at="2026-09-07T00:00:00Z")
    out_base = tmp_path / "x_report"

    scene_doctor_cli.write_report(report, out_base, "json")

    assert out_base.with_suffix(".json").exists()
    assert not out_base.with_suffix(".csv").exists()


@pytest.fixture
def fake_hou_adapter_module(monkeypatch: pytest.MonkeyPatch):
    """sys.modulesに偽のhou_adapterを注入し、main()をhou非依存でテスト可能にする。"""

    def _install(geo, network):
        module = types.ModuleType("scene_doctor.adapters.hou_adapter")
        module.load_scene = lambda hip_path: (geo, network)  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "scene_doctor.adapters.hou_adapter", module)

    return _install


def test_main_reports_no_violations_and_exits_zero(tmp_path: Path, fake_hou_adapter_module) -> None:
    hip = tmp_path / "good.hip"
    hip.touch()
    rules_path = tmp_path / "rules.yaml"
    rules_path.write_text(
        "schema_version: 1\nproject_type: generic\nnaming_rules: []\n", encoding="utf-8"
    )
    fake_hou_adapter_module(FakeGeometry([]), FakeNode("/obj/geo1", "geo1", _type_name="geo"))

    exit_code = scene_doctor_cli.main(
        ["--hip", str(hip), "--rules", str(rules_path), "--out", str(tmp_path / "out")]
    )

    assert exit_code == scene_doctor_cli.EXIT_NO_VIOLATIONS


def test_main_missing_hip_file_returns_e001(tmp_path: Path) -> None:
    exit_code = scene_doctor_cli.main(["--hip", str(tmp_path / "missing.hip")])

    assert exit_code == scene_doctor_cli.EXIT_HIP_NOT_FOUND


def test_main_invalid_rules_file_returns_e004(tmp_path: Path) -> None:
    hip = tmp_path / "scene.hip"
    hip.touch()
    rules_path = tmp_path / "broken.yaml"
    rules_path.write_text("schema_version: 1\n", encoding="utf-8")

    exit_code = scene_doctor_cli.main(["--hip", str(hip), "--rules", str(rules_path)])

    assert exit_code == scene_doctor_cli.EXIT_RULE_FILE_ERROR
