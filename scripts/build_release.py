"""配布用の zip を作る。`python scripts/build_release.py [出力フォルダ]`。

中身: Python の本体・規則・HDA(`otls/`)・PDG・package のテンプレートとインストーラー・PyYAML(純 Python)。
PyYAML は、`hython` に入っていないため同梱する。C 拡張は含めない(版ごとに違うため。無くても動く)。
"""

from __future__ import annotations

import sys
import tomllib
import zipfile
from pathlib import Path

import yaml

TOP_LEVEL_FILES = ("scene_doctor_cli.py", "LICENSE", "README.md", "CHANGELOG.md")


def _version(root: Path) -> str:
    data = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    return str(data["project"]["version"])


def _python_files(folder: Path) -> list[Path]:
    return sorted(p for p in folder.rglob("*.py") if "__pycache__" not in p.parts)


def release_members(root: Path) -> list[tuple[Path, str]]:
    """(元のファイル, zip の中の相対パス)の一覧。"""
    members: list[tuple[Path, str]] = [(root / name, name) for name in TOP_LEVEL_FILES]
    members.append((root / "scripts" / "install_package.py", "install_package.py"))
    members.append((root / "packages" / "scene_doctor.json", "packages/scene_doctor.json"))
    members.append((root / "hda" / "SceneDoctor.hdalc", "otls/SceneDoctor.hdalc"))
    for folder in ("scene_doctor",):
        members += [(p, p.relative_to(root).as_posix()) for p in _python_files(root / folder)]
    members += [
        (p, p.relative_to(root).as_posix()) for p in sorted((root / "rules").glob("*.yaml"))
    ]
    members += [
        (p, p.relative_to(root).as_posix()) for p in sorted((root / "pdg").glob("*_source.py"))
    ]
    yaml_dir = Path(yaml.__file__).resolve().parent
    members += [(p, f"vendor/yaml/{p.name}") for p in sorted(yaml_dir.glob("*.py"))]
    members.append((_pyyaml_license(yaml_dir), "vendor/LICENSE.PyYAML"))
    return members


def _pyyaml_license(yaml_dir: Path) -> Path:
    for dist in yaml_dir.parent.glob("[Pp]y[Yy][Aa][Mm][Ll]-*.dist-info"):
        for candidate in (dist / "licenses" / "LICENSE", dist / "LICENSE"):
            if candidate.is_file():
                return candidate
    raise FileNotFoundError("PyYAML's LICENSE was not found next to the installed package")


def build(root: Path, out_dir: Path) -> Path:
    version = _version(root)
    top = f"scene-doctor-{version}"
    out_dir.mkdir(parents=True, exist_ok=True)
    archive = out_dir / f"{top}.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
        for source, relative in release_members(root):
            zf.write(source, f"{top}/{relative}")
    return archive


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else root / "dist"
    print(build(root, out))


if __name__ == "__main__":
    main()
