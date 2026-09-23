"""`ui/background.py`: one call off the UI thread, its answer back on it (F17).

The window tests use `Inline`, so these are the ones that exercise the thread.
"""

from __future__ import annotations

import threading

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
