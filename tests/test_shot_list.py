"""The shot list's view, filter and two line cells. `ui/shot_list.py`, M5.2.

What can honestly be asserted about a view drawn to nothing: which rows it shows, what
it spans, what it hands back as selected, and that a cell paints without raising. How it
looks is a person's job on a Mac (docs/MAC_SESSION.md).
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QModelIndex, QRect, Qt
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QStyleOptionViewItem

from proingest.ui.shot_list import ShotListView, TwoLineDelegate
from proingest.ui.shot_model import IN, SHOT, DisplayMode, ShotListModel
from tests.fixtures.batches import batch, row, turnover


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
