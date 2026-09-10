"""Directory indexing, sequence detection, path mapping and probing.

These tests generate real media and call real ffprobe, because the value of this
module is entirely in how it handles what ffprobe actually returns.
"""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

import pytest

from proingest.core import ffmpeg, media
from proingest.core.models import FrameRate, MediaInfo
from tests.fixtures import media as fixtures

RATE_24 = FrameRate(24)


class TestSequenceGrouping:
    def test_groups_a_sequence(self, tmp_path: Path) -> None:
        fixtures.make_exr_sequence(tmp_path, base="MELT0001_pl01", count=5)
        index = media.index_directory(tmp_path)
        assert len(index.sequences) == 1
        sequence = index.sequences[0]
        assert (sequence.base, sequence.count, sequence.first, sequence.last) == (
            "MELT0001_pl01",
            5,
            1001,
            1005,
        )

    def test_separate_sequences_stay_separate(self, tmp_path: Path) -> None:
        fixtures.make_exr_sequence(tmp_path, base="MELT0001_pl01", count=3)
        fixtures.make_exr_sequence(tmp_path, base="MELT0001_cp01", count=3)
        index = media.index_directory(tmp_path)
        assert {s.base for s in index.sequences} == {"MELT0001_pl01", "MELT0001_cp01"}

    def test_a_lone_numbered_file_is_a_still_not_a_sequence(self, tmp_path: Path) -> None:
        """One frame is a still. Treating it as a sequence would misreport durations."""
        fixtures.make_exr_sequence(tmp_path, base="MELT0001_pl01_colorChart_01", count=1)
        index = media.index_directory(tmp_path)
        assert index.sequences == []
        assert len(index.singles) == 1

    def test_finds_sequences_in_subfolders(self, tmp_path: Path) -> None:
        fixtures.make_exr_sequence(tmp_path / "plates" / "shot1", base="MELT0001_pl01", count=3)
        index = media.index_directory(tmp_path)
        assert len(index.sequences) == 1

    def test_non_media_files_are_singles(self, tmp_path: Path) -> None:
        (tmp_path / "MELT0001_pl01_camData_v01.txt").write_text("lens: 40mm")
        index = media.index_directory(tmp_path)
        assert index.sequences == []
        assert index.singles[0].suffix == ".txt"

    def test_empty_directory(self, tmp_path: Path) -> None:
        index = media.index_directory(tmp_path)
        assert index.sequences == [] and index.singles == []


class TestSequenceProperties:
    def test_contiguous_sequence_has_no_gaps(self, tmp_path: Path) -> None:
        fixtures.make_exr_sequence(tmp_path, count=5)
        sequence = media.index_directory(tmp_path).sequences[0]
        assert not sequence.has_gaps
        assert sequence.missing_frames == []

    def test_gaps_are_detected(self, tmp_path: Path) -> None:
        """QC-015: a hole in the numbering means frames are missing."""
        fixture = fixtures.make_exr_sequence(tmp_path, count=5)
        fixture.path_for(1003).unlink()
        sequence = media.index_directory(tmp_path).sequences[0]
        assert sequence.has_gaps
        assert sequence.missing_frames == [1003]

    def test_printf_pattern(self, tmp_path: Path) -> None:
        fixtures.make_exr_sequence(tmp_path, base="MELT0001_pl01", count=3)
        sequence = media.index_directory(tmp_path).sequences[0]
        assert sequence.printf_pattern().endswith("MELT0001_pl01.%04d.exr")

    def test_path_for_pads_correctly(self, tmp_path: Path) -> None:
        fixtures.make_exr_sequence(tmp_path, base="MELT0001_pl01", count=3)
        sequence = media.index_directory(tmp_path).sequences[0]
        assert sequence.path_for(1001).name == "MELT0001_pl01.1001.exr"
        assert sequence.path_for(1001).is_file()


class TestLookups:
    def test_media_matching(self, tmp_path: Path) -> None:
        fixtures.make_exr_sequence(tmp_path, base="MELT0001_pl01", count=3)
        index = media.index_directory(tmp_path)
        assert len(index.media_matching("MELT0001_pl01")) == 1
        assert index.media_matching("MELT0009_pl01") == []

    def test_ambiguous_match_returns_both(self, tmp_path: Path) -> None:
        """FR-2: many matches is QC-013, so the lookup must surface all of them."""
        fixtures.make_exr_sequence(tmp_path / "a", base="MELT0001_pl01", count=3)
        fixtures.make_exr_sequence(tmp_path / "b", base="MELT0001_pl01", count=3)
        assert len(media.index_directory(tmp_path).media_matching("MELT0001_pl01")) == 2

    def test_audio_matching(self, tmp_path: Path) -> None:
        fixtures.make_wav(tmp_path / "MELT0001_pl01.wav")
        assert len(media.index_directory(tmp_path).audio_matching("MELT0001_pl01")) == 1

    def test_containing_finds_side_files(self, tmp_path: Path) -> None:
        (tmp_path / "MELT0001_pl01_HDRI.exr").write_bytes(b"not really an exr")
        (tmp_path / "MELT0001_pl01_camData.txt").write_text("iso: 800")
        index = media.index_directory(tmp_path)
        assert len(index.containing("HDRI")) == 1
        assert len(index.containing("camdata")) == 1, "matching is case-insensitive"


class TestUrlToPath:
    @pytest.mark.parametrize(
        ("url", "expected"),
        [
            ("/Volumes/GoogleDrive/turnover/a.exr", "/Volumes/GoogleDrive/turnover/a.exr"),
            ("file:///Volumes/GoogleDrive/a.exr", "/Volumes/GoogleDrive/a.exr"),
            ("file:///G:/turnover/a.exr", "G:/turnover/a.exr"),
            ("file:///Volumes/My%20Drive/a.exr", "/Volumes/My Drive/a.exr"),
        ],
    )
    def test_converts(self, url: str, expected: str) -> None:
        assert media.url_to_path(url) == Path(expected)


class TestRemap:
    MAP: ClassVar[dict[str, str]] = {"/Volumes/GoogleDrive/Shared drives": "G:/Shared drives"}

    def test_rewrites_a_mapped_prefix(self) -> None:
        source = Path("/Volumes/GoogleDrive/Shared drives/turnover001/a.exr")
        assert media.remap(source, self.MAP) == Path("G:/Shared drives/turnover001/a.exr")

    def test_leaves_unmapped_paths_alone(self) -> None:
        source = Path("/some/other/place/a.exr")
        assert media.remap(source, self.MAP) == source

    def test_longest_prefix_wins(self) -> None:
        mapping = {"/Volumes": "X:/", "/Volumes/GoogleDrive": "G:/"}
        assert media.remap(Path("/Volumes/GoogleDrive/a.exr"), mapping) == Path("G:/a.exr")

    def test_is_case_insensitive(self) -> None:
        """The source paths come from macOS, so case cannot be relied on."""
        source = Path("/volumes/googledrive/Shared Drives/a.exr")
        mapping = {"/Volumes/GoogleDrive/Shared drives": "G:/x"}
        assert media.remap(source, mapping) == Path("G:/x/a.exr")

    def test_empty_map_is_a_no_op(self) -> None:
        assert media.remap(Path("/a/b.exr"), {}) == Path("/a/b.exr")


class TestProbe:
    def test_exr_sequence(self, tmp_path: Path) -> None:
        fixtures.make_exr_sequence(tmp_path, count=6, first=1001, size=(64, 36))
        sequence = media.index_directory(tmp_path).sequences[0]
        info = media.probe(sequence)
        assert info.is_sequence
        assert info.resolution == (64, 36)
        assert info.frame_count == 6
        assert info.start_frame == 1001
        assert info.max_available_out == 1006
        assert info.codec == "exr"

    def test_exr_sequence_rate_comes_from_the_header_not_ffprobe(self, tmp_path: Path) -> None:
        """ffprobe invents 25/1 for a single frame; the EXR header states the truth."""
        fixtures.make_exr_sequence(tmp_path, count=3, fps=24)
        sequence = media.index_directory(tmp_path).sequences[0]
        assert media.probe(sequence).rate == RATE_24

    def test_exr_timecode_comes_from_the_header(self, tmp_path: Path) -> None:
        """COLOR_AND_FORMAT section 5: source TC may come from the EXR header."""
        fixtures.make_exr_sequence(tmp_path, count=3, timecode="01:00:00:00")
        sequence = media.index_directory(tmp_path).sequences[0]
        assert media.probe(sequence).start_timecode == 86400

    def test_missing_timecode_is_none(self, tmp_path: Path) -> None:
        """No embedded timecode is QC-028, not a failure."""
        fixtures.make_exr_sequence(tmp_path, count=3, timecode=None)
        sequence = media.index_directory(tmp_path).sequences[0]
        assert media.probe(sequence).start_timecode is None

    def test_fallback_rate_is_used_when_media_cannot_say(self, tmp_path: Path) -> None:
        fixtures.make_dpx_sequence(tmp_path, count=3)
        sequence = media.index_directory(tmp_path).sequences[0]
        info = media.probe(sequence, fallback_rate=FrameRate(24))
        assert info.rate == RATE_24

    def test_mov_container(self, tmp_path: Path) -> None:
        fixtures.make_mov(tmp_path / "a.mov", count=8, timecode="01:00:00:00")
        info = media.probe(tmp_path / "a.mov")
        assert not info.is_sequence
        assert info.frame_count == 8
        assert info.start_frame == 0
        assert info.rate == RATE_24
        assert info.start_timecode == 86400

    def test_mov_with_audio(self, tmp_path: Path) -> None:
        fixtures.make_mov(tmp_path / "a.mov", count=8, with_audio=True)
        info = media.probe(tmp_path / "a.mov")
        assert info.has_audio
        assert info.audio_channels == 2
        assert info.audio_sample_rate == 48000

    def test_mp4_is_8bit_420(self, tmp_path: Path) -> None:
        """QC-020 rejects this as a linear plate; probing must report it accurately."""
        fixtures.make_mp4(tmp_path / "a.mp4", count=4)
        info = media.probe(tmp_path / "a.mp4")
        assert info.pixel_format == "yuv420p"
        assert info.codec == "h264"

    def test_unreadable_file_raises(self, tmp_path: Path) -> None:
        """QC-014 is built on this failing cleanly rather than crashing the scan."""
        bad = tmp_path / "broken.exr"
        bad.write_bytes(b"this is not an exr")
        with pytest.raises(ffmpeg.FFprobeError):
            media.probe(bad)

    def test_audio_only_file_has_no_video_stream(self, tmp_path: Path) -> None:
        fixtures.make_wav(tmp_path / "a.wav")
        with pytest.raises(ffmpeg.FFprobeError, match="no video stream"):
            media.probe(tmp_path / "a.wav")


class TestProbeCache:
    def test_second_probe_is_served_from_cache(self, tmp_path: Path) -> None:
        fixtures.make_exr_sequence(tmp_path, count=3)
        sequence = media.index_directory(tmp_path).sequences[0]
        cache: dict[str, MediaInfo] = {}
        first = media.probe_cached(sequence, cache)
        assert len(cache) == 1
        assert media.probe_cached(sequence, cache) is first, "same object, not re-probed"

    def test_changed_mtime_misses_the_cache(self, tmp_path: Path) -> None:
        """FR-3 keys on path, size and mtime, so a re-export re-probes itself."""
        fixtures.make_exr_sequence(tmp_path, count=3)
        sequence = media.index_directory(tmp_path).sequences[0]
        cache: dict[str, MediaInfo] = {}
        media.probe_cached(sequence, cache)
        touched = media.Sequence(**{**sequence.__dict__, "mtime": sequence.mtime + 100})
        media.probe_cached(touched, cache)
        assert len(cache) == 2


class TestToolResolution:
    def test_finds_ffprobe(self) -> None:
        assert ffmpeg.resolve_tool("ffprobe").is_file()

    def test_missing_override_is_reported(self, tmp_path: Path) -> None:
        with pytest.raises(ffmpeg.FFmpegNotFound):
            ffmpeg.resolve_tool("ffmpeg", override=tmp_path / "nope")

    def test_override_may_name_a_folder(self) -> None:
        real = ffmpeg.resolve_tool("ffprobe")
        assert ffmpeg.resolve_tool("ffprobe", override=real.parent) == real

    def test_version_string_is_recorded(self) -> None:
        """PACKAGING.md requires the ffmpeg version in every QC log."""
        assert "ffmpeg version" in ffmpeg.tool_info("ffmpeg").version.lower()


class TestConformedRate:
    """Shooters set every clip to the project rate in Resolve before exporting.

    That makes the timeline authoritative and can leave stale camera metadata in the
    media. Frame math must follow the timeline; QC-026 still needs to see the
    disagreement, so what the media claims is kept separately.
    """

    def test_timeline_rate_wins_over_a_stale_exr_header(self, tmp_path: Path) -> None:
        fixtures.make_exr_sequence(tmp_path, count=3, fps=24, header_fps=30)
        sequence = media.index_directory(tmp_path).sequences[0]
        info = media.probe(sequence, fallback_rate=RATE_24)
        assert info.rate == RATE_24, "frame math follows the conformed timeline"

    def test_the_stale_rate_is_still_recorded(self, tmp_path: Path) -> None:
        """QC-026 needs the disagreement, even though nothing computes with it."""
        fixtures.make_exr_sequence(tmp_path, count=3, fps=24, header_fps=30)
        sequence = media.index_directory(tmp_path).sequences[0]
        info = media.probe(sequence, fallback_rate=RATE_24)
        assert info.stated_rate == FrameRate(30)
        assert not info.rate_matches_timeline

    def test_agreeing_rates_match(self, tmp_path: Path) -> None:
        fixtures.make_exr_sequence(tmp_path, count=3, fps=24)
        sequence = media.index_directory(tmp_path).sequences[0]
        assert media.probe(sequence, fallback_rate=RATE_24).rate_matches_timeline

    def test_media_that_states_nothing_matches_by_definition(self, tmp_path: Path) -> None:
        """A DPX sequence claims no rate, so there is nothing to disagree with."""
        fixtures.make_dpx_sequence(tmp_path, count=3)
        sequence = media.index_directory(tmp_path).sequences[0]
        info = media.probe(sequence, fallback_rate=RATE_24)
        assert info.stated_rate is None
        assert info.rate_matches_timeline

    def test_timecode_is_read_at_the_conformed_rate(self, tmp_path: Path) -> None:
        """Reading 01:00:00:00 at a stale 30 would be off by a quarter."""
        fixtures.make_exr_sequence(tmp_path, count=3, timecode="01:00:00:00", header_fps=30)
        sequence = media.index_directory(tmp_path).sequences[0]
        info = media.probe(sequence, fallback_rate=RATE_24)
        assert info.start_timecode == 86400, "3600 seconds at 24, not at 30"

    def test_container_frame_count_uses_the_containers_own_rate(self, tmp_path: Path) -> None:
        """A file holds the frames it holds, whatever the timeline plays it at."""
        fixtures.make_mov(tmp_path / "a.mov", count=30, fps=30)
        info = media.probe(tmp_path / "a.mov", fallback_rate=RATE_24)
        assert info.rate == RATE_24
        assert info.stated_rate == FrameRate(30)
        assert info.frame_count == 30, "counting at 24 would have lost frames"

    def test_scan_passes_the_timeline_rate_through(self, tmp_path: Path) -> None:
        """The whole point: a scanned row uses the timeline's rate, not the media's."""
        from proingest.core import scan

        folder = tmp_path / "turnover001_02_23_2026_dan"
        sequence = fixtures.make_exr_sequence(
            folder / "media", base="MELT0001_pl01", count=6, fps=24, header_fps=30
        )
        fixtures.make_otio(
            folder / "t.otio",
            [("MELT0001_pl01", sequence.path_for(1001).as_uri())],
            fps=24,
            duration=6,
            available_duration=6,
        )
        _, rows = scan.scan_turnover(folder, "t1")
        assert rows[0].media is not None
        assert rows[0].media.rate == RATE_24
        assert rows[0].media.stated_rate == FrameRate(30)
