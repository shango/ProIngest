"""The log file and the bridge out of a worker process. `core/logsetup.py`, M5.8.1.

Two things here are worth more than the rest. The first is that a rotated file is still
deleted after `BACKUP_COUNT` of them: the handler finds old files by matching a date
pattern against their names, and a custom `namer` that does not agree with that pattern
breaks pruning **silently** - rotation keeps working and the folder grows forever.

The second is that an ffmpeg command line logged inside a spawned render worker arrives
in the parent. That is FR-13's actual requirement, and before M5.8 it was false: a
spawned process has no handlers, so `logging.lastResort` dropped every INFO line the
worker made.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from pathlib import Path

import pytest

from proingest.core import logsetup, render
from tests.fixtures import media as fixtures
from tests.test_render import raw_job, ref_job


@pytest.fixture
def quiet_root() -> Iterator[None]:
    """Put the root logger back after a test has reconfigured it.

    `configure` only removes its own handlers, so a test runner's stay put; the level is
    the one thing a test does change for everybody.
    """
    level = logging.getLogger().level
    yield
    # No folder and no stream: this module's handlers come off and none go back on.
    logsetup.configure(stream=False, level=level)


class Captured(logging.Handler):
    """Every record the root logger handled, kept as records rather than as text."""

    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


class TestConfigure:
    def test_a_line_reaches_the_file(self, tmp_path: Path, quiet_root: None) -> None:
        logsetup.configure(tmp_path, stream=False)
        logging.getLogger("proingest.test").info("running: ffmpeg -i in.mov")

        written = (tmp_path / logsetup.LOG_FILENAME).read_text()
        assert "running: ffmpeg -i in.mov" in written
        assert "INFO" in written

    def test_the_folder_is_made_rather_than_required(self, tmp_path: Path, quiet_root: None) -> None:
        nested = tmp_path / "Logs" / "ProIngest"
        logsetup.configure(nested, stream=False)
        assert (nested / logsetup.LOG_FILENAME).exists()

    def test_configuring_twice_does_not_write_every_line_twice(
        self, tmp_path: Path, quiet_root: None
    ) -> None:
        logsetup.configure(tmp_path, stream=False)
        logsetup.configure(tmp_path, stream=False)
        logging.getLogger("proingest.test").warning("once")

        written = (tmp_path / logsetup.LOG_FILENAME).read_text()
        assert written.count("once") == 1

    def test_configuring_leaves_another_owner_s_handler_alone(
        self, tmp_path: Path, quiet_root: None
    ) -> None:
        mine = Captured()
        logging.getLogger().addHandler(mine)
        try:
            logsetup.configure(tmp_path, stream=False)
            assert mine in logging.getLogger().handlers
        finally:
            logging.getLogger().removeHandler(mine)

    def test_the_level_gates_what_is_written(self, tmp_path: Path, quiet_root: None) -> None:
        logsetup.configure(tmp_path, level=logging.WARNING, stream=False)
        log = logging.getLogger("proingest.test")
        log.info("quiet")
        log.warning("loud")

        written = (tmp_path / logsetup.LOG_FILENAME).read_text()
        assert "quiet" not in written
        assert "loud" in written

    def test_set_level_changes_what_is_written_without_a_new_file(
        self, tmp_path: Path, quiet_root: None
    ) -> None:
        logsetup.configure(tmp_path, level=logging.WARNING, stream=False)
        logsetup.set_level(logging.DEBUG)
        logging.getLogger("proingest.test").debug("now audible")

        assert "now audible" in (tmp_path / logsetup.LOG_FILENAME).read_text()
        assert sorted(path.name for path in tmp_path.iterdir()) == [logsetup.LOG_FILENAME]


class TestRotation:
    """The naming and the pruning, which are one decision and have to agree."""

    def test_a_rotated_file_is_dated_the_way_packaging_names_it(self, tmp_path: Path) -> None:
        handler = logsetup.file_handler(tmp_path)
        try:
            handler.emit(
                logging.LogRecord("proingest.test", logging.INFO, __file__, 1, "yesterday", (), None)
            )
            handler.doRollover()
        finally:
            handler.close()

        names = sorted(path.name for path in tmp_path.iterdir())
        assert logsetup.LOG_FILENAME in names
        dated = [name for name in names if name != logsetup.LOG_FILENAME]
        assert len(dated) == 1
        assert dated[0].startswith("proingest-")
        assert dated[0].endswith(".log")
        assert dated[0][len("proingest-") : -len(".log")].isdigit()

    def test_the_oldest_are_still_found_for_deletion(self, tmp_path: Path) -> None:
        """The regression this class exists for: a `namer` the pruning cannot read back."""
        handler = logsetup.file_handler(tmp_path)
        try:
            for day in range(1, 21):
                (tmp_path / f"proingest-202609{day:02d}.log").write_text("x")
            doomed = sorted(Path(name).name for name in handler.getFilesToDelete())
        finally:
            handler.close()

        assert len(doomed) == 20 - logsetup.BACKUP_COUNT
        assert doomed[0] == "proingest-20260901.log"
        assert doomed[-1] == "proingest-20260906.log"

    def test_a_file_that_is_not_ours_is_never_deleted(self, tmp_path: Path) -> None:
        handler = logsetup.file_handler(tmp_path)
        try:
            for day in range(1, 21):
                (tmp_path / f"proingest-202609{day:02d}.log").write_text("x")
            (tmp_path / "crash-20260901.txt").write_text("x")
            doomed = [Path(name).name for name in handler.getFilesToDelete()]
        finally:
            handler.close()

        assert "crash-20260901.txt" not in doomed


class TestShotOf:
    def test_a_record_from_the_window_is_about_no_shot_in_particular(self) -> None:
        record = logging.LogRecord("proingest.ui", logging.INFO, __file__, 1, "hello", (), None)
        assert logsetup.shot_of(record) == ""

    def test_a_stamped_record_names_its_shot(self) -> None:
        record = logging.LogRecord("proingest.core", logging.INFO, __file__, 1, "hello", (), None)
        setattr(record, logsetup.SHOT_FIELD, "MELT0001")
        assert logsetup.shot_of(record) == "MELT0001"


class TestWorkerBridge:
    """FR-13's "every ffmpeg command line logged", where the commands actually run."""

    def test_a_worker_s_ffmpeg_command_arrives_in_this_process(
        self, tmp_path: Path, quiet_root: None
    ) -> None:
        captured = Captured()
        root = logging.getLogger()
        root.addHandler(captured)
        root.setLevel(logging.INFO)
        try:
            source = fixtures.make_mov(tmp_path / "src.mov", count=3)
            job = ref_job(tmp_path, source, 0, 2)
            assert render.execute([job], workers=1)[0].status == "done"
        finally:
            root.removeHandler(captured)

        commands = [
            record.getMessage()
            for record in captured.records
            if record.getMessage().startswith("running: ")
        ]
        assert commands, "a render decodes with ffmpeg, so at least one command was run"
        assert any("ffmpeg" in command for command in commands)

    def test_a_worker_s_record_names_the_shot_it_was_rendering(
        self, tmp_path: Path, quiet_root: None
    ) -> None:
        captured = Captured()
        root = logging.getLogger()
        root.addHandler(captured)
        root.setLevel(logging.INFO)
        try:
            job = raw_job(tmp_path, count=2)
            render.execute([job], workers=1)
        finally:
            root.removeHandler(captured)

        stamped = {logsetup.shot_of(record) for record in captured.records}
        assert job.shot_code in stamped

    def test_a_quiet_parent_is_not_sent_the_worker_s_info_lines(
        self, tmp_path: Path, quiet_root: None
    ) -> None:
        """The level travels to the worker, so nothing is pickled only to be dropped."""
        captured = Captured()
        root = logging.getLogger()
        root.addHandler(captured)
        root.setLevel(logging.WARNING)
        try:
            source = fixtures.make_mov(tmp_path / "src.mov", count=3)
            render.execute([ref_job(tmp_path, source, 0, 2)], workers=1)
        finally:
            root.removeHandler(captured)

        assert not [r for r in captured.records if r.getMessage().startswith("running: ")]
