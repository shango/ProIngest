"""The Fix-it report (user, 2026-10-06): what Ben needs to change, in plain words."""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from proingest.core import fixit, models, scan
from proingest.core.models import Batch, QCResult, ShotRow
from tests.fixtures import media as fixtures

FOLDER = "turnover134_09_29_26_sethcarroll"
DAY = date(2026, 10, 6)


def scanned(folder: Path) -> Batch:
    turnover, rows = scan.scan_turnover(folder, "t1", scan.ScanSettings(rules=fixtures.SMALL_RULES))
    return Batch(name="sethcarroll", turnovers=[turnover], rows=rows)


def turnover(tmp_path: Path, shots: int = 2, shot_types: list[str] | None = None) -> Path:
    return fixtures.make_turnover(tmp_path / FOLDER, shots=shots, frames=4, shot_types=shot_types)


def only(batch: Batch) -> fixit.TurnoverReport:
    (report,) = fixit.reports(batch)
    return report


def titled(report: fixit.TurnoverReport, title: str) -> fixit.Item:
    (item,) = [item for item in report.items if item.advice.title == title]
    return item


class TestTheReport:
    def test_a_clean_turnover_says_there_is_nothing_to_fix(self, tmp_path: Path) -> None:
        batch = scanned(turnover(tmp_path))
        report = only(batch)
        assert report.items == [] and report.blocked == 0
        page = fixit.render(batch, DAY)
        assert fixit.NOTHING_TO_FIX in page and "Nothing blocking" in page

    def test_missing_amfs_are_one_item_listing_each_clip_and_it_blocks(self, tmp_path: Path) -> None:
        folder = turnover(tmp_path, shots=3)
        next(folder.glob("*_0_*.amf")).unlink()
        report = only(scanned(folder))
        item = titled(report, fixit.ADVICE["QC-075"].title)
        assert item.blocks and item.advice.where == "resolve"
        assert [clip.name for clip in item.clips] == ["MELT0001_pl01"]
        assert item.clips[0].who == "MELT0001 plate"
        assert report.blocked == 1 and fixit._status(report) == "1 of 3 clips blocked"
        assert fixit.ADVICE["QC-046"].title not in {other.advice.title for other in report.items}

    def test_every_clip_is_listed_even_when_it_is_every_clip(self, tmp_path: Path) -> None:
        """User, 2026-10-07: "If it's every clip, list each clip in the fixit item." """
        folder = turnover(tmp_path, shots=3)
        for path in folder.glob("*.amf"):
            path.unlink()
        report = only(scanned(folder))
        item = titled(report, fixit.ADVICE["QC-075"].title)
        assert [clip.who for clip in item.clips] == ["MELT0001 plate", "MELT0002 plate", "MELT0003 plate"]
        assert fixit._status(report) == "Every clip blocked"

    def test_a_clip_whose_shot_did_not_read_is_named_by_the_metadata(self) -> None:
        said = ShotRow(turnover_id="t1", clip_name="x.exr", csv_shot="SECA0009", csv_shot_type="HDRI")
        blank = ShotRow(turnover_id="t1", clip_name="y.exr", csv_shot_type="HDRI")
        assert fixit._who(said) == "SECA0009 HDRI"
        assert fixit._who(blank) == "HDRI, no Shot in the metadata"

    def test_a_missing_file_is_a_folder_fix(self, tmp_path: Path) -> None:
        folder = turnover(tmp_path)
        fixtures.make_meta_csv(
            folder / "metadata.csv", [("MELT0001_pl01", "MELT0001", "pl01"), ("GONE", "MELT0002", "pl01")]
        )
        report = only(scanned(folder))
        item = titled(report, fixit.ADVICE["QC-012"].title)
        assert item.advice.where == "folder" and item.blocks
        assert [clip.name for clip in item.clips] == ["GONE"]

    def test_a_shot_with_references_and_no_plate_is_worth_a_look(self, tmp_path: Path) -> None:
        """Turnover134's mirror ball typed SECA0001 rather than SECA0011."""
        batch = scanned(turnover(tmp_path, shot_types=["pl01", "mirrorBall"]))
        item = titled(only(batch), fixit.NO_PLATE.title)
        assert [(clip.who, clip.name) for clip in item.clips] == [("MELT0002 mirror ball", "MELT0002_pl01")]
        assert not item.blocks

    def test_a_blank_duplicate_row_says_it_can_go(self, tmp_path: Path) -> None:
        """Turnover135's A001_09301520_C026_S003 on two rows, the first with no Shot Type."""
        batch = scanned(turnover(tmp_path))
        names = "MELT0001_pl01, OTHER.mov"
        batch.turnovers[0].qc.append(QCResult("QC-064", "warning", "turnover", f"2 clips ...: {names}"))
        item = titled(only(batch), fixit.ADVICE["QC-064"].title)
        assert item.clips == [
            fixit.Clip(name="MELT0001_pl01", detail=fixit.DUPLICATE_ROW),
            fixit.Clip(name="OTHER.mov"),
        ]

    def test_the_editors_own_findings_are_left_out(self, tmp_path: Path) -> None:
        batch = scanned(turnover(tmp_path))
        batch.rows[0].qc.append(QCResult("QC-031", "error", "row", "In/Out outside"))
        batch.turnovers[0].qc.append(QCResult("QC-069", "error", "turnover", "folder moved"))
        assert only(batch).items == []


class TestDetails:
    def test_handles_say_which_side_in_words(self) -> None:
        message = "0 before In and 3 after Out, fewer than the 8 handle frames expected"
        assert fixit._handles_detail(message) == (
            "no spare frames before the cut and only 3 spare frames after the cut"
        )

    def test_seconds_are_rounded_and_frames_counted(self) -> None:
        assert fixit._seconds(131, 24.0) == "about 5 seconds"
        assert fixit._seconds(1, 24.0) == "1 frame"

    def test_the_fix_in_resolve_prefix_is_not_repeated(self) -> None:
        assert fixit._plain(models.FIX_IN_RESOLVE + "no AMF") == "no AMF"


class TestTheAdvice:
    def test_every_fix_in_resolve_rule_has_words_for_ben(self) -> None:
        assert set(fixit.ADVICE) >= models.RESOLVE_FIX_RULES

    def test_every_rule_it_speaks_for_is_in_qc_rules(self) -> None:
        documented = set(re.findall(r"^\| (QC-\d{3}) \|", Path("docs/QC_RULES.md").read_text(), re.MULTILINE))
        assert set(fixit.ADVICE) <= documented

    def test_no_rule_ids_reach_the_page(self, tmp_path: Path) -> None:
        folder = turnover(tmp_path)
        for path in folder.glob("*.amf"):
            path.unlink()
        assert not re.search(r"QC-\d{3}", fixit.render(scanned(folder), DAY))


class TestThePage:
    def test_names_are_escaped(self, tmp_path: Path) -> None:
        batch = scanned(turnover(tmp_path))
        batch.rows[0].qc.append(QCResult("QC-012", "error", "row", "missing"))
        batch.rows[0].clip_name = "<b>clip</b>.mov"
        page = fixit.render(batch, DAY)
        assert "&lt;b&gt;clip&lt;/b&gt;.mov" in page and "<b>clip" not in page

    def test_it_is_written_beside_the_spreadsheets_whole(self, tmp_path: Path) -> None:
        batch = scanned(turnover(tmp_path))
        path = fixit.report_path(batch, tmp_path / "delivery", DAY)
        assert path == tmp_path / "delivery" / "MELT" / "_reports" / "fixit_report_sethcarroll_20261006.html"
        fixit.write(batch, path, DAY)
        assert path.read_text(encoding="utf-8").startswith("<!doctype html>")
        assert list(path.parent.iterdir()) == [path]

    def test_the_page_loads_nothing_from_elsewhere(self, tmp_path: Path) -> None:
        """Opened from disk and sent on as a file, so it must work offline."""
        page = fixit.render(scanned(turnover(tmp_path)), DAY)
        assert "http" not in page and "<script" not in page
