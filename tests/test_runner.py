"""The render pool driven from the window. `ui/runner.py`, M5.5.

Two halves, and they are tested differently. `RunProgress` is arithmetic with no Qt in
it, so it is driven with `Progress` messages made by hand and a fake clock, which is the
only way an ETA is testable at all. The `Runner` is a thread, so what is asserted about
it is the handover: where the work happens, that the messages arrive on the UI thread,
that `finished` always fires, and that cancelling reaches the pool.

`render.execute` is replaced in most of these, because what is under test is the wiring
and a real pool would spend a second spawning processes to prove something about Qt. The
stand-in replaces it on `core.render`, the module `ui/runner.py` reaches through, so
nothing about the patch depends on how it imported. One test at the end runs the real
pool on real jobs, so the stand-in is not the only thing this module is proved against.

Nothing waits on a signal with `QSignalSpy.wait`: a signal that fires before the wait
starts leaves it sitting until the timeout. `pump_until` spins the loop and asks.
"""

from __future__ import annotations

import multiprocessing
import time
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import QThread
from PySide6.QtWidgets import QApplication

from proingest.core import render
from proingest.core.models import Deliverable, FrameRate
from proingest.core.planner import DeliverableJob
from proingest.core.render import Progress
from proingest.ui.runner import RENDERING, STARTING, Runner, RunProgress, format_eta
from tests.fixtures import color as color_fixtures
from tests.fixtures import media as media_fixtures

TIMEOUT_MS = 60_000


@pytest.fixture
def runner(qt_app: QApplication) -> Iterator[Runner]:
    built = Runner()
    yield built
    built.shutdown()


def pump_until(predicate: Callable[[], bool], timeout_ms: int = TIMEOUT_MS) -> bool:
    """Run the event loop until the predicate holds or the time is up."""
    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        QApplication.processEvents()
        if predicate():
            return True
        time.sleep(0.005)
    return predicate()


def job(name: str = "MELT0001_pl01_v01", frames: int = 10) -> DeliverableJob:
    """A job with a frame range, which is all `RunProgress` and the thread need of one."""
    return DeliverableJob(
        kind="raw_dir",
        source=Path("/turnover/MELT0001_pl01.mov"),
        destination=Path("/delivery") / name,
        version=1,
        shot_code="MELT0001",
        elem="pl01",
        in_frame=0 if frames else None,
        out_frame=frames - 1 if frames else None,
        rate=FrameRate(24),
    )


class Collected:
    """Everything one run emitted, in the order it arrived."""

    def __init__(self, runner: Runner) -> None:
        self.messages: list[Progress] = []
        self.written: list[Deliverable] | None = None
        self.cancelled: bool | None = None
        self.failures: list[str] = []
        runner.progressed.connect(self.messages.append)
        runner.failed.connect(self.failures.append)
        runner.finished.connect(self._done)

    def _done(self, written: list[Deliverable], cancelled: bool) -> None:
        self.written = written
        self.cancelled = cancelled

    @property
    def finished(self) -> bool:
        return self.written is not None


def fake_execute(
    body: Callable[[Callable[[Progress], None]], None] | None = None,
) -> Callable[..., list[Deliverable]]:
    """A stand-in for `render.execute` that answers without a pool."""

    def execute(
        jobs: list[DeliverableJob],
        workers: int = 4,
        on_progress: Callable[[Progress], None] | None = None,
        cancel: object = None,
    ) -> list[Deliverable]:
        if body is not None and on_progress is not None:
            body(on_progress)
        return [item.to_deliverable() for item in jobs]

    return execute


class TestTheArithmetic:
    def test_a_job_with_no_messages_has_got_nowhere(self) -> None:
        progress = RunProgress([job(frames=10)])
        assert progress.fraction("MELT0001_pl01_v01") == 0.0
        assert progress.percent == 0

    def test_frames_move_the_fraction(self) -> None:
        progress = RunProgress([job(frames=10)])
        progress.update(Progress("MELT0001_pl01_v01", "frame", 5, 10))
        assert progress.fraction("MELT0001_pl01_v01") == 0.5
        assert progress.percent == 50

    def test_a_finished_job_is_full_whatever_its_frame_count(self) -> None:
        """A copy has no frames at all, and a bar stuck at zero would read as stalled."""
        progress = RunProgress([job("camdata.txt", frames=0)])
        progress.update(Progress("camdata.txt", "done", 0, 0))
        assert progress.fraction("camdata.txt") == 1.0

    def test_percent_falls_back_to_jobs_when_nothing_has_frames(self) -> None:
        progress = RunProgress([job("a.txt", frames=0), job("b.txt", frames=0)])
        progress.update(Progress("a.txt", "done", 0, 0))
        assert progress.percent == 50

    def test_a_failed_job_is_finished_but_not_done(self) -> None:
        progress = RunProgress([job()])
        progress.update(Progress("MELT0001_pl01_v01", "failed", 0, 10, "ffmpeg said no"))
        assert progress.jobs_finished == 1
        assert not progress.is_done("MELT0001_pl01_v01")
        assert not progress.is_running("MELT0001_pl01_v01")

    def test_a_started_job_is_running_until_it_says_otherwise(self) -> None:
        progress = RunProgress([job()])
        progress.update(Progress("MELT0001_pl01_v01", "started", 0, 10))
        assert progress.is_running("MELT0001_pl01_v01")
        assert progress.jobs_running == 1
        progress.update(Progress("MELT0001_pl01_v01", "done", 10, 10))
        assert progress.jobs_running == 0

    def test_a_name_the_run_never_planned_is_not_known(self) -> None:
        """The model asks about every deliverable on a row, including ones from a
        previous run that this one did not plan."""
        progress = RunProgress([job()])
        assert progress.knows("MELT0001_pl01_v01")
        assert not progress.knows("MELT0002_pl01_v01")

    def test_throughput_and_eta_come_from_the_clock(self) -> None:
        now = [100.0]
        progress = RunProgress([job(frames=100)], clock=lambda: now[0])
        assert progress.frames_per_second is None, "nothing written yet"
        now[0] = 110.0
        progress.update(Progress("MELT0001_pl01_v01", "frame", 20, 100))
        assert progress.frames_per_second == pytest.approx(2.0)
        assert progress.eta_seconds == pytest.approx(40.0)

    def test_the_summary_says_only_what_it_knows(self) -> None:
        now = [100.0]
        progress = RunProgress([job(frames=100)], clock=lambda: now[0])
        assert progress.summary() == "0%, 0/1 deliverables"
        now[0] = 110.0
        progress.update(Progress("MELT0001_pl01_v01", "frame", 20, 100))
        assert progress.summary() == "20%, 0/1 deliverables, 1 running, 2.0 frames/s, 40s left"

    @pytest.mark.parametrize(
        ("seconds", "text"),
        [(9, "9s"), (59, "59s"), (60, "1m 00s"), (425, "7m 05s"), (4320, "1h 12m")],
    )
    def test_an_eta_reads_coarser_the_longer_it_is(self, seconds: int, text: str) -> None:
        assert format_eta(seconds) == text


class TestTheLineOfWords:
    """`activity`, which is what UI_SPEC section 7.1's line under the bar says."""

    def test_a_run_whose_pool_has_not_spoken_yet_says_it_is_starting(self) -> None:
        assert RunProgress([job()]).activity == STARTING

    def test_a_running_job_is_named(self) -> None:
        progress = RunProgress([job()])
        progress.update(Progress("MELT0001_pl01_v01", "started", 0, 10))
        assert progress.activity == f"{RENDERING} MELT0001_pl01_v01"

    def test_the_line_holds_still_while_other_jobs_report(self) -> None:
        """Four workers report several times a second, and a line that followed the
        newest message would be a flicker rather than a sentence."""
        progress = RunProgress([job("a"), job("b")])
        progress.update(Progress("a", "started", 0, 10))
        progress.update(Progress("b", "started", 0, 10))
        progress.update(Progress("b", "frame", 5, 10))
        assert progress.activity == f"{RENDERING} a"

    def test_it_moves_on_when_the_job_it_names_finishes(self) -> None:
        progress = RunProgress([job("a"), job("b")])
        progress.update(Progress("a", "started", 0, 10))
        progress.update(Progress("b", "started", 0, 10))
        progress.update(Progress("a", "done", 10, 10))
        assert progress.activity == f"{RENDERING} b"

    def test_a_run_with_nothing_left_running_says_nothing(self) -> None:
        """What comes after the last job is the window's step, not a worker's."""
        progress = RunProgress([job()])
        progress.update(Progress("MELT0001_pl01_v01", "started", 0, 10))
        progress.update(Progress("MELT0001_pl01_v01", "done", 10, 10))
        assert progress.activity == ""


class TestWhereItRuns:
    def test_the_pool_is_driven_from_another_thread(
        self, runner: Runner, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """CLAUDE.md keeps long work off the UI thread, and a run is the longest there is."""
        threads: list[QThread] = []
        monkeypatch.setattr(
            render, "execute", fake_execute(lambda _p: threads.append(QThread.currentThread()))
        )
        collected = Collected(runner)
        runner.start([job()])

        assert pump_until(lambda: collected.finished)
        assert threads and threads[0] is not QThread.currentThread()

    def test_progress_arrives_on_the_ui_thread(self, runner: Runner, monkeypatch: pytest.MonkeyPatch) -> None:
        """`execute` calls back on its own drain thread; the queued signal is the last leg."""
        ui_thread = QThread.currentThread()
        seen: list[QThread] = []

        def body(on_progress: Callable[[Progress], None]) -> None:
            on_progress(Progress("MELT0001_pl01_v01", "frame", 1, 10))

        monkeypatch.setattr(render, "execute", fake_execute(body))
        collected = Collected(runner)
        runner.progressed.connect(lambda _m: seen.append(QThread.currentThread()))
        runner.start([job()])

        assert pump_until(lambda: collected.finished and bool(collected.messages))
        assert seen == [ui_thread]
        assert collected.messages[0].frames_done == 1

    def test_the_records_come_back(self, runner: Runner, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(render, "execute", fake_execute())
        collected = Collected(runner)
        runner.start([job("one_v01"), job("two_v01")])

        assert pump_until(lambda: collected.finished)
        assert collected.written is not None
        assert [item.name for item in collected.written] == ["one_v01", "two_v01"]
        assert collected.cancelled is False


class TestStartingAndStopping:
    def test_it_is_busy_while_it_runs_and_free_afterwards(
        self, runner: Runner, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(render, "execute", fake_execute())
        collected = Collected(runner)
        runner.start([job()])
        assert runner.busy

        assert pump_until(lambda: collected.finished)
        assert not runner.busy

    def test_a_second_run_on_top_of_one_is_refused(
        self, runner: Runner, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(render, "execute", fake_execute())
        collected = Collected(runner)
        runner.start([job()])
        with pytest.raises(RuntimeError):
            runner.start([job()])
        assert pump_until(lambda: collected.finished)

    def test_no_jobs_still_reports_finished(self, runner: Runner) -> None:
        """The window turns its progress bar off on `finished`, so it always fires."""
        collected = Collected(runner)
        runner.start([])
        assert collected.finished
        assert collected.written == []
        assert not runner.busy

    def test_cancelling_sets_the_event_the_workers_watch(
        self, runner: Runner, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The pool's own cancellation, not a flag this module invented."""
        seen: list[bool] = []

        def execute(
            jobs: list[DeliverableJob],
            workers: int = 4,
            on_progress: Callable[[Progress], None] | None = None,
            cancel: object = None,
        ) -> list[Deliverable]:
            assert cancel is not None
            while not cancel.is_set():  # type: ignore[attr-defined]
                time.sleep(0.005)
            seen.append(True)
            return []

        monkeypatch.setattr(render, "execute", execute)
        collected = Collected(runner)
        runner.start([job()])
        assert pump_until(lambda: runner.busy)
        runner.cancel()

        assert pump_until(lambda: collected.finished)
        assert seen == [True]
        assert collected.cancelled is True

    def test_a_pool_that_cannot_start_is_reported_and_still_finishes(
        self, runner: Runner, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A worker thread that dies silently is a window waiting forever."""

        def explode(*args: object, **kwargs: object) -> list[Deliverable]:
            raise OSError("no processes left")

        monkeypatch.setattr(render, "execute", explode)
        collected = Collected(runner)
        runner.start([job()])

        assert pump_until(lambda: collected.finished)
        assert collected.written == []
        assert collected.failures == ["no processes left"]

    def test_shutdown_waits_for_the_thread(self, runner: Runner, monkeypatch: pytest.MonkeyPatch) -> None:
        """A `QThread` still running when its owner is collected is a crash on the way out."""
        monkeypatch.setattr(render, "execute", fake_execute())
        runner.start([job()])
        thread = runner._thread
        assert thread is not None
        runner.shutdown()
        assert thread.isFinished()


class TestAHungRun:
    def test_shutdown_ends_the_workers_rather_than_waiting_again(
        self, runner: Runner, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """F18: the close has already waited; blocking two more minutes froze the window."""
        from proingest.ui import runner as module

        waits: list[int] = []

        class Stuck:
            def quit(self) -> None:
                pass

            def wait(self, ms: int) -> bool:
                waits.append(ms)
                return len(waits) > 1

        class Child:
            terminated = False

            def terminate(self) -> None:
                Child.terminated = True

        monkeypatch.setattr(multiprocessing, "active_children", lambda: [Child()])
        runner._thread = Stuck()  # type: ignore[assignment]
        runner.shutdown()
        runner._thread = None

        assert Child.terminated
        assert waits == [module.SHUTDOWN_GRACE_MS, module.SHUTDOWN_GRACE_MS]


def test_a_real_pool_runs_through_the_worker_thread(runner: Runner, tmp_path: Path) -> None:
    """The one case with no stand-in: real processes, spawned from inside a `QThread`.

    Worth the second it costs. Everything above replaces `execute`, and the thing most
    likely to go wrong with a process pool driven from a GUI is the spawn itself.
    """
    first = 1001
    fixture = media_fixtures.make_exr_sequence(tmp_path / "src", count=3, first=first)
    real = DeliverableJob(
        kind="raw_dir",
        source=fixture.path_for(first),
        destination=tmp_path / "out" / "MELT0001_pl01_raw_4k_v01",
        version=1,
        shot_code="MELT0001",
        elem="pl01",
        in_frame=first,
        out_frame=first + 2,
        source_is_sequence=True,
        source_size=media_fixtures.SMALL,
        rate=FrameRate(24),
        source_start_frame=first,
        shot_color=color_fixtures.UNGRADED,
    )
    collected = Collected(runner)
    runner.start([real], workers=1)

    assert pump_until(lambda: collected.finished)
    assert collected.written is not None
    assert [item.status for item in collected.written] == ["done"]
    assert real.destination.is_dir()
    assert [message.state for message in collected.messages][-1] == "done"
