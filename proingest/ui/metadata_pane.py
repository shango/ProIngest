"""The reading surface beside the list. UI_SPEC sections 1 and 12.

What it shows is `ui/metadata.py`'s answer; this draws it. The division matters more
here than it looks: the pane is rebuilt from scratch whenever its answer changes, which
is only safe because working the answer out is cheap and comparing two of them is exact.

**Three properties are structural rather than cosmetic.**

- **It never writes.** The list owns every edit (FR-5), and a second editable surface
  for the same fields is two code paths writing one model and two places for validation
  to disagree. Nothing here takes a `Batch` and nothing here has a setter.
- **It never takes focus.** Tab belongs to the row's four editable cells (section 4), so
  every widget in here is `NoFocus` and the pane is reachable by mouse and by Ctrl+I.
  That is also why a path is elided for reading and copied by a button rather than by
  selecting text: selecting elided text copies the ellipsis.
- **It follows three signals, not one.** A pane listening to the selection alone shows a
  stale value the moment a cell is committed or a run finishes, and a stale value looks
  like a wrong one rather than a late one. `MainWindow` wires all three; this widget
  just redraws when it is told to, and does nothing when the answer has not moved.
"""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFontMetrics, QGuiApplication, QResizeEvent
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from proingest.ui.metadata import NO_SELECTION, Field, Section, as_text

COPY_ALL = "Copy all"
COPY = "Copy"

OPEN_ARROW = "▾"
SHUT_ARROW = "▸"
"""The disclosure triangles, as text rather than an icon.

Two characters against a theme that ships no icon set at all, and they read the same at
2x as at 1x, which a hand drawn 12 pixel triangle does not.
"""

LABEL_COLUMN = 0
VALUE_COLUMN = 1
COPY_COLUMN = 2


class ElidedLabel(QLabel):
    """One line, shortened to fit, with the whole value in the tooltip.

    **Every value in the pane is one of these**, and that is structural rather than
    cosmetic. A wrapping `QLabel` reports a one line minimum height whatever it will
    actually need, so a column of them inside a scroll area gives the scroll area a
    minimum that is far too small: the sections are then squashed to fit the viewport
    instead of scrolling, and the text of one overlaps the next. One line per field
    makes every height exact. It also stops a single unbreakable 40 character value
    from setting the pane's minimum width, which is what `Ignored` is for below.

    **What is given up is reading a long message in the pane**, which is why the Issues
    dock sits under the list carrying the full text of every one, and why a rule ID here
    clicks straight through to it.

    Paths elide in the **middle** (section 12.1): the filename identifies the file and
    the middle of a Drive path is the least informative part of it. Everything else
    elides at the end, where a sentence loses least.
    """

    def __init__(
        self,
        text: str,
        mode: Qt.TextElideMode = Qt.TextElideMode.ElideRight,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._full = text
        self._mode = mode
        self.setToolTip(text)
        self.setMinimumWidth(1)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        # Selectable, and then put back to `NoFocus`: `setTextInteractionFlags` gives a
        # label click focus of its own, and section 12.1 says the pane never takes focus.
        # Selecting with the mouse does not need it; only a keyboard caret would.
        self.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._elide()

    @property
    def full_text(self) -> str:
        """What Copy puts on the clipboard: the value, never the elision of it."""
        return self._full

    def _elide(self) -> None:
        metrics = QFontMetrics(self.font())
        width = max(1, self.width())
        super().setText(metrics.elidedText(self._full, self._mode, width))

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._elide()


class SectionBox(QWidget):
    """One collapsible group: a header that toggles it, and a grid of label and value."""

    toggled = Signal(str, bool)
    link_clicked = Signal(str)
    copy_requested = Signal(str)

    def __init__(self, title: str, fields: Sequence[Field], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.title = title
        self.setObjectName("metadata_section")

        # A flat `QPushButton` rather than a `QToolButton`: a tool button centres its
        # text and no stylesheet rule moves it, and a section title centred over a column
        # of left aligned labels reads as a heading for the window rather than for the
        # six lines under it.
        self.header = QPushButton(self)
        self.header.setObjectName("metadata_section_header")
        self.header.setFlat(True)
        self.header.setCheckable(True)
        self.header.setChecked(True)
        self.header.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.header.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.header.toggled.connect(self._header_toggled)

        self.body = QWidget(self)
        self.body.setObjectName("metadata_section_body")
        grid = QGridLayout(self.body)
        grid.setContentsMargins(10, 4, 8, 8)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(3)
        grid.setColumnStretch(VALUE_COLUMN, 1)
        for position, item in enumerate(fields):
            self._add_field(grid, position, item)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.header)
        layout.addWidget(self.body)
        self._say_title()

    def _add_field(self, grid: QGridLayout, position: int, item: Field) -> None:
        label = QLabel(item.label, self.body)
        label.setObjectName("metadata_label")
        if item.rule_id is not None:
            # The rule ID is the click through to the Issues dock (section 12.2). A link
            # rather than a button because it is one word inside a column of words, and a
            # button there would read as something that changes the batch.
            label.setText(f'<a href="{item.rule_id}">{item.label}</a>')
            label.setTextFormat(Qt.TextFormat.RichText)
            label.linkActivated.connect(self.link_clicked.emit)
        grid.addWidget(label, position, LABEL_COLUMN, Qt.AlignmentFlag.AlignTop)

        mode = Qt.TextElideMode.ElideMiddle if item.is_path else Qt.TextElideMode.ElideRight
        value = ElidedLabel(item.value, mode, self.body)
        value.setObjectName("metadata_value")
        grid.addWidget(value, position, VALUE_COLUMN)

        if not item.is_path:
            return

        # A copy button on paths only (section 12.1). Every value is selectable, and a
        # value short enough to fit is not elided at all, so selecting it gives the exact
        # text; a path is the one kind that is always too long for the pane, so selecting
        # it would copy the ellipsis and the button is the only honest way to get it.
        button = QPushButton(COPY, self.body)
        button.setObjectName("metadata_copy")
        button.setFlat(True)
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        button.setToolTip(f"Copy {item.label}")
        button.clicked.connect(lambda _checked=False, text=item.value: self.copy_requested.emit(text))
        grid.addWidget(button, position, COPY_COLUMN, Qt.AlignmentFlag.AlignTop)

    @property
    def is_open(self) -> bool:
        return self.header.isChecked()

    def set_open(self, opened: bool) -> None:
        self.header.setChecked(opened)

    def _header_toggled(self, opened: bool) -> None:
        self.body.setVisible(opened)
        self._say_title()
        self.toggled.emit(self.title, opened)

    def _say_title(self) -> None:
        arrow = OPEN_ARROW if self.is_open else SHUT_ARROW
        self.header.setText(f"{arrow}  {self.title}")


class MetadataPane(QWidget):
    """Everything known about the selection, read only (FR-14, UI_SPEC section 12)."""

    issue_clicked = Signal(str)
    """A rule ID whose line was clicked. The window brings the Issues dock forward."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("metadata_pane")
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self.summary = QLabel("", self)
        self.summary.setObjectName("metadata_summary")
        self.summary.setVisible(False)

        self.copy_all = QPushButton(COPY_ALL, self)
        self.copy_all.setObjectName("metadata_copy_all")
        self.copy_all.setFlat(True)
        self.copy_all.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.copy_all.setVisible(False)
        self.copy_all.clicked.connect(self._copy_all)

        self.placeholder = QLabel(NO_SELECTION, self)
        self.placeholder.setObjectName("metadata_placeholder")
        self.placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.placeholder.setWordWrap(True)

        self.holder = QWidget(self)
        self._holder_layout = QVBoxLayout(self.holder)
        self._holder_layout.setContentsMargins(0, 0, 0, 0)
        self._holder_layout.setSpacing(0)
        self._holder_layout.addStretch(1)

        self.scroll_area = QScrollArea(self)
        self.scroll_area.setObjectName("metadata_scroll")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.scroll_area.setFrameShape(QScrollArea.Shape.NoFrame)
        self.scroll_area.setWidget(self.holder)
        self.scroll_area.setVisible(False)

        self.top = QWidget(self)
        self.top.setObjectName("metadata_top")
        top_layout = QHBoxLayout(self.top)
        top_layout.setContentsMargins(10, 4, 6, 4)
        top_layout.setSpacing(6)
        top_layout.addWidget(self.summary)
        top_layout.addStretch(1)
        top_layout.addWidget(self.copy_all)
        self.top.setVisible(False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.top)
        layout.addWidget(self.placeholder, 1)
        layout.addWidget(self.scroll_area, 1)

        self._sections: list[Section] = []
        self._summary_text = ""
        self._shut: set[str] = set()
        self._boxes: list[SectionBox] = []

    # --- what it is showing ------------------------------------------------------------

    @property
    def sections(self) -> list[Section]:
        """What is on screen. The window compares against it rather than tracking state."""
        return list(self._sections)

    def show_sections(self, sections: Sequence[Section], summary: str = "") -> bool:
        """Draw these, and say whether anything was redrawn.

        **Redrawn only when the answer moved**, which is what lets the window wire this
        to every signal that can change a value without thinking about how often they
        fire. Rebuilding is destroying and rebuilding a few dozen widgets; comparing is
        comparing two lists of frozen dataclasses.
        """
        if list(sections) == self._sections and summary == self._summary_text:
            return False
        self._sections = list(sections)
        self._summary_text = summary
        self._rebuild()
        return True

    def clear(self) -> None:
        """Nothing selected: section 12.3's sentence rather than a blank panel."""
        self.show_sections([], "")

    def _rebuild(self) -> None:
        for box in self._boxes:
            box.setParent(None)
            box.deleteLater()
        self._boxes = []

        has_content = bool(self._sections)
        self.placeholder.setVisible(not has_content)
        self.scroll_area.setVisible(has_content)
        self.top.setVisible(has_content)
        self.copy_all.setVisible(has_content)
        self.summary.setText(self._summary_text)
        self.summary.setVisible(bool(self._summary_text))

        for position, section in enumerate(self._sections):
            box = SectionBox(section.title, section.fields, self.holder)
            box.set_open(section.title not in self._shut)
            box.toggled.connect(self._remember_toggle)
            box.link_clicked.connect(self.issue_clicked.emit)
            box.copy_requested.connect(self.copy)
            self._holder_layout.insertWidget(position, box)
            self._boxes.append(box)

    # --- what it remembers -------------------------------------------------------------

    @property
    def collapsed(self) -> list[str]:
        """Titles of the sections the editor has shut, for the window to remember.

        The shut ones rather than the open ones, so a section added by a later chunk
        arrives open: a new field list that nobody can see is worse than one nobody
        asked for.
        """
        return sorted(self._shut)

    def set_collapsed(self, titles: Sequence[str]) -> None:
        self._shut = set(titles)
        for box in self._boxes:
            box.set_open(box.title not in self._shut)

    def _remember_toggle(self, title: str, opened: bool) -> None:
        self._shut.discard(title) if opened else self._shut.add(title)

    # --- copying -----------------------------------------------------------------------

    def copy(self, text: str) -> None:
        """Its own method so a test can assert what was copied without a clipboard."""
        clipboard = QGuiApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(text)

    def _copy_all(self) -> None:
        self.copy(as_text(self._sections))
