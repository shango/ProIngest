"""`build/mac_build.sh`, the one command a fresh Mac clone runs.

A shell script cannot be type checked, is not linted with the Python, and is the one
file in this repo that nothing else imports - so a rename anywhere in `build/` leaves it
naming a file that is gone and nothing says so until somebody is sitting at the Mac.
These are the three ways it can rot without a person noticing.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

SCRIPT = REPO_ROOT / "build" / "mac_build.sh"

REPO_PATH = re.compile(r"\b(?:build|docs|proingest|tests)/[A-Za-z0-9_./-]+")
"""Anything in the script that reads as a path into this repo. `dist/` is deliberately
not here: it is the script's output and does not exist before it runs."""


def test_the_script_is_executable() -> None:
    """The mode is carried in git, and losing it turns the documented
    `bash build/mac_build.sh` into the only way to start it."""
    assert os.access(SCRIPT, os.X_OK)


def test_bash_parses_it() -> None:
    """The only syntax check this file ever gets. `-n` reads it without running a line
    of it, which matters for a script whose first act is to refuse to run here."""
    result = subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_every_repo_path_it_names_exists() -> None:
    """The check that catches a renamed build script or a moved document."""
    # Trailing punctuation because most of these are named in a sentence.
    named = {match.rstrip("./") for match in REPO_PATH.findall(SCRIPT.read_text())}
    missing = sorted(path for path in named if not (REPO_ROOT / path).exists())
    assert not missing, f"{SCRIPT.name} names paths that do not exist: {missing}"
