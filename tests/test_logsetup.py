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

from proingest.core import ffmpeg, logsetup, render
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

    def test_configuring_leaves_another_owner_s_handler_alone(self, tmp_path: Path, quiet_root: None) -> None:
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
            record.getMessage() for record in captured.records if record.getMessage().startswith("running: ")
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


class TestTheFfmpegOverrideReachingAWorker:
    """M5.8.3. It travels on the channel M5.8.1 built, for the reason M5.8.1 built it.

    `ffmpeg.resolve_tool` is called inside a spawned worker, which is a fresh
    interpreter that knows nothing the Settings page was told. An override that stayed
    in the parent would be a render done with the wrong build of ffmpeg and nothing said.
    """

    def test_a_worker_renders_with_the_override_rather_than_with_path(
        self, tmp_path: Path, quiet_root: None
    ) -> None:
        captured = Captured()
        root = logging.getLogger()
        root.addHandler(captured)
        root.setLevel(logging.INFO)
        real = ffmpeg.resolve_tool("ffmpeg")
        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir()
        (elsewhere / "ffmpeg").symlink_to(real)
        (elsewhere / "ffprobe").symlink_to(ffmpeg.resolve_tool("ffprobe"))
        ffmpeg.set_override(elsewhere)
        try:
            source = fixtures.make_mov(tmp_path / "src.mov", count=3)
            assert render.execute([ref_job(tmp_path, source, 0, 2)], workers=1)[0].status == "done"
        finally:
            ffmpeg.set_override(None)
            root.removeHandler(captured)

        commands = [r.getMessage() for r in captured.records if r.getMessage().startswith("running")]
        assert commands, "the run logged no command at all"
        assert all(str(elsewhere) in command for command in commands), commands

    def test_a_worker_with_no_override_uses_the_normal_order(self, tmp_path: Path, quiet_root: None) -> None:
        assert ffmpeg.current_override() is None
        source = fixtures.make_mov(tmp_path / "src.mov", count=3)
        assert render.execute([ref_job(tmp_path, source, 0, 2)], workers=1)[0].status == "done"

    def test_a_worker_encodes_at_the_quality_the_settings_page_set(
        self, tmp_path: Path, quiet_root: None
    ) -> None:
        """M5.12, the Output section's half of the same channel.

        Here rather than in `test_render.py` because the logged command is the only place
        the rate factor is visible afterwards: ffprobe does not surface it. The other
        Output setting is observable in the file it wrote, so its test is with the render.
        """
        captured = Captured()
        root = logging.getLogger()
        root.addHandler(captured)
        root.setLevel(logging.INFO)
        was = ffmpeg.current_reference_crf()
        ffmpeg.set_reference_crf(30)
        try:
            source = fixtures.make_mov(tmp_path / "src.mov", count=3)
            assert render.execute([ref_job(tmp_path, source, 0, 2)], workers=1)[0].status == "done"
        finally:
            ffmpeg.set_reference_crf(was)
            root.removeHandler(captured)

        encodes = [r.getMessage() for r in captured.records if "libx264" in r.getMessage()]
        assert encodes, "the run logged no encode at all"
        assert all("-crf 30" in command for command in encodes), encodes


class TestTheDiagnosticsExport:
    """The Log tab's Save Logs as CSV: every kept file, oldest first, one row a record."""

    def test_every_kept_file_is_read_oldest_first(self, tmp_path: Path) -> None:
        (tmp_path / "proingest-20260921.log").write_text("2026-09-21 10:00:00,000 INFO    a: old\n")
        (tmp_path / "proingest-20260922.log").write_text("2026-09-22 10:00:00,000 INFO    a: middle\n")
        (tmp_path / "proingest.log").write_text("2026-09-23 10:00:00,000 WARNING b.c: now\n")
        assert [p.name for p in logsetup.log_files(tmp_path)] == [
            "proingest-20260921.log",
            "proingest-20260922.log",
            "proingest.log",
        ]

    def test_a_traceback_stays_with_its_record(self, tmp_path: Path) -> None:
        log = tmp_path / "proingest.log"
        log.write_text(
            "2026-09-23 10:00:00,000 ERROR   proingest.ui: it broke\n"
            "Traceback (most recent call last):\n"
            "ValueError: nope\n"
            "2026-09-23 10:00:01,000 INFO    proingest.core.ffmpeg: ffmpeg -i a.mov\n"
        )
        rows = logsetup.log_rows(log)
        assert [row[1] for row in rows] == ["ERROR", "INFO"]
        assert rows[0][3] == "it broke\nTraceback (most recent call last):\nValueError: nope"
        assert rows[1][2:4] == ["proingest.core.ffmpeg", "ffmpeg -i a.mov"]

    def test_the_csv_opens_with_what_build_it_came_from(self, tmp_path: Path) -> None:
        import csv

        (tmp_path / "proingest.log").write_text("2026-09-23 10:00:00,000 INFO    a: hello, world\n")
        out = tmp_path / "logs.csv"
        count = logsetup.export_csv(tmp_path, out, [("ProIngest", "0.5.2")])
        with out.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.reader(handle))
        assert count == 1
        assert rows[0] == list(logsetup.EXPORT_COLUMNS)
        assert rows[1] == ["", "ABOUT", "ProIngest", "0.5.2", ""]
        assert rows[2][3] == "hello, world", "a comma in a message is quoted, not a new column"

    def test_what_the_handler_writes_is_what_the_export_reads(self, tmp_path: Path) -> None:
        """The pattern is pinned to `FILE_FORMAT` by writing through the real handler."""
        handler = logsetup.file_handler(tmp_path)
        logger = logging.getLogger("proingest.test.export")
        logger.addHandler(handler)
        try:
            logger.warning("probe failed: %s", "C0145.MP4")
        finally:
            logger.removeHandler(handler)
            handler.close()
        rows = logsetup.log_rows(tmp_path / logsetup.LOG_FILENAME)
        assert [row[1:4] for row in rows] == [["WARNING", "proingest.test.export", "probe failed: C0145.MP4"]]
