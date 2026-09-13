"""The strip above the list: what a run is doing, and what it did.

UI_SPEC section 7.1. The strip has **three states and only ever one of them**: nothing
before a run, a thin bar and a line of words during one, the completion banner after.
They share a strip rather than stacking because a banner from the last run sitting above
the bar of this one is two answers to the same question, and the empty state is the
widget hidden rather than an empty page, so a window that has never run a batch gives
the list the height back.

**This widget knows nothing about a run.** It is told a percentage and a sentence; what
those say is `ui/runner.py`'s and the window's. Four surfaces report a run and the only
thing that keeps them agreeing is that all four read the same `RunProgress`.
"""

from __future__ import annotations

from typing import Literal

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QLabel, QProgressBar, QVBoxLayout, QWidget

BAR_HEIGHT = 4
"""A few pixels, no text and no percentage on it (section 7.1).

The same four pixels as the Progress column's per row bar, because they are the same
kind of answer at two scales and a batch bar twice the height of a row's would read as
the more precise of the two.
"""

LINK_COLOR = "#4d8fd6"
"""The accent, for the path in the banner, written into the anchor by `banner_text`.

Neither the theme nor a palette can say it. A Qt stylesheet cannot reach an anchor
inside a `QLabel`, so `#run_banner a` does nothing; the palette's `Link` role can, but
an application stylesheet overrides a palette set in code, and this window has one. What
is left is the style attribute, and without it the path renders in Qt's own `#0000ff` on
a `#1b1e23` band, which cannot be read at all. `theme.qss` lists the palette it is from.
"""

State = Literal["empty", "running", "done"]


class RunStrip(QWidget):
    """The batch's progress bar, the line saying what is happening, and the banner."""

    link_activated = Signal()
    """The banner's path was clicked. The window is what knows where it points."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("run_strip")

        self.bar = QProgressBar(self)
        self.bar.setObjectName("run_strip_bar")
        self.bar.setRange(0, 100)
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(BAR_HEIGHT)

        self.line = QLabel("", self)
        self.line.setObjectName("run_strip_line")

        self.running_side = QWidget(self)
        self.running_side.setObjectName("run_strip_progress")
        running_layout = QVBoxLayout(self.running_side)
        running_layout.setContentsMargins(0, 0, 0, 0)
        running_layout.setSpacing(0)
        running_layout.addWidget(self.bar)
        running_layout.addWidget(self.line)

        self.banner = QLabel("", self)
        self.banner.setObjectName("run_banner")
        self.banner.setTextFormat(Qt.TextFormat.RichText)
        self.banner.linkActivated.connect(lambda _href: self.link_activated.emit())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.running_side)
        layout.addWidget(self.banner)

        self.clear()

    @property
    def state(self) -> State:
        """Which of the three the strip is in. The invariant is that it is exactly one."""
        if not self.running_side.isHidden():
            return "running"
        if not self.banner.isHidden():
            return "done"
        return "empty"

    def clear(self) -> None:
        """Nothing: no run has happened, or the batch was swapped for another one."""
        self.running_side.setVisible(False)
        self.banner.setVisible(False)
        self.setVisible(False)

    def start(self) -> None:
        """A run is beginning. The bar goes back to nothing and the banner goes away."""
        self.bar.setValue(0)
        self.line.setText("")
        self.banner.setVisible(False)
        self.running_side.setVisible(True)
        self.setVisible(True)

    def set_percent(self, percent: int) -> None:
        self.bar.setValue(max(0, min(100, percent)))

    def say(self, text: str) -> None:
        """The line under the bar: one step, replaced in place, never a scrollback.

        Repainted immediately rather than on the next trip round the event loop,
        because two of the steps it names - planning the batch and writing the
        spreadsheets - run on the UI thread and block it. A line that waited would
        appear after the step it announces had already finished. Guarded on the text
        actually changing, so the five draws a second a run does cost nothing extra.
        """
        if text == self.line.text():
            return
        self.line.setText(text)
        self.line.repaint()

    def show_banner(self, text: str) -> None:
        """The run is over: section 7's banner, and the bar it replaces goes away."""
        self.banner.setText(text)
        self.running_side.setVisible(False)
        self.banner.setVisible(True)
        self.setVisible(True)
