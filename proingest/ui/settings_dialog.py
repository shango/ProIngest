"""The Settings page. UI_SPEC section 9, PRD FR-12.

A section list on the left and a form on the right, Apply and Cancel at the bottom,
which is the shape the spec asks for and the one the editor already knows from Resolve's
project settings. `ui/settings_form.py` says what the sections are; this draws them and
owns every widget.

**Nothing here reaches the batch.** The dialog hands back the two settings objects and
the window decides what to do with them, for the same reason the metadata pane never
writes to a row: one surface writing to the model is a rule worth keeping, and a
settings page that re-ran the checks itself would be a second one.

**A value that will not parse changes nothing**, rather than being corrected to
something plausible. That is UI_SPEC section 5's rule for the shot list's In and Out and
it is the right one here too: a resolution typed as `3840` is a person part way through
typing, not a person asking for a height of zero.
"""

from __future__ import annotations

import re
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from proingest.core import qc
from proingest.core.settings import AppSettings
from proingest.ui import settings_form

DIALOG_SIZE = (760, 520)
SECTION_LIST_WIDTH = 150

CHOOSE = "Choose..."
CHOOSE_TITLE = "Choose a folder"

RESOLUTION_PATTERN = re.compile(r"^\s*(\d+)\s*x\s*(\d+)\s*$", re.IGNORECASE)
"""`3840x2160`, with spaces allowed around the x. Anything else is not a resolution and
leaves the setting alone."""

LINES_HEIGHT = 96


class SettingsDialog(QDialog):
    """The page, opened modally over the window.

    `rules` comes in as whatever the open batch is being checked with, or the app's own
    defaults when no batch is open, and goes back out the same way. Which of the two the
    caller then writes to is the caller's business (`MainWindow.open_settings`).
    """

    def __init__(
        self, app: AppSettings, rules: qc.RuleSettings, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setObjectName("settings_dialog")
        self.setModal(True)
        self.resize(*DIALOG_SIZE)

        self._app = app
        self._rules = rules
        self._values = settings_form.to_values(app, rules)
        self._editors: dict[str, QWidget] = {}
        self._sections = settings_form.sections()

        self.list = QListWidget(self)
        self.list.setObjectName("settings_sections")
        self.list.setFixedWidth(SECTION_LIST_WIDTH)
        self.pages = QStackedWidget(self)
        for section in self._sections:
            self.list.addItem(section.title)
            self.pages.addWidget(self._page(section))
        self.list.currentRowChanged.connect(self.pages.setCurrentIndex)
        self.list.setCurrentRow(0)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Apply | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        apply = self.buttons.button(QDialogButtonBox.StandardButton.Apply)
        apply.setDefault(True)
        apply.clicked.connect(self.accept)
        self.buttons.rejected.connect(self.reject)

        columns = QHBoxLayout()
        columns.setContentsMargins(0, 0, 0, 0)
        columns.addWidget(self.list)
        columns.addWidget(self.pages, 1)

        layout = QVBoxLayout(self)
        layout.addLayout(columns, 1)
        layout.addWidget(self.buttons)

    # --- building -----------------------------------------------------------------

    def _page(self, section: settings_form.Section) -> QWidget:
        """One section's form, or its note alone when the section is not built yet."""
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(14, 12, 14, 12)
        if section.note:
            layout.addWidget(self._note(section.note))
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        for field in section.fields:
            form.addRow(field.label, self._editor(field))
            if field.help:
                form.addRow("", self._note(field.help))
        layout.addLayout(form)
        layout.addStretch(1)
        page.setEnabled(section.enabled)
        return page

    def _note(self, text: str) -> QLabel:
        label = QLabel(text, self)
        label.setObjectName("settings_note")
        label.setWordWrap(True)
        return label

    def _editor(self, field: settings_form.Field) -> QWidget:
        """The widget for one field, registered under its key so Apply can read it back."""
        value = self._values.get(field.key)
        widget: QWidget
        if field.kind == "int":
            spin = QSpinBox(self)
            spin.setRange(field.minimum, field.maximum)
            spin.setValue(int(value or 0))
            widget = spin
        elif field.kind == "bool":
            check = QCheckBox(self)
            check.setChecked(bool(value))
            widget = check
        elif field.kind == "resolution":
            width, height = value if value else (0, 0)
            edit = QLineEdit(f"{width}x{height}", self)
            widget = edit
        elif field.kind == "lines":
            block = QPlainTextEdit(self)
            block.setPlainText(_lines_of(dict(value or {})))
            block.setFixedHeight(LINES_HEIGHT)
            widget = block
        elif field.kind == "folder":
            widget = self._folder_editor(str(value or ""))
        elif field.kind == "readonly":
            widget = self._readonly(str(value or ""))
        else:
            widget = QLineEdit(str(value or ""), self)
        self._editors[field.key] = widget
        return widget

    def _folder_editor(self, current: str) -> QWidget:
        """A path and a chooser beside it. The path stays typable: a person who knows
        where it is should not have to walk a dialog to it."""
        row = QWidget(self)
        edit = QLineEdit(current, row)
        edit.setObjectName("settings_folder")
        button = QPushButton(CHOOSE, row)
        button.clicked.connect(lambda: self._choose_into(edit))
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(edit, 1)
        layout.addWidget(button)
        return row

    def _readonly(self, text: str) -> QWidget:
        """A value the tool states rather than takes. Selectable, because the reason to
        read it is usually to paste it into a message to the colourist."""
        label = QLabel(text, self)
        label.setObjectName("settings_readonly")
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        label.setWordWrap(True)
        return label

    def _choose_into(self, edit: QLineEdit) -> None:
        chosen = self.ask_folder(edit.text())
        if chosen:
            edit.setText(chosen)

    def ask_folder(self, start: str) -> str:
        """Overridden in tests, which cannot answer a native modal dialog."""
        return QFileDialog.getExistingDirectory(self, CHOOSE_TITLE, start)

    # --- reading back -------------------------------------------------------------

    def values(self) -> dict[str, Any]:
        """What the editors hold now, with anything unparseable simply absent.

        Absent rather than corrected, so `settings_form.apply_values` keeps what was
        already set: a half typed resolution changes nothing instead of becoming a
        number nobody asked for.
        """
        read: dict[str, Any] = {}
        for section in self._sections:
            if not section.enabled:
                continue
            for field in section.fields:
                widget = self._editors[field.key]
                value = _read(field, widget)
                if value is not None:
                    read[field.key] = value
        return read

    def result_settings(self) -> tuple[AppSettings, qc.RuleSettings]:
        """Apply the form and hand back both objects. The caller saves and re-checks."""
        rules = settings_form.apply_values(self._app, self.values(), self._rules)
        return self._app, rules


def _read(field: settings_form.Field, widget: QWidget) -> Any:
    """One editor's value, or None when it holds nothing this field can use."""
    if isinstance(widget, QSpinBox):
        return widget.value()
    if isinstance(widget, QCheckBox):
        return widget.isChecked()
    if isinstance(widget, QPlainTextEdit):
        return _map_of(widget.toPlainText())
    edit = widget if isinstance(widget, QLineEdit) else widget.findChild(QLineEdit)
    if edit is None:
        return None
    if field.kind == "resolution":
        matched = RESOLUTION_PATTERN.match(edit.text())
        return (int(matched.group(1)), int(matched.group(2))) if matched else None
    return edit.text().strip()


def _lines_of(mapping: dict[str, str]) -> str:
    return "\n".join(f"{key} = {value}" for key, value in sorted(mapping.items()))


def _map_of(text: str) -> dict[str, str]:
    """`from = to` per line. A line with no `=` is dropped rather than guessed at."""
    mapping: dict[str, str] = {}
    for line in text.splitlines():
        key, separator, value = line.partition("=")
        if separator and key.strip():
            mapping[key.strip()] = value.strip()
    return mapping
