"""The headless `proingest scan` entry point (M1's definition of done)."""

from __future__ import annotations

from pathlib import Path

import OpenEXR
import pytest

from proingest.__main__ import _ProgressPrinter, main
from proingest.core import batchfile, clf, color, exr, qc, render
from proingest.core.models import Batch, FrameRate, QCResult
from tests.fixtures import color as color_fixtures
from tests.fixtures import media as fixtures

FOLDER = "turnover001_02_23_2026_danielluckett"


class TestScanCommand:
    def test_clean_turnover_exits_zero(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        folder = tmp_path / FOLDER
        fixtures.make_turnover(folder, shots=2, frames=4, side_files=True)
        rules = fixtures.write_rules_file(tmp_path / "rules.json")

        assert main(["scan", str(folder), "--rules", str(rules)]) == 0
        out = capsys.readouterr().out
        assert "MELT0001" in out
        assert "MELT0002" in out
        assert "2 rows, 0 errors, 0 warnings" in out

    def test_fixture_sized_media_fails_the_real_rules(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Without overrides the shipped thresholds apply, and 64x36 is not 4k."""
        folder = tmp_path / FOLDER
        fixtures.make_turnover(folder, shots=1, frames=4)

        assert main(["scan", str(folder)]) == 1
        out = capsys.readouterr().out
        assert "QC-023" in out
        assert "QC-033" in out

    def test_a_rules_value_of_the_wrong_type_exits_two(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        folder = tmp_path / FOLDER
        fixtures.make_turnover(folder, shots=1, frames=4)
        rules = tmp_path / "rules.json"
        rules.write_text('{"target_resolution": 3840}', encoding="utf-8")

        assert main(["scan", str(folder), "--rules", str(rules)]) == 2
        assert capsys.readouterr().err.startswith("error:")

    def test_a_bad_rules_file_exits_two(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        folder = tmp_path / FOLDER
        fixtures.make_turnover(folder, shots=1, frames=4)
        rules = tmp_path / "rules.json"
        rules.write_text('{"min_duraiton_frames": 4}', encoding="utf-8")

        assert main(["scan", str(folder), "--rules", str(rules)]) == 2
        assert "unknown rule settings: min_duraiton_frames" in capsys.readouterr().err

    def test_rules_are_saved_into_the_batch(self, tmp_path: Path) -> None:
        """A later `run` or `qc` must apply the same thresholds the scan did."""
        folder = tmp_path / FOLDER
        fixtures.make_turnover(folder, shots=1, frames=4, side_files=True)
        rules = fixtures.write_rules_file(tmp_path / "rules.json")
        target = tmp_path / "melt.pibatch"

        main(["scan", str(folder), "--rules", str(rules), "--save", str(target)])
        loaded = batchfile.load(target)
        assert qc.settings_for(loaded) == fixtures.SMALL_RULES

    def test_prints_the_turnover_header(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        folder = tmp_path / FOLDER
        fixtures.make_turnover(folder, shots=1, frames=4)
        main(["scan", str(folder)])
        assert "turnover001  02_23_2026  danielluckett" in capsys.readouterr().out

    def test_errors_exit_one(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """A row-level error is a non-zero exit so a script can react."""
        folder = tmp_path / FOLDER
        folder.mkdir(parents=True)
        fixtures.make_otio(folder / "t.otio", [("MELT0001_pl01", "file:///nowhere/x.exr")], duration=4)
        assert main(["scan", str(folder)]) == 1
        assert "QC-012" in capsys.readouterr().out

    def test_missing_folder_exits_two(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        assert main(["scan", str(tmp_path / "absent")]) == 2
        assert "is not a directory" in capsys.readouterr().err

    def test_save_writes_a_loadable_batch(self, tmp_path: Path) -> None:
        folder = tmp_path / FOLDER
        fixtures.make_turnover(folder, shots=1, frames=4)
        target = tmp_path / "melt"

        main(["scan", str(folder), "--save", str(target), "--name", "melt"])
        loaded = batchfile.load(target.with_suffix(".pibatch"))
        assert loaded.name == "melt"
        assert len(loaded.rows) == 1

    def test_scans_several_folders(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        first = tmp_path / "turnover001_02_23_2026_dan"
        second = tmp_path / "turnover002_02_24_2026_sam"
        fixtures.make_turnover(first, shots=1, frames=4, side_files=True)
        fixtures.make_turnover(second, shots=1, frames=4, side_files=True)
        rules = fixtures.write_rules_file(tmp_path / "rules.json")

        assert main(["scan", str(first), str(second), "--rules", str(rules)]) == 0
        out = capsys.readouterr().out
        assert "turnover001" in out and "turnover002" in out
        assert "2 rows" in out


class TestTopLevel:
    def test_no_command_launches_the_ui(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """M5.1: that is what `proingest` with no subcommand is for.

        The launch is stubbed because the real one hands control to Qt's event loop and
        does not come back. This test used to assert that no subcommand printed help,
        and it is what caught the change: an un-stubbed call hangs the suite rather than
        failing it.
        """
        launched: list[str] = []

        def fake_run() -> int:
            launched.append("ui")
            return 7

        from proingest.ui import app as ui_app

        monkeypatch.setattr(ui_app, "run", fake_run)
        assert main([]) == 7
        assert launched == ["ui"]

    def test_help_is_still_reachable(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Nothing launches from `--help`, which is how the subcommands are discovered."""
        with pytest.raises(SystemExit) as exit_info:
            main(["--help"])
        assert exit_info.value.code == 0
        assert "usage: proingest" in capsys.readouterr().out

    def test_version(self, capsys: pytest.CaptureFixture[str]) -> None:
        with pytest.raises(SystemExit) as exit_info:
            main(["--version"])
        assert exit_info.value.code == 0
        assert "proingest" in capsys.readouterr().out


class TestRunCommand:
    """`proingest run` is the whole pipeline headless: load, plan, render, save."""

    def scanned(self, tmp_path: Path) -> Path:
        """A saved batch of one small turnover, ready to render."""
        folder = tmp_path / FOLDER
        fixtures.make_turnover(folder, shots=1, frames=4, side_files=True)
        rules = fixtures.write_rules_file(tmp_path / "rules.json")
        batch_path = tmp_path / "batch.pibatch"
        assert main(["scan", str(folder), "--rules", str(rules), "--save", str(batch_path)]) == 0
        return batch_path

    def graded(self, tmp_path: Path) -> list[str]:
        """The flags a run needs to produce anything: QC-008 refuses one without them."""
        return ["--color-session", str(color_fixtures.make_session(tmp_path / "session"))]

    def test_a_dry_run_prints_the_plan_and_writes_nothing(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        batch_path = self.scanned(tmp_path)
        delivery = tmp_path / "delivery"

        argv = ["run", str(batch_path), "--delivery-root", str(delivery), "--dry-run"]
        assert main(argv + self.graded(tmp_path)) == 0
        out = capsys.readouterr().out
        assert "MELT0001_pl01_raw_4k_v01" in out
        assert "deliverables from 1 shots" in out
        assert not delivery.exists()

    def test_a_run_writes_the_deliverables_it_planned(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        batch_path = self.scanned(tmp_path)
        delivery = tmp_path / "delivery"

        argv = ["run", str(batch_path), "--delivery-root", str(delivery), "--jobs", "2"]
        assert main(argv + self.graded(tmp_path)) == 0
        out = capsys.readouterr().out

        shot = delivery / "MELT" / "MELT0001"
        assert (shot / "MELT0001_pl01_raw_4k_v01").is_dir()
        assert (shot / "MELT0001_pl01_raw_HD_v01").is_dir()
        assert (shot / "MELT0001_pl01_audio_v01.wav").is_file()
        assert len(list((shot / "MELT0001_pl01_raw_4k_v01").iterdir())) == 4
        assert "written" in out
        assert not list(shot.glob("*.part"))

    def test_the_run_is_recorded_back_into_the_batch_file(self, tmp_path: Path) -> None:
        batch_path = self.scanned(tmp_path)
        argv = ["run", str(batch_path), "--delivery-root", str(tmp_path / "delivery")]
        main(argv + self.graded(tmp_path))

        batch = batchfile.load(batch_path)
        done = [d for row in batch.rows for d in row.deliverables if d.status == "done"]
        raw = next(d for d in done if d.name.endswith("raw_4k_v01"))
        assert raw.frame_count == 4
        assert len(raw.frame_checksums) == 4
        assert batchfile.backup(batch_path) is not None

    def test_the_preflight_is_reported_before_the_render(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """The disk-touching rules run once, when a run is about to start."""
        batch_path = self.scanned(tmp_path)
        main(["run", str(batch_path), "--delivery-root", str(tmp_path / "delivery"), "--dry-run"])
        assert "QC-054" in capsys.readouterr().out

    def test_a_row_error_from_the_preflight_is_printed_too(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A row with an error is dropped from the plan, so the shot count is short and
        this line is the only thing that says why."""
        batch_path = self.scanned(tmp_path)

        def flag_a_row(batch: Batch) -> None:
            batch.rows[0].qc.append(QCResult("QC-019", "error", "row", "the HDRI will not open"))

        monkeypatch.setattr(qc, "preflight", flag_a_row)
        main(["run", str(batch_path), "--delivery-root", str(tmp_path / "delivery"), "--dry-run"])
        out = capsys.readouterr().out
        assert "QC-019" in out and "MELT0001" in out

    def test_an_unwritable_delivery_root_stops_the_run(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        batch_path = self.scanned(tmp_path)
        locked = tmp_path / "locked"
        locked.mkdir(mode=0o500)
        try:
            assert main(["run", str(batch_path), "--delivery-root", str(locked / "d")]) == 2
        finally:
            locked.chmod(0o700)
        assert "QC-062" in capsys.readouterr().err

    def test_a_missing_batch_file_exits_two(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        assert main(["run", str(tmp_path / "nope.pibatch")]) == 2
        assert "does not exist" in capsys.readouterr().err

    def test_no_delivery_root_anywhere_exits_two(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """The batch carries no root and none was passed, so there is nowhere to write."""
        assert main(["run", str(self.scanned(tmp_path))]) == 2
        assert "delivery root" in capsys.readouterr().err


class TestColorSession:
    """`run --color-session` is where the colour session package comes in until the

    Settings page holds it (PRD section 7). The run has to work without one, and with
    one the grade has to reach the file rather than just the command line.
    """

    def scanned(self, tmp_path: Path) -> Path:
        folder = tmp_path / FOLDER
        fixtures.make_turnover(folder, shots=1, frames=4, side_files=True)
        rules = fixtures.write_rules_file(tmp_path / "rules.json")
        batch_path = tmp_path / "batch.pibatch"
        assert main(["scan", str(folder), "--rules", str(rules), "--save", str(batch_path)]) == 0
        return batch_path

    def session(self, tmp_path: Path) -> Path:
        """A final EDL and one CLF, laid out the way the session exports them."""
        folder = tmp_path / "session"
        folder.mkdir()
        edl = folder / "MELT_FINAL_v01.edl"
        edl.write_text(
            "TITLE: MELT_FINAL_v01\nFCM: NON-DROP FRAME\n\n"
            "001  MELT0001 V     C        01:00:00:00 01:00:00:04 01:00:00:00 01:00:00:04\n"
            "* FROM CLIP NAME: MELT0001_pl01.exr\n"
            "*ASC_SOP (1.020000 0.990000 1.010000)"
            "(0.001000 -0.002000 0.000000)(0.980000 1.000000 1.020000)\n"
            "*ASC_SAT 1.050000\n"
        )
        color_fixtures.plate_clf(folder / "MELT0001_grade_v01.clf")
        return edl

    def test_the_grade_reaches_the_delivered_frames(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        batch_path = self.scanned(tmp_path)
        delivery = tmp_path / "delivery"
        main(
            [
                "run",
                str(batch_path),
                "--delivery-root",
                str(delivery),
                "--color-session",
                str(self.session(tmp_path)),
            ]
        )
        assert "colour session: 1 events, 1 shots with a CLF" in capsys.readouterr().out

        frame = next((delivery / "MELT" / "MELT0001" / "MELT0001_pl01_raw_4k_v01").iterdir())
        with OpenEXR.File(str(frame)) as handle:
            header = dict(handle.header())
        assert header[exr.CLF_ATTRIBUTE] == "MELT0001_grade_v01.clf"
        assert header[exr.COLORSPACE_ATTRIBUTE] == color.PLATE_SPACE

    def test_the_qc_log_names_the_clf_it_rendered_through(self, tmp_path: Path) -> None:
        batch_path = self.scanned(tmp_path)
        main(
            [
                "run",
                str(batch_path),
                "--delivery-root",
                str(tmp_path / "delivery"),
                "--color-session",
                str(self.session(tmp_path)),
            ]
        )
        reopened = batchfile.load(batch_path)
        assert reopened.rows[0].clf_path is not None
        assert reopened.rows[0].clf_path.name == "MELT0001_grade_v01.clf"

    def test_an_unreadable_edl_stops_the_run_before_anything_is_written(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        batch_path = self.scanned(tmp_path)
        delivery = tmp_path / "delivery"
        code = main(
            [
                "run",
                str(batch_path),
                "--delivery-root",
                str(delivery),
                "--color-session",
                str(tmp_path / "nothing.edl"),
            ]
        )
        assert code == 2
        assert "could not read" in capsys.readouterr().err
        assert not delivery.exists()

    def test_a_run_with_no_session_delivers_nothing_and_says_why(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Rendering waits for colour (COLOR_AND_FORMAT section 1). QC-008 is the refusal.

        Scanning, review and In/Out all still happen without one, because they are about
        frames rather than pixels. An ungraded plate is not a lesser deliverable here, it
        is the wrong pixels under the right filename, so nothing is written at all.
        """
        batch_path = self.scanned(tmp_path)
        delivery = tmp_path / "delivery"
        assert main(["run", str(batch_path), "--delivery-root", str(delivery)]) == 0
        out = capsys.readouterr().out
        assert "QC-008" in out
        assert "nothing to render" in out
        assert not (delivery / "MELT").exists()

    def test_a_turnover_with_a_session_renders_while_another_waits(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """QC-008 is turnover scope, and this is what that buys (`qc.blocked_turnovers`)."""
        folder = tmp_path / FOLDER
        fixtures.make_turnover(folder, shots=1, frames=4, side_files=True)
        waiting = tmp_path / "turnover002_02_24_2026_danielluckett"
        fixtures.make_turnover(waiting, shots=1, frames=4, side_files=True)
        rules = fixtures.write_rules_file(tmp_path / "rules.json")
        batch_path = tmp_path / "batch.pibatch"
        main(["scan", str(folder), str(waiting), "--rules", str(rules), "--save", str(batch_path)])

        batch = batchfile.load(batch_path)
        session = clf.load_session(self.session(tmp_path), FrameRate(24))
        first = batch.turnovers[0]
        clf.ingest(first, batch.rows_for(first.turnover_id), session)
        batchfile.save(batch, batch_path)

        delivery = tmp_path / "delivery"
        main(["run", str(batch_path), "--delivery-root", str(delivery)])
        assert "holding back" in capsys.readouterr().out
        assert (delivery / "MELT" / "MELT0001").is_dir()


class TestQcCommand:
    """`proingest qc` is M4.3 headless: reopen a batch, re-run the rules, write both sheets."""

    def rendered(self, tmp_path: Path) -> tuple[Path, Path]:
        """A batch that has actually been through a run, so there is something to report."""
        folder = tmp_path / FOLDER
        fixtures.make_turnover(folder, shots=1, frames=4, side_files=True)
        rules = fixtures.write_rules_file(tmp_path / "rules.json")
        batch_path = tmp_path / "batch.pibatch"
        delivery = tmp_path / "delivery"
        session = color_fixtures.make_session(tmp_path / "session")
        main(["scan", str(folder), "--rules", str(rules), "--save", str(batch_path)])
        main(
            [
                "run",
                str(batch_path),
                "--delivery-root",
                str(delivery),
                "--jobs",
                "2",
                "--color-session",
                str(session),
            ]
        )
        return batch_path, delivery

    def test_both_sheets_land_in_the_show_s_reports_folder(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        batch_path, delivery = self.rendered(tmp_path)
        capsys.readouterr()

        main(["qc", str(batch_path)])
        reports = delivery / "MELT" / "_reports"

        assert len(list(reports.glob("qc_ingest_log_*.xlsx"))) == 1
        assert len(list(reports.glob("shot_tracker_*.xlsx"))) == 1

    def test_it_prints_where_they_went_and_what_they_say(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        batch_path, _ = self.rendered(tmp_path)
        capsys.readouterr()

        main(["qc", str(batch_path)])
        out = capsys.readouterr().out
        assert "qc_ingest_log_" in out
        assert "shot_tracker_" in out
        assert "1 rows" in out

    def test_out_overrides_the_reports_folder(self, tmp_path: Path) -> None:
        batch_path, _ = self.rendered(tmp_path)
        elsewhere = tmp_path / "somewhere"

        main(["qc", str(batch_path), "--out", str(elsewhere)])

        assert len(list(elsewhere.glob("*.xlsx"))) == 2

    def test_a_missing_batch_exits_two(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        assert main(["qc", str(tmp_path / "nope.pibatch")]) == 2
        assert "error:" in capsys.readouterr().err

    def test_a_batch_with_no_delivery_root_says_what_to_pass(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        folder = tmp_path / FOLDER
        fixtures.make_turnover(folder, shots=1, frames=4)
        batch_path = tmp_path / "batch.pibatch"
        main(["scan", str(folder), "--save", str(batch_path)])
        capsys.readouterr()

        assert main(["qc", str(batch_path)]) == 2
        assert "--delivery-root" in capsys.readouterr().err


class TestProgressPrinter:
    """Several workers interleave, so per-frame lines have to stay off a log."""

    def printer(self, live: bool) -> _ProgressPrinter:
        reporter = _ProgressPrinter(interval=0.0)
        reporter._live = live
        return reporter

    def test_redirected_output_gets_result_lines_only(self, capsys: pytest.CaptureFixture[str]) -> None:
        reporter = self.printer(live=False)
        reporter(render.Progress("shot_raw_4k_v01", "started", 0, 3))
        for frame in (1, 2, 3):
            reporter(render.Progress("shot_raw_4k_v01", "frame", frame, 3))
        reporter(render.Progress("shot_raw_4k_v01", "done", 3, 3))

        lines = [line for line in capsys.readouterr().out.splitlines() if line.strip()]
        assert lines == ["  shot_raw_4k_v01                                      done"]

    def test_a_tty_gets_one_aggregate_line_not_one_per_job(self, capsys: pytest.CaptureFixture[str]) -> None:
        reporter = self.printer(live=True)
        reporter(render.Progress("a", "started", 0, 4))
        reporter(render.Progress("b", "started", 0, 4))
        reporter(render.Progress("a", "frame", 2, 4))
        reporter(render.Progress("b", "frame", 1, 4))

        out = capsys.readouterr().out
        assert "0/2 deliverables, 3/8 frames, 37%" in out

    def test_a_failure_reports_its_reason(self, capsys: pytest.CaptureFixture[str]) -> None:
        reporter = self.printer(live=False)
        reporter(render.Progress("x_ref_4k_v01.mp4", "started", 0, 2))
        reporter(render.Progress("x_ref_4k_v01.mp4", "failed", 0, 2, "source vanished"))
        assert "FAILED  source vanished" in capsys.readouterr().out
