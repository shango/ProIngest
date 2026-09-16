"""The two shell scripts: `build/mac_build.sh` and `ProIngest.command`.

One builds the app from a fresh clone, the other runs the app out of the folder without
building anything. Neither can be type checked, neither is linted with the Python, and
nothing imports either - so a rename anywhere in `build/` leaves one naming a file that
is gone and nothing says so until somebody is sitting at the Mac. These are the three
ways they can rot without a person noticing.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

SCRIPTS = [REPO_ROOT / "build" / "mac_build.sh", REPO_ROOT / "ProIngest.command"]
"""Every shell script that ships. `ProIngest.command` is double-clicked in Finder, which
only offers to run a file that carries the executable bit, so its mode is load bearing
rather than a convention."""

REPO_PATH = re.compile(r"\b(?:build|docs|proingest|tests)/[A-Za-z0-9_./-]+")
"""Anything in the script that reads as a path into this repo. `dist/` is deliberately
not here: it is the script's output and does not exist before it runs."""


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: p.name)
def test_the_script_is_executable(script: Path) -> None:
    """The mode is carried in git. Losing it turns `build/mac_build.sh` into something
    only `bash <path>` can start, and stops Finder opening `ProIngest.command` at all."""
    assert os.access(script, os.X_OK)


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: p.name)
def test_bash_parses_it(script: Path) -> None:
    """The only syntax check these files ever get. `-n` reads one without running a line
    of it, which matters for a script whose first act is to refuse to run here."""
    result = subprocess.run(["bash", "-n", str(script)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: p.name)
def test_every_repo_path_it_names_exists(script: Path) -> None:
    """The check that catches a renamed build script or a moved document."""
    # Trailing punctuation because most of these are named in a sentence.
    named = {match.rstrip("./") for match in REPO_PATH.findall(script.read_text())}
    missing = sorted(path for path in named if not (REPO_ROOT / path).exists())
    assert not missing, f"{script.name} names paths that do not exist: {missing}"
