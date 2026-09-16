"""The user guide's screenshot harness. `build/screenshots.py`, M9.4.

The guide is illustrated by running that script, which means a broken script is a guide
full of broken images and nobody finds out until somebody reads it. What is asserted
here is the part a person cannot check by eye on a machine with no display: that every
picture the guide references is taken, and that none of them come back blank.

Whether they *look* right is a person's job on a Mac, which is also where the set that
ships is taken (docs/MAC_SESSION.md).
"""

from __future__ import annotations

import os
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

from build import screenshots
from proingest.ui.main_window import MainWindow


@pytest.fixture
def window(qt_app: QApplication, tmp_path: Path) -> Iterator[MainWindow]:
    """A window with a settings file of its own, never the user's.

    Detached from the root logger afterwards: every window installs a handler there,
    and one left behind formats every later log line into it.
    """
    built = MainWindow(tmp_path / "settings.json")
    built.resize(*screenshots.WINDOW_SIZE)
    built.show()
    screenshots.settle(qt_app)
    yield built
    built.log_view.detach()
    built.close()


def blank_like(image: QImage) -> QImage:
    """One flat colour, taken from the image's own top left corner."""
    empty = QImage(image.size(), image.format())
    empty.fill(image.pixelColor(0, 0))
    return empty


class TestTheScenes:
    def test_it_takes_every_picture_the_guide_references(
        self, window: MainWindow, qt_app: QApplication, tmp_path: Path
    ) -> None:
        taken = [name for name, _ in screenshots.scenes(window, tmp_path)]
        assert taken == list(screenshots.PICTURES)

    def test_none_of_them_come_back_blank(
        self, window: MainWindow, qt_app: QApplication, tmp_path: Path
    ) -> None:
        """The failure this exists for: a widget grabbed before Qt has laid it out, or
        a dock that is hidden when its own picture is taken, comes back as a rectangle
        of one colour and the script still reports success."""
        for name, widget in screenshots.scenes(window, tmp_path):
            screenshots.settle(qt_app)
            image = widget.grab().toImage()
            assert not image.isNull(), name
            assert image != blank_like(image), name

    def test_the_pictures_land_on_disk_as_png(
        self, window: MainWindow, qt_app: QApplication, tmp_path: Path
    ) -> None:
        out = tmp_path / "images"
        out.mkdir()
        for name, widget in screenshots.scenes(window, tmp_path):
            screenshots.settle(qt_app)
            screenshots.take(widget, out / f"{name}.png")
        written = sorted(path.name for path in out.iterdir())
        assert written == sorted(f"{name}.png" for name in screenshots.PICTURES)
        assert all(QImage(str(path)).width() > 0 for path in out.iterdir())


class TestTheDemoBatch:
    def test_it_is_the_synthetic_show_and_names_nobody_real(self, tmp_path: Path) -> None:
        """The pictures go into a document that gets emailed around, so the batch in
        them is the fixtures' MELT show rather than anything from a real turnover."""
        built = screenshots.demo_batch(tmp_path)
        assert {row.clip_name.split("_")[0][:4] for row in built.rows} == {"MELT"}

    def test_it_shows_more_than_one_row_state(self, tmp_path: Path) -> None:
        """A list where every row is grey is a picture of nothing in particular."""
        from proingest.ui.shot_model import row_state

        assert len({row_state(row) for row in screenshots.demo_batch(tmp_path).rows}) >= 4


class TestChoosingThePlatform:
    def test_it_leaves_a_mac_on_its_own_plugin(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The offscreen plugin draws with Qt's own style and font fallbacks, so forcing
        it on a Mac would produce pictures of a tool the editor does not have."""
        monkeypatch.setattr(sys, "platform", "darwin")
        monkeypatch.delenv("QT_QPA_PLATFORM", raising=False)
        assert screenshots.choose_platform() == "cocoa"
        assert "QT_QPA_PLATFORM" not in os.environ

    def test_everywhere_else_has_nothing_to_draw_to(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.delenv("QT_QPA_PLATFORM", raising=False)
        assert screenshots.choose_platform() == "offscreen"

    def test_it_never_overrides_what_the_caller_asked_for(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.setenv("QT_QPA_PLATFORM", "xcb")
        assert screenshots.choose_platform() == "xcb"
