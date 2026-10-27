"""scene_doctor_cli.py のオプション・終了コード・出力のテスト(Houdini なしで動く)。"""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path, PureWindowsPath

import jsonschema
import pytest

import scene_doctor_cli as cli
from scene_doctor.report import (
    SceneReport,
    Severity,
    Violation,
    exceeds_threshold,
    report_to_common_json,
)
from tests.fakes import FakeGeometry, FakeNode, FakePrim

SCHEMA = json.loads(
    (Path(__file__).resolve().parents[1] / "docs/schema/common-report.schema.json").read_text(
        encoding="utf-8"
    )
)
EMPTY_RULES = "schema_version: 1\nproject_type: generic\nnaming_rules: []\n"


def _violation(severity: Severity, check: str = "ngon", candidate: str | None = None) -> Violation:
    return Violation(check, "12", "msg", severity, candidate)


def _hip(tmp_path: Path) -> Path:
    hip = tmp_path / "scene.hip"
    hip.touch()
    return hip


def _rules(tmp_path: Path, text: str = EMPTY_RULES) -> Path:
    path = tmp_path / "rules.yaml"
    path.write_text(text, encoding="utf-8")
    return path


@pytest.fixture
def scene(monkeypatch: pytest.MonkeyPatch):
    def install(geo: FakeGeometry, network: FakeNode) -> None:
        module = types.ModuleType("scene_doctor.adapters.hou_adapter")
        module.load_scene = lambda hip: (geo, network)  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "scene_doctor.adapters.hou_adapter", module)

    return install


def _bad_scene() -> tuple[FakeGeometry, FakeNode]:
    geo = FakeGeometry([FakePrim(_point_ids=[0, 1, 2, 3, 4, 5], _area=1.0)])
    return geo, FakeNode("/obj/geo1", "geo1", _type_name="geo")


class TestOutsideHoudini:
    def test_without_hou_the_command_explains_and_exits_with_15(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delitem(sys.modules, "scene_doctor.adapters.hou_adapter", raising=False)
        monkeypatch.setitem(sys.modules, "hou", None)

        code = cli.main(["--hip", str(_hip(tmp_path)), "--rules", str(_rules(tmp_path))])

        err = capsys.readouterr().err
        assert code == cli.EXIT_HOU_UNAVAILABLE == 15
        assert "hython" in err
        assert "--list-rules" in err
        assert "Traceback" not in err

    def test_a_missing_module_other_than_hou_is_not_hidden(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def broken(hip: Path) -> None:
            raise ModuleNotFoundError("No module named 'yaml'", name="yaml")

        module = types.ModuleType("scene_doctor.adapters.hou_adapter")
        module.load_scene = broken  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "scene_doctor.adapters.hou_adapter", module)

        with pytest.raises(ModuleNotFoundError, match="yaml"):
            cli.main(["--hip", str(_hip(tmp_path)), "--rules", str(_rules(tmp_path))])

    def test_a_missing_hip_is_reported_before_the_hou_check(self, tmp_path: Path) -> None:
        assert cli.main(["--hip", str(tmp_path / "none.hip")]) == cli.EXIT_HIP_NOT_FOUND


class TestListRules:
    def test_it_lists_the_bundled_rules_without_houdini(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code = cli.main(["--list-rules"])

        out = capsys.readouterr().out
        assert code == 0
        assert "naming rule(s) in" in out
        assert "[" in out

    def test_a_given_rules_file_is_listed_with_its_template(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        rules = _rules(
            tmp_path,
            "schema_version: 1\nproject_type: x\nnaming_rules:\n"
            "  - pattern: '^geo_'\n    applies_to: geo\n    description: d\n"
            "    rename_template: 'geo_{seq:03d}'\n",
        )

        cli.main(["--list-rules", "--rules", str(rules)])

        assert "[geo] ^geo_  d -> geo_{seq:03d}" in capsys.readouterr().out

    def test_a_broken_rules_file_exits_13(self, tmp_path: Path) -> None:
        assert cli.main(["--list-rules", "--rules", str(_rules(tmp_path, "x: 1\n"))]) == 13

    def test_list_rules_does_not_need_a_hip(self) -> None:
        assert cli.main(["--list-rules"]) == 0

    def test_without_hip_or_list_rules_it_is_a_parameter_error(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert cli.main([]) == cli.EXIT_INVALID_PARAMETER
        assert "--hip is required" in capsys.readouterr().err


class TestFailOn:
    @pytest.mark.parametrize(
        ("severities", "fail_on", "expected"),
        [
            ([], "warning", False),
            ([Severity.WARNING], "warning", True),
            ([Severity.WARNING], "error", False),
            ([Severity.ERROR], "error", True),
            ([Severity.WARNING, Severity.ERROR], "error", True),
            ([Severity.ERROR], "never", False),
            ([], "never", False),
        ],
    )
    def test_the_threshold(self, severities: list[Severity], fail_on: str, expected: bool) -> None:
        report = SceneReport("x", "t", [_violation(s) for s in severities])

        assert exceeds_threshold(report, fail_on) is expected

    def test_the_cli_exit_code_follows_fail_on(self, tmp_path: Path, scene) -> None:
        scene(*_bad_scene())
        base = ["--hip", str(_hip(tmp_path)), "--rules", str(_rules(tmp_path)), "--force"]

        default = cli.main([*base, "--out", str(tmp_path / "a")])
        never = cli.main([*base, "--out", str(tmp_path / "b"), "--fail-on", "never"])

        assert default == cli.EXIT_VIOLATIONS_FOUND
        assert never == cli.EXIT_NO_VIOLATIONS


class TestOverwrite:
    def test_an_existing_report_is_not_overwritten_without_force(
        self, tmp_path: Path, scene, capsys: pytest.CaptureFixture[str]
    ) -> None:
        scene(FakeGeometry([]), FakeNode("/obj/geo1", "geo1"))
        out = tmp_path / "out"
        out.with_suffix(".json").write_text("precious", encoding="utf-8")

        code = cli.main(
            ["--hip", str(_hip(tmp_path)), "--rules", str(_rules(tmp_path)), "--out", str(out)]
        )

        assert code == cli.EXIT_OUTPUT_EXISTS == 16
        assert out.with_suffix(".json").read_text(encoding="utf-8") == "precious"
        assert "--force" in capsys.readouterr().err

    def test_nothing_is_written_when_one_of_the_files_exists(self, tmp_path: Path, scene) -> None:
        scene(FakeGeometry([]), FakeNode("/obj/geo1", "geo1"))
        out = tmp_path / "out"
        out.with_suffix(".csv").write_text("precious", encoding="utf-8")

        cli.main(
            ["--hip", str(_hip(tmp_path)), "--rules", str(_rules(tmp_path)), "--out", str(out)]
        )

        assert not out.with_suffix(".json").exists()

    def test_force_overwrites(self, tmp_path: Path, scene) -> None:
        scene(FakeGeometry([]), FakeNode("/obj/geo1", "geo1"))
        out = tmp_path / "out"
        out.with_suffix(".json").write_text("old", encoding="utf-8")

        code = cli.main(
            [
                "--hip",
                str(_hip(tmp_path)),
                "--rules",
                str(_rules(tmp_path)),
                "--out",
                str(out),
                "--force",
            ]
        )

        assert code == 0
        assert (
            json.loads(out.with_suffix(".json").read_text(encoding="utf-8"))["violation_count"] == 0
        )

    def test_a_first_run_needs_no_force(self, tmp_path: Path, scene) -> None:
        scene(FakeGeometry([]), FakeNode("/obj/geo1", "geo1"))

        code = cli.main(
            [
                "--hip",
                str(_hip(tmp_path)),
                "--rules",
                str(_rules(tmp_path)),
                "--out",
                str(tmp_path / "fresh"),
            ]
        )

        assert code == 0

    def test_an_unwritable_output_exits_14(self, tmp_path: Path, scene) -> None:
        scene(FakeGeometry([]), FakeNode("/obj/geo1", "geo1"))

        code = cli.main(
            [
                "--hip",
                str(_hip(tmp_path)),
                "--rules",
                str(_rules(tmp_path)),
                "--out",
                str(tmp_path / "no" / "such" / "dir" / "out"),
            ]
        )

        assert code == cli.EXIT_OUTPUT_NOT_WRITABLE


class TestOutputsAndVerbosity:
    def test_quiet_hides_the_summary(
        self, tmp_path: Path, scene, capsys: pytest.CaptureFixture[str]
    ) -> None:
        scene(FakeGeometry([]), FakeNode("/obj/geo1", "geo1"))

        cli.main(
            [
                "-q",
                "--hip",
                str(_hip(tmp_path)),
                "--rules",
                str(_rules(tmp_path)),
                "--out",
                str(tmp_path / "o"),
            ]
        )

        assert capsys.readouterr().out == ""

    def test_verbose_prints_progress_to_stderr_only(
        self, tmp_path: Path, scene, capsys: pytest.CaptureFixture[str]
    ) -> None:
        scene(FakeGeometry([]), FakeNode("/obj/geo1", "geo1"))

        cli.main(
            [
                "-v",
                "--hip",
                str(_hip(tmp_path)),
                "--rules",
                str(_rules(tmp_path)),
                "--out",
                str(tmp_path / "o"),
            ]
        )

        captured = capsys.readouterr()
        assert "opening" in captured.err and "running checks" in captured.err
        assert "violation(s) found" in captured.out
        assert "opening" not in captured.out

    def test_quiet_and_verbose_cannot_be_combined(self) -> None:
        with pytest.raises(SystemExit):
            cli.main(["-q", "-v", "--list-rules"])

    @pytest.mark.parametrize(
        ("fmt", "suffixes"),
        [
            ("json", [".json"]),
            ("csv", [".csv"]),
            ("common", [".common.json"]),
            ("both", [".json", ".csv"]),
            ("all", [".json", ".csv", ".common.json"]),
        ],
    )
    def test_each_format_writes_exactly_its_files(
        self, tmp_path: Path, fmt: str, suffixes: list[str]
    ) -> None:
        out = tmp_path / "r"
        cli.write_report(SceneReport("x", "2026-10-28T00:00:00Z"), out, fmt)

        assert sorted(p.name for p in tmp_path.iterdir()) == sorted(f"r{s}" for s in suffixes)
        assert [p.name for p in cli.output_files(out, fmt)] == [f"r{s}" for s in suffixes]


class TestCommonReport:
    def test_the_output_matches_the_shared_schema(self) -> None:
        report = SceneReport(
            "/s/a.hip",
            "2026-10-28T00:00:00Z",
            [_violation(Severity.WARNING), _violation(Severity.ERROR, "naming", "geo_001")],
        )

        payload = json.loads(report_to_common_json(report))

        jsonschema.validate(payload, SCHEMA)
        assert payload["tool"] == "scene-doctor"
        assert payload["subject"] == "/s/a.hip"
        assert payload["has_errors"] is True

    def test_an_empty_report_validates_and_has_no_errors(self) -> None:
        payload = json.loads(report_to_common_json(SceneReport("a", "2026-10-28T00:00:00Z")))

        jsonschema.validate(payload, SCHEMA)
        assert payload["has_errors"] is False and payload["findings"] == []

    def test_the_rename_candidate_is_kept_in_the_message(self) -> None:
        report = SceneReport("a", "t", [_violation(Severity.WARNING, "naming", "geo_001")])

        finding = json.loads(report_to_common_json(report))["findings"][0]

        assert finding["rule"] == "naming"
        assert finding["message"].endswith("(rename candidate: geo_001)")

    def test_a_windows_path_survives_the_round_trip(self) -> None:
        path = str(PureWindowsPath("C:/Users/artist/シーン/scene.hip"))

        payload = json.loads(report_to_common_json(SceneReport(path, "2026-10-28T00:00:00Z")))

        assert payload["subject"] == path
        jsonschema.validate(payload, SCHEMA)


class TestHelp:
    def test_the_help_ends_with_the_exit_code_table(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with pytest.raises(SystemExit):
            cli.main(["--help"])

        out = capsys.readouterr().out
        for code, _ in cli.EXIT_CODE_TABLE:
            assert f"  {code:>2}  " in out

    def test_every_exit_code_constant_is_in_the_table(self) -> None:
        names = [n for n in dir(cli) if n.startswith("EXIT_") and n != "EXIT_CODE_TABLE"]
        constants = {getattr(cli, n) for n in names}

        assert constants == {code for code, _ in cli.EXIT_CODE_TABLE}
