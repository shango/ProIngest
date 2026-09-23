"""One call off the UI thread, its answer back on it.

A run does disk work either side of the pool: the pre-flight stats the delivery root,
the planner lists every shot's delivery folder to pick a version, and the exports write
two spreadsheets. On a Google Drive mount each of those can take seconds, and on the UI
thread that is a window that has stopped responding (review 2026-09-23, F17).

The shape is `ui/scanner.py`'s: a worker `QObject` moved onto a `QThread` that lives only
as long as the call. **The batch is locked while it runs** (D15), which is what makes it
safe for the call to write to the batch from the other thread: nothing on this one may
change it until the answer is back.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from PySide6.QtCore import QObject, QThread, Signal

log = logging.getLogger(__name__)

SHUTDOWN_WAIT_MS = 30_000
"""How long closing the window waits for a call in flight. The scan's wait, for the same
reason: a slow mount must not be a window that cannot be closed."""


class Failure:
    """The call raised. Carried rather than raised, so the answer always arrives."""

    def __init__(self, error: BaseException) -> None:
        self.error = error


class _Call(QObject):
    done = Signal(object)

    def __init__(self, work: Callable[[], object]) -> None:
        super().__init__()
        self._work = work

    def run(self) -> None:
        try:
            result: object = self._work()
        except Exception as exc:
            log.exception("background work failed")
            result = Failure(exc)
        self.done.emit(result)


class Background(QObject):
    """Runs one call at a time on a worker thread and hands its result to `then`.

    `then` runs on the UI thread with the call's return value, or a `Failure`.
    """

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._thread: QThread | None = None
        self._call: _Call | None = None
        self._then: Callable[[object], None] | None = None
        self._result: object = None

    @property
    def busy(self) -> bool:
        return self._thread is not None

    def run(self, work: Callable[[], object], then: Callable[[object], None]) -> None:
        if self.busy:
            raise RuntimeError("background work is already running")
        call = _Call(work)
        thread = QThread(self)
        call.moveToThread(thread)
        thread.started.connect(call.run)
        call.done.connect(self._collect)
        thread.finished.connect(self._cleanup)
        self._thread, self._call, self._then = thread, call, then
        thread.start()

    def shutdown(self) -> None:
        """Wait for a call in flight. What closing the window calls."""
        thread = self._thread
        if thread is None:
            return
        # Nobody is left to hand the answer to: the window is closing.
        self._then = None
        thread.quit()
        if not thread.wait(SHUTDOWN_WAIT_MS):
            log.warning("background work did not finish within %d ms", SHUTDOWN_WAIT_MS)

    def _collect(self, result: object) -> None:
        self._result = result
        if self._thread is not None:
            self._thread.quit()

    def _cleanup(self) -> None:
        """Hand the answer over once the thread is gone, so `then` may start another."""
        if self._call is not None:
            self._call.deleteLater()
        if self._thread is not None:
            self._thread.deleteLater()
        then, result = self._then, self._result
        self._thread, self._call, self._then, self._result = None, None, None, None
        if then is not None:
            then(result)


class Inline(Background):
    """The same contract, run on the calling thread. What the window tests use, so a
    test reads the result straight after the trigger; `Background` has its own tests."""

    def run(self, work: Callable[[], object], then: Callable[[object], None]) -> None:
        try:
            result: object = work()
        except Exception as exc:
            result = Failure(exc)
        then(result)
