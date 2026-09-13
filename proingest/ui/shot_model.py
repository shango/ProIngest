"""The shot list's model: a batch presented as turnovers with their rows beneath.

UI_SPEC section 2 is the column list and section 3 the row colouring. Both live here
rather than in the view, because what a cell says is a fact about the batch and what it
looks like is one colour per state: a delegate that had to work either out would be
reading the model twice.

Editing (M5.3) is here too, because the cell that writes has to write to the row the
cell that reads read. Four columns are editable (FR-5) and `core/frames.py` is the input
grammar behind In and Out.

**A commit re-runs the row's rules and nothing else.** `qc.apply_row_rules` is per row
and cheap, which is what UI_SPEC section 5 asks for, and the only batch level input the
row rules take is the clip name counts QC-011 needs - which no editable cell can change,
since `clip_name` is the name the turnover arrived with and is not one of the four. The
rules that read the disk belong to pre-flight and to the run, and neither is a
keystroke's job.

Two levels and no more: a turnover, then its rows in timeline order. Sorting is fixed
(section 2), so there is no sort implementation to get wrong, and the search box filters
through a proxy rather than by rebuilding the model.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any

from PySide6.QtCore import (
    QAbstractItemModel,
    QModelIndex,
    QObject,
    QPersistentModelIndex,
    Qt,
    Signal,
)
from PySide6.QtGui import QBrush, QColor, QPainter, QPixmap

from proingest.core import frames, qc
from proingest.core.models import Batch, InOut, ShotRow, Turnover

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

EDITABLE_COLUMNS = (SHOT, IN, OUT, NOTES)
"""The cells the list owns and nothing else does (FR-5), in Tab order.

Everything else in the row is either read off the media, derived from these, or written
by a run. A tuple rather than a set because section 4 tabs through them in this order,
and there are four of them.
"""

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

    row_edited = Signal(object)
    """One `ShotRow`, after a commit changed it. What autosave listens to.

    The row rather than the index, because what is saved is the batch and what the
    listener wants to know is which row moved, not where it was on screen.
    """

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._batch = Batch()
        self._rows: dict[str, list[ShotRow]] = {}
        self._mode = DisplayMode.FRAMES
        self._dots: dict[tuple[RowState, bool], QPixmap] = {}
        self._rules = qc.DEFAULT_SETTINGS
        self._name_counts: dict[str, int] = {}

    # --- what it is showing ----------------------------------------------------------

    def set_batch(self, batch: Batch) -> None:
        """Show a different batch. A whole reset, because everything changed."""
        self.beginResetModel()
        self._batch = batch
        self._rows = {t.turnover_id: batch.rows_for(t.turnover_id) for t in batch.turnovers}
        self._rules = qc.settings_for(batch)
        self._name_counts = qc.clip_name_counts(batch)
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

    def index_for_row(self, row: ShotRow) -> QModelIndex:
        """Where a `ShotRow` sits, for anything holding a row and wanting the cell.

        Identity rather than equality, because two rows of a turnover can be equal in
        every field that is set before a scan finishes and only one of them is the one
        the Issues dock was talking about.
        """
        for position, turnover in enumerate(self._batch.turnovers):
            rows = self._rows[turnover.turnover_id]
            for offset, candidate in enumerate(rows):
                if candidate is row:
                    return self.index(offset, 0, self.index(position, 0, NO_PARENT))
        return QModelIndex()

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
        if role == Qt.ItemDataRole.EditRole:
            return self._edit_text(row, column)
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

    def _edit_text(self, row: ShotRow, column: int) -> str | None:
        """What an editor opens on, which is the displayed value with one exception.

        Shot opens on the shot code alone, never on the clip name the cell falls back to
        when there is no identity: an editor prefilled with the clip name commits the
        clip name as an override the moment somebody presses Enter on it.
        """
        if column == SHOT:
            return row.shot_code or ""
        if column in (IN, OUT, NOTES):
            return self._text(row, column)
        return None

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

    # --- what a cell can be changed to ------------------------------------------------

    def flags(self, index: ModelIndex) -> Qt.ItemFlag:
        """Section 2's four editable columns, on shot rows that have something to edit.

        In and Out are not editable on a row with no range at all: a row whose media was
        never found has nothing for a typed offset to be relative to, and QC-020 is
        already saying so.
        """
        base = super().flags(index)
        row = self.row_at(index)
        if row is None or index.column() not in EDITABLE_COLUMNS:
            return base
        if index.column() in (IN, OUT) and row.current is None:
            return base
        return base | Qt.ItemFlag.ItemIsEditable

    def parse_frame(self, index: ModelIndex, text: str) -> frames.ParsedInput:
        """Read a typed In or Out against this row, by UI_SPEC section 5's grammar.

        Public because the cell shows its error inline while the editor is still open
        (section 5) and the commit has to reach the same answer: a second parser is how
        a cell comes to reject what it has just shown as valid.
        """
        row = self.row_at(index)
        current = row.current if row else None
        if row is None or current is None:
            return frames.ParsedInput(None, "no range to edit")
        held = current.in_frame if index.column() == IN else current.out_frame
        return frames.parse_in_out(text, held, self._context(row))

    def setData(self, index: ModelIndex, value: Any, role: int = Qt.ItemDataRole.EditRole) -> bool:
        """Commit one cell. False means nothing was written and the cell keeps what it had.

        An unparseable In or Out is the ordinary case of False here, and it is not an
        error the model reports anywhere: the editor has already shown it inline, and a
        QC result for a value that was never stored would outlive the typing that caused it.
        """
        if role != Qt.ItemDataRole.EditRole:
            return False
        row = self.row_at(index)
        if row is None or index.column() not in EDITABLE_COLUMNS:
            return False
        text = str(value)
        if index.column() == SHOT:
            changed = self._set_shot_code(row, text)
        elif index.column() == NOTES:
            changed = self._set_notes(row, text)
        else:
            changed = self._set_frame(row, index, text)
        if changed:
            self._committed(row, index)
        return changed

    def set_skipped(self, index: ModelIndex, skipped: bool, reason: str | None = None) -> bool:
        """Ctrl+K (section 4). The reason is asked for by the view, which owns the prompt.

        Un-skipping keeps the reason rather than clearing it, so a row toggled off and on
        again is not a second interrogation about a decision already explained.
        """
        row = self.row_at(index)
        if row is None or row.skipped == skipped:
            return False
        row.skipped = skipped
        if skipped:
            row.skip_reason = reason or row.skip_reason
        self._committed(row, index)
        return True

    def _set_shot_code(self, row: ShotRow, text: str) -> bool:
        """An override, or none at all when the cell is emptied.

        Emptying it puts the parsed code back rather than leaving the row nameless: the
        override is a correction of what `naming.parse_clip_name` read, and withdrawing a
        correction means the original stands.
        """
        override = text.strip() or None
        if override == row.shot_code_override:
            return False
        row.shot_code_override = override
        return True

    def _set_notes(self, row: ShotRow, text: str) -> bool:
        if text == row.notes:
            return False
        row.notes = text
        return True

    def _set_frame(self, row: ShotRow, index: ModelIndex, text: str) -> bool:
        """In or Out, through section 5's grammar.

        A range the media cannot satisfy is stored and then reported, not refused:
        QC-031 and QC-032 are what say so, they say it about the row rather than about
        the keystroke, and an editor who types Out before In on the way to a valid range
        should not be stopped halfway.
        """
        parsed = self.parse_frame(index, text)
        current = row.current
        if parsed.frame is None or current is None:
            return False
        moved = (
            InOut(parsed.frame, current.out_frame)
            if index.column() == IN
            else InOut(current.in_frame, parsed.frame)
        )
        if moved == current:
            return False
        row.current = moved
        return True

    def _committed(self, row: ShotRow, index: ModelIndex) -> None:
        """Re-run the row's rules, repaint what could have changed, and say so.

        The whole row repaints rather than the one cell, because an In moves Duration,
        Max Avail, the dot and the tint; and the turnover header with it, since its
        summary counts the errors and warnings that just changed.
        """
        qc.apply_row_rules(row, self._batch.project_rate, self._rules, self._name_counts)
        parent = index.parent()
        self.dataChanged.emit(
            self.index(index.row(), 0, parent), self.index(index.row(), len(COLUMNS) - 1, parent)
        )
        if parent.isValid():
            self.dataChanged.emit(parent, parent)
        self.row_edited.emit(row)
