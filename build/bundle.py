"""What goes into the frozen bundle, kept out of the `.spec` file so it can be checked.

A PyInstaller spec is *executed*, not imported, so neither `ruff` nor `mypy` nor the
suite ever sees one. That makes it the worst possible home for a decision, because a
mistake in it does not fail a build: it ships an app with a file missing and surfaces
the first time a user opens a turnover. So everything with a judgement in it lives
here, in a normal module the linters and `tests/test_bundle.py` do see, and
`build/proingest.spec` is a six line shim that calls it.

Nothing here imports PySide6, OpenEXR or OpenColorIO. PyInstaller's own analysis finds
those by following the imports from the entry script; what this module supplies is only
the three kinds of thing that analysis *cannot* find - data files, package metadata,
and modules reached by name at run time.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from PyInstaller.utils.hooks import collect_data_files, copy_metadata

REPO_ROOT = Path(__file__).resolve().parent.parent

APP_NAME = "ProIngest"
"""The `.app` and the executable inside it. `ui/paths.py` builds the settings folder
from `QApplication.applicationName()` rather than from this, so the two are independent
by design and the app data folder does not move if the bundle is ever renamed."""

BUNDLE_IDENTIFIER = "com.proingest.ProIngest"
"""`CFBundleIdentifier`. PACKAGING.md specifies `com.<studio>.proingest` and no studio
name exists in this repository, so this is a placeholder and it is OQ-52. It has to be
settled **before** the first build reaches the editor's machine: macOS keys per-app
state off the identifier, so changing it later orphans whatever the old one accumulated
and re-prompts for everything the user already granted."""

MACOS = "darwin"

MINIMUM_MACOS = "12.0"
"""`LSMinimumSystemVersion`. PySide6 6.7's own floor, per PACKAGING.md."""

FFMPEG_DIR = Path("proingest") / "resources" / "ffmpeg"
"""Where `core/ffmpeg.py` looks, relative to the package root.

`BUNDLED_DIR` there is `Path(__file__).parent.parent / "resources" / "ffmpeg"`, and in a
frozen bundle `__file__` is `<sys._MEIPASS>/proingest/core/ffmpeg.py`, so laying the
binaries out under the same relative path is what makes that resolution work unchanged.
"""

FFMPEG_TOOLS = ("ffmpeg", "ffprobe")


def version() -> str:
    """The version the bundle is stamped with, read from the package itself.

    `proingest/__init__.py` is a single assignment with no imports behind it, so this
    costs nothing and cannot fail for a missing dependency. `tests/test_bundle.py` pins
    it equal to `pyproject.toml`'s, which is what stops a dmg from being named after a
    version the About box does not agree with.
    """
    from proingest import __version__

    return __version__


def datas(platform: str = sys.platform) -> list[tuple[str, str]]:
    """Files PyInstaller's import analysis cannot find by following imports.

    Three groups, and the middle one is the one that breaks a naive build:

    - `theme.qss`, read by `ui/app.py` with `Path(__file__).parent`. Its absence is not
      fatal there by design, which is exactly why it has to be listed: a missing
      stylesheet would ship as an app that merely looks wrong.
    - **OpenTimelineIO's adapters.** otio finds adapters through `importlib.metadata`
      entry points and JSON manifests, neither of which survives freezing on its own.
      The `.py` sources go too, and that is not belt and braces: otio's loader tries
      `importlib.import_module("opentimelineio.adapters.<name>")` first and falls back
      to `spec_from_file_location` on the path in the manifest. The CMX3600 adapter is
      named `cmx_3600` but lives in `otio_cmx3600_adapter`, so the import always misses
      and **only the file path fallback ever works** for it. No source file on disk, no
      EDL support.
    - ffmpeg's licence and provenance, which ship beside the binaries or not at all.
    """
    collected: list[tuple[str, str]] = [
        (str(REPO_ROOT / "proingest" / "ui" / "theme.qss"), str(Path("proingest") / "ui")),
    ]
    collected += collect_data_files("opentimelineio", include_py_files=True)
    collected += collect_data_files("otio_cmx3600_adapter", include_py_files=True)
    collected += copy_metadata("opentimelineio")
    collected += copy_metadata("otio-cmx3600-adapter")

    if platform == MACOS:
        for name in ("LICENSE.ffmpeg.txt", "PROVENANCE.md"):
            collected.append((str(REPO_ROOT / FFMPEG_DIR / name), str(FFMPEG_DIR)))
    return collected


def binaries(platform: str = sys.platform) -> list[tuple[str, str]]:
    """The bundled ffmpeg pair, on macOS only.

    They are macOS arm64 Mach-O and `core/ffmpeg.py` skips them off macOS for that
    reason, so collecting them on a Linux build would put 132 MB into an artifact that
    could never run them.

    Listed as *binaries* rather than as data so PyInstaller lays them out the way the
    `.app` needs and re-signs them ad-hoc after it rewrites their load commands, which
    the arm64 kernel requires of anything it executes. Their existing Developer ID
    signatures do not survive that. For an unsigned v01 bundle (OQ-9) nothing depends
    on them; if ProIngest is ever signed for real, PACKAGING.md's note about signing
    the nested binaries as part of the bundle is what applies.
    """
    if platform != MACOS:
        return []
    return [(str(REPO_ROOT / FFMPEG_DIR / tool), str(FFMPEG_DIR)) for tool in FFMPEG_TOOLS]


def hidden_imports() -> list[str]:
    """Modules reached by name at run time rather than by an `import` statement.

    otio's builtin adapters are named in a manifest and imported by string, so the
    analysis never sees them. `otio_json` is the one that reads the `.otio` a turnover
    arrives with, which makes it the module whose absence stops the tool doing anything
    at all.
    """
    return [
        "opentimelineio.adapters.otio_json",
        "opentimelineio.adapters.otiod",
        "opentimelineio.adapters.otioz",
        "otio_cmx3600_adapter",
        "otio_cmx3600_adapter.cmx_3600",
    ]


def excludes() -> list[str]:
    """Packages to keep out of a bundle that a developer's environment drags in.

    Deliberately short. The Qt modules are not listed because PyInstaller's PySide6
    hooks are per module and the tool imports only QtCore, QtGui and QtWidgets, so
    nothing pulls QtWebEngine in to be excluded. If the installed size ever runs at the
    300 MB budget in PRD section 8, `build/build.py` prints the number to argue from
    and this is the list to grow - but measure before adding to it.
    """
    return ["pytest", "mypy", "ruff", "tkinter", "PyInstaller"]


def info_plist() -> dict[str, Any]:
    """`Info.plist` additions for the `.app`, per PACKAGING.md.

    No `CFBundleDocumentTypes` and no URL schemes: a `.pibatch` is opened through the
    app's own dialogs, so registering it with Launch Services would claim an extension
    the tool has no way of being handed.
    """
    return {
        "CFBundleIdentifier": BUNDLE_IDENTIFIER,
        "CFBundleShortVersionString": version(),
        "CFBundleVersion": version(),
        "LSMinimumSystemVersion": MINIMUM_MACOS,
        "LSApplicationCategoryType": "public.app-category.video",
        "NSHighResolutionCapable": True,
        # One window, one document at a time. Without this macOS offers to reopen the
        # app in a second instance from the Dock, and a second instance would fight the
        # first over the same settings file.
        "LSMultipleInstancesProhibited": True,
    }
