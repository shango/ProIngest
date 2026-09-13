"""The Log tab. `ui/log_view.py`, M5.8.2.

The panel is driven through its buffer rather than through its timer: a test that waited
250 ms per assertion would be a slow suite asserting that `QTimer` works. `drain` is
called directly, which is exactly what the timer does.

What is worth pinning here is the filtering, the bound, and that a record made on
another thread reaches the table at all - the last one being the whole reason the buffer
exists between the handler and the widget.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Iterator

import pytest
from PySide6.QtWidgets import QApplication

from proingest.core import logsetup
from proingest.ui import log_view
from proingest.ui.log_view import LogView


@pytest.fixture
def view(qt_app: QApplication) -> Iterator[LogView]:
    """A panel attached to the root logger, detached again whatever the test did."""
    panel = LogView()
    yield panel
    panel.detach()
    panel.deleteLater()


def record(message: str, level: int = logging.INFO, shot: str = "") -> logging.LogRecord:
    made = logging.LogRecord("proingest.core.ffmpeg", level, __file__, 1, message, (), None)
    if shot:
        setattr(made, logsetup.SHOT_FIELD, shot)
    return made


def feed(panel: LogView, *records: logging.LogRecord) -> None:
    for one in records:
        panel.handler.handle(one)
    panel.drain()


def messages(panel: LogView) -> list[str]:
    return [line.message for line in panel.visible_lines()]


class TestWhatArrives:
    def test_a_line_logged_anywhere_reaches_the_table(self, view: LogView) -> None:
        logging.getLogger("proingest.test").warning("something happened")
        view.drain()
        assert messages(view) == ["something happened"]

    def test_a_line_from_another_thread_reaches_it_too(self, view: LogView) -> None:
        """The reason the handler hands to a buffer instead of to a widget.

        A run's ffmpeg command lines are republished by `core/logsetup.py`'s listener
        thread, and a widget touched from there is a crash rather than a wrong pixel.
        """
        # `warning` rather than `info`, so the test says something about threads rather
        # than about whatever level the root logger happens to be at while the suite runs.
        worker = threading.Thread(target=lambda: logging.getLogger("proingest.test").warning("from a worker"))
        worker.start()
        worker.join()
        view.drain()
        assert messages(view) == ["from a worker"]

    def test_draining_nothing_leaves_the_table_alone(self, view: LogView) -> None:
        feed(view, record("one"))
        view.drain()
        assert messages(view) == ["one"]

    def test_the_message_is_kept_verbatim(self, view: LogView) -> None:
        """CLAUDE.md logs a command so it can be pasted into a terminal and re-run."""
        command = "running: /usr/bin/ffmpeg -i 'a b.mov' -vf lut3d=x.cube -crf 18 out.mp4"
        feed(view, record(command))
        assert messages(view) == [command]

    def test_detaching_stops_it_hearing_anything(self, view: LogView) -> None:
        view.detach()
        logging.getLogger("proingest.test").warning("after the window closed")
        view.drain()
        assert messages(view) == []


class TestBound:
    def test_the_table_keeps_the_tail_and_no_more(
        self, view: LogView, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(log_view, "MAX_LINES", 10)
        feed(view, *(record(f"line {index}") for index in range(25)))
        assert len(view.lines()) == 10
        assert messages(view)[0] == "line 15"
        assert messages(view)[-1] == "line 24"

    def test_a_hidden_line_still_ages_out(self, view: LogView, monkeypatch: pytest.MonkeyPatch) -> None:
        """The bound is the table, not the filter: otherwise a filter would leak memory."""
        monkeypatch.setattr(log_view, "MAX_LINES", 10)
        view.search.setText("keep")
        feed(view, *(record(f"line {index}") for index in range(25)))
        assert len(view.lines()) == 10
        assert messages(view) == []


class TestFilters:
    def test_the_text_box_matches_the_message(self, view: LogView) -> None:
        feed(view, record("running: ffmpeg -i a.mov"), record("wrote /out/MELT0001"))
        view.search.setText("ffmpeg")
        assert messages(view) == ["running: ffmpeg -i a.mov"]

    def test_the_text_box_ignores_case(self, view: LogView) -> None:
        feed(view, record("running: FFmpeg -i a.mov"))
        view.search.setText("ffmpeg")
        assert len(messages(view)) == 1

    def test_the_text_box_matches_the_shot_column_too(self, view: LogView) -> None:
        feed(view, record("wrote a frame", shot="MELT0001"), record("wrote another"))
        view.search.setText("melt0001")
        assert messages(view) == ["wrote a frame"]

    def test_the_level_box_keeps_that_level_and_above(self, view: LogView) -> None:
        feed(
            view,
            record("chatty", logging.INFO),
            record("odd", logging.WARNING),
            record("broken", logging.ERROR),
        )
        view.level_box.setCurrentIndex([name for name, _ in log_view.LEVELS].index("Warning"))
        assert messages(view) == ["odd", "broken"]

    def test_clearing_a_filter_brings_the_lines_back(self, view: LogView) -> None:
        feed(view, record("one"), record("two"))
        view.search.setText("one")
        view.search.setText("")
        assert messages(view) == ["one", "two"]

    def test_a_line_arriving_while_a_filter_is_on_obeys_it(self, view: LogView) -> None:
        view.search.setText("ffmpeg")
        feed(view, record("running: ffmpeg -i a.mov"), record("wrote /out/MELT0001"))
        assert messages(view) == ["running: ffmpeg -i a.mov"]
        assert len(view.lines()) == 2


class TestFilterByRow:
    """FR-13's "filter by row", which is the one filter the requirement actually names."""

    def test_it_is_not_available_until_a_row_is_selected(self, view: LogView) -> None:
        assert not view.selected_only.isEnabled()
        view.set_selected_shot("MELT0001")
        assert view.selected_only.isEnabled()

    def test_it_keeps_only_what_a_worker_stamped_with_that_shot(self, view: LogView) -> None:
        feed(
            view,
            record("rendering", shot="MELT0001"),
            record("rendering", shot="MELT0002"),
            record("the window said something"),
        )
        view.set_selected_shot("MELT0001")
        view.selected_only.setChecked(True)
        assert [line.shot for line in view.visible_lines()] == ["MELT0001"]

    def test_moving_the_selection_moves_the_filter(self, view: LogView) -> None:
        feed(view, record("a", shot="MELT0001"), record("b", shot="MELT0002"))
        view.set_selected_shot("MELT0001")
        view.selected_only.setChecked(True)
        view.set_selected_shot("MELT0002")
        assert messages(view) == ["b"]

    def test_losing_the_selection_unticks_it_rather_than_filtering_to_nothing(self, view: LogView) -> None:
        """A ticked box filtering nothing is a control saying something untrue."""
        feed(view, record("a", shot="MELT0001"), record("b"))
        view.set_selected_shot("MELT0001")
        view.selected_only.setChecked(True)
        view.set_selected_shot("")
        assert not view.selected_only.isChecked()
        assert messages(view) == ["a", "b"]


class TestTheCount:
    def test_it_says_nothing_yet_before_anything_is_logged(self, view: LogView) -> None:
        assert view.count.text() == log_view.EMPTY

    def test_it_says_how_many_of_how_many_are_showing(self, view: LogView) -> None:
        feed(view, record("one ffmpeg"), record("two"))
        view.search.setText("ffmpeg")
        assert view.count.text() == log_view.HIDDEN.format(shown=1, total=2)


class TestCopy:
    def test_the_selection_copies_as_text_with_the_message_last(
        self, view: LogView, qt_app: QApplication
    ) -> None:
        feed(view, record("running: ffmpeg -i a.mov", shot="MELT0001"))
        view.tree.selectAll()
        view.copy_selection()
        copied = qt_app.clipboard().text()
        assert copied.endswith("running: ffmpeg -i a.mov")
        assert "MELT0001" in copied
        assert "INFO" in copied

    def test_copying_nothing_leaves_the_clipboard_alone(self, view: LogView, qt_app: QApplication) -> None:
        qt_app.clipboard().setText("something the editor had")
        view.copy_selection()
        assert qt_app.clipboard().text() == "something the editor had"
