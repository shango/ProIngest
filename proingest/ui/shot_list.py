"""The shot list itself: the view, its two line cells, and the search filter.

UI_SPEC section 2. The view is thin on purpose - what a cell says and what colour it is
are the model's answers (`ui/shot_model.py`), and what is left here is how a row is
drawn, which rows are shown, and what typing into one does.

Editing (M5.3) is the model's too: what arrives here is the editor widget, the inline
error section 5 asks for while it is open, Tab across the four editable columns, and
the prompt Ctrl+K puts in front of somebody skipping a row. A dialog is the one part of
an edit that cannot live in a model.

**The frozen left columns are not in this chunk.** Section 2 wants Status, Shot and Elem
to stay put while the rest scrolls, and QTreeView has no such thing: it needs a second
view overlaid on the first, sharing the model and the selection. It is the known awkward
part (PROGRESS section 9), it interacts with editing and selection, and both of those
land in M5.3, so it is built after them rather than twice. `shot_model.FROZEN_COLUMNS`
is where the count already lives.
"""

from __future__ import annotations

from typing import cast

from PySide6.QtCore import (
    QModelIndex,
    QPersistentModelIndex,
    QRect,
    QSize,
    QSortFilterProxyModel,
    Qt,
)
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QInputDialog,
    QLineEdit,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTreeView,
    QWidget,
)

from proingest.core.frames import ParsedInput
from proingest.core.models import ShotRow
from proingest.ui import shot_model
from proingest.ui.shot_model import (
    COLUMNS,
    DOT_COLORS,
    EDITABLE_COLUMNS,
    IN,
    OUT,
    PROGRESS,
    PROGRESS_ROLE,
    SECONDARY_ROLE,
    SHOT,
    RowState,
    ShotListModel,
)

SECONDARY_COLOR = QColor("#5c626d")
SECONDARY_SCALE = 0.85
"""The demoted line is smaller and dimmer, never hidden (section 2)."""

ERROR_COLOR = QColor("#cf5a52")
"""What an unrecognized In or Out turns while the editor is still open (section 5).
The same red as the error dot, because it is the same thing being said."""

BAR_HEIGHT = 4
BAR_TRACK = QColor("#2b2f36")
"""The slim bar in the Progress column (section 7). Four pixels: it sits where the
demoted second line sits in every other column, and it is a glance, not a readout."""

SKIP_PROMPT_TITLE = "Skip shot"
SKIP_PROMPT_LABEL = "Reason for skipping this shot:"

ModelIndex = QModelIndex | QPersistentModelIndex


def source_of(index: ModelIndex) -> tuple[ShotListModel, ModelIndex]:
    """The `ShotListModel` behind a view index, and the index into it.

    Everything the view holds is a proxy index, because the search box filters through
    one. Only the model can parse an In or Out, so anything that needs an answer rather
    than a cell has to come back through here first.
    """
    model = index.model()
    if isinstance(model, QSortFilterProxyModel):
        return cast(ShotListModel, model.sourceModel()), model.mapToSource(index)
    return cast(ShotListModel, model), index


def show_parse(editor: QLineEdit, parsed: ParsedInput) -> None:
    """Section 5's inline red text, while the editor is still open.

    It colours what was typed rather than replacing it: the editor has to be able to see
    the mistake to fix it, and Escape is what reverts. No result is recorded anywhere,
    because a value that was never committed is not a fact about the row.
    """
    editor.setStyleSheet("" if parsed.ok else f"color: {ERROR_COLOR.name()}")
    editor.setToolTip("" if parsed.ok else parsed.error or "")


class TwoLineDelegate(QStyledItemDelegate):
    """Draws the primary value and, under it, whichever representation is not primary.

    Applied to every column rather than only In and Out, because the row height has to
    fit two lines whatever the cell holds, and a delegate that only some columns use
    would leave the rest vertically centred against a different height.
    """

    def createEditor(
        self, parent: QWidget, option: QStyleOptionViewItem, index: ModelIndex
    ) -> QWidget:
        """A line edit, and for In and Out one that says while typing whether it parses.

        Qt's own `setEditorData` and `setModelData` do the rest: they read the edit role
        and write it back through `setData`, which is where the commit lives. Nothing
        here decides what a cell may hold.
        """
        editor = QLineEdit(parent)
        if index.column() in (IN, OUT):
            model, source_index = source_of(index)
            editor.textChanged.connect(
                lambda text: show_parse(editor, model.parse_frame(source_index, text))
            )
        return editor

    def sizeHint(self, option: QStyleOptionViewItem, index: ModelIndex) -> QSize:
        size = super().sizeHint(option, index)
        line = option.fontMetrics.height()
        size.setHeight(max(size.height(), int(line * (1 + SECONDARY_SCALE)) + 6))
        return size

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: ModelIndex) -> None:
        if index.column() == PROGRESS and index.data(PROGRESS_ROLE) is not None:
            self._paint_progress(painter, option, index)
            return
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

    def _paint_progress(
        self, painter: QPainter, option: QStyleOptionViewItem, index: ModelIndex
    ) -> None:
        """The job count, and under it the slim bar (UI_SPEC section 7).

        Under rather than beside: the row is already two lines high for the In and Out
        cells, and the bar in the demoted line means the count stays where every other
        column's value is. A row with nothing planned has no bar at all rather than an
        empty track, because an empty track reads as a job that has not started.
        """
        styled = QStyleOptionViewItem(option)
        self.initStyleOption(styled, index)
        count = styled.text
        styled.text = ""
        widget = styled.widget
        style = widget.style() if widget else QApplication.style()
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, styled, painter, widget)

        rect = styled.rect.adjusted(3, 2, -3, -2)
        line = option.fontMetrics.height()
        painter.save()
        painter.setPen(styled.palette.text().color())
        painter.drawText(
            rect.adjusted(0, 0, 0, -line), int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop), count
        )
        if count:
            fraction = float(index.data(PROGRESS_ROLE))
            track = rect.adjusted(0, rect.height() - BAR_HEIGHT, 0, 0)
            painter.fillRect(track, BAR_TRACK)
            filled = QRect(track)
            filled.setWidth(int(track.width() * max(0.0, min(1.0, fraction))))
            done = fraction >= 1.0
            painter.fillRect(filled, DOT_COLORS[RowState.DONE if done else RowState.RENDERING])
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
        self.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
            | QAbstractItemView.EditTrigger.AnyKeyPressed
        )
        # QTreeView ships with this off, where QTableView ships with it on, so Tab moved
        # focus out of the list entirely unless a cell editor happened to be open. Section
        # 4 gives Tab to the cells, and `moveCursor` below is only reached when it is on.
        self.setTabKeyNavigation(True)
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

    def select_row(self, row: ShotRow) -> None:
        """Put the cursor on a shot somebody pointed at from somewhere else.

        A row the search box has filtered out has no index in the proxy, so the filter
        is cleared first: the alternative is a double-click in the Issues dock that
        silently does nothing because of a search the editor typed a minute ago.
        """
        source = self.shot_model.index_for_row(row)
        if not source.isValid():
            return
        index = self.proxy.mapFromSource(source)
        if not index.isValid():
            self.filter_by("")
            index = self.proxy.mapFromSource(source)
        self.setCurrentIndex(index)
        self.scrollTo(index)
        self.setFocus(Qt.FocusReason.OtherFocusReason)

    def _fit_group_headers(self) -> None:
        """Expand every turnover and let its header span the full width.

        Spanned because a group header carries one sentence, not fifteen cells, and
        expanded because a collapsed turnover on first sight hides the thing the editor
        opened the tool to look at. Collapsing is theirs to do (Space, section 4).
        """
        self.expandAll()
        for row in range(self.proxy.rowCount()):
            self.setFirstColumnSpanned(row, QModelIndex(), True)

    def toggle_skip(self) -> None:
        """Ctrl+K on the current row, prompting for a reason the first time (section 4).

        A row that has been skipped before keeps the reason it was given, so toggling it
        back on does not ask again about a decision already explained. Escape at the
        prompt cancels the skip rather than skipping without a reason.
        """
        index = self.proxy.mapToSource(self.currentIndex())
        row = self.shot_model.row_at(index)
        if row is None:
            return
        if row.skipped:
            self.shot_model.set_skipped(index, False)
            return
        reason = row.skip_reason or self.ask_skip_reason(row)
        if reason is None:
            return
        self.shot_model.set_skipped(index, True, reason)

    def ask_skip_reason(self, row: ShotRow) -> str | None:
        """The prompt, and the one part of an edit that cannot live in the model.

        None means cancelled. Its own method so a test can answer it without a dialog:
        an offscreen modal is a hung suite, not a failed assertion.
        """
        shot = row.shot_code or row.clip_name
        reason, accepted = QInputDialog.getText(
            self, SKIP_PROMPT_TITLE, f"{SKIP_PROMPT_LABEL}\n{shot}"
        )
        return reason if accepted else None

    def moveCursor(
        self, action: QAbstractItemView.CursorAction, modifiers: Qt.KeyboardModifier
    ) -> QModelIndex:
        """Tab and Shift+Tab step through editable cells only (section 4).

        Qt's own next cell is the next column, editable or not, which on this list means
        tabbing out of In and into Duration. The other cursor actions are Qt's: arrows
        move by row and by column, and nothing here has an opinion about that.
        """
        forward = action is QAbstractItemView.CursorAction.MoveNext
        if forward or action is QAbstractItemView.CursorAction.MovePrevious:
            stepped = self._step_editable(forward)
            if stepped is not None:
                return stepped
        return super().moveCursor(action, modifiers)

    def _step_editable(self, forward: bool) -> QModelIndex | None:
        """The editable cell after (or before) the current one, wrapping round the list.

        Wrapping rather than stopping: section 4 wraps to the next row's first editable
        cell, and the end of the last row is the same move made at the end of the list.
        """
        cells = self._editable_cells()
        if not cells:
            return None
        current = self.currentIndex()
        position = next((at for at, cell in enumerate(cells) if cell == current), None)
        if position is None:
            return cells[0]
        return cells[(position + (1 if forward else -1)) % len(cells)]

    def _editable_cells(self) -> list[QModelIndex]:
        """Every editable cell the list is showing, in reading order.

        Built per Tab rather than kept, because filtering, skipping and a row losing its
        media all change what is editable, and a cached list is one that goes stale
        silently. Four columns per visible row is a cheap walk.
        """
        cells: list[QModelIndex] = []
        for group in range(self.proxy.rowCount()):
            parent = self.proxy.index(group, 0)
            for shot in range(self.proxy.rowCount(parent)):
                for column in EDITABLE_COLUMNS:
                    index = self.proxy.index(shot, column, parent)
                    if index.flags() & Qt.ItemFlag.ItemIsEditable:
                        cells.append(index)
        return cells

    def current_shot_row(self) -> ShotRow | None:
        """The row under the cursor, or None when a group header is."""
        return self.shot_model.row_at(self.proxy.mapToSource(self.currentIndex()))


def display_mode_of(view: ShotListView) -> shot_model.DisplayMode:
    """Convenience for the batch bar, which owns the control rather than the state."""
    return view.shot_model.display_mode
