"""Shared fixtures. Synthetic media is generated per test into tmp_path."""

from __future__ import annotations

import os
from collections.abc import Iterator
from typing import TYPE_CHECKING

import pytest

from tests.fixtures import media as media_fixtures

if TYPE_CHECKING:
    from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="session", autouse=True)
def _require_ffmpeg() -> None:
    """Core is testable headless, but the media tests genuinely need ffmpeg present."""
    if not media_fixtures.ffmpeg_available():
        pytest.skip("ffmpeg and ffprobe are required for media tests", allow_module_level=True)


@pytest.fixture(scope="session")
def qt_app() -> Iterator[QApplication]:
    """One QApplication for the whole session, drawing to nothing.

    Qt allows exactly one per process, so this is session scoped and every UI test
    takes it. The offscreen platform is set before Qt is asked for a window: CI has no
    display on either runner, and the alternative is a suite that only runs on a
    developer's desktop.
    """
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from proingest.ui import app as ui_app

    application = ui_app.build_application([])
    yield application
    application.quit()
