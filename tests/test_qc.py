"""Rate contract and audio sync rules.

Everything is conformed to the project rate in Resolve, so anything that disagrees
means a file escaped the conform and must be flagged rather than absorbed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from proingest.core import qc
from proingest.core.models import (
    AudioInfo,
    FrameRate,
    InOut,
    MediaInfo,
    QCResult,
    ShotRow,
    Turnover,
)

RATE_24 = FrameRate(24)
RATE_30 = FrameRate(30)
NTSC = FrameRate(24000, 1001)


def media(stated: FrameRate | None) -> MediaInfo:
    return MediaInfo(
        path=Path("/t/MELT0001_pl01.1001.exr"),
        codec="exr",
        pixel_format="gbrpf32le",
        width=3840,
        height=2160,
        rate=RATE_24,
        frame_count=240,
        start_frame=1001,
        stated_rate=stated,
    )


def row(stated: FrameRate | None = RATE_24, audio: AudioInfo | None = None) -> ShotRow:
    return ShotRow(
        turnover_id="t1",
        clip_name="MELT0001_pl01",
        media=media(stated),
        current=InOut(1001, 1240),
        audio=audio,
        audio_path=audio.path if audio else None,
    )


def audio_of(frames: int, sample_rate: int = 48000, rate: FrameRate = RATE_24) -> AudioInfo:
    """An audio file exactly `frames` long at the given project rate."""
    return AudioInfo(
        path=Path("/t/MELT0001_pl01.wav"),
        duration_samples=round(frames * sample_rate / rate.as_float()),
        sample_rate=sample_rate,
        channels=2,
        bit_depth=16,
    )


def ids(results: list[QCResult]) -> list[str]:
    return [result.rule_id for result in results]


class TestTimelineRate:
    def test_matching_rate_is_clean(self) -> None:
        turnover = Turnover("t1", Path("/t"))
        assert qc.check_timeline_rate(turnover, RATE_24, RATE_24) == []

    def test_mismatched_rate_is_qc_025(self) -> None:
        turnover = Turnover("t1", Path("/t"))
        results = qc.check_timeline_rate(turnover, RATE_30, RATE_24)
        assert ids(results) == ["QC-025"]
        assert results[0].severity == "error"
        assert results[0].scope == "turnover"

    def test_ntsc_does_not_pass_as_24(self) -> None:
        """23.976 and 24 are different rates, and exact comparison keeps them apart."""
        turnover = Turnover("t1", Path("/t"))
        assert ids(qc.check_timeline_rate(turnover, NTSC, RATE_24)) == ["QC-025"]


class TestSourceRate:
    def test_conformed_media_is_clean(self) -> None:
        assert qc.check_source_rate(row(stated=RATE_24), RATE_24) == []

    def test_unconformed_media_is_qc_026(self) -> None:
        """The file escaped the conform in Resolve, so the file gets flagged."""
        results = qc.check_source_rate(row(stated=RATE_30), RATE_24)
        assert ids(results) == ["QC-026"]
        assert results[0].severity == "error"
        assert "MELT0001_pl01.1001.exr" in results[0].message, "the message names the file"

    def test_media_that_states_no_rate_cannot_disagree(self) -> None:
        """A DPX sequence claims nothing, so there is nothing to flag."""
        assert qc.check_source_rate(row(stated=None), RATE_24) == []

    def test_a_row_with_no_media_is_skipped(self) -> None:
        assert qc.check_source_rate(ShotRow(turnover_id="t1", clip_name="x"), RATE_24) == []

    def test_ntsc_source_against_a_24_project_is_flagged(self) -> None:
        assert ids(qc.check_source_rate(row(stated=NTSC), RATE_24)) == ["QC-026"]


class TestAudioSync:
    def test_matching_duration_is_clean(self) -> None:
        assert qc.check_audio_sync(row(audio=audio_of(240)), RATE_24) == []

    def test_one_frame_of_slack_is_tolerated(self) -> None:
        """Audio rarely lands exactly on a frame boundary."""
        assert qc.check_audio_sync(row(audio=audio_of(241)), RATE_24) == []
        assert qc.check_audio_sync(row(audio=audio_of(239)), RATE_24) == []

    def test_short_audio_will_not_sync(self) -> None:
        results = qc.check_audio_sync(row(audio=audio_of(200)), RATE_24)
        assert ids(results) == ["QC-043"]
        assert "shorter" in results[0].message

    def test_long_audio_will_not_sync(self) -> None:
        """Drift in either direction is a sync problem, not just a short file."""
        results = qc.check_audio_sync(row(audio=audio_of(300)), RATE_24)
        assert ids(results) == ["QC-043"]
        assert "longer" in results[0].message

    def test_audio_recorded_at_the_wrong_rate_shows_as_drift(self) -> None:
        """A 240 frame take cut at 30 fps is 8 seconds; at 24 that is 192 frames."""
        recorded_at_30 = audio_of(240, rate=RATE_30)
        results = qc.check_audio_sync(row(audio=recorded_at_30), RATE_24)
        assert ids(results) == ["QC-043"]

    def test_format_is_not_constrained(self) -> None:
        """Audio stays flexible: an odd sample rate that still syncs is fine."""
        odd = audio_of(240, sample_rate=44100)
        assert qc.check_audio_sync(row(audio=odd), RATE_24) == []

    def test_no_audio_is_not_a_sync_problem(self) -> None:
        """A missing plate wav is QC-040's business, not this rule's."""
        assert qc.check_audio_sync(row(audio=None), RATE_24) == []

    @pytest.mark.parametrize("sample_rate", [48000, 44100, 96000])
    def test_sync_is_measured_in_frames_not_samples(self, sample_rate: int) -> None:
        assert qc.check_audio_sync(row(audio=audio_of(240, sample_rate)), RATE_24) == []


class TestApplyRowRules:
    def test_adds_results(self) -> None:
        target = row(stated=RATE_30, audio=audio_of(200))
        qc.apply_row_rules(target, RATE_24)
        assert set(ids(target.qc)) == {"QC-026", "QC-043"}

    def test_rerunning_does_not_duplicate(self) -> None:
        """Rules re-run after every edit, so they must be idempotent."""
        target = row(stated=RATE_30)
        qc.apply_row_rules(target, RATE_24)
        qc.apply_row_rules(target, RATE_24)
        assert ids(target.qc) == ["QC-026"]

    def test_results_from_elsewhere_are_left_alone(self) -> None:
        """The scan owns QC-012; this registry must not clear it."""
        target = row(stated=RATE_24)
        target.qc.append(QCResult("QC-012", "error", "row", "media not found"))
        qc.apply_row_rules(target, RATE_24)
        assert "QC-012" in ids(target.qc)

    def test_fixing_the_cause_clears_the_result(self) -> None:
        target = row(stated=RATE_30)
        qc.apply_row_rules(target, RATE_24)
        assert target.media is not None
        target.media.stated_rate = RATE_24
        qc.apply_row_rules(target, RATE_24)
        assert ids(target.qc) == []
