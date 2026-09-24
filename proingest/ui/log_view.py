"""The Log tab: what the tool has been doing, including every ffmpeg command it ran.

FR-13's third part, and the reason the other two exist. CLAUDE.md's rule is that every
ffmpeg command is logged verbatim **so the user can reproduce a render**, and a command
line the editor cannot select and copy has only half kept that promise. So the messages
are never abbreviated, never re-wrapped, and Ctrl+C copies what is selected.

**Records arrive on threads that are not this one.** A run's command lines are made in a
worker process and republished by `core/logsetup.py`'s listener thread; the scan logs
from its own `QThread`. A `logging.Handler` therefore cannot touch a widget, so this
module splits in two: `LogBuffer` is a plain, locked ring buffer that any thread may
append to, and the view drains it on a timer. That is the same arrangement `ui/runner.py`
uses for progress and for the same reason - a run emits a message per ffmpeg call, and a
repaint per message is a UI thread doing nothing else.

**It is bounded and it is bounded at the buffer.** A hundred shot batch is thousands of
lines and an unbounded panel is a window that grows until it is closed; the file is the
complete record and this is the window onto its tail. `MAX_LINES` is what the tail is.

**The filters hide rows rather than rebuild the table**, because every line is already an
item and building three thousand of them again on a keystroke is the one thing that would
make the box unpleasant to type in.
"""

from __future__ import annotations

import logging
import threading
from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QGuiApplication, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from proingest.core import logsetup

COLUMNS = ("Time", "Level", "Shot", "Message")

SAVE_TEXT = "Save Logs as CSV..."
"""Every kept log file as one CSV, for the editor to send when something went wrong.
The window answers it, because it owns the dialogs and knows where the logs are."""

WIDTHS = (90, 70, 130, 900)

MAX_LINES = 5000
"""How much of the tail the panel keeps. The file keeps all of it.

Five thousand is roughly a full run of a large turnover: a command line per deliverable
plus a line per file written. Beyond that the panel is being read as a file, and the
file is `~/Library/Logs/ProIngest` (PACKAGING.md), which is where that reading belongs.
"""

DRAIN_MS = 250
"""How often the view takes what has arrived. Slower than a repaint, faster than reading."""

LEVELS: tuple[tuple[str, int], ...] = (
    ("All", 0),
    ("Info", logging.INFO),
    ("Warning", logging.WARNING),
    ("Error", logging.ERROR),
)
"""The level combo, each entry meaning "this and above"."""

SELECTED_ONLY = "Selected row only"
"""FR-13's "filter by row". Only a record a render worker stamped names a shot, so this
hides everything the window itself logged as well, which is the point: it answers "what
happened to this shot" rather than "what happened while this shot was selected"."""

NO_SELECTION = "Select a row in the list to filter by it"

EMPTY = "Nothing logged yet"

HIDDEN = "{shown} of {total} lines"

LEVEL_COLORS = {
    logging.WARNING: QColor("#cf9a3a"),
    logging.ERROR: QColor("#cf5a52"),
    logging.CRITICAL: QColor("#cf5a52"),
}
"""The same two the Issues dock paints a warning and an error with (UI_SPEC section 3).
Info is left in the default text colour, because almost every line is one."""


@dataclass(frozen=True)
class Line:
    """One record, already formatted, with nothing of the original left referenced.

    A `LogRecord` carries `args` and an `exc_info`, which can be any live object at all,
    and holding five thousand of them would be a panel that keeps a run's worth of
    memory alive. Formatting happens on whichever thread made the record, which is also
    the thread that should pay for it.
    """

    time: str
    level: int
    level_name: str
    shot: str
    message: str

    @classmethod
    def of(cls, record: logging.LogRecord) -> Line:
        return cls(
            time=datetime.fromtimestamp(record.created).strftime("%H:%M:%S"),
            level=record.levelno,
            level_name=record.levelname,
            shot=logsetup.shot_of(record),
            message=record.getMessage(),
        )


class LogBuffer:
    """A bounded queue of lines that any thread may add to and one thread drains.

    No Qt: a `logging.Handler` is called from a render's listener thread, the scan's
    `QThread` and the UI thread, and a widget touched from any of the first two is a
    crash rather than a wrong pixel.
    """

    def __init__(self, capacity: int = MAX_LINES) -> None:
        self._lines: deque[Line] = deque(maxlen=capacity)
        self._lock = threading.Lock()

    def append(self, line: Line) -> None:
        with self._lock:
            self._lines.append(line)

    def drain(self) -> list[Line]:
        """Everything added since the last call, oldest first."""
        with self._lock:
            taken = list(self._lines)
            self._lines.clear()
        return taken


class BufferHandler(logging.Handler):
    """The root logger's line into the panel. Formats, then hands over and returns.

    It never blocks on the UI and never raises into the logging call: a panel that
    cannot keep up drops nothing, because the buffer is bounded at the far end.
    """

    def __init__(self, buffer: LogBuffer) -> None:
        super().__init__()
        self.buffer = buffer

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.buffer.append(Line.of(record))
        except Exception:  # pragma: no cover - a logging call must never take the app down
            self.handleError(record)


class LogView(QWidget):
    """The tab itself: a filter bar over a table of lines.

    It installs its own handler on the root logger and takes it off again in `detach`,
    which the window calls on the way out. Owning it here rather than in the window
    keeps the one thing that has to be undone next to the thing that does it.
    """

    save_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.buffer = LogBuffer()
        self.handler = BufferHandler(self.buffer)
        self._selected_shot = ""

        self.level_box = QComboBox(self)
        self.level_box.setObjectName("log_level_filter")
        for name, _ in LEVELS:
            self.level_box.addItem(name)
        self.level_box.currentIndexChanged.connect(lambda _index: self._refilter())

        self.search = QLineEdit(self)
        self.search.setObjectName("log_search")
        self.search.setPlaceholderText("Filter the log")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(lambda _text: self._refilter())

        self.selected_only = QCheckBox(SELECTED_ONLY, self)
        self.selected_only.setObjectName("log_selected_only")
        self.selected_only.setToolTip(NO_SELECTION)
        self.selected_only.setEnabled(False)
        self.selected_only.stateChanged.connect(lambda _state: self._refilter())

        self.count = QLabel(EMPTY, self)
        self.count.setObjectName("log_count")

        self.save_button = QPushButton(SAVE_TEXT, self)
        self.save_button.setObjectName("log_save")
        self.save_button.setToolTip("Every log the tool has kept, as one file to send for diagnostics")
        self.save_button.clicked.connect(self.save_requested)

        self.tree = QTreeWidget(self)
        self.tree.setObjectName("log_tree")
        self.tree.setColumnCount(len(COLUMNS))
        self.tree.setHeaderLabels(list(COLUMNS))
        self.tree.setRootIsDecorated(False)
        self.tree.setUniformRowHeights(True)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tree.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        for index, width in enumerate(WIDTHS):
            self.tree.setColumnWidth(index, width)
        self.tree.header().setStretchLastSection(True)
        self.tree.header().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)

        copy = QShortcut(QKeySequence.StandardKey.Copy, self.tree)
        copy.setContext(Qt.ShortcutContext.WidgetShortcut)
        copy.activated.connect(self.copy_selection)

        bar = QHBoxLayout()
        bar.setContentsMargins(0, 0, 0, 0)
        bar.addWidget(self.level_box)
        bar.addWidget(self.search, 1)
        bar.addWidget(self.selected_only)
        bar.addWidget(self.count)
        bar.addWidget(self.save_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.addLayout(bar)
        layout.addWidget(self.tree, 1)

        logging.getLogger().addHandler(self.handler)

        self._timer = QTimer(self)
        self._timer.setInterval(DRAIN_MS)
        self._timer.timeout.connect(self.drain)
        self._timer.start()

    # --- what the window tells it -------------------------------------------------------

    def set_selected_shot(self, shot: str) -> None:
        """Which row the list is on, so "selected row only" has something to mean.

        Empty for no selection, for a selection spanning two shots, and for a row with
        no shot code yet: all three are "there is no one row to filter by", and a
        checkbox that filters to nothing would read as a log that had stopped.
        """
        if shot == self._selected_shot:
            return
        self._selected_shot = shot
        self.selected_only.setEnabled(bool(shot))
        self.selected_only.setToolTip(NO_SELECTION if not shot else f"Only lines about {shot}")
        if not shot:
            # Unchecked rather than left checked and ignored: a box that is ticked while
            # filtering nothing is a control saying something untrue about the table.
            # `setChecked` re-filters through its own signal when it changes anything.
            self.selected_only.setChecked(False)
        if self.selected_only.isChecked():
            self._refilter()

    def detach(self) -> None:
        """Take the handler off the root logger. The window calls this on the way out."""
        self._timer.stop()
        logging.getLogger().removeHandler(self.handler)

    # --- what arrives --------------------------------------------------------------------

    def drain(self) -> None:
        """Move what the buffer has collected into the table. Called on a timer."""
        arrived = self.buffer.drain()
        if not arrived:
            return
        at_bottom = self._at_bottom()
        self.tree.setUpdatesEnabled(False)
        try:
            self._append(arrived)
            self._trim()
        finally:
            self.tree.setUpdatesEnabled(True)
        self._update_count()
        if at_bottom:
            self.tree.scrollToBottom()

    def lines(self) -> list[Line]:
        """Every line the panel is holding, filtered or not. For tests and for counting."""
        return [self._line_of(index) for index in range(self.tree.topLevelItemCount())]

    def visible_lines(self) -> list[Line]:
        """The ones the filters are letting through, in order."""
        return [
            self._line_of(index)
            for index in range(self.tree.topLevelItemCount())
            if not self._item(index).isHidden()
        ]

    def copy_selection(self) -> None:
        """The selected lines as text, tab separated, message last and never truncated."""
        rows = [
            "\t".join(item.text(column) for column in range(len(COLUMNS)))
            for item in self.tree.selectedItems()
        ]
        if rows:
            QGuiApplication.clipboard().setText("\n".join(rows))

    # --- the table ------------------------------------------------------------------------

    def _append(self, arrived: Iterable[Line]) -> None:
        for line in arrived:
            item = QTreeWidgetItem([line.time, line.level_name, line.shot, line.message])
            item.setData(0, Qt.ItemDataRole.UserRole, line)
            colour = LEVEL_COLORS.get(line.level)
            if colour is not None:
                item.setForeground(1, QBrush(colour))
                item.setForeground(3, QBrush(colour))
            # Added before it is hidden: `setHidden` on an item with no tree yet does
            # nothing at all, which reads as a filter that ignores everything new.
            self.tree.addTopLevelItem(item)
            item.setHidden(not self._matches(line))

    def _trim(self) -> None:
        """Keep the tail. The table is the bound, so a filtered-out line still ages out."""
        excess = self.tree.topLevelItemCount() - MAX_LINES
        for _ in range(max(0, excess)):
            self.tree.takeTopLevelItem(0)

    def _refilter(self) -> None:
        for index in range(self.tree.topLevelItemCount()):
            self._item(index).setHidden(not self._matches(self._line_of(index)))
        self._update_count()

    def _matches(self, line: Line) -> bool:
        if line.level < LEVELS[self.level_box.currentIndex()][1]:
            return False
        if self.selected_only.isChecked() and self._selected_shot != line.shot:
            return False
        text = self.search.text().strip().lower()
        if not text:
            return True
        return text in line.message.lower() or text in line.shot.lower()

    def _item(self, index: int) -> QTreeWidgetItem:
        item = self.tree.topLevelItem(index)
        assert item is not None, "every index comes from topLevelItemCount"
        return item

    def _line_of(self, index: int) -> Line:
        line = self._item(index).data(0, Qt.ItemDataRole.UserRole)
        assert isinstance(line, Line)
        return line

    def _update_count(self) -> None:
        total = self.tree.topLevelItemCount()
        if not total:
            self.count.setText(EMPTY)
            return
        shown = sum(not self._item(index).isHidden() for index in range(total))
        self.count.setText(HIDDEN.format(shown=shown, total=total))

    def _at_bottom(self) -> bool:
        """Whether to follow the tail. A person who has scrolled up is reading something."""
        bar = self.tree.verticalScrollBar()
        return bar.value() >= bar.maximum() - 1
