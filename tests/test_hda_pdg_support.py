"""hda_support.py / pdg_support.py(hou に依存しない部分)のテスト。"""

from __future__ import annotations

import csv
import io
from pathlib import Path

import pytest

from scene_doctor.hda_support import (
    HOME_VARIABLE,
    default_home,
    format_results,
    options_from_parms,
    rename_targets,
    rules_path_from_parm,
    scene_doctor_home,
)
from scene_doctor.pdg_support import (
    CSV_HEADER,
    aggregate_csv,
    aggregate_reports,
    build_cli_command,
    is_failure,
    report_base_name,
)
from scene_doctor.report import SceneReport, Severity, Violation


def _violation(check: str, path: str, candidate: str | None = None) -> Violation:
    return Violation(
        check_type=check,
        target_path=path,
        message="msg",
        severity=Severity.WARNING,
        rename_candidate=candidate,
    )


class TestHome:
    def test_the_environment_variable_wins(self, tmp_path: Path) -> None:
        assert scene_doctor_home({HOME_VARIABLE: "/opt/sd"}, tmp_path) == Path("/opt/sd")

    def test_the_fallback_is_used_without_it(self, tmp_path: Path) -> None:
        assert scene_doctor_home({}, tmp_path) == tmp_path

    def test_an_empty_value_counts_as_unset(self, tmp_path: Path) -> None:
        assert scene_doctor_home({HOME_VARIABLE: ""}, tmp_path) == tmp_path

    def test_the_default_home_is_the_repository_root(self) -> None:
        assert (default_home() / "scene_doctor_cli.py").is_file()


class TestOptionsFromParms:
    def test_every_parm_is_mapped_to_the_matching_build_report_argument(self) -> None:
        values = {
            "enable_geometry": 1,
            "enable_nodes": 0,
            "enable_naming": 1,
            "ngon_threshold": 6.0,
            "zero_area_epsilon": 1,
            "recurse_subnets": 0,
        }

        options = options_from_parms(values.__getitem__)

        assert options == {
            "enable_geometry": True,
            "enable_nodes": False,
            "enable_naming": True,
            "ngon_threshold": 6,
            "zero_area_epsilon": 1.0,
            "recurse_into_subnets": False,
        }
        assert isinstance(options["ngon_threshold"], int)
        assert isinstance(options["zero_area_epsilon"], float)

    def test_the_names_are_accepted_by_build_report(self) -> None:
        import inspect

        from scene_doctor_cli import build_report

        values = {
            "enable_geometry": 1,
            "enable_nodes": 1,
            "enable_naming": 1,
            "ngon_threshold": 5,
            "zero_area_epsilon": 1e-6,
            "recurse_subnets": 1,
        }

        accepted = set(inspect.signature(build_report).parameters)

        assert set(options_from_parms(values.__getitem__)) <= accepted


class TestFormatResults:
    def test_the_first_line_counts_the_violations_and_names_the_file(self) -> None:
        report = SceneReport("/obj/geo1", "t", [_violation("ngon", "12")])

        assert format_results(report).splitlines()[0] == "1 violation(s) found in /obj/geo1"

    def test_a_violation_line_has_the_check_the_target_and_the_message(self) -> None:
        report = SceneReport("x", "t", [_violation("ngon", "12")])

        assert "[ngon] 12: msg" in format_results(report).splitlines()

    def test_a_rename_candidate_is_appended(self) -> None:
        report = SceneReport("x", "t", [_violation("naming", "/obj/a", "geo_a_001")])

        assert "[naming] /obj/a: msg -> rename to 'geo_a_001'" in format_results(report)

    def test_no_violations_gives_only_the_header(self) -> None:
        assert format_results(SceneReport("x", "t")) == "0 violation(s) found in x\n"


class TestRenameTargets:
    def test_only_naming_violations_with_a_candidate_are_returned(self) -> None:
        report = SceneReport(
            "x",
            "t",
            [
                _violation("naming", "/obj/a", "geo_a"),
                _violation("naming", "/obj/b", None),
                _violation("ngon", "3", "ignored"),
            ],
        )

        assert rename_targets(report) == [("/obj/a", "geo_a")]


class TestRulesPath:
    def test_an_empty_value_means_no_rules(self) -> None:
        assert rules_path_from_parm("", str) is None

    def test_houdini_variables_are_expanded(self) -> None:
        assert rules_path_from_parm("$HIP/r.yaml", lambda s: s.replace("$HIP", "/proj")) == Path(
            "/proj/r.yaml"
        )


class TestPdg:
    def test_the_report_name_keeps_the_extension_so_hip_and_hiplc_do_not_collide(self) -> None:
        assert report_base_name("/s/a.hip") == "a_hip_report"
        assert report_base_name("/s/a.hiplc") == "a_hiplc_report"

    def test_the_command_is_a_list_of_strings_with_fixed_options(self, tmp_path: Path) -> None:
        command = build_cli_command(
            "/hfs/bin/hython", tmp_path, "/s/a b.hip", tmp_path / "r.yaml", "/o/x"
        )

        assert command[0] == "/hfs/bin/hython"
        assert command[1] == str(tmp_path / "scene_doctor_cli.py")
        assert command[command.index("--hip") + 1] == "/s/a b.hip"
        assert command[command.index("--format") + 1] == "json"
        assert all(isinstance(part, str) for part in command)

    def test_a_hostile_file_name_stays_one_argument(self, tmp_path: Path) -> None:
        command = build_cli_command("h", tmp_path, "a.hip; rm -x", tmp_path / "r.yaml", "/o/x")

        assert "a.hip; rm -x" in command

    @pytest.mark.parametrize(
        ("code", "failed"), [(0, False), (1, False), (10, True), (12, True), (2, True)]
    )
    def test_zero_and_one_are_not_failures(self, code: int, failed: bool) -> None:
        assert is_failure(code) is failed

    def _report(self, hip: str, count: int) -> tuple[str, dict]:  # type: ignore[type-arg]
        violations = [
            {
                "check_type": "ngon",
                "target_path": str(i),
                "message": "m",
                "severity": "warning",
                "rename_candidate": None,
            }
            for i in range(count)
        ]
        return (
            f"{hip}.json",
            {"hip_path": hip, "violation_count": count, "violations": violations},
        )

    def test_aggregation_counts_files_and_violations(self) -> None:
        aggregate = aggregate_reports([self._report("a.hip", 2), self._report("b.hip", 1)])

        assert aggregate["total_files"] == 2
        assert aggregate["total_violation_count"] == 3
        assert aggregate["per_file_counts"] == {"a.hip": 2, "b.hip": 1}
        assert aggregate["source_reports"] == ["a.hip.json", "b.hip.json"]
        assert {v["hip_path"] for v in aggregate["violations"]} == {"a.hip", "b.hip"}

    def test_aggregating_nothing_is_empty(self) -> None:
        aggregate = aggregate_reports([])

        assert aggregate["total_files"] == 0 and aggregate["violations"] == []

    def test_the_csv_has_the_shared_header_and_one_row_per_violation(self) -> None:
        aggregate = aggregate_reports([self._report("a.hip", 2)])

        rows = list(csv.reader(io.StringIO(aggregate_csv(aggregate))))

        assert rows[0] == CSV_HEADER
        assert len(rows) == 3
        assert rows[1][0] == "a.hip"
        assert rows[1][5] == ""

    def test_the_csv_header_matches_the_single_report_csv(self) -> None:
        from scene_doctor.report import CSV_HEADER as SINGLE_HEADER

        assert CSV_HEADER == SINGLE_HEADER
