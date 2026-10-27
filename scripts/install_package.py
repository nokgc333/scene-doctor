"""展開した配布物を、Houdini の package として登録する(標準ライブラリだけで動く)。

使い方: `python install_package.py --prefs <Houdini のユーザー設定フォルダ>`
  例(macOS): ~/Library/Preferences/houdini/22.0
  例(Windows): ~/Documents/houdini22.0
  例(Linux): ~/houdini22.0
`<prefs>/packages/scene_doctor.json` に、この配布物の場所を書き込む。消すときは、そのファイルを消す。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PLACEHOLDER = "@SCENE_DOCTOR_HOME@"
TEMPLATE = Path("packages") / "scene_doctor.json"


def render_package(template: str, home: Path) -> str:
    """テンプレートの目印を、配布物の場所に置き換える。Windows の `\\` も、JSON として正しく出す。"""
    escaped = json.dumps(str(home))[1:-1]
    return template.replace(PLACEHOLDER, escaped)


def install(home: Path, prefs: Path) -> Path:
    template = home / TEMPLATE
    if not template.is_file():
        raise FileNotFoundError(f"'{template}' not found: run this from the extracted release")
    target = prefs / "packages" / "scene_doctor.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    text = render_package(template.read_text(encoding="utf-8"), home)
    json.loads(text)
    target.write_text(text, encoding="utf-8")
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Register Scene Doctor as a Houdini package")
    parser.add_argument("--prefs", required=True, help="Houdini user preferences folder")
    args = parser.parse_args(argv)
    try:
        written = install(Path(__file__).resolve().parent, Path(args.prefs).expanduser())
    except (OSError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(f"installed: {written}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
