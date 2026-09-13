"""The Issues dock: every QC result in the batch, as a table you can click into.

UI_SPEC section 6. One row per result, carrying which shot it is about, the rule ID from
`docs/QC_RULES.md`, the severity, the message, and a fix hint where one exists.
Double-clicking a row selects that shot in the list, which is the whole point of the
dock: a hundred shot batch reports its problems here and is corrected over there.

**The rule ID is a column rather than a prefix on the message**, because it is the thing
that survives: a log line, a spreadsheet cell and a conversation with the studio all
quote the ID, and the wording behind it is free to improve.

**The fix hints are text in this chunk and nothing more.** Section 6 names two of them,
"Rename shot code" and "Locate media", and the second is specified to open a file picker
and write a path override into the batch. That is a batch edit from outside the list,
which UI_SPEC section 1 says is the list's alone to make, so it wants deciding rather
than assuming: the hint says what to do, the editor does it in the cell.

Ordering is the batch's own: what the batch says first, then each turnover, then the
rows in list order with their deliverables. Not sorted by severity, because the dock is
read next to the list and the two agreeing about where a shot is worth more than the
errors being at the top of a table that is already coloured by severity.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QTreeWidget, QTreeWidgetItem, QWidget

from proingest.core.models import Batch, QCResult, ShotRow

COLUMNS = ("Shot", "Rule", "Severity", "Message", "Fix")

WIDTHS = (150, 80, 80, 620, 140)

FIX_HINTS = {
    "QC-010": "Rename shot code",
    "QC-012": "Locate media",
    "QC-013": "Locate media",
    "QC-031": "Check In",
    "QC-032": "Check Out",
    "QC-045": "Trimmed from the approved cut",
}
"""What to do about a result, for the rules where there is one obvious answer.

Deliberately short. A hint per rule would be a second copy of `QC_RULES.md` maintained
in a different file and going stale at a different rate; these are the ones section 6
names plus the three an editor can act on in a cell without leaving the window.
"""

SEVERITY_COLORS = {
    "error": QColor("#cf5a52"),
    "warning": QColor("#cf9a3a"),
    "info": QColor("#868d9a"),
}
"""The same three the shot list paints its dots with (UI_SPEC section 3)."""

BATCH_SCOPE = "Batch"
"""What the Shot column says for a result about the batch rather than about a shot."""


@dataclass(frozen=True)
class Issue:
    """One QC result with the thing it is about, which the result itself does not carry.

    `row` is None for a batch or turnover result, and it is what a double-click selects.
    """

    label: str
    result: QCResult
    row: ShotRow | None = None


def issues_for(batch: Batch) -> list[Issue]:
    """Every result in the batch, in the order the list shows the things they are about."""
    found = [Issue(BATCH_SCOPE, result) for result in batch.qc]
    for turnover in batch.turnovers:
        found.extend(Issue(turnover.folder.name, result) for result in turnover.qc)
        for row in batch.rows_for(turnover.turnover_id):
            label = row.shot_code or row.clip_name
            found.extend(Issue(label, result, row) for result in row.qc)
            for deliverable in row.deliverables:
                found.extend(Issue(label, result, row) for result in deliverable.qc)
    return found


class IssuesDock(QTreeWidget):
    """Section 6's table. A `QTreeWidget` because it is a flat list of fixed columns.

    A widget rather than a model and a view: nothing filters or edits it, it is rebuilt
    whenever the batch changes, and a hundred shot batch's worth of results is a list
    short enough that rebuilding it costs less than keeping a model in step with rules
    that re-run on every keystroke.
    """

    row_activated = Signal(object)
    """A `ShotRow` to select in the list. Section 6: double-click selects the row.

    Activation rather than selection, so that walking the dock with the arrow keys to
    read the messages does not drag the list along behind it.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("issues_dock")
        self.setColumnCount(len(COLUMNS))
        self.setHeaderLabels(list(COLUMNS))
        self.setRootIsDecorated(False)
        self.setUniformRowHeights(True)
        self.setAlternatingRowColors(False)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        for column, width in enumerate(WIDTHS):
            self.setColumnWidth(column, width)
        self.header().setSectionResizeMode(
            COLUMNS.index("Message"), QHeaderView.ResizeMode.Stretch
        )
        self.itemActivated.connect(self._activated)
        self.itemDoubleClicked.connect(self._activated)
        self._rows: list[ShotRow | None] = []

    def show_batch(self, batch: Batch) -> None:
        """Rebuild from the batch as it stands now."""
        self.clear()
        self._rows = []
        for issue in issues_for(batch):
            item = QTreeWidgetItem(
                [
                    issue.label,
                    issue.result.rule_id,
                    issue.result.severity,
                    issue.result.message,
                    FIX_HINTS.get(issue.result.rule_id, ""),
                ]
            )
            colour = SEVERITY_COLORS.get(issue.result.severity)
            if colour is not None:
                item.setForeground(COLUMNS.index("Severity"), QBrush(colour))
            item.setToolTip(COLUMNS.index("Message"), issue.result.message)
            item.setData(0, Qt.ItemDataRole.UserRole, len(self._rows))
            self._rows.append(issue.row)
            self.addTopLevelItem(item)

    @property
    def count(self) -> int:
        return self.topLevelItemCount()

    def select_result(self, rule_id: str, rows: Sequence[ShotRow] = ()) -> bool:
        """Select the row for this rule, preferring one about a shot that is selected.

        What the metadata pane's rule ID links land on (UI_SPEC section 12.2). Preferring
        the selection matters because a rule fires on many shots: QC-023 clicked while
        MELT0007 is selected should land on MELT0007's line, not on the first one in the
        batch. Falls back to the first line carrying that rule, and selects nothing when
        the dock no longer holds one.
        """
        wanted = {id(row) for row in rows}
        fallback: QTreeWidgetItem | None = None
        for position in range(self.topLevelItemCount()):
            item = self.topLevelItem(position)
            if item is None or item.text(COLUMNS.index("Rule")) != rule_id:
                continue
            if fallback is None:
                fallback = item
            index = item.data(0, Qt.ItemDataRole.UserRole)
            row = self._rows[index] if index is not None else None
            if row is not None and id(row) in wanted:
                fallback = item
                break
        if fallback is None:
            return False
        self.setCurrentItem(fallback)
        self.scrollToItem(fallback)
        return True

    def _activated(self, item: QTreeWidgetItem, _column: int = 0) -> None:
        """Ask for the shot this result is about, if it is about one."""
        position = item.data(0, Qt.ItemDataRole.UserRole)
        row = self._rows[position] if position is not None else None
        if row is not None:
            self.row_activated.emit(row)
