"""Build the frozen app, and on macOS the dmg beside it. Writes into `dist/`.

Usage:
    python build/build.py              # app, and a dmg if this is macOS
    python build/build.py --no-dmg     # app only
    python build/build.py --clean      # throw away build/ and dist/ first

macOS on Apple Silicon is the target (PACKAGING.md). The script runs on Linux too and
produces a Linux `onedir` that no one ships: it is there so that `build/proingest.spec`
can be exercised - a missing hidden import or an uncollected plugin manifest fails a
build the same way on either platform, and finding that on a rented Mac is the expensive
way to find it (`docs/MAC_SESSION.md`).
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from build import bundle

REPO_ROOT = bundle.REPO_ROOT
SPEC_PATH = REPO_ROOT / "build" / "proingest.spec"
DIST_DIR = REPO_ROOT / "dist"
WORK_DIR = REPO_ROOT / "build" / "pyinstaller"

INSTALLER_BUDGET_BYTES = 300 * 1024 * 1024
"""PRD section 8: "Installer under 300 MB". The installer is the dmg, so this is
measured against the compressed disk image and the installed size is reported beside it
as the number that explains it. Printed rather than enforced: a budget that fails a
build is a red `main` the first time PySide6 gains a megabyte, and the decision about
what to drop is a person's."""


class BuildError(RuntimeError):
    """Something the build needs is missing or a tool it ran came back non-zero."""


def app_dir(platform: str = sys.platform) -> Path:
    """Where PyInstaller leaves the collected app.

    The `BUNDLE` step on macOS writes `ProIngest.app` *beside* the `COLLECT` output
    rather than instead of it, so the two names coexist in `dist/` and only one of them
    is the thing to ship.
    """
    if platform == bundle.MACOS:
        return DIST_DIR / f"{bundle.APP_NAME}.app"
    return DIST_DIR / bundle.APP_NAME


def executable_path(platform: str = sys.platform) -> Path:
    """The binary to run, inside whichever of those two layouts this platform built."""
    if platform == bundle.MACOS:
        return app_dir(platform) / "Contents" / "MacOS" / bundle.APP_NAME
    return app_dir(platform) / bundle.APP_NAME


def dmg_path(version: str) -> Path:
    """`ProIngest-0.1.0.dmg`. The version is in the filename so two builds cannot be
    confused for each other on a machine that has downloaded both."""
    return DIST_DIR / f"{bundle.APP_NAME}-{version}.dmg"


def directory_size(path: Path) -> int:
    """Bytes on disk under `path`, following nothing.

    Symlinks are counted as links rather than as their targets, which is what makes the
    number match the bundle: PyInstaller's macOS layout is a symlink farm between
    `Contents/Frameworks` and `Contents/Resources`, and resolving those would count most
    of the app twice.
    """
    total = 0
    for root, _, files in os.walk(path):
        for name in files:
            entry = Path(root) / name
            if not entry.is_symlink():
                total += entry.stat().st_size
    return total


def format_size(size: int) -> str:
    return f"{size / (1024 * 1024):.0f} MB"


def check_ffmpeg(platform: str = sys.platform) -> None:
    """Refuse a macOS build that would silently ship without ffmpeg.

    The binaries are untracked and fetched by `build/fetch_ffmpeg.py`, so a fresh clone
    has none. PyInstaller would not complain - a missing file in `binaries` is a warning
    it prints among hundreds - and the app would install, start, and fail on the first
    probe with `FFmpegNotFound`. Off macOS there is nothing to check: `core/ffmpeg.py`
    does not use the bundled pair there.
    """
    if platform != bundle.MACOS:
        return
    missing = [tool for tool in bundle.FFMPEG_TOOLS if not (REPO_ROOT / bundle.FFMPEG_DIR / tool).is_file()]
    if missing:
        raise BuildError(
            f"{', '.join(missing)} missing from {bundle.FFMPEG_DIR}. "
            "Run `python build/fetch_ffmpeg.py` first."
        )


def run_pyinstaller(clean: bool) -> None:
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        str(SPEC_PATH),
        "--distpath",
        str(DIST_DIR),
        "--workpath",
        str(WORK_DIR),
        "--noconfirm",
    ]
    if clean:
        command.append("--clean")
    print(" ".join(command))
    result = subprocess.run(command, cwd=REPO_ROOT, check=False)
    if result.returncode != 0:
        raise BuildError(f"PyInstaller exited {result.returncode}")


def build_dmg(version: str) -> Path:
    """A compressed disk image with an Applications symlink beside the app.

    `hdiutil` rather than `create-dmg`, which PACKAGING.md used to name: the only part
    of create-dmg this needs is the drag-to-install layout, and that is one symlink in a
    staging folder. Doing it this way means the CI runner installs nothing through
    Homebrew to package a build, and there is no cosmetic background image in this
    repository for create-dmg to place anyway.
    """
    source = app_dir()
    if not source.is_dir():
        raise BuildError(f"{source} does not exist; the app was not built")

    output = dmg_path(version)
    output.unlink(missing_ok=True)

    with tempfile.TemporaryDirectory() as staging_name:
        staging = Path(staging_name)
        shutil.copytree(source, staging / source.name, symlinks=True)
        (staging / "Applications").symlink_to("/Applications")
        command = [
            "hdiutil",
            "create",
            "-volname",
            f"{bundle.APP_NAME} {version}",
            "-srcfolder",
            str(staging),
            "-ov",
            "-format",
            "UDZO",
            str(output),
        ]
        print(" ".join(command))
        result = subprocess.run(command, check=False)
        if result.returncode != 0:
            raise BuildError(f"hdiutil exited {result.returncode}")
    return output


def report_sizes(version: str, image: Path | None) -> None:
    """Print the installed size, and the dmg against the budget when there is one."""
    installed = directory_size(app_dir())
    print(f"\n{bundle.APP_NAME} {version}")
    print(f"  {app_dir()}")
    print(f"  installed  {format_size(installed)}")
    if image is None:
        print("  installer  not built on this platform")
        return
    size = image.stat().st_size
    verdict = "within" if size <= INSTALLER_BUDGET_BYTES else "OVER"
    print(f"  {image}")
    print(f"  installer  {format_size(size)}, {verdict} the {format_size(INSTALLER_BUDGET_BYTES)} budget")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-dmg", action="store_true", help="build the app but not the disk image")
    parser.add_argument("--clean", action="store_true", help="discard previous build and dist output")
    args = parser.parse_args(argv)

    version = bundle.version()
    try:
        check_ffmpeg()
        if args.clean:
            shutil.rmtree(WORK_DIR, ignore_errors=True)
            shutil.rmtree(DIST_DIR, ignore_errors=True)
        run_pyinstaller(args.clean)
        image = None
        if sys.platform == bundle.MACOS and not args.no_dmg:
            image = build_dmg(version)
    except BuildError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    report_sizes(version, image)
    print(f"\nsmoke test it:  python build/smoke_test.py {executable_path()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
