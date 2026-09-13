"""The toolbar tooltips. `ui/toolbar_help.py` and its wiring, M5.11.

Split the way the code is: the wording is a value and is asserted without a window, and
the window is driven offscreen to check it says the right one at the right moment.

The width test is the one that would not otherwise exist. Qt word-wraps a tooltip only
when the text looks like rich text, so a plain sentence is drawn on one line however long
it is, and nothing about that fails - it just renders as a strip across the screen. The
first draft had a line at 104 characters and it was found by printing the real window.
"""

from __future__ import annotations

from itertools import product
from pathlib import Path

import pytest
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QApplication

from proingest.ui import toolbar_help as help_
from proingest.ui.toolbar_help import ToolbarState, note, tooltip
from tests.fixtures.batches import batch, row
from tests.test_ui_shell import DrivenWindow

KEYS = tuple(help_.WHAT_IT_DOES)


def native(action: QAction) -> str:
    """The shortcut as the tooltip spells it, which is not how a test would spell it.

    `toString()` gives the portable `Ctrl+R` on every platform; the tooltip asks for
    native text, so macOS draws Cmd-R as one glyph and Linux draws `Ctrl+R`. A test that wrote
    either one out passed here and failed on the arm64 runner, which is what that runner
    is for.
    """
    return action.shortcut().toString(QKeySequence.SequenceFormat.NativeText)


def every_state() -> list[ToolbarState]:
    """All 2^7 combinations. Nonsensical ones included: a tooltip has to say something
    whatever the window is doing, and the point of the width test is that none is long."""
    return [
        ToolbarState(*flags)
        for flags in product((False, True), repeat=7)
    ]


class TestTheWording:
    def test_every_toolbar_button_has_a_sentence(self) -> None:
        """The list is section 1's toolbar, in the order it is drawn."""
        assert KEYS == (
            help_.NEW,
            help_.OPEN,
            help_.SAVE,
            help_.ADD_TURNOVER,
            help_.SCAN,
            help_.INGEST,
            help_.RUN,
            help_.STOP,
            help_.EXPORT,
            help_.SETTINGS,
        )

    def test_no_sentence_is_just_the_label_again(self) -> None:
        """Section 1: Scan saying "Scans" is a tooltip nobody reads twice.

        A word count rather than a check on the opening verb, because the opening verb
        is usually the label's own and should be: "Opens a saved .pibatch file" is the
        right sentence for Open. What makes it worth reading is what comes after it.
        """
        for key, sentence in help_.WHAT_IT_DOES.items():
            assert len(sentence.split()) >= 8, f"{key}: {sentence!r} says too little"

    def test_every_sentence_is_one_sentence_in_the_present_tense(self) -> None:
        for key, sentence in help_.WHAT_IT_DOES.items():
            assert sentence.endswith("."), key
            assert sentence[0].isupper(), key

    def test_no_line_is_wider_than_the_limit(self) -> None:
        """The regression this file exists for: a plain text tooltip never wraps.

        `Ctrl+R` is the longest shortcut any toolbar button carries, and on macOS the
        native form is shorter still, so Linux is the worst case and it is the one the
        suite runs on.
        """
        widest = 0
        for key, state, enabled in product(KEYS, every_state(), (False, True)):
            for line in tooltip(key, state, enabled, shortcut="Ctrl+R").split("\n"):
                assert len(line) <= help_.MAX_LINE, f"{key}: {line!r} is {len(line)}"
                widest = max(widest, len(line))
        # Not so far under the limit that the limit is meaningless.
        assert widest > help_.MAX_LINE // 2

    def test_nothing_reads_as_markup(self) -> None:
        """Qt draws a tooltip that looks like rich text with a wrapper nobody asked for."""
        for key, state in product(KEYS, every_state()):
            for enabled in (False, True):
                assert "<" not in tooltip(key, state, enabled)


class TestWhyItIsUnavailable:
    def test_an_enabled_button_says_only_what_it_does(self) -> None:
        ready = ToolbarState(batch_open=True, has_rows=True, has_session=True)
        assert tooltip(help_.RUN, ready, enabled=True) == help_.WHAT_IT_DOES[help_.RUN]

    def test_the_shortcut_is_part_of_the_first_line(self) -> None:
        text = tooltip(help_.RUN, ToolbarState(), enabled=False, shortcut="Ctrl+R")
        first, second = text.split("\n")
        assert first.endswith("Ctrl+R")
        assert second == help_.NO_BATCH

    def test_no_batch_beats_every_other_reason(self) -> None:
        """A batch that is not open is a truer answer than a scan that is going."""
        busy = ToolbarState(scanning=True, rendering=True)
        assert note(help_.ADD_TURNOVER, busy, enabled=False) == help_.NO_BATCH

    def test_a_scan_and_a_run_are_named_separately(self) -> None:
        open_batch = ToolbarState(batch_open=True, has_rows=True)
        scanning = ToolbarState(batch_open=True, has_rows=True, scanning=True)
        rendering = ToolbarState(batch_open=True, has_rows=True, rendering=True)
        assert note(help_.ADD_TURNOVER, scanning, enabled=False) == help_.SCANNING
        assert note(help_.ADD_TURNOVER, rendering, enabled=False) == help_.RENDERING
        assert note(help_.ADD_TURNOVER, open_batch, enabled=False) == ""

    def test_scan_says_there_is_nothing_left_to_re_try(self) -> None:
        """The commonest greyed button of the four, and the least obvious."""
        state = ToolbarState(batch_open=True, has_rows=True, has_unscanned=False)
        assert note(help_.SCAN, state, enabled=False) == help_.NOTHING_UNSCANNED

    def test_ingest_says_it_needs_something_to_write_onto(self) -> None:
        state = ToolbarState(batch_open=True, has_rows=False)
        assert note(help_.INGEST, state, enabled=False) == help_.NO_ROWS_TO_INGEST

    def test_run_says_to_add_a_turnover(self) -> None:
        """UI_SPEC section 1's own example of what a disabled tooltip is for."""
        state = ToolbarState(batch_open=True, has_rows=False)
        assert note(help_.RUN, state, enabled=False) == help_.NO_ROWS_TO_RUN

    def test_stop_tells_a_second_press_that_it_already_heard(self) -> None:
        stopping = ToolbarState(batch_open=True, has_rows=True, rendering=True, stopping=True)
        idle = ToolbarState(batch_open=True, has_rows=True)
        assert note(help_.STOP, stopping, enabled=False) == help_.ALREADY_STOPPING
        assert note(help_.STOP, idle, enabled=False) == help_.NOT_RUNNING

    def test_new_and_open_say_what_is_holding_them(self) -> None:
        """They are disabled only during a run, so there is only one thing to say."""
        state = ToolbarState(batch_open=True, has_rows=True, rendering=True)
        assert note(help_.NEW, state, enabled=False) == help_.RUN_FIRST
        assert note(help_.OPEN, state, enabled=False) == help_.RUN_FIRST

    def test_export_says_it_is_not_built_rather_than_inventing_a_reason(self) -> None:
        for state in every_state():
            assert note(help_.EXPORT, state, enabled=False) == help_.EXPORT_UNBUILT


class TestTheNoteOnAnEnabledRun:
    """The half of this that is not about greyed buttons at all."""

    def test_run_warns_that_nothing_has_been_ingested(self) -> None:
        state = ToolbarState(batch_open=True, has_rows=True, has_session=False)
        assert note(help_.RUN, state, enabled=True) == help_.NO_SESSION

    def test_it_goes_away_once_a_session_is_ingested(self) -> None:
        state = ToolbarState(batch_open=True, has_rows=True, has_session=True)
        assert note(help_.RUN, state, enabled=True) == ""

    def test_no_other_enabled_button_carries_a_note(self) -> None:
        state = ToolbarState(batch_open=True, has_rows=True, has_session=False)
        for key in KEYS:
            if key != help_.RUN:
                assert note(key, state, enabled=True) == "", key


@pytest.fixture
def window(qt_app: QApplication, tmp_path: Path) -> DrivenWindow:
    return DrivenWindow(tmp_path / "settings.json")


class TestTheWindowSaysTheRightOne:
    def test_every_toolbar_action_carries_a_tooltip_from_the_first_launch(
        self, window: DrivenWindow
    ) -> None:
        """Section 10's first-run state is where a greyed toolbar most needs to explain."""
        for key, action in window._toolbar_help:
            assert action.toolTip(), key
            assert action.toolTip().startswith(help_.WHAT_IT_DOES[key]), key

    def test_with_no_batch_the_greyed_ones_say_so(self, window: DrivenWindow) -> None:
        assert window.action_run.toolTip().endswith(help_.NO_BATCH)
        assert window.action_save.toolTip().endswith(help_.NO_BATCH)

    def test_opening_a_batch_rewrites_them(self, window: DrivenWindow) -> None:
        window.set_batch(batch())
        assert window.action_run.toolTip().endswith(help_.NO_ROWS_TO_RUN)
        assert not window.action_save.toolTip().endswith(help_.NO_BATCH)

    def test_a_batch_with_shots_and_no_session_warns_on_run(
        self, window: DrivenWindow
    ) -> None:
        """The answer to "why does Run write nothing", said before Run is pressed."""
        window.set_batch(batch(row()))
        assert window.action_run.isEnabled()
        assert window.action_run.toolTip().endswith(help_.NO_SESSION)

    def test_an_ingested_session_takes_the_warning_off(
        self, window: DrivenWindow, tmp_path: Path
    ) -> None:
        window.set_batch(batch(row()))
        window.batch.turnovers[0].color_session_edl = tmp_path / "final.edl"
        window._update_state()
        expected = f"{help_.WHAT_IT_DOES[help_.RUN]}  {native(window.action_run)}"
        assert window.action_run.toolTip() == expected

    def test_scan_explains_itself_once_every_turnover_has_shots(
        self, window: DrivenWindow
    ) -> None:
        window.set_batch(batch(row()))
        assert not window.action_scan.isEnabled()
        assert window.action_scan.toolTip().endswith(help_.NOTHING_UNSCANNED)

    def test_no_real_tooltip_is_wider_than_the_limit(self, window: DrivenWindow) -> None:
        """The value test uses an assumed shortcut; this uses the ones actually set."""
        window.set_batch(batch(row()))
        for key, action in window._toolbar_help:
            for line in action.toolTip().split("\n"):
                assert len(line) <= help_.MAX_LINE, f"{key}: {line!r} is {len(line)}"

    def test_the_shortcut_in_the_tooltip_is_the_action_s_own(
        self, window: DrivenWindow
    ) -> None:
        """Native text, so it reads as Cmd on the Mac without a platform branch here."""
        assert native(window.action_run) in window.action_run.toolTip()
        assert not window.action_add_turnover.toolTip().split("\n")[0].endswith(" ")
