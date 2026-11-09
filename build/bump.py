"""Set the version everywhere it is written, so a release is one command.

    python build/bump.py            # the next patch: 0.5.55 -> 0.5.56
    python build/bump.py 0.6.0      # a stated version

The places are listed here and nowhere else. Each must hold the current version
exactly as many times as stated, or nothing is written: a count that is off means
the list has gone stale, and a half-bumped tree is worse than none.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# (file, text around the version with {v} standing for it, times it appears)
PLACES: tuple[tuple[str, str, int], ...] = (
    ("pyproject.toml", 'version = "{v}"', 1),
    ("proingest/__init__.py", '__version__ = "{v}"', 1),
    ("build/build.py", "ProIngest-Setup-{v}.exe", 1),
    ("build/build.py", "ProIngest-{v}.dmg", 1),
    ("docs/guide/install.md", "ProIngest-{v}.dmg", 1),
    ("docs/guide/install.md", "ProIngest-Setup-{v}.exe", 1),
    ("uv.lock", 'name = "proingest"\nversion = "{v}"', 1),
)


def current(root: Path = ROOT) -> str:
    text = (root / "proingest/__init__.py").read_text(encoding="utf-8")
    found = re.search(r'__version__ = "(\d+\.\d+\.\d+)"', text)
    if not found:
        raise SystemExit("no __version__ in proingest/__init__.py")
    return found.group(1)


def next_patch(version: str) -> str:
    major, minor, patch = version.split(".")
    return f"{major}.{minor}.{int(patch) + 1}"


def _read(path: Path) -> str:
    """The file's text with its line endings as they are on disk.

    `newline=""` on the read and the write both: without it a CRLF file comes back LF,
    and on Windows every LF file is written back CRLF (review, 2026-11-08).
    `Path.read_text` takes no `newline` before Python 3.13, hence `open`.
    """
    with path.open(encoding="utf-8", newline="") as handle:
        return handle.read()


def bump(new: str, root: Path = ROOT) -> list[str]:
    """Rewrite every place from the current version to `new`; returns the files changed."""
    if not re.fullmatch(r"\d+\.\d+\.\d+", new):
        raise SystemExit(f"not a version: {new}")
    old = current(root)
    texts: dict[str, str] = {}
    for name, pattern, times in PLACES:
        text = texts.get(name) or _read(root / name)
        before, after = pattern.format(v=old), pattern.format(v=new)
        if text.count(before) != times:
            raise SystemExit(f"{name}: expected {before!r} {times} time(s), found {text.count(before)}")
        texts[name] = text.replace(before, after)
    for name, text in texts.items():
        (root / name).write_text(text, encoding="utf-8", newline="")
    return sorted(texts)


def main(argv: list[str]) -> int:
    new = argv[1] if len(argv) > 1 else next_patch(current())
    old = current()
    for name in bump(new):
        print(f"{name}: {old} -> {new}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
