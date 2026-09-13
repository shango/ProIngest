"""The shot list itself: the view, its two line cells, and the search filter.

UI_SPEC section 2. The view is thin on purpose - what a cell says and what colour it is
are the model's answers (`ui/shot_model.py`), and what is left here is how a row is
drawn and which rows are shown.

**The frozen left columns are not in this chunk.** Section 2 wants Status, Shot and Elem
to stay put while the rest scrolls, and QTreeView has no such thing: it needs a second
view overlaid on the first, sharing the model and the selection. It is the known awkward
part (PROGRESS section 9), it interacts with editing and selection, and both of those
land in M5.3, so it is built after them rather than twice. `shot_model.FROZEN_COLUMNS`
is where the count already lives.
"""

from __future__ import annotations

from PySide6.QtCore import QModelIndex, QPersistentModelIndex, QSize, QSortFilterProxyModel, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTreeView,
    QWidget,
)

from proingest.core.models import ShotRow
from proingest.ui import shot_model
from proingest.ui.shot_model import COLUMNS, SECONDARY_ROLE, SHOT, ShotListModel

SECONDARY_COLOR = QColor("#5c626d")
SECONDARY_SCALE = 0.85
"""The demoted line is smaller and dimmer, never hidden (section 2)."""

ModelIndex = QModelIndex | QPersistentModelIndex


class TwoLineDelegate(QStyledItemDelegate):
    """Draws the primary value and, under it, whichever representation is not primary.

    Applied to every column rather than only In and Out, because the row height has to
    fit two lines whatever the cell holds, and a delegate that only some columns use
    would leave the rest vertically centred against a different height.
    """

    def sizeHint(self, option: QStyleOptionViewItem, index: ModelIndex) -> QSize:
        size = super().sizeHint(option, index)
        line = option.fontMetrics.height()
        size.setHeight(max(size.height(), int(line * (1 + SECONDARY_SCALE)) + 6))
        return size

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: ModelIndex) -> None:
        secondary = index.data(SECONDARY_ROLE)
        if not secondary:
            super().paint(painter, option, index)
            return

        styled = QStyleOptionViewItem(option)
        self.initStyleOption(styled, index)
        primary = styled.text
        styled.text = ""
        widget = styled.widget
        style = widget.style() if widget else QApplication.style()
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, styled, painter, widget)

        rect = styled.rect.adjusted(3, 2, -3, -2)
        align = Qt.AlignmentFlag(styled.displayAlignment) & Qt.AlignmentFlag.AlignHorizontal_Mask
        line = option.fontMetrics.height()

        painter.save()
        painter.setPen(styled.palette.text().color())
        painter.drawText(rect.adjusted(0, 0, 0, -line), int(align | Qt.AlignmentFlag.AlignTop), primary)
        small = painter.font()
        small.setPointSizeF(max(small.pointSizeF() * SECONDARY_SCALE, 7.0))
        painter.setFont(small)
        painter.setPen(SECONDARY_COLOR)
        painter.drawText(rect, int(align | Qt.AlignmentFlag.AlignBottom), str(secondary))
        painter.restore()


class ShotFilterProxy(QSortFilterProxyModel):
    """The search box: shot code substring, and never an empty turnover.

    A turnover is kept when anything under it matches, so filtering narrows the list
    without losing which turnover a shot came from. Nothing here sorts: section 2 fixes
    the order to the timeline's, and a sortable list is one an editor can put into an
    order the delivery does not use.
    """

    def filterAcceptsRow(self, source_row: int, source_parent: ModelIndex) -> bool:
        text = self.filterRegularExpression().pattern()
        if not text:
            return True
        model = self.sourceModel()
        index = model.index(source_row, SHOT, source_parent)
        if not source_parent.isValid():
            return any(
                self.filterAcceptsRow(child, index) for child in range(model.rowCount(index))
            )
        return text.lower() in str(index.data(Qt.ItemDataRole.DisplayRole) or "").lower()


class ShotListView(QTreeView):
    """The list. Two levels, always expanded, fixed order, one row per shot."""

    def __init__(self, model: ShotListModel, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.shot_model = model
        self.proxy = ShotFilterProxy(self)
        self.proxy.setSourceModel(model)
        self.setModel(self.proxy)

        self.setItemDelegate(TwoLineDelegate(self))
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setUniformRowHeights(True)
        self.setAllColumnsShowFocus(True)
        self.setSortingEnabled(False)
        self.setExpandsOnDoubleClick(False)
        self.setAlternatingRowColors(False)
        header = self.header()
        header.setStretchLastSection(True)
        for column, spec in enumerate(COLUMNS):
            self.setColumnWidth(column, spec.width)

        for signal in (model.modelReset, model.layoutChanged):
            signal.connect(self._fit_group_headers)
        self._fit_group_headers()

    def filter_by(self, text: str) -> None:
        """What the search box types. Substring, not a pattern the editor has to escape."""
        self.proxy.setFilterFixedString(text)
        self._fit_group_headers()

    def selected_rows(self) -> list[ShotRow]:
        """The `ShotRow`s currently selected, headers excluded.

        The metadata pane reads this, and section 12.3 wants a multiple selection to
        report what it agrees on, so it is a list rather than the current row.
        """
        rows: list[ShotRow] = []
        for index in self.selectionModel().selectedRows():
            row = self.shot_model.row_at(self.proxy.mapToSource(index))
            if row is not None:
                rows.append(row)
        return rows

    def _fit_group_headers(self) -> None:
        """Expand every turnover and let its header span the full width.

        Spanned because a group header carries one sentence, not fifteen cells, and
        expanded because a collapsed turnover on first sight hides the thing the editor
        opened the tool to look at. Collapsing is theirs to do (Space, section 4).
        """
        self.expandAll()
        for row in range(self.proxy.rowCount()):
            self.setFirstColumnSpanned(row, QModelIndex(), True)

    def current_shot_row(self) -> ShotRow | None:
        """The row under the cursor, or None when a group header is."""
        return self.shot_model.row_at(self.proxy.mapToSource(self.currentIndex()))


def display_mode_of(view: ShotListView) -> shot_model.DisplayMode:
    """Convenience for the batch bar, which owns the control rather than the state."""
    return view.shot_model.display_mode
