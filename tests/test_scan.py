"""Scanning a turnover folder into shot rows, and the QC the scan uncovers."""

from __future__ import annotations

from pathlib import Path

import pytest

from proingest.core import scan
from proingest.core.models import Batch, ShotRow
from tests.fixtures import media as fixtures

GOOD_FOLDER = "turnover001_02_23_2026_danielluckett"


def rules(row: ShotRow) -> set[str]:
    return {result.rule_id for result in row.qc}


def turnover_rules(batch: Batch) -> set[str]:
    return {result.rule_id for turnover in batch.turnovers for result in turnover.qc}


class TestParseTurnoverFolder:
    def test_parses_the_documented_pattern(self) -> None:
        fields = scan.parse_turnover_folder(Path(f"/x/{GOOD_FOLDER}"))
        assert fields is not None
        assert (fields.number, fields.month, fields.day, fields.year) == (1, 2, 23, 2026)
        assert fields.shooter == "danielluckett"

    @pytest.mark.parametrize(
        "name", ["messy", "turnover1_02_23_2026_dan", "turnover001_2_23_2026_dan", "turnover001"]
    )
    def test_rejects_other_names(self, name: str) -> None:
        assert scan.parse_turnover_folder(Path(f"/x/{name}")) is None


class TestScanTurnover:
    def test_happy_path(self, tmp_path: Path) -> None:
        folder = tmp_path / GOOD_FOLDER
        fixtures.make_turnover(folder, shots=2, frames=6, side_files=True)
        settings = scan.ScanSettings(rules=fixtures.SMALL_RULES)
        turnover, rows = scan.scan_turnover(folder, "t1", settings)

        assert turnover.number == 1
        assert turnover.shooter == "danielluckett"
        assert turnover.has_stringout_fields
        assert turnover.qc == []
        assert len(rows) == 2
        assert all(row.qc == [] for row in rows)

    def test_rows_carry_identity_media_and_ranges(self, tmp_path: Path) -> None:
        folder = tmp_path / GOOD_FOLDER
        fixtures.make_turnover(folder, shots=1, frames=6)
        _, rows = scan.scan_turnover(folder, "t1")
        row = rows[0]

        assert row.shot_code == "MELT0001"
        assert row.identity is not None and row.identity.elem == "pl01"
        assert row.media is not None and row.media.is_sequence
        assert row.current == row.snapshot, "a fresh scan has not been edited"
        assert row.duration == 6
        assert row.audio_path is not None

    def test_the_path_map_reaches_the_audio_as_well_as_the_picture(self, tmp_path: Path) -> None:
        """QC-016 rewrites the picture URL onto the local mount; the audio URL came from
        the same machine and has to go through the same map."""
        folder = tmp_path / GOOD_FOLDER
        fixtures.make_turnover(folder, shots=1, frames=6)
        media_dir = folder / "media"
        foreign = "file:///G:/turnover/media"
        fixtures.make_otio(
            folder / "turnover001.otio",
            [("MELT0001_pl01", f"{foreign}/MELT0001_pl01.1001.exr")],
            duration=6,
            source_start=86400,
            available_start=86400,
            available_duration=6,
            audio_clips=[("MELT0001_pl01_audio", f"{foreign}/MELT0001_pl01.wav")],
        )
        settings = scan.ScanSettings(path_map={"G:/turnover/media": str(media_dir)})
        _, rows = scan.scan_turnover(folder, "t1", settings)

        assert rows[0].media is not None, "the picture was remapped"
        assert rows[0].audio_path == media_dir / "MELT0001_pl01.wav"
        assert rows[0].audio is not None, "and so was the audio"

    def test_snapshot_matches_the_timeline_range(self, tmp_path: Path) -> None:
        """The snapshot is what the turnover arrived with; QC-035 compares against it."""
        folder = tmp_path / GOOD_FOLDER
        fixtures.make_turnover(folder, shots=1, frames=6)
        _, rows = scan.scan_turnover(folder, "t1")
        assert rows[0].snapshot is not None
        assert rows[0].snapshot.duration == 6

    def test_unparseable_clip_name_still_produces_a_row(self, tmp_path: Path) -> None:
        """QC-010: the row must appear so the editor can fix the name in place."""
        folder = tmp_path / GOOD_FOLDER
        sequence = fixtures.make_exr_sequence(folder / "media", base="garbage", count=4)
        fixtures.make_otio(
            folder / "t.otio",
            [("garbage", sequence.path_for(1001).as_uri())],
            duration=4,
            available_duration=4,
        )
        _, rows = scan.scan_turnover(folder, "t1")
        assert len(rows) == 1
        assert rows[0].identity is None
        assert "QC-010" in rules(rows[0])

    def test_missing_media_is_qc_012(self, tmp_path: Path) -> None:
        folder = tmp_path / GOOD_FOLDER
        folder.mkdir(parents=True)
        fixtures.make_otio(
            folder / "t.otio", [("MELT0001_pl01", "file:///nowhere/x.exr")], duration=4
        )
        _, rows = scan.scan_turnover(folder, "t1")
        assert "QC-012" in rules(rows[0])
        assert rows[0].media is None

    def test_qc_012_names_the_path_the_timeline_claimed(self, tmp_path: Path) -> None:
        """Nothing stores it once the row has no media, so the rule's message is the
        only record of what the timeline asked for (UI_SPEC section 12.3)."""
        folder = tmp_path / GOOD_FOLDER
        folder.mkdir(parents=True)
        fixtures.make_otio(
            folder / "t.otio", [("MELT0001_pl01", "file:///nowhere/x.exr")], duration=4
        )
        _, rows = scan.scan_turnover(folder, "t1")
        message = next(r.message for r in rows[0].qc if r.rule_id == "QC-012")
        assert "/nowhere/x.exr is missing" in message

    def test_a_clip_referencing_no_path_at_all_says_that_instead(self, tmp_path: Path) -> None:
        folder = tmp_path / GOOD_FOLDER
        folder.mkdir(parents=True)
        fixtures.make_otio(folder / "t.otio", [("MELT0001_pl01", "")], duration=4)
        _, rows = scan.scan_turnover(folder, "t1")
        message = next(r.message for r in rows[0].qc if r.rule_id == "QC-012")
        assert "references no path" in message

    def test_ambiguous_media_is_qc_013(self, tmp_path: Path) -> None:
        folder = tmp_path / GOOD_FOLDER
        fixtures.make_exr_sequence(folder / "a", base="MELT0001_pl01", count=4)
        fixtures.make_exr_sequence(folder / "b", base="MELT0001_pl01", count=4)
        fixtures.make_otio(
            folder / "t.otio", [("MELT0001_pl01", "file:///nowhere/x.exr")], duration=4
        )
        _, rows = scan.scan_turnover(folder, "t1")
        assert "QC-013" in rules(rows[0])

    def test_sequence_gap_is_qc_015(self, tmp_path: Path) -> None:
        folder = tmp_path / GOOD_FOLDER
        sequence = fixtures.make_exr_sequence(folder / "media", base="MELT0001_pl01", count=6)
        sequence.path_for(1003).unlink()
        fixtures.make_otio(
            folder / "t.otio",
            [("MELT0001_pl01", sequence.path_for(1001).as_uri())],
            duration=4,
            available_duration=6,
        )
        _, rows = scan.scan_turnover(folder, "t1")
        assert "QC-015" in rules(rows[0])

    def test_range_beyond_the_media_is_qc_029(self, tmp_path: Path) -> None:
        folder = tmp_path / GOOD_FOLDER
        sequence = fixtures.make_exr_sequence(folder / "media", base="MELT0001_pl01", count=4)
        fixtures.make_otio(
            folder / "t.otio",
            [("MELT0001_pl01", sequence.path_for(1001).as_uri())],
            duration=100,
            available_duration=100,
        )
        _, rows = scan.scan_turnover(folder, "t1")
        assert "QC-029" in rules(rows[0])

    def test_media_found_by_name_when_the_url_is_wrong(self, tmp_path: Path) -> None:
        """FR-2: a unique filename match resolves silently."""
        folder = tmp_path / GOOD_FOLDER
        fixtures.make_exr_sequence(folder / "media", base="MELT0001_pl01", count=4)
        fixtures.make_otio(
            folder / "t.otio",
            [("MELT0001_pl01", "file:///wrong/place/MELT0001_pl01.1001.exr")],
            duration=4,
            available_duration=4,
        )
        _, rows = scan.scan_turnover(folder, "t1")
        assert rows[0].media is not None
        assert "QC-012" not in rules(rows[0])

    def test_side_files_are_discovered(self, tmp_path: Path) -> None:
        folder = tmp_path / GOOD_FOLDER
        fixtures.make_turnover(folder, shots=1, frames=4)
        (folder / "media" / "MELT0001_pl01_HDRI.exr").write_bytes(b"x")
        (folder / "media" / "MELT0001_pl01_camData.txt").write_text("iso: 800")
        _, rows = scan.scan_turnover(folder, "t1")
        assert rows[0].side_files.hdri is not None
        assert rows[0].side_files.camdata is not None

    def test_a_side_file_in_the_wrong_format_is_not_matched(self, tmp_path: Path) -> None:
        """NAMING_SPEC section 2 matches `*HDRI*.exr`, not any file with HDRI in the name.

        Delivery renames without converting, so a jpeg picked up here would ship under
        an `.exr` name.
        """
        folder = tmp_path / GOOD_FOLDER
        fixtures.make_turnover(folder, shots=1, frames=4)
        (folder / "media" / "MELT0001_pl01_HDRI_preview.jpg").write_bytes(b"x")
        (folder / "media" / "MELT0001_pl01_camData.pdf").write_bytes(b"x")
        _, rows = scan.scan_turnover(folder, "t1")
        assert rows[0].side_files.hdri is None
        assert rows[0].side_files.camdata is None

    def test_the_real_side_file_still_wins_beside_a_preview(self, tmp_path: Path) -> None:
        folder = tmp_path / GOOD_FOLDER
        fixtures.make_turnover(folder, shots=1, frames=4)
        (folder / "media" / "MELT0001_pl01_HDRI.exr").write_bytes(b"x")
        (folder / "media" / "MELT0001_pl01_HDRI_preview.jpg").write_bytes(b"x")
        _, rows = scan.scan_turnover(folder, "t1")
        assert rows[0].side_files.hdri == folder / "media" / "MELT0001_pl01_HDRI.exr"

    def test_no_side_files_leaves_them_none(self, tmp_path: Path) -> None:
        folder = tmp_path / GOOD_FOLDER
        fixtures.make_turnover(folder, shots=1, frames=4)
        _, rows = scan.scan_turnover(folder, "t1")
        assert rows[0].side_files.hdri is None


class TestSourceEncoding:
    """Reading the encoding off the clip. COLOR_AND_FORMAT section 1, OQ-44, M4.6.4."""

    def scanned(self, tmp_path: Path, **turnover: object) -> ShotRow:
        folder = tmp_path / GOOD_FOLDER
        fixtures.make_turnover(folder, shots=1, frames=4, **turnover)  # type: ignore[arg-type]
        settings = scan.ScanSettings(rules=fixtures.SMALL_RULES)
        return scan.scan_turnover(folder, "t1", settings)[1][0]

    def test_the_clip_s_own_metadata_is_read_verbatim(self, tmp_path: Path) -> None:
        """Stored as written, because QC-047 has to quote it back at whoever typed it."""
        row = self.scanned(tmp_path, source_encoding="C-Log3")
        assert row.source_encoding == "C-Log3"
        assert row.source_encoding_origin == "clip metadata"

    def test_a_clip_that_names_none_has_no_origin_either(self, tmp_path: Path) -> None:
        """Nothing wrote it, so there is nobody to trace a wrong one back to (M4.6.5)."""
        row = self.scanned(tmp_path, source_encoding=None)
        assert row.source_encoding_origin is None

    def test_a_clip_that_names_none_says_so_rather_than_guessing(self, tmp_path: Path) -> None:
        row = self.scanned(tmp_path, source_encoding=None)
        assert row.source_encoding is None
        assert "QC-046" in rules(row)

    def test_a_row_that_names_one_raises_nothing(self, tmp_path: Path) -> None:
        row = self.scanned(tmp_path, source_encoding="ACEScct")
        assert not {"QC-046", "QC-047"} & rules(row)

    def test_a_name_the_table_cannot_resolve_is_qc_047(self, tmp_path: Path) -> None:
        """A plate renders regardless, so it is a warning here and an error on an aux still."""
        row = self.scanned(tmp_path, source_encoding="S-Log3")
        assert row.source_encoding == "S-Log3"
        assert "QC-047" in rules(row)

    def test_the_container_s_tags_are_the_second_carrier(self, tmp_path: Path) -> None:
        """The timeline first, the file second: a media file outlives the session (OQ-44)."""
        clip = fixtures.clip_record("MELT0001_pl01", metadata={})
        row = ShotRow(turnover_id="t1", clip_name="MELT0001_pl01")
        row.media = fixtures.media_info_with_tags({scan.SOURCE_ENCODING_KEY: "BM Film"})
        assert scan._source_encoding(clip, row, scan.SOURCE_ENCODING_KEY) == (
            "BM Film",
            "container tag",
        )

    def test_the_clip_wins_over_the_container(self, tmp_path: Path) -> None:
        clip = fixtures.clip_record(
            "MELT0001_pl01", metadata={scan.SOURCE_ENCODING_KEY: "C-Log3"}
        )
        row = ShotRow(turnover_id="t1", clip_name="MELT0001_pl01")
        row.media = fixtures.media_info_with_tags({scan.SOURCE_ENCODING_KEY: "BM Film"})
        assert scan._source_encoding(clip, row, scan.SOURCE_ENCODING_KEY) == (
            "C-Log3",
            "clip metadata",
        )

    def test_a_field_that_is_there_and_empty_is_no_field(self, tmp_path: Path) -> None:
        """QC-046's own words: the field is absent, or empty."""
        clip = fixtures.clip_record("MELT0001_pl01", metadata={scan.SOURCE_ENCODING_KEY: "   "})
        row = ShotRow(turnover_id="t1", clip_name="MELT0001_pl01")
        assert scan._source_encoding(clip, row, scan.SOURCE_ENCODING_KEY) == (None, None)

    def test_the_field_name_is_a_setting(self, tmp_path: Path) -> None:
        """OQ-44's answer is a different field name and nothing else."""
        clip = fixtures.clip_record("MELT0001_pl01", metadata={"Camera Log": "C-Log3"})
        row = ShotRow(turnover_id="t1", clip_name="MELT0001_pl01")
        assert scan._source_encoding(clip, row, "camera log") == ("C-Log3", "clip metadata")


class TestTurnoverLevelProblems:
    def test_no_timeline_is_qc_001(self, tmp_path: Path) -> None:
        folder = tmp_path / GOOD_FOLDER
        folder.mkdir(parents=True)
        turnover, rows = scan.scan_turnover(folder, "t1")
        assert {r.rule_id for r in turnover.qc} == {"QC-001"}
        assert rows == []

    def test_unparseable_timeline_is_qc_002(self, tmp_path: Path) -> None:
        folder = tmp_path / GOOD_FOLDER
        folder.mkdir(parents=True)
        (folder / "broken.otio").write_text("{nope")
        turnover, rows = scan.scan_turnover(folder, "t1")
        assert "QC-002" in {r.rule_id for r in turnover.qc}
        assert rows == []

    def test_unmatched_folder_name_is_qc_005(self, tmp_path: Path) -> None:
        folder = tmp_path / "messy"
        fixtures.make_turnover(folder, shots=1, frames=4)
        turnover, _ = scan.scan_turnover(folder, "t1")
        assert "QC-005" in {r.rule_id for r in turnover.qc}
        assert not turnover.has_stringout_fields

    def test_a_bad_turnover_does_not_raise(self, tmp_path: Path) -> None:
        """One bad folder must not take down a batch."""
        folder = tmp_path / "empty"
        folder.mkdir()
        turnover, rows = scan.scan_turnover(folder, "t1")
        assert rows == []
        assert turnover.qc


class TestScanBatch:
    def test_scans_several_turnovers(self, tmp_path: Path) -> None:
        first = tmp_path / "turnover001_02_23_2026_dan"
        second = tmp_path / "turnover002_02_24_2026_sam"
        fixtures.make_turnover(first, shots=2, frames=4)
        fixtures.make_turnover(second, shots=1, frames=4)

        batch = scan.scan_batch([first, second], name="melt")
        assert len(batch.turnovers) == 2
        assert len(batch.rows) == 3
        assert len(batch.rows_for("t1")) == 2
        assert len(batch.rows_for("t2")) == 1

    def test_probe_cache_is_shared_across_turnovers(self, tmp_path: Path) -> None:
        """FR-3 probes each media item once; the cache is per batch, not per turnover."""
        folder = tmp_path / "turnover001_02_23_2026_dan"
        fixtures.make_turnover(folder, shots=2, frames=4)
        batch = scan.scan_batch([folder])
        assert len(batch.probe_cache) == 2

    def test_a_broken_turnover_does_not_stop_the_others(self, tmp_path: Path) -> None:
        good = tmp_path / "turnover001_02_23_2026_dan"
        broken = tmp_path / "turnover002_02_24_2026_sam"
        fixtures.make_turnover(good, shots=1, frames=4)
        broken.mkdir(parents=True)

        batch = scan.scan_batch([good, broken])
        assert len(batch.rows) == 1
        assert "QC-001" in turnover_rules(batch)
