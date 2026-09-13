"""Timeline loading, clip extraction and audio association (FR-1)."""

from __future__ import annotations

from pathlib import Path

import pytest

from proingest.core import timeline
from proingest.core.models import FrameRate
from proingest.core.timeline import ClipRecord, TimelineError
from tests.fixtures import media as fixtures

URL = "file:///G:/t/MELT0001_pl01.exr"


def clip(record_start: int, duration: int, name: str = "c", track: str = "V1") -> ClipRecord:
    return ClipRecord(
        name=name, track=track, record_start=record_start, duration=duration, source_start=0
    )


class TestClipRecord:
    def test_record_end_is_inclusive(self) -> None:
        assert clip(100, 240).record_end == 339

    @pytest.mark.parametrize(
        ("a_start", "a_len", "b_start", "b_len", "expected"),
        [
            (0, 100, 0, 100, True),  # identical
            (0, 100, 50, 100, True),  # partial
            (0, 100, 99, 10, True),  # one frame of overlap
            (0, 100, 100, 10, False),  # abutting, not overlapping
            (0, 100, 200, 10, False),  # disjoint
            (100, 10, 0, 100, False),  # abutting the other way
        ],
    )
    def test_overlap(
        self, a_start: int, a_len: int, b_start: int, b_len: int, expected: bool
    ) -> None:
        assert clip(a_start, a_len).overlaps(clip(b_start, b_len)) is expected

    def test_overlap_is_symmetric(self) -> None:
        first, second = clip(0, 100), clip(50, 100)
        assert first.overlaps(second) == second.overlaps(first)

    def test_source_offset_uses_the_available_range(self) -> None:
        """source_range is in media coordinates, so the media's own start is the origin."""
        record = ClipRecord("c", "V1", 0, 240, source_start=86430, available_start=86400)
        assert record.source_offset() == 30

    def test_source_offset_without_an_available_range(self) -> None:
        """An EDL states no media range, so the source range is already an offset."""
        assert ClipRecord("c", "V1", 0, 240, source_start=30).source_offset() == 30


class TestFlattenMetadata:
    """The walk that finds a named field wherever Resolve nested it (M4.6.4, OQ-44)."""

    def test_a_nested_field_is_found_by_its_own_name(self) -> None:
        tree = {"Resolve_OTIO": {"Clip Properties": {"Input Color Space": "S-Log3 S-Gamut3"}}}
        assert timeline.flatten_metadata(tree)["Input Color Space"] == "S-Log3 S-Gamut3"

    def test_the_outer_spelling_of_a_name_wins(self) -> None:
        """An outer field is the one a person filled in; a nested copy is an export detail."""
        tree = {"Input Color Space": "C-Log3", "Resolve_OTIO": {"Input Color Space": "BM Film"}}
        assert timeline.flatten_metadata(tree)["Input Color Space"] == "C-Log3"

    def test_non_strings_are_dropped(self) -> None:
        """The one thing read from here is a colour space name somebody typed."""
        flat = timeline.flatten_metadata({"frames": 240, "name": "MELT0001", "ok": True})
        assert flat == {"name": "MELT0001"}

    def test_nothing_at_all_is_an_empty_dict(self) -> None:
        assert timeline.flatten_metadata(None) == {}


class TestLoad:
    def test_reads_clips(self, tmp_path: Path) -> None:
        path = fixtures.make_otio(tmp_path / "t.otio", [("MELT0001_pl01", URL)])
        loaded = timeline.load(path)
        assert [c.name for c in loaded.video] == ["MELT0001_pl01"]
        assert loaded.rate == FrameRate(24)
        assert not loaded.is_edl

    def test_reads_multiple_clips_in_record_order(self, tmp_path: Path) -> None:
        path = fixtures.make_otio(
            tmp_path / "t.otio",
            [("MELT0001_pl01", URL), ("MELT0002_pl01", URL), ("MELT0003_pl01", URL)],
            duration=100,
        )
        loaded = timeline.load(path)
        assert [c.name for c in loaded.video] == [
            "MELT0001_pl01",
            "MELT0002_pl01",
            "MELT0003_pl01",
        ]
        assert [c.record_start for c in loaded.video] == [0, 100, 200]

    def test_carries_the_media_url(self, tmp_path: Path) -> None:
        path = fixtures.make_otio(tmp_path / "t.otio", [("MELT0001_pl01", URL)])
        assert timeline.load(path).video[0].media_url == URL

    def test_source_offset_survives_the_round_trip(self, tmp_path: Path) -> None:
        path = fixtures.make_otio(
            tmp_path / "t.otio", [("MELT0001_pl01", URL)], source_start=86430, available_start=86400
        )
        assert timeline.load(path).video[0].source_offset() == 30

    def test_global_start_is_the_record_origin(self, tmp_path: Path) -> None:
        path = fixtures.make_otio(tmp_path / "t.otio", [("a", URL)], global_start=864000)
        assert timeline.load(path).global_start == 864000

    def test_audio_track_is_separated_from_video(self, tmp_path: Path) -> None:
        path = fixtures.make_otio(
            tmp_path / "t.otio", [("MELT0001_pl01", URL)], audio_clips=[("MELT0001_audio", URL)]
        )
        loaded = timeline.load(path)
        assert len(loaded.video) == 1
        assert len(loaded.audio) == 1
        assert loaded.audio[0].is_audio

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(TimelineError):
            timeline.load(tmp_path / "nope.otio")

    def test_unparseable_file_raises(self, tmp_path: Path) -> None:
        """QC-002 is built on this failing cleanly."""
        bad = tmp_path / "bad.otio"
        bad.write_text("{not valid otio")
        with pytest.raises(TimelineError):
            timeline.load(bad)

    def test_drop_frame_defaults_to_false(self, tmp_path: Path) -> None:
        path = fixtures.make_otio(tmp_path / "t.otio", [("a", URL)])
        assert not timeline.load(path).is_drop_frame


class TestMultipleVideoTracks:
    def test_a_clip_on_v2_is_still_a_shot(self, tmp_path: Path) -> None:
        """FR-1 is explicit: a clip on a track other than V1 is still a shot."""
        import opentimelineio as otio
        from opentimelineio import opentime as ot

        tl = otio.schema.Timeline(name="two_tracks")
        for index, (track_name, clip_name) in enumerate(
            [("V1", "MELT0001_pl01"), ("V2", "MELT0002_el01")]
        ):
            track = otio.schema.Track(name=track_name, kind=otio.schema.TrackKind.Video)
            tl.tracks.append(track)
            track.append(
                otio.schema.Clip(
                    name=clip_name,
                    source_range=ot.TimeRange(ot.RationalTime(0, 24), ot.RationalTime(100, 24)),
                )
            )
            assert index >= 0
        path = tmp_path / "t.otio"
        otio.adapters.write_to_file(tl, str(path))

        loaded = timeline.load(path)
        assert {c.name for c in loaded.video} == {"MELT0001_pl01", "MELT0002_el01"}
        assert {c.track for c in loaded.video} == {"V1", "V2"}


class TestAudioAssociation:
    def test_overlapping_audio_is_associated(self, tmp_path: Path) -> None:
        path = fixtures.make_otio(
            tmp_path / "t.otio",
            [("MELT0001_pl01", URL)],
            duration=100,
            audio_clips=[("MELT0001_audio", URL)],
        )
        loaded = timeline.load(path)
        assert len(loaded.audio_for(loaded.video[0])) == 1

    def test_no_audio_returns_empty(self, tmp_path: Path) -> None:
        """Zero audio on a plate is QC-040, which the caller decides."""
        path = fixtures.make_otio(tmp_path / "t.otio", [("MELT0001_pl01", URL)])
        loaded = timeline.load(path)
        assert loaded.audio_for(loaded.video[0]) == []

    def test_two_overlapping_audio_clips_are_both_returned(self) -> None:
        """More than one is QC-041, so the association must not silently pick one."""
        video = clip(0, 100, name="v")
        loaded = timeline.Timeline(
            path=Path("t.otio"),
            rate=FrameRate(24),
            video=[video],
            audio=[clip(0, 100, name="a1"), clip(50, 100, name="a2")],
        )
        assert len(loaded.audio_for(video)) == 2

    def test_non_overlapping_audio_is_not_associated(self) -> None:
        video = clip(0, 100, name="v")
        loaded = timeline.Timeline(
            path=Path("t.otio"), rate=FrameRate(24), video=[video], audio=[clip(500, 100, name="a")]
        )
        assert loaded.audio_for(video) == []


class TestFindTimelineFiles:
    def test_finds_an_otio(self, tmp_path: Path) -> None:
        fixtures.make_otio(tmp_path / "turnover001.otio", [("a", URL)])
        assert len(timeline.find_timeline_files(tmp_path)) == 1

    def test_prefers_otio_over_edl(self, tmp_path: Path) -> None:
        fixtures.make_otio(tmp_path / "t.otio", [("a", URL)])
        (tmp_path / "t.edl").write_text("TITLE: t\n")
        found = timeline.find_timeline_files(tmp_path)
        assert found[0].suffix == ".otio"

    def test_finds_nothing_in_an_empty_folder(self, tmp_path: Path) -> None:
        """No timeline at all is QC-001."""
        assert timeline.find_timeline_files(tmp_path) == []

    def test_multiple_otio_files_are_all_returned(self, tmp_path: Path) -> None:
        """OQ-14: the user picks, so the finder must not choose for them."""
        fixtures.make_otio(tmp_path / "a.otio", [("a", URL)])
        fixtures.make_otio(tmp_path / "b.otio", [("b", URL)])
        assert len(timeline.find_timeline_files(tmp_path)) == 2

    def test_searches_subfolders(self, tmp_path: Path) -> None:
        fixtures.make_otio(tmp_path / "deep" / "nested" / "t.otio", [("a", URL)])
        assert len(timeline.find_timeline_files(tmp_path)) == 1


class TestEdlFallback:
    EDL = """TITLE: MELT_TURNOVER
FCM: NON-DROP FRAME

001  MELT0001 V     C        01:00:00:00 01:00:10:00 10:00:00:00 10:00:10:00
* FROM CLIP NAME: MELT0001_pl01
"""

    def test_reads_an_edl(self, tmp_path: Path) -> None:
        path = tmp_path / "t.edl"
        path.write_text(self.EDL)
        loaded = timeline.load(path)
        assert loaded.is_edl
        assert len(loaded.video) == 1

    def test_clip_name_comes_from_the_from_clip_name_comment(self, tmp_path: Path) -> None:
        path = tmp_path / "t.edl"
        path.write_text(self.EDL)
        assert timeline.load(path).video[0].name == "MELT0001_pl01"

    def test_drop_frame_edl_raises_the_specific_error(self, tmp_path: Path) -> None:
        """QC-027, not QC-002.

        otio rejects a drop-frame timecode at a non-drop rate with a generic parse
        error, so drop frame is detected from the text first and reported precisely.
        """
        path = tmp_path / "df.edl"
        path.write_text(self.EDL.replace("10:00:00:00 10:00:10:00", "10:00:00;00 10:00:10;00"))
        with pytest.raises(timeline.DropFrameError, match="QC-027"):
            timeline.load(path)

    def test_drop_frame_error_is_a_timeline_error(self, tmp_path: Path) -> None:
        """Callers that only care that loading failed still catch it."""
        path = tmp_path / "df.edl"
        path.write_text(self.EDL.replace("10:00:00:00 10:00:10:00", "10:00:00;00 10:00:10;00"))
        with pytest.raises(TimelineError):
            timeline.load(path)
