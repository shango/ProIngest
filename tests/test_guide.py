"""The user guide's prose. M9, and `docs/guide/`.

A document has no unit tests, and most of what is in one cannot have any: whether the
quickstart is clear is a person's job. Three things in it can drift silently, and those
are what is here.

- **An image reference that names a picture the harness does not take** leaves a broken
  image in a document that gets emailed around, and nothing says so until somebody opens
  it. `build/screenshots.py` already declares every picture it writes for this reason.
- **A shortcut the guide names that the window does not bind.** The guide is written for
  the Mac, where Qt draws `Ctrl` as Command, so the guide says `⌘R` where the code says
  `Ctrl+R`; they are the same key and the comparison has to go through `QKeySequence` to
  see that, which is also why this cannot be a grep.
- **A QC rule ID that has been retired.** Same rule and the same reason as the Settings
  page's help lines, which is where this check was first written.
- **The reference page's button table.** `ui/toolbar_help.py`'s own docstring says the guide
  reads it so the two cannot drift, and a markdown table cannot import a module: this is what
  makes that claim true. The sentences have to match **verbatim**, because a paraphrase in the
  guide is a second wording of the thing the module exists to keep single.
- **The two numbers on the install page that move on their own**: the dmg's version, which
  follows `proingest.__version__`, and the macOS floor, which follows `bundle.MINIMUM_MACOS`.
  Both are the kind of fact a reader acts on - looking for a filename, or deciding whether
  their machine is new enough - and neither announces that it has changed.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from PySide6.QtGui import QAction, QKeySequence, QShortcut
from PySide6.QtWidgets import QApplication

from build import bundle, screenshots
from proingest import __version__
from proingest.ui import toolbar_help
from proingest.ui.main_window import MainWindow

GUIDE_DIR = Path(__file__).resolve().parent.parent / "docs" / "guide"

PAGES = sorted(GUIDE_DIR.glob("*.md"))
"""Every page written so far. A glob rather than a list, so a page added later is
covered without anybody remembering to add it here."""

IMAGE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")
SHORTCUT = re.compile(r"⌘([A-Z.])")
RULE_ID = re.compile(r"\bQC-(\d{3})\b")
DMG = re.compile(r"ProIngest-([0-9.]+)\.dmg")
MACOS_FLOOR = re.compile(r"macOS (\d+(?:\.\d+)?) or later")
BUTTON_ROW = re.compile(r"^\| \*\*(.+?)\*\* \| (.+?) \|$", re.MULTILINE)
"""A row of the reference page's toolbar table: `| **Run** | Renders every ... |`."""

BUTTON_LABELS = {
    toolbar_help.NEW: "New",
    toolbar_help.OPEN: "Open...",
    toolbar_help.SAVE: "Save",
    toolbar_help.ADD_TURNOVER: "Add Turnover",
    toolbar_help.SCAN: "Scan",
    toolbar_help.RUN: "Run",
    toolbar_help.STOP: "Stop",
    toolbar_help.EXPORT: "Export",
    toolbar_help.SETTINGS: "Settings",
}
"""The label beside each key, which `toolbar_help.py` deliberately does not hold: it is the
wording that is shared with the guide, not the button text, and the window creates the labels.
Asserted against the window below, so this cannot be a third place they are written."""


def pages() -> list[Path]:
    assert PAGES, f"no guide pages under {GUIDE_DIR}"
    return PAGES


def text_of(page: Path) -> str:
    return page.read_text(encoding="utf-8")


@pytest.mark.parametrize("page", pages(), ids=lambda p: p.name)
class TestThePages:
    def test_every_picture_it_shows_is_one_the_harness_takes(self, page: Path) -> None:
        """Otherwise the guide ships with a broken image and nothing says so."""
        for target in IMAGE.findall(text_of(page)):
            assert target.startswith("images/"), target
            assert target.endswith(".png"), target
            assert Path(target).stem in screenshots.PICTURES, target

    def test_every_rule_id_it_names_is_live(self, page: Path) -> None:
        rules = (GUIDE_DIR.parent / "QC_RULES.md").read_text(encoding="utf-8")
        for number in RULE_ID.findall(text_of(page)):
            assert f"QC-{number}" in rules, number

    def test_any_dmg_it_names_is_the_version_that_is_built(self, page: Path) -> None:
        """The filename is what somebody looks for in a folder, so a stale one sends them
        looking for a file that is not there."""
        for named in DMG.findall(text_of(page)):
            assert named == __version__, named

    def test_any_macos_floor_it_names_is_the_one_the_bundle_sets(self, page: Path) -> None:
        """`LSMinimumSystemVersion` is what actually refuses to launch, so the guide has to
        agree with it: too low reads as a broken app, too high turns somebody away."""
        for named in MACOS_FLOOR.findall(text_of(page)):
            assert named == bundle.MINIMUM_MACOS.removesuffix(".0"), named

    def test_it_has_no_em_dashes(self, page: Path) -> None:
        """CLAUDE.md, and the guide is the document most likely to be pasted elsewhere."""
        assert "\u2014" not in text_of(page)


def test_the_button_table_is_the_tooltips_word_for_word() -> None:
    """`ui/toolbar_help.py` says the guide reads it. A markdown table cannot, so this does.

    Verbatim rather than "mentions", because a paraphrase in the guide is exactly the second
    wording that module is apart from the window to prevent.
    """
    page = GUIDE_DIR / "reference.md"
    rows = dict(BUTTON_ROW.findall(text_of(page)))
    expected = {BUTTON_LABELS[key]: sentence for key, sentence in toolbar_help.WHAT_IT_DOES.items()}
    assert {label: rows.get(label) for label in expected} == expected


def test_the_labels_that_table_uses_are_the_windows_own(qt_app: QApplication, tmp_path: Path) -> None:
    """Otherwise `BUTTON_LABELS` above is a third place the button text is written down."""
    window = MainWindow(tmp_path / "settings.json")
    try:
        drawn = {action.text() for _key, action in window._toolbar_help}
    finally:
        window.log_view.detach()
        window.close()
    assert set(BUTTON_LABELS.values()) <= drawn


def test_every_shortcut_the_guide_names_is_one_the_window_binds(qt_app: QApplication, tmp_path: Path) -> None:
    """Written as the Mac draws them and compared as Qt spells them portably.

    A window rather than a list of strings, because the point is that the guide agrees
    with the actions the window actually creates: a shortcut moved in `_build_actions`
    is exactly the drift a guide cannot notice on its own.

    `QShortcut` as well as `QAction`, because not every key in the window is a toolbar
    button: the Log tab's copy is a shortcut on the tree itself, which is how it stays a
    copy of the selection rather than of whatever the window thinks is current.
    """
    window = MainWindow(tmp_path / "settings.json")
    try:
        # An action calls it `shortcut` and a QShortcut calls it `key`, which is the
        # only reason this is not one comprehension.
        keys = [action.shortcut() for action in window.findChildren(QAction)]
        keys += [shortcut.key() for shortcut in window.findChildren(QShortcut)]
        bound = {key.toString() for key in keys if not key.isEmpty()}
    finally:
        window.log_view.detach()
        window.close()

    named = {key for page in pages() for key in SHORTCUT.findall(text_of(page))}
    assert named, "the guide names no shortcuts at all, which means the pattern stopped matching"
    for key in sorted(named):
        assert QKeySequence(f"Ctrl+{key}").toString() in bound, key
