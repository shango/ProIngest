"""The shot list's view, filter and two line cells. `ui/shot_list.py`, M5.2.

What can honestly be asserted about a view drawn to nothing: which rows it shows, what
it spans, what it hands back as selected, and that a cell paints without raising. How it
looks is a person's job on a Mac (docs/MAC_SESSION.md).
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from PySide6.QtCore import QEvent, QModelIndex, QRect, Qt
from PySide6.QtGui import QImage, QKeyEvent, QPainter, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QLineEdit,
    QStyleOptionViewItem,
)

from proingest.ui.shot_list import BAR_HEIGHT, ERROR_COLOR, ShotListView, TwoLineDelegate
from proingest.ui.shot_model import (
    DOT_COLORS,
    FROZEN_COLUMNS,
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

    def test_a_row_half_rendered_draws_a_bar_about_half_way(self, qt_app: QApplication) -> None:
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

    def test_an_unrecognized_in_goes_red_while_it_is_still_being_typed(self, view: ShotListView) -> None:
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

    def test_the_end_of_a_row_wraps_to_the_next_row_s_first_cell(self, view: ShotListView) -> None:
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

    def test_from_a_turnover_header_it_starts_at_the_first_editable_cell(self, view: ShotListView) -> None:
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


@pytest.fixture
def tall(qt_app: QApplication) -> Iterator[ShotListView]:
    """A list with more rows and columns than it can show, on screen.

    Scroll ranges, geometry and fonts are what Qt only works out for a view that has
    been shown and had its events delivered, and the frozen overlay is about all three.
    """
    model = ShotListModel()
    model.set_batch(batch(*[row(f"MELT{shot:04d}_pl01") for shot in range(1, 30)], turnovers=[turnover()]))
    view = ShotListView(model)
    view.resize(500, 200)
    view.show()
    qt_app.processEvents()
    yield view
    view.close()


class TestTheFrozenColumns:
    """M5.9, UI_SPEC section 2: Status, Shot and Elem stay while the rest scrolls.

    What can be asserted about an overlay drawn to nothing is that it shows the same
    rows as the view under it, covers the columns it claims to, and moves with it.
    Whether it looks like one list is a person's job on a Mac (docs/MAC_SESSION.md).
    """

    def test_it_shows_the_columns_section_2_freezes(self, view: ShotListView) -> None:
        assert [view.frozen.isColumnHidden(column) for column in range(FROZEN_COLUMNS)] == [
            False,
            False,
            False,
        ]

    def test_and_hides_every_column_that_scrolls(self, view: ShotListView) -> None:
        hidden = [view.frozen.isColumnHidden(column) for column in range(FROZEN_COLUMNS, NOTES + 1)]
        assert all(hidden)

    def test_it_is_the_same_rows_through_the_same_filter(self, view: ShotListView) -> None:
        """One model between the two views is what stops them disagreeing about a row."""
        assert view.frozen.model() is view.proxy

    def test_and_the_same_selection(self, view: ShotListView) -> None:
        assert view.frozen.selectionModel() is view.selectionModel()

    def test_it_covers_exactly_the_three_columns(self, tall: ShotListView) -> None:
        expected = sum(tall.columnWidth(column) for column in range(FROZEN_COLUMNS))
        assert tall.frozen.width() == expected

    def test_it_covers_the_header_as_well_as_the_rows(self, tall: ShotListView) -> None:
        """The titles have to stay above the columns they name."""
        assert tall.frozen.height() == tall.viewport().height() + tall.header().height()

    def test_the_rows_line_up(self, tall: ShotListView) -> None:
        """Two views of a row at two heights is a list that reads as torn in half."""
        cell = tall.proxy.index(0, SHOT, tall.proxy.index(0, 0))
        assert tall.frozen.rowHeight(cell) == tall.rowHeight(cell)

    def test_widening_a_column_widens_the_overlay_with_it(self, tall: ShotListView) -> None:
        tall.header().resizeSection(SHOT, 300)
        assert tall.frozen.columnWidth(SHOT) == 300
        assert tall.frozen.width() == sum(tall.columnWidth(column) for column in range(FROZEN_COLUMNS))

    def test_widening_it_on_the_overlay_widens_the_list(self, tall: ShotListView) -> None:
        """Either header can be the one the mouse is on, so both are wired."""
        tall.frozen.header().resizeSection(SHOT, 300)
        assert tall.columnWidth(SHOT) == 300

    def test_a_column_that_scrolls_leaves_the_overlay_alone(self, tall: ShotListView) -> None:
        before = tall.frozen.width()
        tall.header().resizeSection(NOTES, 400)
        assert tall.frozen.width() == before

    def test_scrolling_the_list_scrolls_the_overlay(self, tall: ShotListView) -> None:
        tall.verticalScrollBar().setValue(40)
        assert tall.frozen.verticalScrollBar().value() == 40

    def test_scrolling_the_overlay_scrolls_the_list(self, tall: ShotListView) -> None:
        """The wheel over the left three columns is over the overlay, not the list."""
        tall.frozen.verticalScrollBar().setValue(25)
        assert tall.verticalScrollBar().value() == 25

    def test_collapsing_a_turnover_collapses_it_in_both(self, view: ShotListView) -> None:
        group = view.proxy.index(0, 0)
        view.collapse(group)
        assert not view.frozen.isExpanded(group)

    def test_and_expanding_it_on_the_overlay_opens_the_list(self, view: ShotListView) -> None:
        group = view.proxy.index(0, 0)
        view.collapse(group)
        view.frozen.expand(group)
        assert view.isExpanded(group)

    def test_a_group_header_spans_the_overlay_too(self, view: ShotListView) -> None:
        assert view.frozen.isFirstColumnSpanned(0, QModelIndex())

    def test_filtering_leaves_the_overlay_spanned_and_open(self, view: ShotListView) -> None:
        """The spans and the expansion are per view, so a filter has to redo both."""
        view.filter_by("BRIK")
        assert view.frozen.isFirstColumnSpanned(0, QModelIndex())
        assert view.frozen.isExpanded(view.proxy.index(0, 0))


class TestEditingAcrossTheSeam:
    """A cell is edited in whichever of the two views is the one that can be seen."""

    def cell(self, view: ShotListView, column: int) -> QModelIndex:
        return view.proxy.index(0, column, view.proxy.index(0, 0))

    def editors(self, view: QAbstractItemView) -> list[QLineEdit]:
        return view.viewport().findChildren(QLineEdit)

    def open_editor(self, view: QAbstractItemView, cell: QModelIndex) -> bool:
        """What a double click or a typed character asks the view for.

        `AllEditTriggers` rather than a synthetic mouse event, because what is under
        test is where the editor opens and not what opens it.
        """
        return view.edit(cell, QAbstractItemView.EditTrigger.AllEditTriggers, QEvent(QEvent.Type.None_))

    def test_a_frozen_cell_opens_its_editor_in_the_overlay(self, view: ShotListView) -> None:
        """The list's own copy of Shot is underneath the overlay: an editor opened
        there is one the editor cannot see or type into."""
        self.open_editor(view, self.cell(view, SHOT))
        assert len(self.editors(view.frozen)) == 1
        assert self.editors(view) == []

    def test_a_scrolling_cell_asked_of_the_overlay_opens_in_the_list(self, view: ShotListView) -> None:
        """Tab out of a Shot editor asks the overlay to edit In, which it hides."""
        self.open_editor(view.frozen, self.cell(view, IN))
        assert len(self.editors(view)) == 1
        assert self.editors(view.frozen) == []

    def test_tab_in_the_overlay_is_the_list_s_own_step(self, view: ShotListView) -> None:
        """One rule for Tab, in `ShotListView.moveCursor`, not two that could drift."""
        view.setCurrentIndex(self.cell(view, SHOT))
        stepped = view.frozen.moveCursor(
            QAbstractItemView.CursorAction.MoveNext, Qt.KeyboardModifier.NoModifier
        )
        assert stepped == self.cell(view, IN)

    def test_tab_out_of_a_shot_editor_opens_the_next_one_in_the_list(self, tall: ShotListView) -> None:
        """The whole seam in one move: the edit is committed by the overlay and the
        next editor opens in the view on the other side of it."""
        shot = tall.proxy.index(0, SHOT, tall.proxy.index(0, 0))
        tall.setCurrentIndex(shot)
        self.open_editor(tall, shot)
        editor = self.editors(tall.frozen)[0]
        editor.setText("MELT0099")
        QApplication.sendEvent(
            editor, QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Tab, Qt.KeyboardModifier.NoModifier)
        )
        assert tall.shot_model.batch.rows[0].shot_code == "MELT0099"
        assert tall.currentIndex().column() == IN
        assert len(self.editors(tall)) == 1

    def test_and_shift_tab_comes_back_into_the_overlay(self, tall: ShotListView) -> None:
        in_cell = tall.proxy.index(0, IN, tall.proxy.index(0, 0))
        tall.setCurrentIndex(in_cell)
        self.open_editor(tall, in_cell)
        editor = self.editors(tall)[0]
        QApplication.sendEvent(
            editor,
            QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Backtab, Qt.KeyboardModifier.ShiftModifier),
        )
        assert tall.currentIndex().column() == SHOT
        assert len(self.editors(tall.frozen)) == 1


class TestScrollingToAFrozenCell:
    def test_it_does_not_drag_the_list_back_to_the_left(self, tall: ShotListView) -> None:
        """Qt's answer to "show me this Shot cell" is to scroll to the left edge, which
        throws away the position the editor was reading at to reveal a cell that the
        overlay was showing all along."""
        tall.horizontalScrollBar().setValue(tall.horizontalScrollBar().maximum())
        kept = tall.horizontalScrollBar().value()
        assert kept > 0
        tall.scrollTo(tall.proxy.index(20, SHOT, tall.proxy.index(0, 0)))
        assert tall.horizontalScrollBar().value() == kept

    def test_it_still_scrolls_down_to_the_row(self, tall: ShotListView) -> None:
        tall.scrollTo(tall.proxy.index(25, SHOT, tall.proxy.index(0, 0)))
        assert tall.verticalScrollBar().value() > 0

    def test_a_cell_that_scrolls_is_scrolled_to_as_usual(self, tall: ShotListView) -> None:
        tall.horizontalScrollBar().setValue(0)
        tall.scrollTo(tall.proxy.index(0, NOTES, tall.proxy.index(0, 0)))
        assert tall.horizontalScrollBar().value() > 0


class TestTheTurnoverLine:
    """The group header sentence is drawn by both views, so it must not move in one.

    Section 2's header spans the width, which means the list draws it from wherever the
    first column has scrolled to while the overlay draws it from the left edge. Pinned,
    the two copies land on each other and the sentence reads once.
    """

    def painted(self, view: ShotListView, scrolled: int = 0, width: int = 600) -> QImage:
        """The group header row as the delegate draws it, at a scroll and a width.

        The width is the row's rectangle rather than the image's: the overlay spans a
        250 pixel row and the list spans the whole of a much wider one, and what that
        difference does to the sentence is the thing being asked about.
        """
        option = QStyleOptionViewItem()
        option.initFrom(view)
        option.widget = view
        option.rect = QRect(-scrolled, 0, width + scrolled, 40)
        pixmap = QPixmap(600, 40)
        pixmap.fill(Qt.GlobalColor.black)
        painter = QPainter(pixmap)
        TwoLineDelegate(view).paint(painter, option, view.proxy.index(0, 0))
        painter.end()
        return pixmap.toImage()

    def test_the_sentence_lands_in_the_same_place_however_far_the_list_has_scrolled(
        self, tall: ShotListView
    ) -> None:
        still = self.painted(tall)
        tall.horizontalScrollBar().setValue(180)
        assert self.painted(tall, scrolled=180) == still

    def test_the_overlay_draws_the_same_sentence_and_does_not_elide_it(self, tall: ShotListView) -> None:
        """An ellipsis at the overlay's edge would land in the middle of a line the
        list is still drawing the rest of, and read as two sentences."""
        seam = QRect(0, 0, sum(tall.columnWidth(c) for c in range(FROZEN_COLUMNS)), 40)
        assert self.painted(tall, width=250).copy(seam) == self.painted(tall, width=900).copy(seam)

    def test_it_is_drawn_at_all(self, tall: ShotListView) -> None:
        """An identical pair of blank images would pass either test above."""
        blank = QPixmap(600, 40)
        blank.fill(Qt.GlobalColor.black)
        assert self.painted(tall) != blank.toImage()
