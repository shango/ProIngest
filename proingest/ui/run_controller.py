"""What one Run does, from the pre-flight to the banner.

`ui/runner.py` is the pool on its worker thread and knows nothing about a batch. This is
the other half: the three steps on the UI thread before a job reaches a worker, the four
surfaces a run reports through while it does, and what is written onto the batch when it
comes back. It is split out of `ui/main_window.py` because it was the largest single
subject in there and the only one with a sequence of its own (REVIEW.md S1).

**It holds the window rather than a list of the pieces it needs.** A run touches the
batch, the model, the strip, the status bar, the autosaver, the Issues dock and two
dialogs, and a constructor taking all seven would be the same coupling written out at
greater length. What the boundary buys is that the run's own state - the progress fold
up, the two timers, where the exports went - lives beside the code that reads it rather
than among the window's attributes.

**The batch is written on this thread and nothing else is.** Pre-flight, planning and
`apply_results` all change the model, which is why they are here and not in the worker.
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, cast

from PySide6.QtCore import QObject, QTimer

from proingest.core import clf, exports, planner, qc, render
from proingest.core.models import Batch, Deliverable, QCResult
from proingest.core.planner import DeliverableJob
from proingest.ui import settings_form
from proingest.ui.background import Background, Failure
from proingest.ui.run_strip import LINK_COLOR
from proingest.ui.runner import SHUTDOWN_WAIT_MS, Runner, RunProgress

if TYPE_CHECKING:
    from proingest.ui.main_window import MainWindow

log = logging.getLogger(__name__)

NOTHING_TO_RENDER = "Nothing to render: no row produced a deliverable"
CLOSING_AFTER_RUN = "Stopping the run, then closing..."

MUST_FIX_TITLE = "Fix these before running"
"""The dialog Run opens when anything must be fixed first (D8, D9).

Every must-fix in the batch, each with where it is, because the fix is in the folder:
the editor corrects it there, presses Scan, and runs.
"""

MUST_FIX_SHOWN = 20
"""How many the dialog lists before it points at the Issues dock for the rest."""

CHECKING_BATCH = "Checking the batch"
PLANNING = "Planning {count} shots"
CHECKING_RESULTS = "Checking what landed"
WRITING_REPORTS = "Writing the QC log and the shot tracker"
"""The steps of a run that happen on the UI thread rather than in a worker.

Section 7.1's line names one step at a time, and the ones a worker reports come from
`RunProgress.activity`. These four are the ones either side of the pool, which are the
steps that would otherwise be a window that has stopped responding with nothing said.
"""

RUN_REFRESH_MS = 200
"""How often the status bar and the row bars are redrawn while a run is going.

Five times a second reads as live and costs nothing. The alternative, repainting per
progress message, is a message per frame per worker: on a fast copy job that is
thousands a second, all of them saying something the eye cannot see."""


def banner_text(written: Sequence[Deliverable], reports: Path | None, cancelled: bool) -> str:
    """UI_SPEC section 7's banner, with the path as the thing that can be clicked.

    The wording is the spec's, except that a stopped run says so: the counts alone would
    read as a batch that finished with most of it skipped, which is the one thing an
    editor who pressed Stop already knows and the one thing somebody who did not needs
    telling. The exports sentence is dropped rather than faked when nothing was written.
    """
    counts = Counter(item.status for item in written)
    head = "Run stopped" if cancelled else "Batch complete"
    text = f"{head}: {counts['done']} done, {counts['failed']} failed, {counts['skipped']} skipped."
    if reports is None:
        return f"{text} No exports were written."
    return f"{text} Exports written to {_reports_link(reports)}"


def export_banner_text(reports: Path) -> str:
    """The banner after Export alone: where the two spreadsheets went, and nothing else."""
    return f"Exports written to {_reports_link(reports)}"


def _reports_link(reports: Path) -> str:
    return f'<a href="#reports" style="color:{LINK_COLOR}">{reports}</a>'


def must_fix_text(found: Sequence[tuple[str, QCResult]]) -> str:
    """The dialog's body: one line per must-fix, where it is first, capped."""
    lines = [f"{where}: {result.rule_id} {result.message}" for where, result in found[:MUST_FIX_SHOWN]]
    if len(found) > MUST_FIX_SHOWN:
        lines.append(f"and {len(found) - MUST_FIX_SHOWN} more; see the Issues dock")
    lines.append("")
    lines.append("Correct them in the turnover folder, press Scan, then Run.")
    return "\n".join(lines)


class RunController(QObject):
    """The window's Run and Stop, and everything between them.

    Built once, in `MainWindow._build_central`, and it wires itself to the pool and to
    the strip's link from there: a run has one owner, and the window asking it to start
    is the whole of what the window has to know.
    """

    def __init__(self, window: MainWindow) -> None:
        super().__init__(window)
        self._window = window
        self.runner = Runner(self)
        self.runner.progressed.connect(self.progressed)
        self.runner.finished.connect(self._finished)
        self.runner.failed.connect(lambda text: window.report_problem("The run failed", text))
        self.background: Background = Background(self)
        """Where a run's disk work goes: the pre-flight, the plan and the reports (F17)."""
        self._stop_requested = False
        self._preparing = False

        self.progress: RunProgress | None = None
        """Everything this run has said so far, or None when nothing is running.

        Public because `build/screenshots.py` poses a run with one, which is the only
        way to photograph a window mid render without rendering anything.
        """

        self._reports_folder: Path | None = None
        self._timer = QTimer(self)
        self._timer.setInterval(RUN_REFRESH_MS)
        self._timer.timeout.connect(self.refresh)
        # A close during a run: the run is stopped and the close retried when its
        # results are in, or when this gives up waiting for them.
        self._close_wait = QTimer(self)
        self._close_wait.setSingleShot(True)
        self._close_wait.timeout.connect(self._close_without_results)
        self._closing_after_run = False
        self.wait_expired = False
        """Whether the bounded wait for a closing run's results ran out, in which case
        the next close goes ahead without them rather than waiting again."""

        window.run_strip.link_activated.connect(self._open_reports)

    @property
    def busy(self) -> bool:
        """A run in any of its steps, from the pre-flight to the last report written."""
        return self.runner.busy or self.background.busy

    @property
    def preparing(self) -> bool:
        """Checking or planning, before anything has reached a worker."""
        return self._preparing

    @property
    def cancelled(self) -> bool:
        """Whether the run now finishing was stopped. Read by the toolbar and the banner."""
        return self.runner.cancelled or self._stop_requested

    @property
    def stoppable(self) -> bool:
        """Whether Stop means anything now: a run rendering, or about to."""
        if self.cancelled:
            return False
        return self.runner.busy or self._preparing

    # --- the run ----------------------------------------------------------------------

    def start(self) -> None:
        """Plan the batch and render it. UI_SPEC section 7, and PRD FR-6 and FR-7.

        Three things happen before a job reaches a worker, and all three write to the
        batch: pre-flight, which reads the disk and records what it found on the rows;
        planning, which resolves one version per shot from what is already in the
        delivery folder and replaces every row's deliverables with the plan; and the
        check that anything came out of it. The pool gets the jobs and nothing else
        (`ui/runner.py`).

        **The first two run off the UI thread** (F17): both read a network mount. The
        batch is locked while they do (D15), so nothing on this thread changes it under
        them, and each answer comes back here before the next step starts.

        **Any must-fix anywhere stops the run** (D8): the whole batch waits for the
        folder to be corrected and re-scanned (`qc.must_fix`).
        """
        window = self._window
        if not window.batch_open or self.busy or window.scanner.busy:
            return
        batch = window.batch
        if batch.delivery_root is None:
            # Section 7: prompted once, here, rather than by a dialog every run opens.
            window.choose_delivery_root()
            if batch.delivery_root is None:
                return

        self._stop_requested = False
        self._preparing = True
        window.run_strip.start()
        window.run_strip.say(CHECKING_BATCH)
        self.background.run(lambda: qc.preflight(batch), self._checked)
        window.update_state()

    def _checked(self, result: object) -> None:
        """The pre-flight is back: refuse, or plan."""
        window = self._window
        batch = window.batch
        strip = window.run_strip
        window.show_results()
        window.shot_model.refresh_rows()
        if isinstance(result, Failure):
            self._refuse("The batch could not be checked", str(result.error))
            return
        if self._stop_requested:
            self._refuse()
            return
        found = qc.must_fix(batch)
        if found:
            self._refuse(MUST_FIX_TITLE, must_fix_text(found))
            window.show_issues()
            return

        strip.say(PLANNING.format(count=len(batch.rows)))
        root = batch.delivery_root
        assert root is not None
        pattern = settings_form.show_pattern_of(window.settings)
        self.background.run(
            lambda: planner.plan_batch(batch, root, pattern),
            self._planned,
        )
        window.update_state()

    def _planned(self, result: object) -> None:
        """The plan is back: hand it to the pool, or say why there is nothing to hand."""
        window = self._window
        self._preparing = False
        window.shot_model.refresh_rows()
        if isinstance(result, Failure):
            if isinstance(result.error, (ValueError, clf.ClfError)):
                self._refuse("The batch cannot be planned", str(result.error))
            else:
                self._refuse("The batch could not be planned", str(result.error))
            return
        jobs = cast("list[DeliverableJob]", result)
        if self._stop_requested:
            self._refuse()
            return
        if not jobs:
            self._refuse()
            window.statusBar().showMessage(NOTHING_TO_RENDER)
            return

        self.progress = RunProgress(jobs)
        window.shot_model.set_run(self.progress)
        window.progress.setRange(0, 100)
        window.progress.setValue(0)
        window.progress.setVisible(True)
        self._timer.start()
        self.runner.start(jobs, window.settings.workers)
        window.update_state()

    def _refuse(self, title: str = "", text: str = "") -> None:
        """A run that will not start: the strip goes away and the batch unlocks."""
        window = self._window
        self._preparing = False
        window.run_strip.clear()
        if title:
            window.report_problem(title, text)
        window.update_state()
        self._idle()

    def export_reports(self) -> None:
        """Export: both spreadsheets from the batch as it stands, with no render (FR-10).

        What `proingest qc <batch>` does from the command line, and for the same reason
        the rules re-run first: the log has to describe the batch as it is now, not as
        it was when it was last scanned. Phase B is re-applied from what a run recorded,
        so a batch that has never run reports every deliverable as not there, which is
        the true answer. The banner is the run's, minus the counts a run would have.

        Off the UI thread, like a run's own steps: phase B reads back every delivered
        file and the reports are written to the delivery root (F17).
        """
        window = self._window
        if not window.batch_open or self.busy or window.scanner.busy:
            return
        batch = window.batch
        if batch.delivery_root is None:
            window.choose_delivery_root()
            if batch.delivery_root is None:
                return

        def work() -> Path:
            qc.apply_batch_rules(batch, qc.settings_for(batch))
            qc.preflight(batch)
            qc.apply_phase_b(batch)
            return self._write_reports(batch)

        window.run_strip.start()
        window.run_strip.say(WRITING_REPORTS)
        self.background.run(work, self._exported)
        window.update_state()

    def _exported(self, result: object) -> None:
        window = self._window
        window.shot_model.refresh_rows()
        window.show_results()
        window.autosave.schedule()
        reports = self._reports_or_problem(result)
        if reports is None:
            window.run_strip.clear()
        else:
            self._reports_folder = reports
            text = export_banner_text(reports)
            window.run_strip.show_banner(text)
            window.statusBar().showMessage(re.sub(r"<[^>]+>", "", text))
        window.update_state()
        self._idle()

    def stop(self) -> None:
        """Stop: no new jobs, in-flight ones stop at their next frame boundary.

        What is already written stays written and what was part way through discards
        its `.part`, so a stopped run leaves the delivery folder holding finished files
        only (UI_SPEC section 7). The results still come back and are still applied,
        because a job that finished before Stop was pressed is a real deliverable.
        """
        if self.runner.busy:
            self.runner.cancel()
        elif self.preparing:
            # Checking or planning: nothing has reached a worker, so the run just does
            # not start when the step in hand comes back.
            self._stop_requested = True
        else:
            return
        self._window.statusBar().showMessage("Stopping after the frames in flight...")
        self._window.update_state()

    def progressed(self, message: render.Progress) -> None:
        """One message from a worker. Folded in and drawn on the timer, never here."""
        if self.progress is not None:
            self.progress.update(message)

    def refresh(self) -> None:
        """Every surface a run has, five times a second, all off the one `RunProgress`.

        Four of them and each says what the others cannot (section 7.1): the strip's
        bar for the batch, its line for the step, the status bar for the numbers, and
        the Progress column for the shot. Drawn from one object in one place, so they
        cannot disagree about how far along the run is.
        """
        if self.progress is None:
            return
        window = self._window
        window.progress.setValue(self.progress.percent)
        window.run_strip.set_percent(self.progress.percent)
        # Left alone when nothing is running: at the end of a run every job is finished
        # and the next thing to say is `_finished`'s rather than a worker's.
        if activity := self.progress.activity:
            window.run_strip.say(activity)
        window.statusBar().showMessage(self.progress.summary())
        window.shot_model.refresh_rows()

    def _finished(self, written: list[Deliverable], cancelled: bool) -> None:
        """The records, back on the UI thread, written onto the rows they were planned from.

        `apply_results` is what re-runs QC-150 and QC-151, the two phase B rules a worker
        cannot answer, so the Issues dock is only right after it. The exports come next,
        off this thread, because they report what the QC just decided, and the banner
        last because it says where they went.
        """
        self._timer.stop()
        self.progress = None
        window = self._window
        window.shot_model.set_run(None)
        window.progress.setVisible(False)

        batch = window.batch
        window.run_strip.say(CHECKING_RESULTS)
        render.apply_results(batch, written, settings_form.show_pattern_of(window.settings))
        window.shot_model.refresh_rows()
        window.show_results()
        window.autosave.schedule()

        window.run_strip.say(WRITING_REPORTS)
        self.background.run(
            lambda: self._write_reports(batch),
            lambda result: self._reported(result, written, cancelled),
        )
        window.update_state()

    def _reported(self, result: object, written: list[Deliverable], cancelled: bool) -> None:
        window = self._window
        reports = self._reports_or_problem(result)
        text = banner_text(written, reports, cancelled)
        window.run_strip.show_banner(text)
        self._reports_folder = reports
        # The same sentence without its link, because the banner is above the list and
        # the status bar is where the eye already is when a long run ends.
        window.statusBar().showMessage(re.sub(r"<[^>]+>", "", text))
        window.update_state()
        self._idle()

    @staticmethod
    def _write_reports(batch: Batch) -> Path:
        """The two spreadsheets, into the delivery root (FR-10). Off the UI thread.

        Written by the run rather than by a button, because section 7's banner says
        where they are and PRD section 7 puts them at the end of a delivery. A batch
        whose rows have no shot code has no show to file them under, which is a
        `ValueError` from `report_paths`, and the banner then says nothing was written
        instead of naming a folder that does not exist.
        """
        if batch.delivery_root is None:
            raise ValueError("the batch has no delivery root")
        log_path, tracker_path = exports.report_paths(batch, batch.delivery_root)
        exports.write_qc_log(batch, log_path)
        exports.write_shot_tracker(batch, tracker_path)
        return log_path.parent

    def _reports_or_problem(self, result: object) -> Path | None:
        """Where the reports went, or None after saying why they did not.

        **Anything the writer raised is reported**, not only the errors it expects: an
        exception escaping here once left Run greyed and Stop lit for good (F15).
        """
        if isinstance(result, Failure):
            self._window.report_problem("The exports could not be written", str(result.error))
            return None
        return cast("Path", result)

    def _open_reports(self) -> None:
        """The banner's link: the folder the two spreadsheets went into."""
        if self._reports_folder is not None:
            self._window.open_folder(self._reports_folder)

    # --- closing the window during a run ----------------------------------------------

    def close_when_finished(self) -> None:
        """Stop the run and close once its results are applied and its reports written."""
        if self._closing_after_run:
            return
        self._closing_after_run = True
        self._close_wait.start(SHUTDOWN_WAIT_MS)
        self.stop()
        self._window.statusBar().showMessage(CLOSING_AFTER_RUN)

    def _idle(self) -> None:
        """Nothing is left in hand. A close that was waiting for that goes ahead now."""
        if not self._closing_after_run or self.busy:
            return
        self._close_wait.stop()
        self._closing_after_run = False
        self._window.close()

    def _close_without_results(self) -> None:
        """The bounded wait ran out: close the way it used to, dropping the results."""
        log.warning("the run did not stop within %d ms; closing without its results", SHUTDOWN_WAIT_MS)
        self.wait_expired = True
        self._window.close()

    def shutdown(self) -> None:
        """Stop and wait for the pool and any step in hand. What closing the window calls."""
        self.runner.shutdown()
        self.background.shutdown()
