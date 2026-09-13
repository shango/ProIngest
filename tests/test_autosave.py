"""Autosave. `ui/autosave.py`, M5.3.

UI_SPEC section 5 ends a commit with "autosave fires". What can be asserted without
waiting out the debounce is what it writes, when it decides there is nothing to write,
and what it does with a batch that has no file yet.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from proingest.core import batchfile
from proingest.ui.autosave import DELAY_MS, AutoSaver
from tests.fixtures.batches import batch, row


@pytest.fixture
def saver(qt_app: QApplication) -> AutoSaver:
    return AutoSaver()


def test_a_scheduled_edit_is_written_on_flush(saver: AutoSaver, tmp_path: Path) -> None:
    path = tmp_path / "melt.pibatch"
    saver.watch(batch(row()), path)
    saver.schedule()
    saver.flush()
    assert batchfile.load(path, reconcile=False).rows[0].clip_name == "MELT0001_pl01"


def test_it_waits_rather_than_writing_per_keystroke(saver: AutoSaver, tmp_path: Path) -> None:
    """Tabbing along a row is four commits in a second and a batch file is the whole batch."""
    saver.watch(batch(row()), tmp_path / "melt.pibatch")
    saver.schedule()
    assert saver.pending
    assert not (tmp_path / "melt.pibatch").exists()


def test_the_wait_is_restarted_rather_than_queued(saver: AutoSaver, tmp_path: Path) -> None:
    saver.watch(batch(row()), tmp_path / "melt.pibatch")
    saver.schedule()
    saver.schedule()
    saver.flush()
    assert not saver.pending
    assert DELAY_MS > 0


def test_the_timer_is_what_calls_flush(saver: AutoSaver, tmp_path: Path) -> None:
    """The signal rather than a real wait: the connection is the thing under test, and
    a test that sat out the debounce would cost the suite a second and a half."""
    path = tmp_path / "melt.pibatch"
    saver.watch(batch(row()), path)
    saver.schedule()
    saver._timer.timeout.emit()
    assert path.exists()


def test_flushing_with_nothing_pending_writes_nothing(saver: AutoSaver, tmp_path: Path) -> None:
    path = tmp_path / "melt.pibatch"
    saver.watch(batch(row()), path)
    saver.flush()
    assert not path.exists()


def test_a_batch_with_no_file_yet_keeps_its_edits_pending(saver: AutoSaver) -> None:
    """New and Open are M5.4. Until one of them names a file there is nowhere to write."""
    saver.watch(batch(row()), None)
    saver.schedule()
    saver.flush()
    assert saver.pending


def test_and_writes_them_as_soon_as_there_is_somewhere_to_write(
    saver: AutoSaver, tmp_path: Path
) -> None:
    held = batch(row())
    saver.watch(held, None)
    saver.schedule()
    saver.watch(held, tmp_path / "melt.pibatch")
    saver.schedule()
    saver.flush()
    assert (tmp_path / "melt.pibatch").exists()


def test_changing_batch_writes_what_the_last_one_still_owed(
    saver: AutoSaver, tmp_path: Path
) -> None:
    """Closing one batch to open another is not a way to lose the last edit made to it."""
    first = tmp_path / "first.pibatch"
    saver.watch(batch(row(), name="first"), first)
    saver.schedule()
    saver.watch(batch(row(), name="second"), tmp_path / "second.pibatch")
    assert batchfile.load(first, reconcile=False).name == "first"
    assert not saver.pending


def test_a_write_that_fails_keeps_the_edits_rather_than_raising(
    saver: AutoSaver, tmp_path: Path
) -> None:
    """A batch on a network mount that blinked is not a reason to lose the window."""
    blocked = tmp_path / "file.txt"
    blocked.write_text("not a folder")
    saver.watch(batch(row()), blocked / "melt.pibatch")
    saver.schedule()
    saver.flush()
    assert saver.pending


def test_it_says_what_it_wrote(saver: AutoSaver, tmp_path: Path) -> None:
    written: list[object] = []
    saver.saved.connect(written.append)
    saver.watch(batch(row()), tmp_path / "melt.pibatch")
    saver.schedule()
    saver.flush()
    assert written == [tmp_path / "melt.pibatch"]
