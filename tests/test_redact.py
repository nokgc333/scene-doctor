"""レポートのパスから、利用者名(ホームフォルダ)を除くテスト。"""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path

import pytest

import scene_doctor_cli as cli
from scene_doctor.report import SceneReport, Severity, Violation, redact_home, redacted
from tests.fakes import FakeGeometry, FakeNode


class TestRedactHome:
    def test_the_home_prefix_becomes_a_tilde(self) -> None:
        assert redact_home("/Users/artist/proj/a.hip", "/Users/artist") == "~/proj/a.hip"

    def test_windows_separators_are_handled_in_both_directions(self) -> None:
        assert redact_home("C:\\Users\\artist\\p\\a.hip", "C:/Users/artist") == "~\\p\\a.hip"
        assert redact_home("C:/Users/artist/p/a.hip", "C:\\Users\\artist") == "~/p/a.hip"

    def test_text_without_the_home_is_unchanged(self) -> None:
        assert redact_home("/obj/geo1", "/Users/artist") == "/obj/geo1"

    def test_an_empty_home_changes_nothing(self) -> None:
        assert redact_home("/a/b", "") == "/a/b"

    def test_every_occurrence_in_a_message_is_replaced(self) -> None:
        text = "see /Users/artist/a and /Users/artist/b"

        assert redact_home(text, "/Users/artist") == "see ~/a and ~/b"


class TestRedactedReport:
    def _report(self) -> SceneReport:
        return SceneReport(
            "/Users/artist/p/a.hip",
            "t",
            [
                Violation(
                    "naming",
                    "/obj/geo1",
                    "path /Users/artist/cache/x.bgeo is missing",
                    Severity.WARNING,
                    "geo_001",
                )
            ],
        )

    def test_the_hip_path_and_messages_are_redacted(self) -> None:
        report = redacted(self._report(), "/Users/artist")

        assert report.hip_path == "~/p/a.hip"
        assert report.violations[0].message == "path ~/cache/x.bgeo is missing"

    def test_other_fields_are_kept(self) -> None:
        violation = redacted(self._report(), "/Users/artist").violations[0]

        assert (violation.check_type, violation.severity, violation.rename_candidate) == (
            "naming",
            Severity.WARNING,
            "geo_001",
        )

    def test_the_original_report_is_not_modified(self) -> None:
        original = self._report()

        redacted(original, "/Users/artist")

        assert original.hip_path == "/Users/artist/p/a.hip"


def test_the_cli_option_redacts_the_written_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    module = types.ModuleType("scene_doctor.adapters.hou_adapter")
    module.load_scene = lambda hip: (FakeGeometry([]), FakeNode("/obj/geo1", "geo1"))
    monkeypatch.setitem(sys.modules, "scene_doctor.adapters.hou_adapter", module)
    hip = tmp_path / "scene.hip"
    hip.touch()
    rules = tmp_path / "r.yaml"
    rules.write_text("schema_version: 1\nproject_type: x\nnaming_rules: []\n", encoding="utf-8")
    out = tmp_path / "out"

    cli.main(["--hip", str(hip), "--rules", str(rules), "--out", str(out), "--redact-home"])

    written = json.loads(out.with_suffix(".json").read_text(encoding="utf-8"))
    assert written["hip_path"].startswith("~")
    assert str(tmp_path) not in out.with_suffix(".json").read_text(encoding="utf-8")


def test_without_the_option_the_full_path_is_kept(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = types.ModuleType("scene_doctor.adapters.hou_adapter")
    module.load_scene = lambda hip: (FakeGeometry([]), FakeNode("/obj/geo1", "geo1"))
    monkeypatch.setitem(sys.modules, "scene_doctor.adapters.hou_adapter", module)
    hip = tmp_path / "scene.hip"
    hip.touch()
    rules = tmp_path / "r.yaml"
    rules.write_text("schema_version: 1\nproject_type: x\nnaming_rules: []\n", encoding="utf-8")
    out = tmp_path / "out"

    cli.main(["--hip", str(hip), "--rules", str(rules), "--out", str(out)])

    payload = json.loads(out.with_suffix(".json").read_text(encoding="utf-8"))
    assert payload["hip_path"].startswith(str(tmp_path))
