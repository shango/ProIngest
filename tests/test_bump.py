"""build/bump.py: every version place moves together, or none does."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from build import bump

REPO = Path(__file__).resolve().parent.parent


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    for name in {place[0] for place in bump.PLACES}:
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(REPO / name, tmp_path / name)
    return tmp_path


def test_the_real_tree_holds_every_place_once() -> None:
    old = bump.current()
    for name, pattern, times in bump.PLACES:
        assert (REPO / name).read_text(encoding="utf-8").count(pattern.format(v=old)) == times, name


def test_next_patch() -> None:
    assert bump.next_patch("0.5.55") == "0.5.56"
    assert bump.next_patch("1.2.9") == "1.2.10"


def test_bump_moves_every_place(tree: Path) -> None:
    bump.bump("9.9.9", tree)
    assert bump.current(tree) == "9.9.9"
    for name, pattern, times in bump.PLACES:
        assert (tree / name).read_text(encoding="utf-8").count(pattern.format(v="9.9.9")) == times


def test_a_stale_place_writes_nothing(tree: Path) -> None:
    lock = tree / "uv.lock"
    lock.write_text(lock.read_text(encoding="utf-8").replace('name = "proingest"', 'name = "x"'))
    before = (tree / "pyproject.toml").read_text(encoding="utf-8")
    with pytest.raises(SystemExit, match=r"uv\.lock"):
        bump.bump("9.9.9", tree)
    assert (tree / "pyproject.toml").read_text(encoding="utf-8") == before
