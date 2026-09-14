"""Populate proingest/resources/ffmpeg/ from build/ffmpeg.lock.json.

The ffmpeg and ffprobe binaries are ~132 MB and are deliberately not tracked in git.
This script is the only supported way to obtain them, so every machine ends up with the
exact build recorded in the lock file and in every QC log.

Usage:
    python build/fetch_ffmpeg.py                    # download, verify, install
    python build/fetch_ffmpeg.py --verify           # check what is there, download nothing
    python build/fetch_ffmpeg.py --from ~/Downloads # install from files already on disk
    python build/fetch_ffmpeg.py --show             # print what to download, and from where

`--from` exists for a machine that cannot or should not reach the internet from a shell:
put the files somewhere by hand and this verifies them against the same sha256 the
download path checks, so a hand-placed binary is exactly as trustworthy as a fetched one
and never silently a different build. See `docs/MAC_SETUP.md`.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
LOCK_PATH = REPO_ROOT / "build" / "ffmpeg.lock.json"

EXEC_BITS = stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH

USER_AGENT = "ProIngest-fetch-ffmpeg/1.0"
"""ffmpeg.martin-riedl.de answers the default `Python-urllib/3.x` agent with 403."""


def display_path(path: Path) -> str:
    """A path to print: relative to the repo when it is inside it, absolute otherwise."""
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def human_size(size: int) -> str:
    return f"{size / 1e6:.0f} MB" if size >= 1_000_000 else f"{size / 1e3:.0f} KB"


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
    return sha256_of(dest) == str(entry["sha256"])


def download(url: str, dest: Path) -> None:
    print(f"  downloading {url}")
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request) as response, dest.open("wb") as out:
            while block := response.read(1 << 20):
                out.write(block)
    except urllib.error.URLError as exc:
        raise SystemExit(
            f"could not download {url}\n  {exc}\n"
            f"Download it on another machine and run `python build/fetch_ffmpeg.py --from <folder>`.\n"
            f"`python build/fetch_ffmpeg.py --show` lists every file and its sha256."
        ) from exc


def copy_bytes(source: Path, dest: Path) -> None:
    """Copy file contents, and only the contents.

    Deliberately not `shutil.copy`: a file a browser put in ~/Downloads on macOS carries
    `com.apple.quarantine`, and an ffmpeg that inherits it is killed on first exec. A
    freshly written file carries no extended attributes, so this sidesteps that instead
    of shelling out to `xattr` afterwards.
    """
    with source.open("rb") as src, dest.open("wb") as out:
        while block := src.read(1 << 20):
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


def place(temp: Path, dest: Path, entry: dict[str, Any]) -> None:
    """Verify the staged bytes against the lock, set the mode, then rename into place.

    The rename is last so that an interrupted or wrong download never leaves a file that
    looks finished, which is the same rule the deliverables follow.
    """
    actual = sha256_of(temp)
    if actual != entry["sha256"]:
        temp.unlink()
        raise SystemExit(
            f"sha256 mismatch for {dest.name}\n  expected {entry['sha256']}\n  got      {actual}"
        )
    if entry["executable"]:
        os.chmod(temp, temp.stat().st_mode | EXEC_BITS)
    temp.replace(dest)
    print(f"  wrote {display_path(dest)}")


def fetch(entry: dict[str, Any], dest_dir: Path, work: Path) -> None:
    """Download one entry, verify it, then move it into place."""
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

    place(temp, dest, entry)


def accepted_names(entry: dict[str, Any]) -> list[str]:
    """What a hand-placed file for this entry may be called.

    Either the archive as the site serves it, or the file already extracted. The name
    the site serves is the one the browser will have used, and the extracted name is what
    double-clicking that archive in the Finder produces, so both are on the list.
    """
    names = [Path(str(entry["url"])).name]
    if entry.get("archive_member") is not None:
        names.append(str(entry["archive_member"]))
    names.append(str(entry["dest_name"]))
    return list(dict.fromkeys(names))


def find_local(entry: dict[str, Any], source_dir: Path) -> Path | None:
    for name in accepted_names(entry):
        candidate = source_dir / name
        if candidate.is_file():
            return candidate
    return None


def install_local(entry: dict[str, Any], source: Path, dest_dir: Path) -> None:
    """Install one entry from a file the user supplied, verifying it like a download."""
    dest = dest_dir / str(entry["dest_name"])
    temp = dest.with_suffix(dest.suffix + ".part")
    member = entry.get("archive_member")

    print(f"  reading {source}")
    if member is not None and zipfile.is_zipfile(source):
        unpack(source, str(member), temp)
    else:
        copy_bytes(source, temp)

    place(temp, dest, entry)


def describe(spec: dict[str, Any]) -> None:
    """Print every file, where it comes from and what it must hash to."""
    dest_dir = REPO_ROOT / str(spec["dest_dir"])
    print(f"ffmpeg {spec['version']} ({spec['license']})")
    print(f"Destination: {dest_dir}")
    for entry in spec["downloads"]:
        print()
        print(f"  {entry['dest_name']}  ({human_size(int(entry['size']))})")
        print(f"    from    {entry['url']}")
        if entry.get("archive_member") is not None:
            print(f"    member  {entry['archive_member']}  (or hand over the .zip itself)")
        print(f"    sha256  {entry['sha256']}")


def report(spec: dict[str, Any], dest_dir: Path) -> int:
    """Say what is present and what is not. Non-zero when anything is missing or wrong."""
    print(f"ffmpeg {spec['version']}")
    bad = 0
    for entry in spec["downloads"]:
        dest = dest_dir / str(entry["dest_name"])
        if is_satisfied(dest, entry):
            print(f"  ok      {entry['dest_name']}")
            continue
        bad += 1
        if not dest.is_file():
            print(f"  missing {entry['dest_name']}")
        else:
            print(f"  WRONG   {entry['dest_name']}: not the pinned build (size, mode or sha256)")
    if bad:
        print(f"\n{bad} file(s) to go. Run `python build/fetch_ffmpeg.py` to download them,")
        print("or `python build/fetch_ffmpeg.py --from <folder>` to install ones already on disk.")
    return 1 if bad else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Populate the bundled ffmpeg binaries.")
    parser.add_argument(
        "--from",
        dest="source_dir",
        type=Path,
        help="install from a folder holding the downloaded zips or the extracted binaries",
    )
    parser.add_argument("--verify", action="store_true", help="check what is installed, fetch nothing")
    parser.add_argument("--show", action="store_true", help="print the URLs and hashes, do nothing else")
    args = parser.parse_args(argv)

    spec = json.loads(LOCK_PATH.read_text())["ffmpeg"]
    dest_dir = REPO_ROOT / str(spec["dest_dir"])

    if args.show:
        describe(spec)
        return 0
    if args.verify:
        return report(spec, dest_dir)

    dest_dir.mkdir(parents=True, exist_ok=True)
    print(f"ffmpeg {spec['version']}")
    missing = [e for e in spec["downloads"] if not is_satisfied(dest_dir / str(e["dest_name"]), e)]
    if not missing:
        print("  all binaries present and verified")
        return 0

    if args.source_dir is not None:
        source_dir = args.source_dir.expanduser()
        if not source_dir.is_dir():
            raise SystemExit(f"not a folder: {source_dir}")
        for entry in missing:
            found = find_local(entry, source_dir)
            if found is None:
                raise SystemExit(
                    f"nothing in {source_dir} for {entry['dest_name']}\n"
                    f"  expected one of: {', '.join(accepted_names(entry))}\n"
                    f"  from {entry['url']}"
                )
            install_local(entry, found, dest_dir)
    else:
        with tempfile.TemporaryDirectory() as tmp:
            for entry in missing:
                fetch(entry, dest_dir, Path(tmp))
    print("done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
