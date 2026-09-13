"""The scan, run off the UI thread.

Scanning a turnover walks a folder on a network mount and runs ffprobe once per clip,
which is the one long operation in M5 that is not the render pool, and CLAUDE.md forbids
it on the UI thread. So `core/scan.py` is called from a worker `QObject` living on a
`QThread` and the results come back as signals. **Core stays Qt-free**: nothing in this
module is imported by anything under `core/`, exactly as the render pool arranges it.

**Three things cross the thread boundary and each is handed over rather than shared.**
The worker is given a copy of the batch's probe cache and emits a copy of it back per
folder, so the UI thread's dictionary is only ever written by the UI thread. The
`Turnover` and its rows are built in the worker and are not touched again after they are
emitted. And the batch itself never goes near the worker: appending what came back is
the window's job, on its own thread.

Cancellation is checked between folders and nowhere else. `scan_turnover` is a single
call into core that cannot be interrupted part way, so cancelling during one folder
waits for that folder and then stops. A turnover is seconds, not minutes, and the
alternative is a cancellation flag threaded through five core functions that have no
other reason to know about one.
"""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal

from proingest.core import scan
from proingest.core.models import MediaInfo

log = logging.getLogger(__name__)

SHUTDOWN_WAIT_MS = 30_000
"""How long `shutdown` waits for the worker before giving up on it.

Long, because what it is waiting for is one folder's ffprobe calls over a mount that
may have gone slow, and a window that closed while a probe was in flight would leave a
thread running into interpreter shutdown. Not infinite, because a hung mount must not
be a window that cannot be closed.
"""


class _ScanJob(QObject):
    """The work itself, on the worker thread. One `run` per `Scanner.start`."""

    scanned = Signal(object, object, object)
    started_folder = Signal(object)
    done = Signal()

    def __init__(
        self,
        folders: list[tuple[Path, str]],
        settings: scan.ScanSettings,
        probe_cache: dict[str, MediaInfo],
    ) -> None:
        super().__init__()
        self._folders = folders
        self._settings = settings
        self._cache = probe_cache
        self._cancelled = False

    def cancel(self) -> None:
        """Stop after the folder in flight. Called from the UI thread.

        A plain attribute rather than a lock: one thread writes it and one reads it,
        the write is a single bytecode, and the reader only has to see it eventually.
        """
        self._cancelled = True

    def run(self) -> None:
        """Scan each folder in turn, reporting one at a time.

        Per folder rather than at the end, so a batch of four turnovers fills the list
        as it goes. A folder that raises is logged and skipped rather than taking the
        rest of the scan with it: `scan_turnover` already turns a bad turnover into QC
        results, so anything that escapes it is a bug, and losing the three good folders
        to it would be a second one.
        """
        for folder, turnover_id in self._folders:
            if self._cancelled:
                break
            self.started_folder.emit(folder)
            try:
                turnover, rows = scan.scan_turnover(
                    folder, turnover_id, self._settings, probe_cache=self._cache
                )
            except Exception:
                log.exception("scanning %s failed", folder)
                continue
            self.scanned.emit(turnover, rows, dict(self._cache))
        self.done.emit()


class Scanner(QObject):
    """Runs scans on a worker thread, one scan at a time.

    One thread per scan rather than a thread kept alive between them: a scan is rare
    and a thread that is only alive while it is working cannot be left holding a stale
    settings object or a cache the batch has since replaced.
    """

    scanned = Signal(object, object, object)
    """`Turnover`, `list[ShotRow]`, and the probe cache as it stood after that folder."""

    started_folder = Signal(object)
    """The `Path` now being scanned. The status bar says so."""

    finished = Signal()
    """Every folder done, or the scan was cancelled. Always fires exactly once."""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._thread: QThread | None = None
        self._job: _ScanJob | None = None

    @property
    def busy(self) -> bool:
        return self._thread is not None

    def start(
        self,
        folders: list[tuple[Path, str]],
        settings: scan.ScanSettings,
        probe_cache: dict[str, MediaInfo] | None = None,
    ) -> None:
        """Scan these folders, each under the turnover id given with it.

        The ids come from the caller because they have to be unique within a batch,
        which is a fact about the batch and not about the folder.
        """
        if self.busy:
            raise RuntimeError("a scan is already running")
        if not folders:
            self.finished.emit()
            return

        job = _ScanJob(folders, settings, dict(probe_cache or {}))
        thread = QThread(self)
        job.moveToThread(thread)

        thread.started.connect(job.run)
        job.scanned.connect(self.scanned)
        job.started_folder.connect(self.started_folder)
        job.done.connect(thread.quit)
        thread.finished.connect(self._cleanup)

        self._thread = thread
        self._job = job
        thread.start()

    def cancel(self) -> None:
        """Ask the scan to stop after the folder in flight. Returns immediately."""
        if self._job is not None:
            self._job.cancel()

    def shutdown(self) -> None:
        """Stop and wait. What closing the window calls.

        A `QThread` still running when its Python owner is collected is a crash on the
        way out rather than an error anyone can act on, so the wait is not optional.
        """
        self.cancel()
        thread = self._thread
        if thread is None:
            return
        thread.quit()
        if not thread.wait(SHUTDOWN_WAIT_MS):
            log.warning("the scan thread did not stop within %d ms", SHUTDOWN_WAIT_MS)

    def _cleanup(self) -> None:
        """Drop the thread and its job once the thread has actually finished.

        `deleteLater` rather than dropping the reference alone: the job lives on a
        thread that is ending, and Qt deletes it on the right one.
        """
        if self._job is not None:
            self._job.deleteLater()
        if self._thread is not None:
            self._thread.deleteLater()
        self._job = None
        self._thread = None
        self.finished.emit()
