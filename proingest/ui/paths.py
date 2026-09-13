"""Where the app's own files live, answered by Qt rather than built by hand.

UI_SPEC section 11: use `QStandardPaths`. On macOS with the application and
organisation names set, `AppDataLocation` is
`~/Library/Application Support/ProIngest`, which is what PACKAGING.md specifies. This
module is the only place that asks, and `core/settings.py` takes the answer as an
argument, so there is one authority for the location rather than a core copy that
cannot check Qt's.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QStandardPaths

from proingest.core import settings as core_settings

APPLICATION_NAME = "ProIngest"
"""Set on the QApplication before anything asks for a path, because `AppDataLocation` is
built from it: asking first answers for a folder named after the executable.

**The organisation name is deliberately left unset.** Qt appends the organisation *and*
the application to this location, so setting both gives
`~/Library/Application Support/ProIngest/ProIngest`, one level deeper than PACKAGING.md
specifies. Nothing else in the tool wants an organisation: there is no `QSettings` here,
because settings are `core/settings.py`'s JSON file at a path this module supplies.
"""


def app_data_dir() -> Path:
    """The per user folder the settings file and window state live in."""
    return Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation))


def settings_path() -> Path:
    """`settings.json` inside it. Not created here; `core.settings.save` makes the folder."""
    return app_data_dir() / core_settings.SETTINGS_FILENAME


MACOS_LOGS = "darwin"
"""The one platform where the log folder is not under the app data folder.

macOS keeps logs in `~/Library/Logs/<app>`, which PACKAGING.md names, and Qt has no
standard location for it: `QStandardPaths` models data, cache and config and stops
there. So the folder is derived from the generic data location's parent rather than
written out with a `~` in it, which keeps CLAUDE.md's rule about platform paths and
still lands where the spec says. Everywhere else - the Linux dev machine and the Linux
CI runner - a `logs` folder beside `settings.json` is the honest answer.
"""


def log_dir() -> Path:
    """Where the rotating log file goes. `core/logsetup.py` creates it, not this."""
    if sys.platform == MACOS_LOGS:
        generic = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.GenericDataLocation))
        return generic.parent / "Logs" / APPLICATION_NAME
    return app_data_dir() / "logs"
