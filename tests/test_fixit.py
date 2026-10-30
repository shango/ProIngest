"""The Fix-it report (user, 2026-10-06): what Ben needs to change, in plain words."""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import pytest

from proingest.core import fixit, models, scan
from proingest.core.models import Batch, QCResult, ShotRow, Turnover
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
        assert fixit.NOTHING_TO_FIX in page and "Nothing held back" in page

    def test_a_clip_with_no_color_at_all_is_one_item_and_it_holds_the_clip(self, tmp_path: Path) -> None:
        """No AMF and no Input Color Space in the CSV: nothing says what color it is in (QC-046)."""
        folder = turnover(tmp_path, shots=3)
        next(folder.glob("*_0_*.amf")).unlink()
        report = only(scanned(folder))
        item = titled(report, fixit.ADVICE["QC-046"].title)
        assert item.blocks and item.advice.where == "resolve"
        assert [clip.name for clip in item.clips] == ["MELT0001_pl01"]
        assert item.clips[0].who == "MELT0001 plate"
        assert report.blocked == 1 and fixit._status(report) == "1 of 3 clips held back"

    def test_a_clip_with_no_amf_but_a_color_space_is_ungraded_not_an_item(self, tmp_path: Path) -> None:
        """User, 2026-10-07: "If there is no CLF, AMF or CDL, assume ungraded". A note in the
        QC log (QC-009), nothing for Ben to fix."""
        folder = turnover(tmp_path, shots=3)
        rows = [(f"MELT000{i}_pl01", f"MELT000{i}", "pl01") for i in (1, 2, 3)]
        fixtures.make_meta_csv(folder / "metadata.csv", rows, input_color_space=fixtures.SOURCE_ENCODING)
        next(folder.glob("*_0_*.amf")).unlink()
        report = only(scanned(folder))
        assert report.items == [] and report.blocked == 0

    def test_every_clip_is_listed_even_when_it_is_every_clip(self, tmp_path: Path) -> None:
        """User, 2026-10-07: "If it's every clip, list each clip in the fixit item." """
        folder = turnover(tmp_path, shots=3)
        for path in folder.glob("*.amf"):
            path.unlink()
        report = only(scanned(folder))
        item = titled(report, fixit.ADVICE["QC-046"].title)
        assert [clip.who for clip in item.clips] == ["MELT0001 plate", "MELT0002 plate", "MELT0003 plate"]
        assert fixit._status(report) == "Every clip held back"

    def test_an_unknown_color_space_from_the_csv_is_reported_by_the_csv(self, tmp_path: Path) -> None:
        """INCA6010 (2026-10-12): no AMF, and the CSV's Input Color Space is 'Rec.709 (Scene)',
        which the config lacks. It is the clip's input color space, not its grade, and the
        CSV said it, not an AMF."""
        folder = turnover(tmp_path, shots=2)
        rows = [("MELT0001_pl01", "MELT0001", "pl01"), ("MELT0002_pl01", "MELT0002", "pl01")]
        fixtures.make_meta_csv(folder / "metadata.csv", rows, input_color_space="Rec.709 (Scene)")
        for path in folder.glob("*.amf"):
            path.unlink()
        batch = scanned(folder)
        item = titled(only(batch), fixit.ADVICE["QC-047"].title)
        assert [clip.name for clip in item.clips] == ["MELT0001_pl01", "MELT0002_pl01"]
        assert all(clip.named_by.endswith("Input Color Space column") for clip in item.clips)
        page = fixit.render(batch, DAY)
        assert page.count("Rec.709 (Scene)") == 1, "the message once, every clip under it"
        assert "<code>MELT0001_pl01</code> - MELT0001 plate, at 01:00:00:00 on the timeline" in page
        assert "<code>MELT0002_pl01</code> - MELT0002 plate, at 01:00:00:04 on the timeline" in page

    def test_the_csv_s_color_space_says_so_and_names_no_amf(self, tmp_path: Path) -> None:
        folder = turnover(tmp_path, shots=1)
        fixtures.make_meta_csv(
            folder / "metadata.csv",
            [("MELT0001_pl01", "MELT0001", "pl01")],
            input_color_space="Rec.709 (Scene)",
        )
        for path in folder.glob("*.amf"):
            path.unlink()
        batch = scanned(folder)
        (clip,) = titled(only(batch), fixit.ADVICE["QC-047"].title).clips
        assert clip.detail.startswith(
            "No AMF was matched to this clip, so the metadata CSV's Input Color Space"
        )
        assert "'Rec.709 (Scene)'" in clip.detail
        assert "the clip's AMF" not in fixit.render(batch, DAY)

    def test_an_amf_passed_over_is_named_with_the_csv_s_color_space(self) -> None:
        """An AMF at the clip's index that names another clip is not used (QC-075, info)."""
        passed = QCResult(
            "QC-075", "info", "row", "x_3.amf grades video clip 4 of the EDL (event 004) but names B.mov"
        )
        row = ShotRow(turnover_id="t1", clip_name="A.mov", source_encoding="Rec.709 (Scene)", qc=[passed])
        row.source_encoding_origin = "CSV"
        said = fixit._color_space_detail(row, QCResult("QC-047", "error", "row", "source encoding"))
        assert said.startswith(
            "x_3.amf grades video clip 4 of the EDL (event 004) but names B.mov. So the metadata"
        )

    def test_a_color_space_from_nowhere_the_tool_can_show_asks_for_a_look(self) -> None:
        """User, 2026-10-12: "This clip is appearing as a rec709, please investigate why"."""
        row = ShotRow(turnover_id="t1", clip_name="A.mov", source_encoding="Rec.709 (Scene)")
        result = QCResult("QC-047", "error", "row", "source encoding")
        said = fixit._color_space_detail(row, result)
        assert said == "This clip is appearing as 'Rec.709 (Scene)', please investigate why."
        assert fixit._named_by(row, result, Turnover(turnover_id="t1", folder=Path("/t")), 24) == ""

    def test_an_amf_with_no_input_transform_is_not_called_missing(self, tmp_path: Path) -> None:
        """QC-046 fires for an AMF naming no input transform too: the item must not say "no AMF"."""
        folder = turnover(tmp_path, shots=1)
        (amf,) = folder.glob("*.amf")
        text = amf.read_text()
        start, end = text.index("<aces:inputTransform"), text.index("</aces:inputTransform>")
        amf.write_text(text[:start] + text[end + len("</aces:inputTransform>") :])
        item = titled(only(scanned(folder)), fixit.ADVICE["QC-046"].title)
        assert "no AMF" not in item.advice.explain and "It has no AMF" not in item.advice.explain
        assert item.clips[0].detail == f"{amf.name} names no input transform"

    @pytest.mark.parametrize(
        "rule",
        [
            "QC-011",
            "QC-014",
            "QC-027",
            "QC-028",
            "QC-041",
            "QC-042",
            "QC-043",
            "QC-046",
            "QC-067",
            "QC-073",
            "QC-075",
        ],
    )
    def test_a_rule_whose_message_names_things_shows_it(self, rule: str) -> None:
        """User, 2026-10-12: "This fixit tool is useless if it's not very specific". Each of these
        messages names events, files or the reason, which the heading alone does not."""
        assert fixit.ADVICE[rule].detail == "message"

    def test_clips_are_grouped_under_each_detail_they_share(self) -> None:
        clips = [
            fixit.Clip("A plate", "a.mov", "said once"),
            fixit.Clip("B plate", "b.mov", "said apart"),
            fixit.Clip("C plate", "c.mov", "said once"),
            fixit.Clip(detail="a turnover's own message"),
        ]
        assert [(detail, [clip.name for clip in group]) for detail, group in fixit.clip_groups(clips)] == [
            ("said once", ["a.mov", "c.mov"]),
            ("said apart", ["b.mov"]),
            ("", [""]),
        ]

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

    def test_a_missing_file_says_where_it_was_looked_for_and_who_named_it(self, tmp_path: Path) -> None:
        """User, 2026-10-07: "filename the tool is looking for along with the expected path ...
        what is reporting the file. Is it the EDL, CSV etc?"."""
        folder = turnover(tmp_path)
        fixtures.make_meta_csv(
            folder / "metadata.csv", [("MELT0001_pl01", "MELT0001", "pl01"), ("GONE", "MELT0002", "pl01")]
        )
        (clip,) = titled(only(scanned(folder)), fixit.ADVICE["QC-012"].title).clips
        assert clip.looked_for == str(folder / "GONE")
        assert clip.named_by.startswith("the metadata CSV (metadata.csv), File Name column")
        page = fixit.render(scanned(folder))
        assert f"Looking for <code>{folder / 'GONE'}</code>" in page
        assert "Reported by the metadata CSV" in page

    def test_a_missing_clf_names_the_clf_and_its_amf(self, tmp_path: Path) -> None:
        folder = turnover(tmp_path)
        clf = next(folder.glob("*.clf"))
        clf.unlink()
        item = titled(only(scanned(folder)), fixit.ADVICE["QC-076"].title)
        clip = item.clips[0]
        assert clip.looked_for == str(folder / clf.name) and clip.named_by.startswith("the AMF (")

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
