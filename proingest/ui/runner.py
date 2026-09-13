"""The render pool, driven from the window.

`core/render.execute` is a blocking call that owns a process pool, so it goes on a
worker thread the same way the scan does (`ui/scanner.py`), and for the same reason:
CLAUDE.md keeps long work off the UI thread and keeps Qt out of core. What crosses the
boundary is a list of `DeliverableJob`, which is already self contained because it
crosses a process boundary too, and a list of `Deliverable` coming back. **The batch
never goes near the worker**: planning and applying the results are the window's own
work, on its own thread.

Progress arrives twice removed - a worker process puts a `Progress` on a queue, and
`execute`'s drain thread hands it to `on_progress` in this process - so what this module
forwards is already in the right process and only in the wrong thread. A queued signal
carries it the last step.

**Nothing here repaints anything.** The messages are folded into a `RunProgress` and the
window reads that on a timer, because a hundred shot run emits a message per frame per
worker and a repaint per message would be a UI thread doing nothing else.
"""

from __future__ import annotations

import logging
import multiprocessing
import time
from collections.abc import Callable, Sequence
from multiprocessing.synchronize import Event as EventType
from typing import cast

from PySide6.QtCore import QObject, QThread, Signal

from proingest.core import render
from proingest.core.models import DEFAULT_WORKERS, Deliverable
from proingest.core.planner import DeliverableJob

log = logging.getLogger(__name__)

SHUTDOWN_WAIT_MS = 120_000
"""How long `shutdown` waits for the pool before giving up on it.

Longer than the scan's wait, because what it is waiting for is every in-flight job
reaching its next frame boundary, and one of those may be a 4k reference encode that
reports no progress and cannot be interrupted (PROGRESS section 9). Not infinite: a
wedged worker must not be a window that cannot be closed.
"""

FINISHED_STATES = frozenset({"done", "failed", "cancelled"})
"""A job the pool will say nothing more about."""

RUNNING_STATES = frozenset({"started", "frame"})

STARTING = "Starting the render pool"
"""What the strip says between the last plan and the first message from a worker.

A spawned pool takes a second or two to exist and the run has genuinely started, so the
alternative is a blank line under a bar at zero, which reads as a tool that has stalled.
"""

RENDERING = "Rendering"
"""The verb the line uses for a job in flight, followed by the deliverable's name.

The name verbatim rather than a prettier form of it: it is the name on disk, the name in
the Deliverables tab and the name in the log, and a line that renames it is a line the
editor cannot search for.
"""


class RunProgress:
    """Everything one run has said so far, folded into what the window shows.

    Plain Python, no Qt: the arithmetic behind a percentage and an ETA is worth testing
    without a window around it, and the same numbers feed the status bar and the
    per row bars in the Progress column.

    Frames are the unit of the percentage rather than jobs, because jobs are wildly
    uneven: a 240 frame plate and a camData copy are one job each. A run made only of
    copies has no frames at all, and falls back to counting jobs.
    """

    def __init__(
        self, jobs: Sequence[DeliverableJob], clock: Callable[[], float] = time.monotonic
    ) -> None:
        self._clock = clock
        self._started_at = clock()
        self._totals = {job.name: job.frame_count for job in jobs}
        self._done: dict[str, int] = {}
        self._states: dict[str, render.ProgressState] = {}

    def update(self, message: render.Progress) -> None:
        """Fold one message in. Called on the UI thread, one message at a time."""
        self._states[message.name] = message.state
        if message.state == "frame":
            self._done[message.name] = message.frames_done
        elif message.state == "done":
            self._done[message.name] = self._totals.get(message.name, message.frames_total)
        elif message.state in FINISHED_STATES:
            # A failed or cancelled job keeps the frames it actually wrote: they were
            # written, and pretending otherwise would make the throughput a lie.
            self._done.setdefault(message.name, 0)

    # --- what one job is doing -------------------------------------------------------

    def fraction(self, name: str) -> float:
        """0.0 to 1.0 for one job. A finished job is full whatever its frame count."""
        if self._states.get(name) in FINISHED_STATES:
            return 1.0
        total = self._totals.get(name, 0)
        if total <= 0:
            return 0.0
        return min(1.0, self._done.get(name, 0) / total)

    def is_done(self, name: str) -> bool:
        """Written and verified. A failed or cancelled job is finished but not done."""
        return self._states.get(name) == "done"

    def is_running(self, name: str) -> bool:
        return self._states.get(name) in RUNNING_STATES

    def knows(self, name: str) -> bool:
        """Whether this job is part of the run at all."""
        return name in self._totals

    # --- what the whole run is doing --------------------------------------------------

    @property
    def jobs_total(self) -> int:
        return len(self._totals)

    @property
    def jobs_finished(self) -> int:
        return sum(1 for state in self._states.values() if state in FINISHED_STATES)

    @property
    def jobs_running(self) -> int:
        return sum(1 for state in self._states.values() if state in RUNNING_STATES)

    @property
    def frames_total(self) -> int:
        return sum(self._totals.values())

    @property
    def frames_done(self) -> int:
        return sum(self._done.values())

    @property
    def percent(self) -> int:
        """Overall percent, by frames where there are any and by jobs where there are not."""
        if self.frames_total:
            return int(100 * self.frames_done / self.frames_total)
        if not self.jobs_total:
            return 0
        return int(100 * self.jobs_finished / self.jobs_total)

    @property
    def frames_per_second(self) -> float | None:
        """Throughput over the whole run, or None until a frame has been written.

        Over the whole run rather than a recent window: the number an editor uses it for
        is "how long is this going to take", and a window narrow enough to feel live
        swings by a factor of ten as jobs start and finish.
        """
        elapsed = self._clock() - self._started_at
        if elapsed <= 0 or not self.frames_done:
            return None
        return self.frames_done / elapsed

    @property
    def eta_seconds(self) -> float | None:
        """Seconds left at the current throughput, or None when it cannot be said yet."""
        rate = self.frames_per_second
        if rate is None or not self.frames_total:
            return None
        return max(0.0, (self.frames_total - self.frames_done) / rate)

    @property
    def activity(self) -> str:
        """What the run is working on now, in words (UI_SPEC section 7.1).

        The **longest running** job rather than the most recent message: four workers
        report several times a second and a line that follows the newest one is a
        flicker rather than a sentence. `_states` is in the order jobs first reported,
        so the job named here stays named until it finishes.

        Empty once every job is finished, because what comes next - applying the
        records and writing the spreadsheets - is the window's step rather than a
        worker's, and the window is what says it.
        """
        for name, state in self._states.items():
            if state in RUNNING_STATES:
                return f"{RENDERING} {name}"
        return STARTING if not self._states else ""

    def summary(self) -> str:
        """The status bar's line: percent, jobs running, throughput and ETA (section 7).

        Each part appears only once it means something. A run in its first second has no
        throughput to report, and a made up one would be read as a real one.
        """
        parts = [f"{self.percent}%", f"{self.jobs_finished}/{self.jobs_total} deliverables"]
        if self.jobs_running:
            parts.append(f"{self.jobs_running} running")
        rate = self.frames_per_second
        if rate is not None:
            parts.append(f"{rate:.1f} frames/s")
        eta = self.eta_seconds
        if eta is not None:
            parts.append(f"{format_eta(eta)} left")
        return ", ".join(parts)


def format_eta(seconds: float) -> str:
    """`42s`, `7m 05s`, `1h 12m`. Coarser as it gets longer, because so is the estimate."""
    total = int(seconds)
    if total < 60:
        return f"{total}s"
    if total < 3600:
        return f"{total // 60}m {total % 60:02d}s"
    return f"{total // 3600}h {(total % 3600) // 60:02d}m"


class _RunJob(QObject):
    """The `execute` call itself, on the worker thread. One `run` per `Runner.start`."""

    progressed = Signal(object)
    done = Signal(object)

    def __init__(self, jobs: list[DeliverableJob], workers: int, cancel: EventType) -> None:
        super().__init__()
        self._jobs = jobs
        self._workers = workers
        self._cancel = cancel

    def run(self) -> None:
        """Render everything and emit the records, whatever happened.

        `execute` returns a record per job even when jobs fail or the run is cancelled,
        so the only thing that reaches the `except` is the pool itself failing to start.
        That is reported as an empty result rather than an exception on a worker thread,
        because a thread that dies silently leaves the window waiting forever.
        """
        try:
            written = render.execute(
                self._jobs,
                workers=self._workers,
                on_progress=self._forward,
                cancel=self._cancel,
            )
        except Exception as exc:
            log.exception("the render pool failed")
            self.done.emit(RunFailure(str(exc)))
            return
        self.done.emit(written)

    def _forward(self, message: render.Progress) -> None:
        """Called on `execute`'s drain thread, which is neither of the two Qt ones.

        The emit is safe from there: the receiver lives on the UI thread, so Qt queues
        it, and `Progress` is frozen and is never touched again by the sender.
        """
        self.progressed.emit(message)


class RunFailure:
    """The pool could not run at all. Carried rather than raised, so `finished` fires."""

    def __init__(self, message: str) -> None:
        self.message = message


class Runner(QObject):
    """Runs a planned batch on a worker thread, one run at a time.

    The shape is `ui/scanner.py`'s, deliberately: a worker `QObject` moved onto a
    `QThread` that lives only as long as the work. The differences are that the work
    here is itself a process pool, and that cancelling is a `multiprocessing.Event` the
    workers watch rather than a flag between folders, so Stop reaches a job mid flight.
    """

    progressed = Signal(object)
    """One `render.Progress`, already in this process, now on the UI thread."""

    finished = Signal(object, bool)
    """`list[Deliverable]` and whether Stop was pressed. Always fires exactly once."""

    failed = Signal(str)
    """The pool could not run. `finished` still fires, with no deliverables."""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._thread: QThread | None = None
        self._job: _RunJob | None = None
        self._cancel: EventType | None = None
        self._cancelled = False
        self._results: list[Deliverable] = []

    @property
    def busy(self) -> bool:
        return self._thread is not None

    @property
    def cancelled(self) -> bool:
        """Whether the run now finishing was stopped. Read by the banner."""
        return self._cancelled

    def start(self, jobs: list[DeliverableJob], workers: int = DEFAULT_WORKERS) -> None:
        """Render these jobs. They are planned by the caller and owned by the worker."""
        if self.busy:
            raise RuntimeError("a run is already going")
        self._cancelled = False
        if not jobs:
            self.finished.emit([], False)
            return

        # Spawn on every platform, matching `execute`: the Event has to come from the
        # same context as the pool that waits on it.
        self._cancel = multiprocessing.get_context("spawn").Event()
        job = _RunJob(jobs, workers, self._cancel)
        thread = QThread(self)
        job.moveToThread(thread)

        thread.started.connect(job.run)
        job.progressed.connect(self.progressed)
        job.done.connect(self._collect)
        thread.finished.connect(self._cleanup)

        self._thread = thread
        self._job = job
        self._results = []
        thread.start()

    def cancel(self) -> None:
        """Stop: no new jobs, and in-flight ones stop at their next frame boundary.

        Returns immediately. What is already written stays written, and a job that was
        part way through discards its `.part` rather than leaving it (UI_SPEC section 7).
        """
        if self._cancel is not None:
            self._cancelled = True
            self._cancel.set()

    def shutdown(self) -> None:
        """Stop and wait. What closing the window calls.

        The wait is not optional: a `QThread` still running when its Python owner is
        collected is a crash on the way out, and this one owns a process pool as well.
        """
        self.cancel()
        thread = self._thread
        if thread is None:
            return
        # `quit` before the wait, not after: `_collect` is what normally ends the
        # thread's event loop and it runs on the UI thread, which is the thread about
        # to block here. Asking the thread directly is what stops that being a deadlock
        # that lasts until the timeout.
        thread.quit()
        if not thread.wait(SHUTDOWN_WAIT_MS):
            log.warning("the render thread did not stop within %d ms", SHUTDOWN_WAIT_MS)

    def _collect(self, written: object) -> None:
        """The worker's answer, on the UI thread. The thread is asked to stop after it."""
        if isinstance(written, RunFailure):
            self.failed.emit(written.message)
            self._results = []
        else:
            self._results = cast("list[Deliverable]", written)
        if self._thread is not None:
            self._thread.quit()

    def _cleanup(self) -> None:
        """Drop the thread and its job, then say the run is over.

        `finished` is emitted from here rather than from `_collect` so that a listener
        that starts another run is not starting it on top of a thread still winding
        down. `deleteLater` because the job lives on a thread that is ending.
        """
        if self._job is not None:
            self._job.deleteLater()
        if self._thread is not None:
            self._thread.deleteLater()
        self._job = None
        self._thread = None
        self._cancel = None
        self.finished.emit(self._results, self._cancelled)
