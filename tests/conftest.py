"""Shared fixtures. Synthetic media is generated per test into tmp_path."""

from __future__ import annotations

import pytest

from tests.fixtures import media as media_fixtures


@pytest.fixture(scope="session", autouse=True)
def _require_ffmpeg() -> None:
    """Core is testable headless, but the media tests genuinely need ffmpeg present."""
    if not media_fixtures.ffmpeg_available():
        pytest.skip("ffmpeg and ffprobe are required for media tests", allow_module_level=True)
