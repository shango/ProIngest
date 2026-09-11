"""Populate proingest/resources/ffmpeg/ from build/ffmpeg.lock.json.

The ffmpeg and ffprobe binaries are ~132 MB and are deliberately not tracked in git.
This script is the only supported way to obtain them, so every machine ends up with the
exact build recorded in the lock file and in every QC log.

Usage: python build/fetch_ffmpeg.py
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
LOCK_PATH = REPO_ROOT / "build" / "ffmpeg.lock.json"

EXEC_BITS = stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH

USER_AGENT = "ProIngest-fetch-ffmpeg/1.0"
"""ffmpeg.martin-riedl.de answers the default `Python-urllib/3.x` agent with 403."""


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def is_satisfied(dest: Path, entry: dict[str, Any]) -> bool:
    """True when dest already holds exactly the pinned bytes, executable if it must be.

    The mode is part of the check because a binary that arrived without its exec bit is
    useless and would otherwise look present forever.
    """
    if not dest.is_file() or dest.stat().st_size != entry["size"]:
        return False
    if entry["executable"] and not dest.stat().st_mode & stat.S_IXUSR:
        return False
    return sha256_of(dest) == entry["sha256"]


def download(url: str, dest: Path) -> None:
    print(f"  downloading {url}")
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request) as response, dest.open("wb") as out:
        while block := response.read(1 << 20):
            out.write(block)


def unpack(archive: Path, member_name: str, dest: Path) -> None:
    """Copy one named member out of a zip.

    Python's zipfile does not carry the archived mode across on extraction, so the
    executable bit is set from the lock file afterwards rather than trusted from here.
    """
    with zipfile.ZipFile(archive) as zf:
        names = [n for n in zf.namelist() if n == member_name]
        if len(names) != 1:
            raise SystemExit(f"expected member {member_name} in {archive.name}, found {zf.namelist()}")
        with zf.open(names[0]) as src, dest.open("wb") as out:
            while block := src.read(1 << 20):
                out.write(block)


def fetch(entry: dict[str, Any], dest_dir: Path, work: Path) -> None:
    """Download one entry, verify it, then move it into place atomically."""
    dest = dest_dir / str(entry["dest_name"])
    temp = dest.with_suffix(dest.suffix + ".part")
    member = entry.get("archive_member")

    if member is None:
        download(str(entry["url"]), temp)
    else:
        archive = work / f"{entry['dest_name']}.zip"
        download(str(entry["url"]), archive)
        unpack(archive, str(member), temp)
        archive.unlink()

    actual = sha256_of(temp)
    if actual != entry["sha256"]:
        temp.unlink()
        raise SystemExit(
            f"sha256 mismatch for {dest.name}\n"
            f"  expected {entry['sha256']}\n"
            f"  got      {actual}"
        )
    if entry["executable"]:
        os.chmod(temp, temp.stat().st_mode | EXEC_BITS)
    temp.replace(dest)
    print(f"  wrote {dest.relative_to(REPO_ROOT)}")


def main() -> int:
    spec = json.loads(LOCK_PATH.read_text())["ffmpeg"]
    dest_dir = REPO_ROOT / str(spec["dest_dir"])
    dest_dir.mkdir(parents=True, exist_ok=True)

    print(f"ffmpeg {spec['version']}")
    missing = [e for e in spec["downloads"] if not is_satisfied(dest_dir / str(e["dest_name"]), e)]
    if not missing:
        print("  all binaries present and verified")
        return 0

    with tempfile.TemporaryDirectory() as tmp:
        for entry in missing:
            fetch(entry, dest_dir, Path(tmp))
    print("done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
