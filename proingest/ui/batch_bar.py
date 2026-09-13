"""The bar above the list: what this batch is, and the two controls that drive the list.

UI_SPEC section 1. The bar also carries the delivery root, which is click to change and
arrives with the batch lifecycle in M5.4; there is nothing to point it at until a batch
can be opened.

The In/Out toggle is three buttons rather than a drop-down because it has three states
and section 2 draws it as `[Frames|Source TC|Record TC]`: all three legible at once is
the point of it, and a drop-down hides two thirds of a control the editor is meant to
read at a glance.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QWidget,
)

from proingest.ui.shot_model import DisplayMode

SEARCH_PLACEHOLDER = "Search shot code"


class BatchBar(QWidget):
    """Batch name, the In/Out display toggle and the search box."""

    display_mode_picked = Signal(object)
    search_changed = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("batch_bar")

        self.name_label = QLabel("", self)
        self.name_label.setObjectName("batch_name")

        self.search = QLineEdit(self)
        self.search.setObjectName("batch_search")
        self.search.setPlaceholderText(SEARCH_PLACEHOLDER)
        self.search.setClearButtonEnabled(True)
        self.search.setMaximumWidth(260)
        self.search.textChanged.connect(self.search_changed.emit)

        self.mode_buttons = QButtonGroup(self)
        self.mode_buttons.setExclusive(True)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(8)
        layout.addWidget(self.name_label)
        layout.addStretch(1)
        for mode in DisplayMode:
            button = QPushButton(mode.value, self)
            button.setCheckable(True)
            button.setProperty("display_mode", mode.name)
            button.setChecked(mode is DisplayMode.FRAMES)
            button.clicked.connect(lambda _checked=False, m=mode: self.display_mode_picked.emit(m))
            self.mode_buttons.addButton(button)
            layout.addWidget(button)
        layout.addSpacing(12)
        layout.addWidget(self.search)

    def set_batch_name(self, name: str) -> None:
        self.name_label.setText(name)

    def show_display_mode(self, mode: DisplayMode) -> None:
        """Follow the model, so Ctrl+T and the buttons cannot end up disagreeing."""
        for button in self.mode_buttons.buttons():
            button.setChecked(button.property("display_mode") == mode.name)

    def focus_search(self) -> None:
        """Ctrl+F. Selects what is there so typing replaces the last search."""
        self.search.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self.search.selectAll()
