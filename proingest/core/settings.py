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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

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

    unknown: dict[str, Any] = field(default_factory=dict)
    """Keys a newer version wrote that this one does not know, kept so a save does not
    delete them. Never read; it exists so downgrading is not destructive."""

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.unknown,
            "schema_version": SCHEMA_VERSION,
            "window_geometry": self.window_geometry,
            "window_state": self.window_state,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AppSettings:
        known = {"schema_version", "window_geometry", "window_state"}
        return cls(
            window_geometry=str(data.get("window_geometry", "")),
            window_state=str(data.get("window_state", "")),
            unknown={key: value for key, value in data.items() if key not in known},
        )


def load(path: Path) -> AppSettings:
    """The settings at `path`, or defaults when there are none that can be read.

    A missing file is the first run. A corrupt one is a crash mid-write or a hand edit,
    and it is logged and replaced rather than raised: refusing to launch over a
    preferences file would be a worse failure than losing a window position.
    """
    try:
        data = json.loads(path.read_text())
    except FileNotFoundError:
        return AppSettings()
    except (OSError, ValueError) as exc:
        log.warning("settings at %s could not be read (%s); using defaults", path, exc)
        return AppSettings()
    if not isinstance(data, dict):
        log.warning("settings at %s are not an object; using defaults", path)
        return AppSettings()
    return AppSettings.from_dict(data)


def save(settings: AppSettings, path: Path) -> None:
    """Write the settings, atomically, creating the folder on first run.

    Same rule as a deliverable: write a temp file beside the target and rename it, so a
    crash mid-write leaves the previous settings rather than a truncated file that the
    next launch has to discard.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".part")
    temp.write_text(json.dumps(settings.to_dict(), indent=2) + "\n")
    temp.replace(path)
