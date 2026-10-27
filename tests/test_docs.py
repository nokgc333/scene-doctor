"""README のリンク・画像と、ADR の連番が壊れていないことのテスト。"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LINK = re.compile(r"!?\[[^\]]*\]\(([^)\s]+)\)")


def _local_targets(markdown: Path) -> list[str]:
    targets = LINK.findall(markdown.read_text(encoding="utf-8"))
    return [t.split("#")[0] for t in targets if not t.startswith(("http", "#", "mailto:")) and t]


def test_every_relative_link_and_image_in_the_readme_exists() -> None:
    missing = [t for t in _local_targets(ROOT / "README.md") if not (ROOT / t).exists()]

    assert missing == []


def test_the_readme_has_an_image() -> None:
    assert "![" in (ROOT / "README.md").read_text(encoding="utf-8")


def test_adr_numbers_have_no_gaps() -> None:
    numbers = sorted(int(p.name[:4]) for p in (ROOT / "docs" / "adr").glob("[0-9]*.md"))

    assert numbers == list(range(1, len(numbers) + 1))


def test_every_adr_is_listed_in_the_readme() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    unlisted = [p.name for p in (ROOT / "docs" / "adr").glob("[0-9]*.md") if p.name not in readme]

    assert unlisted == []
