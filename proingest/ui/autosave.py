"""Autosave: the batch file written a moment after the editing stops.

UI_SPEC section 5 ends every commit with "autosave fires". It is debounced rather than
written per keystroke, because a batch file is the whole batch serialized and tabbing
along a row is four commits in a second.

**A batch with no file yet is not an error and is not silently dropped.** A batch made
by New has no path until it is saved, so until then the pending state is kept and
`adopt` is what Save calls once there is somewhere to write. That is also why `flush` is
public: closing the window is the other moment the wait has to end, and what is still
pending there is what the window asks about before it closes.

Core writes the file (`core/batchfile.py`) and it writes atomically, so a save
interrupted by a crash leaves the previous batch rather than half of this one.
"""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal

from proingest.core import batchfile
from proingest.core.models import Batch

log = logging.getLogger(__name__)

DELAY_MS = 1500
"""How long after the last commit the write happens. Long enough that tabbing across a
row is one save, short enough that nobody gets to the end of a shot before it lands."""


class AutoSaver(QObject):
    """Watches one batch and writes it a moment after it changes."""

    saved = Signal(object)
    """The `Path` written. The status bar says so; nothing else listens yet."""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._batch: Batch | None = None
        self._path: Path | None = None
        self._pending = False
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(DELAY_MS)
        self._timer.timeout.connect(self.flush)

    @property
    def pending(self) -> bool:
        """True when there are edits this has not managed to write yet."""
        return self._pending

    def watch(self, batch: Batch, path: Path | None) -> None:
        """Follow a different batch, writing anything still pending for the last one.

        The order matters: the old batch is flushed to the old path before either is
        replaced, or closing one batch to open another loses the last edit made to it.
        """
        self.flush()
        self._batch = batch
        self._path = path
        self._pending = False

    def adopt(self, path: Path) -> None:
        """Follow the same batch to a file it did not have before. What Save does.

        `watch` would be wrong here: it flushes to the *old* path first, and the old
        path is the one that does not exist. Nothing is left pending because Save has
        just written the batch itself; what changes is where the next autosave goes.
        """
        self._path = path
        self._pending = False

    def schedule(self) -> None:
        """Something changed. Restart the wait rather than adding a second one."""
        self._pending = True
        self._timer.start()

    def flush(self) -> None:
        """Write now, if there is anything to write and anywhere to write it.

        A write that fails is logged and stays pending rather than raising: the delivery
        root and the batch beside it can be on a network mount, and an editor who has
        just typed an In point should not lose the window over a mount that blinked.
        """
        self._timer.stop()
        if not self._pending or self._batch is None or self._path is None:
            return
        try:
            written = batchfile.save(self._batch, self._path)
        except OSError as exc:
            log.warning("autosave to %s failed (%s); the edits are still pending", self._path, exc)
            return
        self._pending = False
        self.saved.emit(written)
