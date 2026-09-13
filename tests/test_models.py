"""Model behaviour and JSON round-tripping.

The batch file is schema versioned and must survive a crash, so to_dict and
from_dict being exact inverses is a hard requirement, not a convenience.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from proingest.core.models import (
    CDL,
    SCHEMA_VERSION,
    Batch,
    Deliverable,
    FrameRate,
    InOut,
    MediaInfo,
    QCResult,
    ShotRow,
    SideFiles,
    Turnover,
)
from proingest.core.naming import ShotIdentity


def make_media(**overrides: object) -> MediaInfo:
    defaults: dict[str, object] = {
        "path": Path("/turnover/MELT0001_pl01.exr"),
        "codec": "exr",
        "pixel_format": "gbrpf32le",
        "width": 3840,
        "height": 2160,
        "rate": FrameRate(24),
        "frame_count": 300,
        "start_frame": 1001,
        "start_timecode": 86400,
        "is_sequence": True,
        "size": 123,
        "mtime": 1.5,
    }
    return MediaInfo(**{**defaults, **overrides})  # type: ignore[arg-type]


def make_row(**overrides: object) -> ShotRow:
    defaults: dict[str, object] = {
        "turnover_id": "t1",
        "clip_name": "MELT0001_pl01",
        "identity": ShotIdentity(show="MELT", shot="0001", elem_type="pl", elem_index="01"),
        "media": make_media(),
        "record_in": 0,
        "record_out": 239,
        "snapshot": InOut(1001, 1240),
        "current": InOut(1001, 1240),
    }
    return ShotRow(**{**defaults, **overrides})  # type: ignore[arg-type]


class TestFrameRate:
    def test_whole_number(self) -> None:
        assert FrameRate(24).as_float() == 24.0
        assert str(FrameRate(24)) == "24"

    def test_ntsc_is_exact(self) -> None:
        rate = FrameRate.from_float(23.976)
        assert (rate.numerator, rate.denominator) == (24000, 1001)
        assert str(rate) == "24000/1001"

    def test_ntsc_counts_at_the_whole_rate(self) -> None:
        """23.976 counts 24 frames per timecode second."""
        assert FrameRate.from_float(23.976).nominal() == 24
        assert FrameRate.from_float(29.97).nominal() == 30

    def test_equality_is_exact(self) -> None:
        """QC-025 and QC-026 compare rates directly, so no float tolerance is involved."""
        assert FrameRate(24) == FrameRate(24)
        assert FrameRate(24) != FrameRate(24000, 1001)

    def test_from_float_whole(self) -> None:
        assert FrameRate.from_float(24.0) == FrameRate(24)

    def test_rejects_unsupported(self) -> None:
        with pytest.raises(ValueError):
            FrameRate.from_float(23.5)

    def test_rejects_non_positive(self) -> None:
        with pytest.raises(ValueError):
            FrameRate(0)

    def test_round_trip(self) -> None:
        rate = FrameRate(24000, 1001)
        assert FrameRate.from_dict(rate.to_dict()) == rate


class TestInOut:
    def test_duration_is_inclusive(self) -> None:
        assert InOut(1001, 1240).duration == 240
        assert InOut(5, 5).duration == 1

    def test_round_trip(self) -> None:
        value = InOut(100, 200)
        assert InOut.from_dict(value.to_dict()) == value


class TestMediaInfo:
    def test_max_available_out(self) -> None:
        assert make_media(start_frame=1001, frame_count=300).max_available_out == 1300

    def test_resolution(self) -> None:
        assert make_media().resolution == (3840, 2160)

    def test_cache_key_changes_with_size_and_mtime(self) -> None:
        """FR-3 keys the probe cache on path, size and mtime."""
        base = make_media()
        assert base.cache_key() != make_media(size=999).cache_key()
        assert base.cache_key() != make_media(mtime=99.0).cache_key()

    def test_round_trip(self) -> None:
        media = make_media()
        assert MediaInfo.from_dict(media.to_dict()) == media

    def test_round_trip_with_container_tags(self) -> None:
        """The tags are a carrier for the source encoding (M4.6.4), so they have to survive."""
        media = make_media(tags={"Input Color Space": "S-Log3 S-Gamut3.Cine"})
        assert MediaInfo.from_dict(media.to_dict()).tags == media.tags

    def test_media_saved_before_tags_existed_reads_back_with_none(self) -> None:
        data = make_media().to_dict()
        del data["tags"]
        assert MediaInfo.from_dict(data).tags == {}

    def test_round_trip_without_timecode(self) -> None:
        """No embedded timecode is QC-028, and must survive serialization as None."""
        media = make_media(start_timecode=None)
        assert MediaInfo.from_dict(media.to_dict()).start_timecode is None


class TestShotRow:
    def test_shot_code_from_identity(self) -> None:
        assert make_row().shot_code == "MELT0001"

    def test_override_wins(self) -> None:
        """The editor corrects a shooter's typo; names re-derive from the correction."""
        assert make_row(shot_code_override="MELT0002").shot_code == "MELT0002"

    def test_shot_code_is_none_when_unparsed(self) -> None:
        assert make_row(identity=None).shot_code is None

    def test_duration_and_max_available(self) -> None:
        row = make_row()
        assert row.duration == 240
        assert row.max_available_out == 1300

    def test_duration_is_none_without_current(self) -> None:
        assert make_row(current=None).duration is None

    def test_was_edited_tracks_the_snapshot(self) -> None:
        assert not make_row().was_edited
        assert make_row(current=InOut(1001, 1300)).was_edited

    def test_was_edited_is_false_without_a_snapshot(self) -> None:
        assert not make_row(snapshot=None).was_edited

    def test_severity_filters(self) -> None:
        row = make_row(
            qc=[
                QCResult("QC-010", "error", "row", "bad name"),
                QCResult("QC-030", "warning", "row", "short handles"),
                QCResult("QC-035", "info", "row", "edited"),
            ]
        )
        assert [r.rule_id for r in row.errors()] == ["QC-010"]
        assert [r.rule_id for r in row.warnings()] == ["QC-030"]

    def test_round_trip(self) -> None:
        row = make_row(
            side_files=SideFiles(hdri=Path("/t/h.exr"), camdata=Path("/t/c.rtf")),
            audio_path=Path("/t/a.wav"),
            notes="watch the flare",
            skipped=True,
            skip_reason="blocked by QC-012",
            deliverables=[Deliverable("raw", "n.exr", Path("/d/n.exr"), 1, res="4k")],
            qc=[QCResult("QC-030", "warning", "row", "handles")],
            source_encoding="S-Log3 S-Gamut3.Cine",
            source_encoding_origin="clip metadata",
        )
        assert ShotRow.from_dict(row.to_dict()) == row

    def test_a_row_saved_before_the_encoding_existed_reads_back_naming_none(self) -> None:
        """Additive, so the schema version does not move (M4.6.1)."""
        data = make_row().to_dict()
        del data["source_encoding"]
        assert ShotRow.from_dict(data).source_encoding is None

    def test_a_row_saved_before_the_origin_existed_reads_back_naming_none(self) -> None:
        """Additive, so the schema version does not move (M4.6.5)."""
        data = make_row(source_encoding="C-Log3").to_dict()
        del data["source_encoding_origin"]
        read = ShotRow.from_dict(data)
        assert read.source_encoding == "C-Log3"
        assert read.source_encoding_origin is None

    def test_round_trip_of_what_the_colour_session_wrote(self) -> None:
        """A batch reopened after the package is archived renders the same grade."""
        row = make_row(
            approved=InOut(1008, 1223),
            cdl=CDL(
                slope=(1.02, 0.99, 1.01),
                offset=(0.001, -0.002, 0.0),
                power=(0.98, 1.0, 1.02),
                saturation=1.05,
                sop_text="(1.02 0.99 1.01)(0.001 -0.002 0.0)(0.98 1.0 1.02)",
                sat_text="1.05",
            ),
            clf_path=Path("/session/MELT0001_grade.clf"),
        )
        assert ShotRow.from_dict(row.to_dict()) == row

    def test_a_row_saved_before_the_session_was_ingestible_reads_back_bare(self) -> None:
        """Additive, so the schema version does not move (M5.7.1)."""
        data = make_row().to_dict()
        del data["approved"]
        del data["cdl"]
        read = ShotRow.from_dict(data)
        assert read.approved is None
        assert read.cdl is None

    def test_round_trip_of_an_unparsed_row(self) -> None:
        """A QC-010 row still appears so the editor can fix the name in place."""
        row = ShotRow(turnover_id="t1", clip_name="garbage name", identity=None)
        assert ShotRow.from_dict(row.to_dict()) == row


class TestTurnover:
    def test_stringout_fields_complete(self) -> None:
        turnover = Turnover("t1", Path("/t"), number=1, month=2, day=23, year=2026, shooter="dan")
        assert turnover.has_stringout_fields

    @pytest.mark.parametrize("missing", ["number", "month", "day", "year", "shooter"])
    def test_stringout_fields_incomplete(self, missing: str) -> None:
        fields: dict[str, object] = {
            "number": 1,
            "month": 2,
            "day": 23,
            "year": 2026,
            "shooter": "dan",
        }
        fields[missing] = None if missing != "shooter" else ""
        turnover = Turnover("t1", Path("/t"), **fields)  # type: ignore[arg-type]
        assert not turnover.has_stringout_fields

    def test_round_trip(self) -> None:
        turnover = Turnover(
            "t1",
            Path("/t"),
            timeline_path=Path("/t/a.otio"),
            color_session_edl=Path("/session/MELT_FINAL.edl"),
            number=1,
            shooter="Daniel Luckett",
        )
        assert Turnover.from_dict(turnover.to_dict()) == turnover

    def test_a_turnover_saved_before_the_session_existed_has_ingested_nothing(self) -> None:
        """Additive, so the schema version does not move (M5.7.1)."""
        data = Turnover("t1", Path("/t")).to_dict()
        del data["color_session_edl"]
        assert Turnover.from_dict(data).color_session_edl is None


class TestBatch:
    def test_rows_for_filters_by_turnover(self) -> None:
        batch = Batch(rows=[make_row(turnover_id="t1"), make_row(turnover_id="t2")])
        assert len(batch.rows_for("t1")) == 1

    def test_round_trip_through_real_json(self) -> None:
        batch = Batch(
            name="melt_day1",
            source_root=Path("/source"),
            delivery_root=Path("/delivery"),
            turnovers=[Turnover("t1", Path("/t"), number=1)],
            rows=[make_row()],
            probe_cache={"k": make_media()},
        )
        restored = Batch.from_dict(json.loads(json.dumps(batch.to_dict())))
        assert restored == batch

    def test_a_batch_saved_before_the_source_root_existed_still_reads(self) -> None:
        """Additive, like every other field added after the schema was frozen."""
        data = Batch().to_dict()
        del data["source_root"]
        assert Batch.from_dict(data).source_root is None

    def test_empty_batch_round_trips(self) -> None:
        assert Batch.from_dict(json.loads(json.dumps(Batch().to_dict()))) == Batch()

    def test_schema_version_is_recorded(self) -> None:
        assert Batch().to_dict()["schema_version"] == SCHEMA_VERSION

    def test_unknown_schema_version_is_refused(self) -> None:
        """Better to refuse than to silently misread a future batch file."""
        data = Batch().to_dict()
        data["schema_version"] = 99
        with pytest.raises(ValueError, match="schema version"):
            Batch.from_dict(data)
