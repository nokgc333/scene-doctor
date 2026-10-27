"""配布物(zip・Houdini package・インストーラー)と、版・CHANGELOG の整合のテスト。"""

from __future__ import annotations

import json
import tomllib
import zipfile
from pathlib import Path

import pytest

from scripts import build_release, install_package

ROOT = Path(__file__).resolve().parent.parent


def _version() -> str:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"][
        "version"
    ]


@pytest.fixture(scope="module")
def names(tmp_path_factory: pytest.TempPathFactory) -> list[str]:
    archive = build_release.build(ROOT, tmp_path_factory.mktemp("dist"))
    with zipfile.ZipFile(archive) as zf:
        return zf.namelist()


class TestReleaseZip:
    def test_everything_lives_under_one_top_level_folder(self, names: list[str]) -> None:
        prefix = f"scene-doctor-{_version()}/"

        assert all(n.startswith(prefix) for n in names)

    @pytest.mark.parametrize(
        "member",
        [
            "scene_doctor_cli.py",
            "install_package.py",
            "scene_doctor/report.py",
            "scene_doctor/checks/quality.py",
            "rules/default.yaml",
            "otls/SceneDoctor.hdalc",
            "pdg/run_scene_doctor_source.py",
            "packages/scene_doctor.json",
            "vendor/yaml/__init__.py",
            "vendor/LICENSE.PyYAML",
            "LICENSE",
            "README.md",
            "CHANGELOG.md",
        ],
    )
    def test_the_needed_files_are_included(self, names: list[str], member: str) -> None:
        assert f"scene-doctor-{_version()}/{member}" in names

    def test_nothing_unneeded_is_included(self, names: list[str]) -> None:
        bad = [n for n in names if "__pycache__" in n or n.endswith((".pyc", ".so", ".hip"))]

        assert bad == []

    def test_no_user_home_path_is_embedded_in_text_files(
        self, tmp_path: Path, names: list[str]
    ) -> None:
        archive = build_release.build(ROOT, tmp_path)
        with zipfile.ZipFile(archive) as zf:
            for name in names:
                if name.endswith((".py", ".json", ".yaml", ".md")):
                    assert b"/Users/" not in zf.read(name), name


class TestVersioning:
    def test_the_changelog_has_an_entry_for_the_current_version(self) -> None:
        changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")

        assert f"## [{_version()}]" in changelog

    def test_the_package_version_matches_the_project_version(self) -> None:
        import scene_doctor

        assert scene_doctor.__version__ == _version()


class TestInstaller:
    def test_the_package_file_points_at_the_install_folder(self, tmp_path: Path) -> None:
        text = install_package.render_package(
            (ROOT / "packages" / "scene_doctor.json").read_text(encoding="utf-8"), tmp_path
        )
        data = json.loads(text)

        assert data["path"] == str(tmp_path)
        assert {"SCENE_DOCTOR_HOME": str(tmp_path)} in data["env"]
        assert "@" not in text

    def test_windows_style_backslashes_stay_valid_json(self) -> None:
        text = install_package.render_package(
            '{"path": "@SCENE_DOCTOR_HOME@"}', Path("C:\\tools\\scene-doctor")
        )

        assert json.loads(text)["path"] == str(Path("C:\\tools\\scene-doctor"))

    def test_install_writes_the_file_into_the_packages_folder(self, tmp_path: Path) -> None:
        home = tmp_path / "home"
        home.mkdir()
        (home / "packages").mkdir()
        (home / "packages" / "scene_doctor.json").write_text(
            '{"path": "@SCENE_DOCTOR_HOME@"}', encoding="utf-8"
        )
        prefs = tmp_path / "houdini22.0"

        written = install_package.install(home, prefs)

        assert written == prefs / "packages" / "scene_doctor.json"
        assert json.loads(written.read_text(encoding="utf-8"))["path"] == str(home)

    def test_install_refuses_a_folder_without_the_template(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            install_package.install(tmp_path, tmp_path / "prefs")
