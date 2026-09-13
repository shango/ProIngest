"""The shot list's model: a batch presented as turnovers with their rows beneath.

UI_SPEC section 2 is the column list and section 3 the row colouring. Both live here
rather than in the view, because what a cell says is a fact about the batch and what it
looks like is one colour per state: a delegate that had to work either out would be
reading the model twice.

**The model is read only in this chunk.** Editing is M5.3 and arrives as `setData` plus
the input grammar `core/frames.py` already implements. Nothing here writes to a row, so
nothing here can disagree with the rules about what a row now says.

Two levels and no more: a turnover, then its rows in timeline order. Sorting is fixed
(section 2), so there is no sort implementation to get wrong, and the search box filters
through a proxy rather than by rebuilding the model.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any

from PySide6.QtCore import QAbstractItemModel, QModelIndex, QObject, QPersistentModelIndex, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPixmap

from proingest.core import frames
from proingest.core.models import Batch, ShotRow, Turnover

ModelIndex = QModelIndex | QPersistentModelIndex

NO_PARENT = QModelIndex()
"""The invalid index, which is what "the top level" means to `QAbstractItemModel`.

A module level one rather than `QModelIndex()` in each signature's default: Qt's own
signatures spell it that way, but a default that constructs an object is built once at
import and shared anyway, so this says so rather than looking like a fresh one per call.
"""


class DisplayMode(Enum):
    """What the In and Out cells show as their primary value. UI_SPEC section 2.

    Three states rather than two, and **frames is the default**: the frame number is
    what the model holds, what the rules quote, what the delivered sequence is numbered
    by and what gets typed into a cell. Timecode is derived at the boundary. Opening on
    the derived value would show the editor a translation of the thing they are about
    to edit rather than the thing itself.
    """

    FRAMES = "Frames"
    SOURCE_TC = "Source TC"
    RECORD_TC = "Record TC"

    def next(self) -> DisplayMode:
        """Ctrl+T cycles, and round again (UI_SPEC section 4)."""
        order = list(DisplayMode)
        return order[(order.index(self) + 1) % len(order)]

    @property
    def timecode_mode(self) -> frames.TimecodeMode:
        """Which anchor a timecode is read against. Meaningless in FRAMES."""
        return "record" if self is DisplayMode.RECORD_TC else "source"


class RowState(Enum):
    """The seven states of UI_SPEC section 3's table, in precedence order.

    Precedence matters because a row can be several at once: a skipped row with a
    warning is skipped, and a row whose render failed is failed even though it also has
    an error rule about it. The order below is the order they are tested in, and it runs
    from "the editor decided this" through "the machine is busy" to "nobody has done
    anything to it yet".
    """

    SKIPPED = "skipped"
    RENDERING = "rendering"
    FAILED = "failed"
    ERROR = "error"
    WARNING = "warning"
    DONE = "done"
    OK = "ok"


DOT_COLORS = {
    RowState.SKIPPED: QColor("#5c626d"),
    RowState.RENDERING: QColor("#4d8fd6"),
    RowState.FAILED: QColor("#cf5a52"),
    RowState.ERROR: QColor("#cf5a52"),
    RowState.WARNING: QColor("#cf9a3a"),
    RowState.DONE: QColor("#58a97a"),
    RowState.OK: QColor("#868d9a"),
}
"""One colour per state, the palette `ui/theme.qss` states at the top. A stylesheet
cannot see a model, so the dot and the tint are painted from here."""

HOLLOW_STATES = frozenset({RowState.SKIPPED})
"""Drawn as an outline rather than filled: the row is deliberately not being delivered."""

TINTS = {
    RowState.FAILED: QColor(207, 90, 82, 28),
    RowState.ERROR: QColor(207, 90, 82, 28),
    RowState.WARNING: QColor(207, 154, 58, 24),
}
"""Faint red and faint amber, section 3. Every other state has no tint at all: a list
where most rows are tinted is a list where the tint means nothing."""

DIMMED_TEXT = QColor("#5c626d")
"""Skipped rows only, which section 3 calls dimmed text."""

DOT_SIZE = 9

SECONDARY_ROLE = Qt.ItemDataRole.UserRole + 1
"""Whichever representation is not primary, for the second line of an In or Out cell.

Section 2: nothing is ever hidden, only demoted. The delegate paints it; the model
decides what it says, because the model is what knows the display mode.
"""

ROW_ROLE = Qt.ItemDataRole.UserRole + 2
"""The `ShotRow` behind an index, for the metadata pane and the Issues dock."""


@dataclass(frozen=True)
class Column:
    """One column of section 2's list."""

    title: str
    width: int


COLUMNS = (
    Column("", 30),
    Column("Shot", 150),
    Column("Elem", 70),
    Column("Source", 230),
    Column("Res", 100),
    Column("FPS", 70),
    Column("In", 110),
    Column("Out", 110),
    Column("Dur", 70),
    Column("Max", 80),
    Column("Audio", 70),
    Column("Side", 120),
    Column("Ver", 60),
    Column("Progress", 90),
    Column("Notes", 240),
)

STATUS, SHOT, ELEM, SOURCE, RES, FPS, IN, OUT, DURATION, MAX_AVAIL = range(10)
AUDIO, SIDE_FILES, VERSION, PROGRESS, NOTES = range(10, 15)

FROZEN_COLUMNS = 3
"""Status, Shot and Elem stay put while the rest scrolls (section 2). The overlaid
second view that does it is its own chunk; this constant is where it will read the
count from, and it is stated here so the model and that view cannot disagree."""


def row_state(row: ShotRow) -> RowState:
    """Which of section 3's states this row is in, by the precedence above."""
    if row.skipped:
        return RowState.SKIPPED
    statuses = {item.status for item in row.deliverables}
    if "rendering" in statuses:
        return RowState.RENDERING
    if "failed" in statuses:
        return RowState.FAILED
    if row.errors():
        return RowState.ERROR
    if row.warnings():
        return RowState.WARNING
    if statuses and statuses <= {"done", "exists", "skipped"}:
        return RowState.DONE
    return RowState.OK


def turnover_state(turnover: Turnover, rows: list[ShotRow]) -> RowState:
    """The group header's aggregate: the worst state anything under it is in.

    A turnover's own rules count too, since QC-001 and QC-002 are turnover level and
    leave it with no rows at all to carry the colour.
    """
    states = [row_state(row) for row in rows]
    if any(result.severity == "error" for result in turnover.qc):
        states.append(RowState.ERROR)
    elif any(result.severity == "warning" for result in turnover.qc):
        states.append(RowState.WARNING)
    if not states:
        return RowState.OK
    order = list(RowState)
    return min(states, key=order.index)


def _summary(turnover: Turnover, rows: list[ShotRow]) -> str:
    """The counts a collapsed group still has to report (section 2)."""
    errors = sum(1 for row in rows if row.errors()) + sum(
        1 for result in turnover.qc if result.severity == "error"
    )
    warnings = sum(1 for row in rows if row.warnings()) + sum(
        1 for result in turnover.qc if result.severity == "warning"
    )
    parts = [f"{len(rows)} shot{'' if len(rows) == 1 else 's'}"]
    if errors:
        parts.append(f"{errors} error{'' if errors == 1 else 's'}")
    if warnings:
        parts.append(f"{warnings} warning{'' if warnings == 1 else 's'}")
    skipped = sum(1 for row in rows if row.skipped)
    if skipped:
        parts.append(f"{skipped} skipped")
    return ", ".join(parts)


def _version(row: ShotRow) -> str:
    """The version the row's deliverables were planned at. Empty before planning."""
    versions = {item.version for item in row.deliverables}
    return f"v{max(versions):02d}" if versions else ""


def _progress(row: ShotRow) -> str:
    """Done out of planned. The slim bar section 7 asks for arrives with the run."""
    if not row.deliverables:
        return ""
    done = sum(1 for item in row.deliverables if item.status in ("done", "exists"))
    return f"{done}/{len(row.deliverables)}"


def _side_files(row: ShotRow) -> str:
    carried = (("HDRI", row.side_files.hdri), ("camData", row.side_files.camdata))
    return ", ".join(name for name, path in carried if path)


def _audio(row: ShotRow) -> str:
    """None, one or many. Section 2 asks for an icon; the tool ships no icon set yet,
    so the count is the honest stand-in and the tooltip carries the path."""
    if not row.audio_path:
        return ""
    return "1" if row.audio_clip_count <= 1 else str(row.audio_clip_count)


class ShotListModel(QAbstractItemModel):
    """A `Batch` as a two level tree. Read only until M5.3.

    The rows of a turnover are cached per turnover id rather than filtered out of the
    batch on every `data` call: a hundred shot batch asks fifteen columns a question per
    visible row, and `Batch.rows_for` is a scan of the whole list each time.
    """

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._batch = Batch()
        self._rows: dict[str, list[ShotRow]] = {}
        self._mode = DisplayMode.FRAMES
        self._dots: dict[tuple[RowState, bool], QPixmap] = {}

    # --- what it is showing ----------------------------------------------------------

    def set_batch(self, batch: Batch) -> None:
        """Show a different batch. A whole reset, because everything changed."""
        self.beginResetModel()
        self._batch = batch
        self._rows = {t.turnover_id: batch.rows_for(t.turnover_id) for t in batch.turnovers}
        self.endResetModel()

    @property
    def batch(self) -> Batch:
        return self._batch

    @property
    def display_mode(self) -> DisplayMode:
        return self._mode

    def set_display_mode(self, mode: DisplayMode) -> None:
        """Change what In and Out show. Only those two columns are repainted."""
        if mode is self._mode:
            return
        self._mode = mode
        for parent_row in range(len(self._batch.turnovers)):
            parent = self.index(parent_row, 0, QModelIndex())
            count = self.rowCount(parent)
            if count:
                self.dataChanged.emit(
                    self.index(0, IN, parent),
                    self.index(count - 1, OUT, parent),
                    [Qt.ItemDataRole.DisplayRole, SECONDARY_ROLE],
                )

    def row_at(self, index: ModelIndex) -> ShotRow | None:
        """The `ShotRow` an index points at, or None for a turnover header."""
        if not index.isValid() or index.internalId() == 0:
            return None
        turnover = self._batch.turnovers[int(index.internalId()) - 1]
        rows = self._rows[turnover.turnover_id]
        return rows[index.row()] if index.row() < len(rows) else None

    def turnover_at(self, index: ModelIndex) -> Turnover | None:
        """The turnover an index is under, header or row alike."""
        if not index.isValid():
            return None
        position = index.row() if index.internalId() == 0 else int(index.internalId()) - 1
        return self._batch.turnovers[position] if position < len(self._batch.turnovers) else None

    # --- the tree ---------------------------------------------------------------------

    def index(self, row: int, column: int, parent: ModelIndex = NO_PARENT) -> QModelIndex:
        """Internal id 0 is a turnover; anything else is its position plus one.

        Plus one because 0 is what an index with no id carries, and a child of the first
        turnover has to be distinguishable from a turnover.
        """
        if not self.hasIndex(row, column, parent):
            return QModelIndex()
        if not parent.isValid():
            return self.createIndex(row, column, 0)
        return self.createIndex(row, column, parent.row() + 1)

    def parent(self, index: ModelIndex = NO_PARENT) -> QModelIndex:  # type: ignore[override]
        if not index.isValid() or index.internalId() == 0:
            return QModelIndex()
        return self.createIndex(int(index.internalId()) - 1, 0, 0)

    def rowCount(self, parent: ModelIndex = NO_PARENT) -> int:
        if not parent.isValid():
            return len(self._batch.turnovers)
        if parent.internalId() != 0:
            return 0
        turnover = self._batch.turnovers[parent.row()]
        return len(self._rows[turnover.turnover_id])

    def columnCount(self, parent: ModelIndex = NO_PARENT) -> int:
        return len(COLUMNS)

    def headerData(
        self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole
    ) -> Any:
        if orientation is Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return COLUMNS[section].title
        return None

    # --- what a cell says --------------------------------------------------------------

    def data(self, index: ModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid():
            return None
        row = self.row_at(index)
        if row is None:
            return self._header_data(index, role)
        return self._row_data(row, index, role)

    def _header_data(self, index: ModelIndex, role: int) -> Any:
        """A turnover group header. The view spans column 0 across the whole width."""
        turnover = self.turnover_at(index)
        if turnover is None:
            return None
        rows = self._rows[turnover.turnover_id]
        state = turnover_state(turnover, rows)
        if role == Qt.ItemDataRole.DisplayRole and index.column() == 0:
            return f"{turnover.folder.name}  -  {_summary(turnover, rows)}"
        if role == Qt.ItemDataRole.ToolTipRole:
            return "\n".join(f"{r.rule_id} {r.message}" for r in turnover.qc) or str(turnover.folder)
        if role == Qt.ItemDataRole.BackgroundRole:
            return QBrush(TINTS[state]) if state in TINTS else None
        return None

    def _row_data(self, row: ShotRow, index: ModelIndex, role: int) -> Any:
        column = index.column()
        state = row_state(row)
        if role == Qt.ItemDataRole.DisplayRole:
            return self._text(row, column)
        if role == SECONDARY_ROLE and column in (IN, OUT):
            return self._secondary(row, column)
        if role == ROW_ROLE:
            return row
        if role == Qt.ItemDataRole.DecorationRole and column == STATUS:
            return self._dot(state)
        if role == Qt.ItemDataRole.ToolTipRole:
            return self._tooltip(row, column)
        if role == Qt.ItemDataRole.BackgroundRole:
            return QBrush(TINTS[state]) if state in TINTS else None
        if role == Qt.ItemDataRole.ForegroundRole and state is RowState.SKIPPED:
            return QBrush(DIMMED_TEXT)
        if role == Qt.ItemDataRole.TextAlignmentRole and column in (IN, OUT, DURATION, MAX_AVAIL):
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        return None

    def _text(self, row: ShotRow, column: int) -> str:
        """One cell, as text. A field the row does not have reads empty rather than a dash.

        An empty cell is how the list says "nothing here"; the status dot and the Issues
        dock are how it says why, and repeating the reason in every column of a row with
        no media would drown the columns that do have something to say.
        """
        media = row.media
        current = row.current
        texts: dict[int, Callable[[], str]] = {
            STATUS: lambda: "",
            SHOT: lambda: row.shot_code or row.clip_name,
            ELEM: lambda: row.identity.elem if row.identity else "",
            SOURCE: lambda: media.path.name if media else "",
            RES: lambda: f"{media.width}x{media.height}" if media else "",
            FPS: lambda: str(media.rate) if media else "",
            IN: lambda: self._frame_text(row, current.in_frame) if current else "",
            OUT: lambda: self._frame_text(row, current.out_frame) if current else "",
            DURATION: lambda: str(row.duration) if row.duration is not None else "",
            MAX_AVAIL: lambda: str(row.max_available_out) if row.max_available_out is not None else "",
            AUDIO: lambda: _audio(row),
            SIDE_FILES: lambda: _side_files(row),
            VERSION: lambda: _version(row),
            PROGRESS: lambda: _progress(row),
            NOTES: lambda: row.notes,
        }
        return texts[column]()

    def _frame_text(self, row: ShotRow, frame: int) -> str:
        """The primary representation of one frame, per the display mode."""
        if self._mode is DisplayMode.FRAMES:
            return str(frame)
        return frames.source_frame_to_timecode(frame, self._context(row))

    def _secondary(self, row: ShotRow, column: int) -> str:
        """The demoted representation: source TC under frames, the frame under either TC."""
        current = row.current
        if current is None:
            return ""
        frame = current.in_frame if column == IN else current.out_frame
        if self._mode is DisplayMode.FRAMES:
            return frames.source_frame_to_timecode(frame, self._context(row, DisplayMode.SOURCE_TC))
        return str(frame)

    def _context(self, row: ShotRow, mode: DisplayMode | None = None) -> frames.EditContext:
        turnover = next(
            (t for t in self._batch.turnovers if t.turnover_id == row.turnover_id), None
        )
        return row.edit_context(
            self._batch.project_rate,
            turnover.timeline_start if turnover else 0,
            (mode or self._mode).timecode_mode,
        )

    def _tooltip(self, row: ShotRow, column: int) -> str | None:
        """Only where the cell cannot hold the whole answer. Section 3 for the dot."""
        if column == STATUS:
            return "\n".join(f"{r.rule_id} {r.message}" for r in row.qc) or None
        if column == SHOT:
            return row.clip_name
        if column == SOURCE:
            return str(row.media.path) if row.media else None
        if column == AUDIO:
            return str(row.audio_path) if row.audio_path else None
        if column == SIDE_FILES:
            paths = [p for p in (row.side_files.hdri, row.side_files.camdata) if p]
            return "\n".join(str(path) for path in paths) or None
        if column == NOTES:
            return row.notes or None
        return None

    def _dot(self, state: RowState) -> QPixmap:
        """Section 3's status dot, drawn once per state and kept.

        Filled for everything the tool decided, hollow for what the editor did: a
        skipped row is not a state the run produced, it is one somebody chose.
        """
        hollow = state in HOLLOW_STATES
        key = (state, hollow)
        if key not in self._dots:
            pixmap = QPixmap(DOT_SIZE + 2, DOT_SIZE + 2)
            pixmap.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            color = DOT_COLORS[state]
            painter.setPen(color)
            painter.setBrush(Qt.BrushStyle.NoBrush if hollow else QBrush(color))
            painter.drawEllipse(1, 1, DOT_SIZE - 1, DOT_SIZE - 1)
            painter.end()
            self._dots[key] = pixmap
        return self._dots[key]
