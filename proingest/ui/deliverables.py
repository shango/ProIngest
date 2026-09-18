"""The Deliverables tab: every output the selected shot plans or has written.

UI_SPEC section 6.2. The shot list's Progress column says how many of a row's
deliverables have landed and the Issues dock says which failed a check; what neither
says is **what** a row delivers - the four picture outputs, the wav, the side files -
where each one went, at which version, and how big it is. That is this table, for the
selected rows, and it is read only like the metadata pane beside it: a deliverable is
written by a run and by nothing else.

A `QTreeWidget` rebuilt from the selection, for the reason the Issues dock is one: a
row plans a dozen outputs at most, nothing edits them, and keeping a model in step with
a run that rewrites statuses five times a second costs more than redrawing a short
list when the selection or the results change.

Double-clicking a line opens the folder the file is in, which is what a person wants
from a path they can read but cannot type.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QTreeWidget, QTreeWidgetItem, QWidget

from proingest.core.models import Deliverable, ShotRow

COLUMNS = ("Shot", "Deliverable", "Kind", "Res", "Ver", "Status", "Frames", "Size", "Failed", "Path")

WIDTHS = (120, 300, 80, 50, 40, 80, 60, 80, 120, 500)

STATUS_COLORS = {
    "done": QColor("#58a97a"),
    "exists": QColor("#58a97a"),
    "failed": QColor("#cf5a52"),
    "rendering": QColor("#4d8fd6"),
    "skipped": QColor("#868d9a"),
}
"""The shot list's own colours for the same states (UI_SPEC section 3): green for a
file that is there, red for one that failed, the accent for one being written."""

NO_DELIVERABLES = "Nothing planned yet. A run plans a row's deliverables and writes them."
"""The one line shown when the selected rows have no deliverables, so an empty table
under a shot that has never run reads as not yet rather than as broken."""


def size_text(size: int) -> str:
    """Bytes as a person reads them: `1.2 GB`, `640 MB`, `12 KB`. Empty for nothing."""
    if size <= 0:
        return ""
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1000 or unit == "GB":
            break
        value /= 1000
    return f"{value:.0f} {unit}" if unit == "B" or value >= 10 else f"{value:.1f} {unit}"


def failed_rules(item: Deliverable) -> str:
    """The rule IDs this deliverable failed, in the order the checks recorded them."""
    return ", ".join(result.rule_id for result in item.qc if result.severity == "error")


class DeliverablesDock(QTreeWidget):
    """Section 6.2's table, for the selected rows."""

    path_activated = Signal(object)
    """A `Path` to show: the folder a deliverable is in. Double-click, like the Issues
    dock's, so that reading the table with the arrow keys opens nothing."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("deliverables_dock")
        self.setColumnCount(len(COLUMNS))
        self.setHeaderLabels(list(COLUMNS))
        self.setRootIsDecorated(False)
        self.setUniformRowHeights(True)
        self.setAlternatingRowColors(False)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        for column, width in enumerate(WIDTHS):
            self.setColumnWidth(column, width)
        self.header().setSectionResizeMode(COLUMNS.index("Path"), QHeaderView.ResizeMode.Stretch)
        self.itemActivated.connect(self._activated)
        self.itemDoubleClicked.connect(self._activated)
        self._paths: list[Path | None] = []

    def show_rows(self, rows: Sequence[ShotRow]) -> None:
        """Rebuild from these rows' deliverables as they stand now."""
        self.clear()
        self._paths = []
        for row in rows:
            for item in row.deliverables:
                line = QTreeWidgetItem(
                    [
                        row.shot_code or row.clip_name,
                        item.name,
                        item.kind,
                        item.res or "",
                        f"v{item.version:02d}",
                        item.status,
                        str(item.frame_count) if item.frame_count else "",
                        size_text(item.size),
                        failed_rules(item),
                        str(item.path),
                    ]
                )
                colour = STATUS_COLORS.get(item.status)
                if colour is not None:
                    line.setForeground(COLUMNS.index("Status"), QBrush(colour))
                line.setToolTip(COLUMNS.index("Path"), str(item.path))
                line.setData(0, Qt.ItemDataRole.UserRole, len(self._paths))
                self._paths.append(item.path)
                self.addTopLevelItem(line)
        if rows and not self._paths:
            note = QTreeWidgetItem([NO_DELIVERABLES])
            note.setFlags(Qt.ItemFlag.NoItemFlags)
            note.setData(0, Qt.ItemDataRole.UserRole, None)
            self.addTopLevelItem(note)

    @property
    def count(self) -> int:
        """Deliverable lines, not counting the note shown when there are none."""
        return len(self._paths)

    def _activated(self, item: QTreeWidgetItem, _column: int = 0) -> None:
        position = item.data(0, Qt.ItemDataRole.UserRole)
        path = self._paths[position] if position is not None else None
        if path is not None:
            self.path_activated.emit(path.parent)
