"""CLI の `--usd` / `--lop` / `--skip` と、build_report への新しい検査の組み込みのテスト。"""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path

import pytest

import scene_doctor_cli as cli
from scene_doctor.report import Severity
from tests.fakes import FakeGeometry, FakeNode, FakePrim

EMPTY_RULES = "schema_version: 1\nproject_type: generic\nnaming_rules: []\n"


def _rules(tmp_path: Path) -> Path:
    path = tmp_path / "rules.yaml"
    path.write_text(EMPTY_RULES, encoding="utf-8")
    return path


class TestBuildReportIntegration:
    def test_a_geometry_without_the_new_methods_still_works(self) -> None:
        geo = FakeGeometry([FakePrim(_point_ids=[0, 1, 2])])
        network = FakeNode("/obj/geo1", "geo1", _type_name="geo", _display_flag=True)

        report = cli.build_report("x.hip", geo, network, [])

        assert [v.check_type for v in report.violations] == []

    def test_quality_checks_run_when_the_geometry_supports_them(self) -> None:
        class UvPrim(FakePrim):
            def has_uv(self) -> bool:
                return False

        geo = FakeGeometry([UvPrim(_point_ids=[0, 1, 2])])
        network = FakeNode("/obj/geo1", "geo1", _type_name="geo", _display_flag=True)

        report = cli.build_report("x.hip", geo, network, [])

        assert "missing_uv" in [v.check_type for v in report.violations]

    def test_quality_checks_can_be_switched_off(self) -> None:
        class UvPrim(FakePrim):
            def has_uv(self) -> bool:
                return False

        geo = FakeGeometry([UvPrim(_point_ids=[0, 1, 2])])
        network = FakeNode("/obj/geo1", "geo1", _type_name="geo", _display_flag=True)

        report = cli.build_report("x.hip", geo, network, [], enable_quality=False)

        assert report.violations == []

    def test_duplicate_points_and_normals_are_checked_when_available(self) -> None:
        class Geo(FakeGeometry):
            def point_positions(self) -> list[tuple[float, float, float]]:
                return [(0, 0, 0), (0, 0, 0)]

        network = FakeNode("/obj/geo1", "geo1", _type_name="geo", _display_flag=True)

        report = cli.build_report("x.hip", Geo([]), network, [])

        assert [v.check_type for v in report.violations] == ["duplicate_point"]

    def test_the_cache_path_check_uses_the_injected_existence_function(self) -> None:
        class FileNode(FakeNode):
            def file_paths(self) -> list[tuple[str, str, str]]:
                return [("file", "$HIP/a.bgeo", "/proj/a.bgeo")]

        child = FileNode(
            "/obj/geo1/f", "f", _type_name="file", _output_connections=[], _display_flag=True
        )
        network = FakeNode("/obj/geo1", "geo1", _type_name="geo", _children=[child])

        missing = cli.build_report(
            "x.hip", FakeGeometry([]), network, [], path_exists=lambda p: False
        )
        present = cli.build_report(
            "x.hip", FakeGeometry([]), network, [], path_exists=lambda p: True
        )

        assert [v.check_type for v in missing.violations] == ["missing_file"]
        assert present.violations == []
        assert missing.violations[0].severity == Severity.ERROR

    def test_references_can_be_switched_off(self) -> None:
        class FileNode(FakeNode):
            def file_paths(self) -> list[tuple[str, str, str]]:
                return [("file", "$HIP/a.bgeo", "/proj/a.bgeo")]

        child = FileNode("/obj/geo1/f", "f", _type_name="file", _display_flag=True)
        network = FakeNode("/obj/geo1", "geo1", _type_name="geo", _children=[child])

        report = cli.build_report(
            "x.hip",
            FakeGeometry([]),
            network,
            [],
            enable_references=False,
            path_exists=lambda p: False,
        )

        assert report.violations == []


class TestSkipOption:
    def test_a_skipped_check_does_not_run(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        geo = FakeGeometry([FakePrim(_point_ids=[0, 1, 2, 3, 4, 5], _area=1.0)])
        module = types.ModuleType("scene_doctor.adapters.hou_adapter")
        module.load_scene = lambda hip: (
            geo,
            FakeNode("/obj/geo1", "geo1", _type_name="geo", _display_flag=True),
        )
        monkeypatch.setitem(sys.modules, "scene_doctor.adapters.hou_adapter", module)
        hip = tmp_path / "s.hip"
        hip.touch()
        base = ["--hip", str(hip), "--rules", str(_rules(tmp_path))]

        cli.main([*base, "--out", str(tmp_path / "a"), "--format", "json"])
        cli.main([*base, "--out", str(tmp_path / "b"), "--format", "json", "--skip", "geometry"])

        with_ngon = json.loads((tmp_path / "a.json").read_text(encoding="utf-8"))
        without = json.loads((tmp_path / "b.json").read_text(encoding="utf-8"))
        assert with_ngon["violation_count"] == 1
        assert without["violation_count"] == 0

    def test_several_checks_can_be_skipped(self) -> None:
        args = cli._build_arg_parser().parse_args(
            ["--hip", "x", "--skip", "nodes", "--skip", "naming"]
        )

        assert args.skip == ["nodes", "naming"]


pxr = pytest.importorskip("pxr")

from pxr import Usd, UsdGeom  # noqa: E402


def _usd(tmp_path: Path, with_mesh: bool = True) -> Path:
    path = tmp_path / "scene.usda"
    stage = Usd.Stage.CreateNew(str(path))
    root = UsdGeom.Xform.Define(stage, "/root")
    stage.SetDefaultPrim(root.GetPrim())
    if with_mesh:
        UsdGeom.Mesh.Define(stage, "/root/m")
    stage.GetRootLayer().Save()
    return path


class TestUsdMode:
    def test_a_usd_file_is_checked_without_houdini(self, tmp_path: Path) -> None:
        usd = _usd(tmp_path)

        code = cli.main(["--usd", str(usd), "--out", str(tmp_path / "r"), "--format", "json"])

        report = json.loads((tmp_path / "r.json").read_text(encoding="utf-8"))
        assert code == cli.EXIT_VIOLATIONS_FOUND
        assert {v["check_type"] for v in report["violations"]} == {"usd_no_material", "usd_no_uv"}
        assert report["hip_path"] == str(usd)

    def test_a_clean_usd_file_exits_zero(self, tmp_path: Path) -> None:
        usd = _usd(tmp_path, with_mesh=False)

        assert cli.main(["--usd", str(usd), "--out", str(tmp_path / "r")]) == 0

    def test_the_default_output_name_follows_the_usd_file(self, tmp_path: Path) -> None:
        usd = _usd(tmp_path, with_mesh=False)

        cli.main(["--usd", str(usd), "--format", "json"])

        assert (tmp_path / "scene_report.json").is_file()

    def test_a_missing_usd_file_is_exit_10(self, tmp_path: Path) -> None:
        assert cli.main(["--usd", str(tmp_path / "none.usda")]) == cli.EXIT_HIP_NOT_FOUND

    def test_a_broken_usd_file_is_a_parameter_error_without_a_traceback(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        broken = tmp_path / "b.usda"
        broken.write_text("not usd", encoding="utf-8")

        code = cli.main(["--usd", str(broken), "--out", str(tmp_path / "r")])

        assert code == cli.EXIT_INVALID_PARAMETER
        assert "Traceback" not in capsys.readouterr().err

    def test_lop_needs_hip(self, capsys: pytest.CaptureFixture[str]) -> None:
        code = cli.main(["--lop", "/stage/out"])

        assert code == cli.EXIT_INVALID_PARAMETER

    def test_a_lop_node_of_a_hip_is_checked_through_the_adapter(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        stage = Usd.Stage.CreateInMemory()
        UsdGeom.Mesh.Define(stage, "/m")
        module = types.ModuleType("scene_doctor.adapters.hou_adapter")
        module.load_lop_stage = lambda hip, node: stage
        monkeypatch.setitem(sys.modules, "scene_doctor.adapters.hou_adapter", module)
        hip = tmp_path / "s.hip"
        hip.touch()

        code = cli.main(
            [
                "--hip",
                str(hip),
                "--lop",
                "/stage/out",
                "--out",
                str(tmp_path / "r"),
                "--format",
                "json",
            ]
        )

        kinds = {
            v["check_type"]
            for v in json.loads((tmp_path / "r.json").read_text(encoding="utf-8"))["violations"]
        }
        assert code == cli.EXIT_VIOLATIONS_FOUND
        assert "usd_no_material" in kinds

    def test_a_lop_check_outside_houdini_explains_how_to_run_it(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.delitem(sys.modules, "scene_doctor.adapters.hou_adapter", raising=False)
        monkeypatch.setitem(sys.modules, "hou", None)
        hip = tmp_path / "s.hip"
        hip.touch()

        code = cli.main(["--hip", str(hip), "--lop", "/stage/out", "--out", str(tmp_path / "r")])

        assert code == cli.EXIT_HOU_UNAVAILABLE
        assert "hython" in capsys.readouterr().err

    def test_a_usd_report_follows_the_shared_schema(self, tmp_path: Path) -> None:
        import jsonschema

        schema = json.loads(
            (
                Path(__file__).resolve().parents[1] / "docs/schema/common-report.schema.json"
            ).read_text(encoding="utf-8")
        )
        usd = _usd(tmp_path)

        cli.main(["--usd", str(usd), "--out", str(tmp_path / "r"), "--format", "common"])

        jsonschema.validate(
            json.loads((tmp_path / "r.common.json").read_text(encoding="utf-8")), schema
        )


class TestRemainingCliPaths:
    def test_lop_without_hip_is_an_invalid_parameter(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        usd = tmp_path / "a.usda"
        usd.write_text("#usda 1.0\n", encoding="utf-8")

        code = cli.main(
            ["--usd", str(usd), "--lop", "/stage/out", "--rules", str(_rules(tmp_path))]
        )

        assert code == cli.EXIT_INVALID_PARAMETER
        assert "--lop needs --hip" in capsys.readouterr().err

    def test_a_missing_pxr_module_gives_guidance_and_exit_15(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        usd = tmp_path / "a.usda"
        usd.write_text("#usda 1.0\n", encoding="utf-8")
        monkeypatch.delitem(sys.modules, "scene_doctor.checks.usd_stage", raising=False)
        monkeypatch.setitem(sys.modules, "pxr", None)

        code = cli.main(["--usd", str(usd), "--rules", str(_rules(tmp_path))])

        assert code == cli.EXIT_HOU_UNAVAILABLE
        assert "pip install usd-core" in capsys.readouterr().err

    def test_lop_without_houdini_gives_the_hython_guidance(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        pytest.importorskip("pxr")
        hip = tmp_path / "a.hip"
        hip.write_text("x", encoding="utf-8")
        monkeypatch.delitem(sys.modules, "scene_doctor.adapters.hou_adapter", raising=False)
        monkeypatch.setitem(sys.modules, "hou", None)

        code = cli.main(
            ["--hip", str(hip), "--lop", "/stage/out", "--rules", str(_rules(tmp_path))]
        )

        assert code == cli.EXIT_HOU_UNAVAILABLE
        assert "hython" in capsys.readouterr().err

    def test_a_value_error_from_the_checks_is_an_invalid_parameter(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        hip = tmp_path / "a.hip"
        hip.write_text("x", encoding="utf-8")
        module = types.ModuleType("scene_doctor.adapters.hou_adapter")
        module.load_scene = lambda _p: (  # type: ignore[attr-defined]
            FakeGeometry([]),
            FakeNode("/obj/geo1", "geo1", _type_name="geo"),
        )
        monkeypatch.setitem(sys.modules, "scene_doctor.adapters.hou_adapter", module)

        def boom(*_a: object, **_k: object) -> None:
            raise ValueError("bad value")

        monkeypatch.setattr(cli, "build_report", boom)

        code = cli.main(["--hip", str(hip), "--rules", str(_rules(tmp_path))])

        assert code == cli.EXIT_INVALID_PARAMETER
        assert "bad value" in capsys.readouterr().err

    def test_a_target_that_is_not_a_sop_network_exits_with_its_own_code(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        hip = tmp_path / "a.hip"
        hip.write_text("x", encoding="utf-8")
        module = types.ModuleType("scene_doctor.adapters.hou_adapter")
        module.load_scene = lambda _p: (  # type: ignore[attr-defined]
            FakeGeometry([]),
            FakeNode("/obj/cam1", "cam1", _type_name="cam"),
        )
        monkeypatch.setitem(sys.modules, "scene_doctor.adapters.hou_adapter", module)

        code = cli.main(["--hip", str(hip), "--rules", str(_rules(tmp_path))])

        assert code == cli.EXIT_INVALID_TARGET_NODE
        assert "Error" in capsys.readouterr().err
