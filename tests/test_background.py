"""`ui/background.py`: one call off the UI thread, its answer back on it (F17).

The window tests use `Inline`, so these are the ones that exercise the thread.
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
from pathlib import Path

from PySide6.QtWidgets import QApplication

from proingest.ui.background import Background, Failure
from tests.test_runner import pump_until


class TestBackground:
    def test_the_work_runs_elsewhere_and_the_answer_comes_back_here(self, qt_app: QApplication) -> None:
        background = Background()
        here = threading.get_ident()
        ran_on: list[int] = []
        answered_on: list[int] = []
        answers: list[object] = []

        def work() -> int:
            ran_on.append(threading.get_ident())
            return 42

        def then(result: object) -> None:
            answered_on.append(threading.get_ident())
            answers.append(result)

        background.run(work, then)
        assert background.busy
        assert pump_until(lambda: bool(answers))
        assert answers == [42]
        assert ran_on != [here]
        assert answered_on == [here]
        assert not background.busy

    def test_a_raise_arrives_as_a_failure_rather_than_a_silent_thread(self, qt_app: QApplication) -> None:
        background = Background()
        answers: list[object] = []

        def work() -> None:
            raise OSError("the mount went away")

        background.run(work, answers.append)
        assert pump_until(lambda: bool(answers))
        assert isinstance(answers[0], Failure)
        assert str(answers[0].error) == "the mount went away"

    def test_the_answer_may_start_the_next_call(self, qt_app: QApplication) -> None:
        """A run's steps chain: the pre-flight's answer starts the plan."""
        background = Background()
        answers: list[object] = []
        background.run(lambda: 1, lambda first: background.run(lambda: 2, answers.append))
        assert pump_until(lambda: bool(answers))
        assert answers == [2]


ABANDONED_SCRIPT = """
import time
from PySide6.QtCore import QObject
from PySide6.QtWidgets import QApplication
from proingest.ui import background

app = QApplication([])
owner = QObject()
work = background.Background(owner)
answers = []
work.run(lambda: time.sleep(2), answers.append)
time.sleep(0.2)
background.SHUTDOWN_WAIT_MS = 100
work.shutdown()
assert not work.busy
del work, owner
assert background.still_running()
while background.still_running():
    time.sleep(0.05)
app.processEvents()
assert answers == [], "nobody is left to hand the answer to"
print("clean")
"""


class TestClosingOnAHungCall:
    def test_a_call_that_will_not_stop_is_left_to_run_out_rather_than_destroyed(self) -> None:
        """Review, 2026-11-08 (E2): after its wait `shutdown` returned with the thread still
        running, the window went, and Qt aborted the process ("QThread: Destroyed while
        thread is still running", exit 134). In a child process, since that is a crash."""
        result = subprocess.run(
            [sys.executable, "-c", ABANDONED_SCRIPT],
            cwd=Path(__file__).resolve().parents[1],
            env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "clean"
