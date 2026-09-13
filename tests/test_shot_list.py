"""The shot list's view, filter and two line cells. `ui/shot_list.py`, M5.2.

What can honestly be asserted about a view drawn to nothing: which rows it shows, what
it spans, what it hands back as selected, and that a cell paints without raising. How it
looks is a person's job on a Mac (docs/MAC_SESSION.md).
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QModelIndex, QRect, Qt
from PySide6.QtGui import QImage, QPainter, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QLineEdit,
    QStyleOptionViewItem,
)

from proingest.ui.shot_list import BAR_HEIGHT, ERROR_COLOR, ShotListView, TwoLineDelegate
from proingest.ui.shot_model import (
    DOT_COLORS,
    IN,
    NOTES,
    OUT,
    PROGRESS,
    SHOT,
    DisplayMode,
    RowState,
    ShotListModel,
)
from tests.fixtures.batches import batch, delivered, row, turnover


@pytest.fixture
def view(qt_app: QApplication) -> ShotListView:
    model = ShotListModel()
    model.set_batch(
        batch(
            row("MELT0001_pl01"),
            row("MELT0002_pl01"),
            row("BRIK0007_pl01", turnover_id="turnover002"),
            turnovers=[turnover(), turnover("turnover002")],
        )
    )
    return ShotListView(model)


def shown(view: ShotListView) -> list[str]:
    """Every shot the list is currently showing, in order, turnover headers aside."""
    proxy = view.proxy
    names = []
    for parent_row in range(proxy.rowCount()):
        parent = proxy.index(parent_row, 0)
        for child in range(proxy.rowCount(parent)):
            names.append(str(proxy.index(child, SHOT, parent).data(Qt.ItemDataRole.DisplayRole)))
    return names


class TestWhatItShows:
    def test_every_shot_of_every_turnover(self, view: ShotListView) -> None:
        assert shown(view) == ["MELT0001", "MELT0002", "BRIK0007"]

    def test_turnovers_open_expanded(self, view: ShotListView) -> None:
        """A collapsed turnover on first sight hides what the tool was opened to look at."""
        assert view.isExpanded(view.proxy.index(0, 0))

    def test_the_group_header_spans_the_width(self, view: ShotListView) -> None:
        """It carries one sentence, not fifteen cells."""
        assert view.isFirstColumnSpanned(0, QModelIndex())

    def test_it_does_not_sort(self, view: ShotListView) -> None:
        """Section 2 fixes the order to the timeline's; a sortable list is one an editor
        can put into an order the delivery does not use."""
        assert not view.isSortingEnabled()

    def test_a_whole_row_is_selected_at_once(self, view: ShotListView) -> None:
        assert view.selectionBehavior().name == "SelectRows"


class TestTheSearchBox:
    def test_it_narrows_to_matching_shots(self, view: ShotListView) -> None:
        view.filter_by("MELT0002")
        assert shown(view) == ["MELT0002"]

    def test_it_is_a_substring_and_not_a_pattern(self, view: ShotListView) -> None:
        """The editor types part of a shot code, not a regular expression to escape."""
        view.filter_by("0007")
        assert shown(view) == ["BRIK0007"]

    def test_case_does_not_matter(self, view: ShotListView) -> None:
        view.filter_by("brik")
        assert shown(view) == ["BRIK0007"]

    def test_a_turnover_with_no_match_disappears_with_its_rows(self, view: ShotListView) -> None:
        view.filter_by("MELT")
        assert view.proxy.rowCount() == 1

    def test_a_matching_shot_keeps_its_turnover_visible(self, view: ShotListView) -> None:
        """Filtering narrows the list without losing which turnover a shot came from."""
        view.filter_by("BRIK")
        header = str(view.proxy.index(0, 0).data(Qt.ItemDataRole.DisplayRole))
        assert "turnover002" in header

    def test_clearing_it_brings_everything_back(self, view: ShotListView) -> None:
        view.filter_by("BRIK")
        view.filter_by("")
        assert shown(view) == ["MELT0001", "MELT0002", "BRIK0007"]

    def test_nothing_matching_shows_nothing_rather_than_everything(self, view: ShotListView) -> None:
        view.filter_by("ZZZZ")
        assert shown(view) == []

    def test_the_rows_that_survive_are_still_spanned_and_expanded(self, view: ShotListView) -> None:
        view.filter_by("BRIK")
        assert view.isFirstColumnSpanned(0, QModelIndex())
        assert view.isExpanded(view.proxy.index(0, 0))


class TestWhatItHandsBack:
    def test_the_selection_is_shot_rows(self, view: ShotListView) -> None:
        parent = view.proxy.index(0, 0)
        view.setCurrentIndex(view.proxy.index(1, SHOT, parent))
        selected = view.selected_rows()
        assert [r.clip_name for r in selected] == ["MELT0002_pl01"]

    def test_a_selected_group_header_is_not_a_shot(self, view: ShotListView) -> None:
        """Section 12.3: a turnover header selects the Turnover section, not a shot."""
        view.setCurrentIndex(view.proxy.index(0, 0))
        assert view.selected_rows() == []
        assert view.current_shot_row() is None

    def test_the_current_row_follows_the_cursor(self, view: ShotListView) -> None:
        parent = view.proxy.index(0, 0)
        view.setCurrentIndex(view.proxy.index(0, SHOT, parent))
        current = view.current_shot_row()
        assert current is not None and current.clip_name == "MELT0001_pl01"


class TestTheTwoLineCell:
    """Section 2: the demoted representation sits under the primary one, never hidden."""

    def option(self, view: ShotListView) -> QStyleOptionViewItem:
        option = QStyleOptionViewItem()
        option.initFrom(view)
        option.rect = QRect(0, 0, 120, 40)
        return option

    def index_of(self, view: ShotListView, column: int) -> QModelIndex:
        return view.proxy.index(0, column, view.proxy.index(0, 0))

    def test_a_row_is_tall_enough_for_two_lines(self, view: ShotListView) -> None:
        delegate = TwoLineDelegate(view)
        option = self.option(view)
        hint = delegate.sizeHint(option, self.index_of(view, IN))
        assert hint.height() >= option.fontMetrics.height() * 2

    def test_it_paints_a_cell_that_has_a_second_line(self, view: ShotListView) -> None:
        """The In cell under Frames carries the source timecode beneath it."""
        pixmap = QPixmap(120, 40)
        painter = QPainter(pixmap)
        TwoLineDelegate(view).paint(painter, self.option(view), self.index_of(view, IN))
        painter.end()

    def test_it_paints_a_cell_that_has_not(self, view: ShotListView) -> None:
        pixmap = QPixmap(120, 40)
        painter = QPainter(pixmap)
        TwoLineDelegate(view).paint(painter, self.option(view), self.index_of(view, SHOT))
        painter.end()

    def test_the_second_line_follows_the_display_mode(self, view: ShotListView) -> None:
        view.shot_model.set_display_mode(DisplayMode.SOURCE_TC)
        from proingest.ui.shot_model import SECONDARY_ROLE

        assert self.index_of(view, IN).data(SECONDARY_ROLE) == "8"


class TestTheProgressCell:
    """Section 7: a slim bar with the job count, in the Progress column.

    Drawn to a pixmap, so what is asserted is the pixels: an offscreen view paints
    nothing by itself, and "it did not raise" would pass with the bar left out.
    """

    def option(self, view: ShotListView) -> QStyleOptionViewItem:
        option = QStyleOptionViewItem()
        option.initFrom(view)
        option.rect = QRect(0, 0, 90, 40)
        return option

    def painted(self, view: ShotListView, row_index: int = 0) -> QImage:
        pixmap = QPixmap(90, 40)
        pixmap.fill(Qt.GlobalColor.black)
        painter = QPainter(pixmap)
        index = view.proxy.index(row_index, PROGRESS, view.proxy.index(0, 0))
        TwoLineDelegate(view).paint(painter, self.option(view), index)
        painter.end()
        return pixmap.toImage()

    def bar_width(self, image: QImage) -> int:
        """How far the filled part of the bar reaches along its own line."""
        line = image.height() - 3
        accent = DOT_COLORS[RowState.RENDERING].rgb()
        done = DOT_COLORS[RowState.DONE].rgb()
        return sum(1 for x in range(image.width()) if image.pixel(x, line) in (accent, done))

    def test_a_row_half_rendered_draws_a_bar_about_half_way(
        self, qt_app: QApplication
    ) -> None:
        model = ShotListModel()
        planned = delivered(row(), status="planned")
        planned.deliverables[0].status = "done"
        model.set_batch(batch(planned))
        view = ShotListView(model)

        width = self.bar_width(self.painted(view))
        assert 0 < width < 90
        assert abs(width - 42) <= 4, "half of the cell, less its padding"

    def test_a_row_with_nothing_planned_has_no_bar_at_all(self, view: ShotListView) -> None:
        """An empty track would read as a job that has not started rather than none."""
        assert self.bar_width(self.painted(view)) == 0

    def test_the_bar_is_slim_rather_than_a_filled_cell(self, qt_app: QApplication) -> None:
        model = ShotListModel()
        model.set_batch(batch(delivered(row())))
        view = ShotListView(model)
        image = self.painted(view)
        done = DOT_COLORS[RowState.DONE].rgb()
        column = sum(1 for y in range(image.height()) if image.pixel(4, y) == done)
        assert column == BAR_HEIGHT


class TestTheCellEditor:
    """Section 5: what the editor shows while it is open, and what it hands back."""

    def index_of(self, view: ShotListView, column: int) -> QModelIndex:
        return view.proxy.index(0, column, view.proxy.index(0, 0))

    def editor(self, view: ShotListView, column: int) -> QLineEdit:
        delegate = TwoLineDelegate(view)
        option = QStyleOptionViewItem()
        option.initFrom(view)
        widget = delegate.createEditor(view, option, self.index_of(view, column))
        assert isinstance(widget, QLineEdit)
        return widget

    def test_a_cell_edits_as_a_line_edit(self, view: ShotListView) -> None:
        assert self.editor(view, SHOT).text() == ""

    def test_an_unrecognized_in_goes_red_while_it_is_still_being_typed(
        self, view: ShotListView
    ) -> None:
        editor = self.editor(view, IN)
        editor.setText("sometime tuesday")
        assert ERROR_COLOR.name() in editor.styleSheet()
        assert editor.toolTip() == "unrecognized"

    def test_and_goes_back_when_it_parses(self, view: ShotListView) -> None:
        editor = self.editor(view, IN)
        editor.setText("nope")
        editor.setText("+12")
        assert editor.styleSheet() == ""
        assert editor.toolTip() == ""

    def test_it_is_read_against_the_row_it_is_editing(self, view: ShotListView) -> None:
        """A timecode the media does hold parses; the same one is nonsense elsewhere."""
        editor = self.editor(view, IN)
        editor.setText("01:00:00:12")
        assert editor.styleSheet() == ""

    def test_a_cell_that_cannot_be_wrong_is_not_policed(self, view: ShotListView) -> None:
        editor = self.editor(view, NOTES)
        editor.setText("anything at all")
        assert editor.styleSheet() == ""

    def test_typing_starts_an_edit_without_f2(self, view: ShotListView) -> None:
        """Section 4. The trigger rather than the keystroke, because an offscreen view
        has no focus to type into."""
        assert view.editTriggers() & QAbstractItemView.EditTrigger.AnyKeyPressed


class TestTabbingBetweenCells:
    """Section 4: Tab moves between editable cells, wrapping to the next row's first."""

    def cell(self, view: ShotListView, shot: int, column: int, group: int = 0) -> QModelIndex:
        return view.proxy.index(shot, column, view.proxy.index(group, 0))

    def tab(self, view: ShotListView, forward: bool = True) -> QModelIndex:
        action = (
            QAbstractItemView.CursorAction.MoveNext
            if forward
            else QAbstractItemView.CursorAction.MovePrevious
        )
        return view.moveCursor(action, Qt.KeyboardModifier.NoModifier)

    def test_tab_reaches_the_list_at_all(self, view: ShotListView) -> None:
        """QTreeView ships with this off and QTableView ships with it on. With it off,
        Tab moves focus out of the list and `moveCursor` is never asked."""
        assert view.tabKeyNavigation()

    def test_it_steps_from_shot_to_in_rather_than_to_elem(self, view: ShotListView) -> None:
        view.setCurrentIndex(self.cell(view, 0, SHOT))
        assert self.tab(view) == self.cell(view, 0, IN)

    def test_it_steps_over_the_columns_nobody_can_edit(self, view: ShotListView) -> None:
        view.setCurrentIndex(self.cell(view, 0, OUT))
        assert self.tab(view) == self.cell(view, 0, NOTES)

    def test_the_end_of_a_row_wraps_to_the_next_row_s_first_cell(
        self, view: ShotListView
    ) -> None:
        view.setCurrentIndex(self.cell(view, 0, NOTES))
        assert self.tab(view) == self.cell(view, 1, SHOT)

    def test_the_end_of_a_turnover_wraps_into_the_next_one(self, view: ShotListView) -> None:
        view.setCurrentIndex(self.cell(view, 1, NOTES))
        assert self.tab(view) == self.cell(view, 0, SHOT, group=1)

    def test_the_end_of_the_list_wraps_round_to_the_start(self, view: ShotListView) -> None:
        view.setCurrentIndex(self.cell(view, 0, NOTES, group=1))
        assert self.tab(view) == self.cell(view, 0, SHOT)

    def test_shift_tab_goes_back(self, view: ShotListView) -> None:
        view.setCurrentIndex(self.cell(view, 0, IN))
        assert self.tab(view, forward=False) == self.cell(view, 0, SHOT)

    def test_it_only_offers_what_the_filter_is_showing(self, view: ShotListView) -> None:
        """A hidden row is not one Tab can put the cursor into."""
        view.filter_by("MELT0002")
        view.setCurrentIndex(self.cell(view, 0, NOTES))
        assert self.tab(view) == self.cell(view, 0, SHOT)

    def test_from_a_turnover_header_it_starts_at_the_first_editable_cell(
        self, view: ShotListView
    ) -> None:
        view.setCurrentIndex(view.proxy.index(0, 0))
        assert self.tab(view) == self.cell(view, 0, SHOT)

    def test_an_empty_list_leaves_qt_to_it(self, qt_app: QApplication) -> None:
        empty = ShotListView(ShotListModel())
        assert not self.tab(empty).isValid()


class TestSkippingFromTheList:
    """Ctrl+K. The prompt is the view's, because a dialog cannot live in a model."""

    def first_row(self, view: ShotListView) -> None:
        view.setCurrentIndex(view.proxy.index(0, SHOT, view.proxy.index(0, 0)))

    def test_it_asks_for_a_reason_and_records_it(self, view: ShotListView) -> None:
        view.ask_skip_reason = lambda row: "reshoot on friday"  # type: ignore[method-assign]
        self.first_row(view)
        view.toggle_skip()
        skipped = view.shot_model.batch.rows[0]
        assert skipped.skipped and skipped.skip_reason == "reshoot on friday"

    def test_escape_at_the_prompt_cancels_the_skip(self, view: ShotListView) -> None:
        view.ask_skip_reason = lambda row: None  # type: ignore[method-assign]
        self.first_row(view)
        view.toggle_skip()
        assert not view.shot_model.batch.rows[0].skipped

    def test_toggling_back_on_does_not_ask_again(self, view: ShotListView) -> None:
        asked: list[object] = []

        def ask(row: object) -> str:
            asked.append(row)
            return "reshoot"

        view.ask_skip_reason = ask  # type: ignore[method-assign]
        self.first_row(view)
        view.toggle_skip()
        view.toggle_skip()
        view.toggle_skip()
        assert len(asked) == 1
        assert view.shot_model.batch.rows[0].skipped

    def test_a_turnover_header_is_not_a_row_to_skip(self, view: ShotListView) -> None:
        view.ask_skip_reason = lambda row: "reshoot"  # type: ignore[method-assign]
        view.setCurrentIndex(view.proxy.index(0, 0))
        view.toggle_skip()
        assert not any(shot.skipped for shot in view.shot_model.batch.rows)
