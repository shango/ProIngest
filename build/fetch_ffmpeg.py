"""Populate proingest/resources/ffmpeg/ from build/ffmpeg.lock.json.

The ffmpeg and ffprobe binaries are ~426 MB and are deliberately not tracked in git.
This script is the only supported way to obtain them, so every machine ends up with the
exact build recorded in the lock file and in every QC log.

Usage: python build/fetch_ffmpeg.py
"""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
LOCK_PATH = REPO_ROOT / "build" / "ffmpeg.lock.json"


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def is_satisfied(dest: Path, member: dict[str, object]) -> bool:
    """True when dest already holds exactly the pinned bytes."""
    if not dest.is_file() or dest.stat().st_size != member["size"]:
        return False
    return sha256_of(dest) == member["sha256"]


def download(url: str, dest: Path) -> None:
    print(f"  downloading {url}")
    with urllib.request.urlopen(url) as response, dest.open("wb") as out:  # noqa: S310
        while block := response.read(1 << 20):
            out.write(block)


def extract(archive: Path, member: dict[str, object], dest_dir: Path) -> None:
    """Extract one member, verify its hash, then move it into place atomically."""
    suffix = str(member["archive_suffix"])
    dest = dest_dir / str(member["dest_name"])
    with zipfile.ZipFile(archive) as zf:
        names = [n for n in zf.namelist() if n.endswith(suffix)]
        if len(names) != 1:
            raise SystemExit(f"expected exactly one member ending in {suffix}, found {names}")
        temp = dest.with_suffix(dest.suffix + ".part")
        with zf.open(names[0]) as src, temp.open("wb") as out:
            while block := src.read(1 << 20):
                out.write(block)
    actual = sha256_of(temp)
    if actual != member["sha256"]:
        temp.unlink()
        raise SystemExit(f"sha256 mismatch for {dest.name}\n  expected {member['sha256']}\n  got      {actual}")
    temp.replace(dest)
    print(f"  wrote {dest.relative_to(REPO_ROOT)}")


def main() -> int:
    spec = json.loads(LOCK_PATH.read_text())["ffmpeg"]
    dest_dir = REPO_ROOT / str(spec["dest_dir"])
    dest_dir.mkdir(parents=True, exist_ok=True)

    print(f"ffmpeg {spec['version']}")
    missing = [m for m in spec["members"] if not is_satisfied(dest_dir / str(m["dest_name"]), m)]
    if not missing:
        print("  all binaries present and verified")
        return 0

    with tempfile.TemporaryDirectory() as tmp:
        archive = Path(tmp) / "ffmpeg.zip"
        download(str(spec["archive_url"]), archive)
        for member in missing:
            extract(archive, member, dest_dir)
    print("done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
