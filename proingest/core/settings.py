"""Application settings: what the app remembers between launches.

JSON at `~/Library/Application Support/ProIngest/settings.json` (PACKAGING.md,
"Runtime locations"). **This module never works out where that is.** The path comes
from `ui/paths.py`, which asks `QStandardPaths` for it as UI_SPEC section 11 requires,
and every function here takes it as an argument. Core imports no Qt, so the alternative
would be a second implementation of the same path in a module that cannot check Qt's
answer, and two authorities for one location is how a settings file ends up written in
one place and read from another.

Unlike a batch file, a settings file is disposable: it is one user's preferences, not a
record of work. So a file that cannot be read is replaced with defaults rather than
raising, and a key the current version does not know is kept on save rather than
dropped, which is what lets an older build open a file a newer one wrote.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any

from proingest.core import logsetup
from proingest.core.exr import DWA_COMPRESSION_LEVEL
from proingest.core.ffmpeg import REFERENCE_CRF
from proingest.core.models import DEFAULT_WORKERS

log = logging.getLogger(__name__)

SCHEMA_VERSION = 1

SETTINGS_FILENAME = "settings.json"
"""The name under the app data folder. The folder itself is `ui/paths.py`'s answer."""


@dataclass
class AppSettings:
    """What the app remembers. Grows a field per Settings page group (PRD FR-12).

    Window state is two opaque base64 strings from Qt's own `saveGeometry` and
    `saveState`, stored rather than interpreted: they encode screen layout and dock
    arrangement in a format only Qt reads, and a settings file is the right place for
    them because they are per user and worthless to anyone else.
    """

    window_geometry: str = ""
    window_state: str = ""

    last_folder: str = ""
    """Where the file choosers open when the batch cannot say (UI_SPEC section 11).

    Per user rather than per batch, because it is about the last thing this person
    browsed to and not about the work: the batch's own two roots are on the batch
    (section 13) and they are what a chooser prefers when there is one open. Empty on a
    first run, which opens the chooser wherever the platform would: **nothing here
    guesses at a Drive mount**, because a wrong guess opens somewhere plausible and
    empty and reads as the folder being wrong.
    """

    workers: int = DEFAULT_WORKERS
    """How many render processes a run uses (PRD FR-12, General).

    Per user rather than per batch: it is a fact about this machine's cores and this
    person's patience, not about the work. `models.DEFAULT_WORKERS` is the default
    rather than a number repeated here, because a settings file written before this
    field existed has to read back as whatever the tool would have done anyway.
    """

    show_pattern: str = ""
    """The show prefix pattern every name is parsed and built with (FR-12, Naming).

    **Empty means the default**, `naming.DEFAULT_SHOW_PATTERN`, rather than a copy of it
    stored on first save: a settings file that froze today's pattern would keep an old
    one after the default moved, and nothing would say why names stopped parsing.
    """

    path_map: dict[str, str] = field(default_factory=dict)
    """Media path prefixes to rewrite, FR-2. A Windows shooter's `G:\\...` for the
    editor's own mount. Per user, because it describes this machine's view of the
    world; `scan._resolve_media`'s filename search is what covers the case where it
    is empty, which is why it is a belt rather than a requirement."""

    rules: dict[str, Any] = field(default_factory=dict)
    """Rule thresholds a **new** batch starts from (FR-12, Rules).

    Stored as the same plain dict a batch carries in `settings_overrides`, so the two
    cannot disagree about the shape and this module needs no import from `core/qc.py`.
    **A batch keeps its own copy** from the moment it is created, for the reason
    UI_SPEC section 13 gives for the two roots: what a delivery was checked against is a
    record of that work, so changing the defaults later must not silently re-judge a
    batch that shipped.
    """

    color_session_folder: str = ""
    """Where the Ingest chooser opens (FR-12, Colour).

    The folder, not the package: which session a turnover was ingested from lives on
    the turnover (OQ-50). This is the same kind of thing as `last_folder` - a starting
    point for a dialog - kept separately because a colour session and a turnover live
    nowhere near each other on the mount.
    """

    log_level: str = logsetup.name_of(logsetup.DEFAULT_LEVEL)
    """How much the tool writes to its log and its Log tab (FR-12, Advanced).

    A name from `logsetup.LEVEL_NAMES` rather than a number, because a settings file is
    occasionally read by a person and `20` says nothing. An unknown name reads back as
    the default rather than raising, which is this module's rule for every field.
    """

    ffmpeg_path: str = ""
    """An ffmpeg and ffprobe to use instead of the bundled pair (FR-12, Advanced).

    The folder holding them or one of the binaries itself; `ffmpeg.resolve_tool` takes
    either, because both are natural things to paste into a field. Empty means the
    normal order: bundled, then PATH. **A path that does not exist is an error rather
    than a fallback**, because an override quietly ignored is a render done with the
    wrong build of ffmpeg and nothing said.
    """

    reference_crf: int = REFERENCE_CRF
    """The x264 rate factor every reference mp4 is encoded at (FR-12, Output).

    Per user rather than per batch, which is the one thing about it worth arguing with:
    it is a delivery quality and the spec pins 18. It is here because the page is where
    the spec's number is checked and, on a turnover that has to fit down a slow line,
    moved for a reason someone stated. `ffmpeg.REFERENCE_CRF` is the default rather than
    a number repeated here, so a settings file written before this field existed reads
    back as whatever the tool would have done anyway.
    """

    exr_compression_level: int = DWA_COMPRESSION_LEVEL
    """The DWAA level every delivered plate is written at (FR-12, Output).

    Same shape and the same argument as `reference_crf`, and the same default from
    `exr.DWA_COMPRESSION_LEVEL`. DWAA is lossy at any level (COLOR_AND_FORMAT section
    7), so this moves how lossy rather than whether.
    """

    metadata_collapsed: list[str] = field(default_factory=list)
    """Which sections of the metadata pane the editor has shut (UI_SPEC section 12.1).

    The shut ones rather than the open ones, so a section a later chunk adds arrives
    open: a field list nobody can see is worse than one nobody asked for. Titles rather
    than indexes, so reordering the sections does not silently collapse a different one.
    """

    unknown: dict[str, Any] = field(default_factory=dict)
    """Keys a newer version wrote that this one does not know, kept so a save does not
    delete them. Never read; it exists so downgrading is not destructive."""

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.unknown,
            "schema_version": SCHEMA_VERSION,
            "window_geometry": self.window_geometry,
            "window_state": self.window_state,
            "last_folder": self.last_folder,
            "workers": self.workers,
            "show_pattern": self.show_pattern,
            "path_map": dict(self.path_map),
            "rules": dict(self.rules),
            "color_session_folder": self.color_session_folder,
            "log_level": self.log_level,
            "ffmpeg_path": self.ffmpeg_path,
            "reference_crf": self.reference_crf,
            "exr_compression_level": self.exr_compression_level,
            "metadata_collapsed": list(self.metadata_collapsed),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AppSettings:
        known = {f.name for f in fields(cls)} - {"unknown"} | {"schema_version"}
        return cls(
            window_geometry=str(data.get("window_geometry", "")),
            window_state=str(data.get("window_state", "")),
            last_folder=str(data.get("last_folder", "")),
            workers=int(data.get("workers", DEFAULT_WORKERS)),
            show_pattern=str(data.get("show_pattern", "")),
            path_map={str(k): str(v) for k, v in dict(data.get("path_map", {})).items()},
            rules=dict(data.get("rules", {})),
            color_session_folder=str(data.get("color_session_folder", "")),
            log_level=logsetup.name_of(logsetup.level_of(str(data.get("log_level", "")))),
            ffmpeg_path=str(data.get("ffmpeg_path", "")),
            reference_crf=int(data.get("reference_crf", REFERENCE_CRF)),
            exr_compression_level=int(data.get("exr_compression_level", DWA_COMPRESSION_LEVEL)),
            metadata_collapsed=[str(item) for item in data.get("metadata_collapsed", [])],
            unknown={key: value for key, value in data.items() if key not in known},
        )


def load(path: Path) -> AppSettings:
    """The settings at `path`, or defaults when there are none that can be read.

    A missing file is the first run. A corrupt one is a crash mid-write or a hand edit,
    and it is logged and replaced rather than raised: refusing to launch over a
    preferences file would be a worse failure than losing a window position.
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return AppSettings()
    except (OSError, ValueError) as exc:
        log.warning("settings at %s could not be read (%s); using defaults", path, exc)
        return AppSettings()
    if not isinstance(data, dict):
        log.warning("settings at %s are not an object; using defaults", path)
        return AppSettings()
    try:
        return AppSettings.from_dict(data)
    except (TypeError, ValueError) as exc:
        log.warning("settings at %s hold a value of the wrong type (%s); using defaults", path, exc)
        return AppSettings()


def save(settings: AppSettings, path: Path) -> None:
    """Write the settings, atomically, creating the folder on first run.

    Same rule as a deliverable: write a temp file beside the target and rename it, so a
    crash mid-write leaves the previous settings rather than a truncated file that the
    next launch has to discard.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".part")
    temp.write_text(json.dumps(settings.to_dict(), indent=2) + "\n", encoding="utf-8")
    temp.replace(path)
