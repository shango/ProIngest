"""The phase A rule registry.

Everything is conformed to the project rate in Resolve, so anything that disagrees
means a file escaped the conform and must be flagged rather than absorbed. The rest
of phase A is the same idea applied to format, range, audio and side files: every
rule is a pure function of the model, so it re-runs after every edit.
"""

from __future__ import annotations

import re
import shutil
from dataclasses import replace
from pathlib import Path

import pytest

from proingest.core import qc, render
from proingest.core.models import (
    CDL,
    AudioInfo,
    Batch,
    Deliverable,
    FrameRate,
    InOut,
    MediaInfo,
    QCResult,
    ShotRow,
    Turnover,
)
from proingest.core.planner import DeliverableJob
from tests.fixtures import color as color_fixtures
from tests.fixtures import media as fixtures
from tests.fixtures.names import identity_of

RATE_24 = FrameRate(24)
RATE_30 = FrameRate(30)
NTSC = FrameRate(24000, 1001)

UHD = (3840, 2160)

FIRST = 1001
"""First frame of the fixture media. A consolidated EXR sequence starts at 1001."""

CHOSEN = InOut(1009, 1248)
"""240 frames with eight to spare at each end: inside every default threshold."""


def media(
    stated: FrameRate | None,
    *,
    size: tuple[int, int] = UHD,
    pixel_format: str = "gbrpf32le",
    codec: str = "exr",
    frame_count: int = 264,
    start_timecode: int | None = 86400,
) -> MediaInfo:
    width, height = size
    return MediaInfo(
        path=Path("/t/MELT0001_pl01.1001.exr"),
        codec=codec,
        pixel_format=pixel_format,
        width=width,
        height=height,
        rate=RATE_24,
        frame_count=frame_count,
        start_frame=FIRST,
        start_timecode=start_timecode,
        is_sequence=True,
        stated_rate=stated,
    )


def row(
    stated: FrameRate | None = RATE_24,
    audio: AudioInfo | None = None,
    *,
    clip_name: str = "MELT0001_pl01",
    current: InOut | None = CHOSEN,
    source_encoding: str | None = "ACEScct",
    **media_kwargs: object,
) -> ShotRow:
    """A plate that passes every default rule, so a test changes only what it is about.

    It names a source encoding because a real clip does: since M4.6.4 a clip that names
    none is QC-046, so a row without one is not the clean row these tests want.
    """
    return ShotRow(
        turnover_id="t1",
        clip_name=clip_name,
        identity=identity_of(clip_name),
        source_encoding=source_encoding,
        media=media(stated, **media_kwargs),  # type: ignore[arg-type]
        snapshot=CHOSEN,
        current=current,
        audio=audio,
        audio_path=audio.path if audio else None,
        audio_clip_count=1 if audio else 0,
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

    def test_ntsc_source_against_a_24_project_is_the_normal_conform(self) -> None:
        """Every real file states 24000/1001 and is rendered at 24 (user, 2026-09-23)."""
        assert qc.check_source_rate(row(stated=NTSC), RATE_24) == []

    def test_25_fps_against_a_24_project_is_an_error(self) -> None:
        results = qc.check_source_rate(row(stated=FrameRate(25)), RATE_24)
        assert ids(results) == ["QC-026"] and results[0].severity == "error"


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

    def test_an_edit_past_the_audio_says_the_wav_is_padded(self) -> None:
        """The wav is cut to the edited range, so sound it lacks becomes silence."""
        longer = InOut(CHOSEN.in_frame, CHOSEN.out_frame + 60)
        results = qc.check_audio_sync(row(audio=audio_of(240), current=longer), RATE_24)
        assert ids(results) == ["QC-043"]
        assert "padded with silence" in results[0].message

    def test_an_edit_inside_the_audio_says_the_wav_is_cut(self) -> None:
        shorter = InOut(CHOSEN.in_frame, CHOSEN.out_frame - 60)
        results = qc.check_audio_sync(row(audio=audio_of(240), current=shorter), RATE_24)
        assert ids(results) == ["QC-043"]
        assert "cut to it" in results[0].message

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
        target = row(stated=RATE_30, audio=audio_of(240))
        qc.apply_row_rules(target, RATE_24)
        qc.apply_row_rules(target, RATE_24)
        assert ids(target.qc) == ["QC-026"]

    def test_results_from_elsewhere_are_left_alone(self) -> None:
        """The scan owns QC-012; this registry must not clear it."""
        target = row(stated=RATE_24, audio=audio_of(240))
        target.qc.append(QCResult("QC-012", "error", "row", "media not found"))
        qc.apply_row_rules(target, RATE_24)
        assert "QC-012" in ids(target.qc)

    def test_fixing_the_cause_clears_the_result(self) -> None:
        target = row(stated=RATE_30, audio=audio_of(240))
        qc.apply_row_rules(target, RATE_24)
        assert target.media is not None
        target.media.stated_rate = RATE_24
        qc.apply_row_rules(target, RATE_24)
        assert ids(target.qc) == []


class TestSourceFormat:
    def test_float_exr_is_what_the_pipeline_wants(self) -> None:
        assert qc.check_source_format(row(pixel_format="gbrpf32le")) == []

    def test_half_float_is_also_clean(self) -> None:
        assert qc.check_source_format(row(pixel_format="gbrpf16le")) == []

    @pytest.mark.parametrize("pixel_format", ["yuv420p", "yuv420p10le", "rgb24", "gray"])
    def test_eight_bit_or_420_is_qc_020(self, pixel_format: str) -> None:
        """8 bit throws away shadow detail and 4:2:0 throws away two thirds of the chroma."""
        results = qc.check_source_format(row(pixel_format=pixel_format))
        assert ids(results) == ["QC-020"]
        assert results[0].severity == "error", "must-fix since 2026-09-25 (user)"

    @pytest.mark.parametrize("pixel_format", ["yuv422p10le", "yuv444p12le", "rgb48le", "gbrp10le"])
    def test_integer_containers_are_qc_021(self, pixel_format: str) -> None:
        """DPX and ProRes 4444 decode fine; the warning is about linear precision."""
        results = qc.check_source_format(row(pixel_format=pixel_format))
        assert ids(results) == ["QC-021"]
        assert results[0].severity == "warning"

    def test_a_row_with_no_media_is_skipped(self) -> None:
        assert qc.check_source_format(ShotRow(turnover_id="t1", clip_name="x")) == []

    @pytest.mark.parametrize(
        ("pixel_format", "depth"),
        [
            ("yuv420p", 8),
            ("rgb24", 8),
            ("rgb48le", 16),
            ("yuv422p10le", 10),
            ("gbrp12le", 12),
            ("gbrpf32le", 32),
            # The number in a packed or semi-planar name is a layout, not a depth.
            ("nv12", 8),
            ("nv21", 8),
            ("uyvy422", 8),
            ("yuyv422", 8),
            ("rgb0", 8),
            ("bgr0", 8),
        ],
    )
    def test_bit_depth_reads_ffmpeg_names(self, pixel_format: str, depth: int) -> None:
        assert qc.bit_depth(pixel_format) == depth

    @pytest.mark.parametrize(
        ("pixel_format", "sampling"),
        [
            ("yuv420p", "4:2:0"),
            ("yuvj420p", "4:2:0"),
            ("yuv422p10le", "4:2:2"),
            ("yuv444p12le", "4:4:4"),
            ("yuva444p10le", "4:4:4"),
            ("gbrpf32le", "4:4:4"),
            ("rgb48le", "4:4:4"),
            ("gray16le", "4:0:0"),
            # Packed and semi-planar names imply the sampling rather than spelling it.
            ("nv12", "4:2:0"),
            ("p010le", "4:2:0"),
            ("uyvy422", "4:2:2"),
            ("y210le", "4:2:2"),
            # Nothing to read: empty, not a guess.
            ("videotoolbox_vld", ""),
            ("bayer_rggb16le", ""),
        ],
    )
    def test_chroma_reads_ffmpeg_names(self, pixel_format: str, sampling: str) -> None:
        assert qc.chroma(pixel_format) == sampling


class TestColorTags:
    """QC-018, info: what matrix a container is decoded with, when it is not a plain BT.709."""

    def container(self, color_space: str = "", color_range: str = "") -> ShotRow:
        subject = row()
        assert subject.media is not None
        subject.media = replace(
            subject.media, is_sequence=False, color_space=color_space, color_range=color_range
        )
        return subject

    def test_a_file_that_states_no_matrix_says_bt709_is_assumed(self) -> None:
        """Every real file of Turnover199 is this: full range, no matrix."""
        results = qc.check_color_tags(self.container(color_range="pc"))
        assert ids(results) == ["QC-018"]
        assert results[0].severity == "info"
        assert "bt709, full range" in results[0].message

    def test_a_file_that_states_bt709_says_nothing(self) -> None:
        assert qc.check_color_tags(self.container(color_space="bt709")) == []

    def test_another_stated_matrix_is_used_and_said(self) -> None:
        results = qc.check_color_tags(self.container(color_space="bt2020nc"))
        assert "bt2020, limited range" in results[0].message

    def test_a_sequence_has_no_matrix_to_choose(self) -> None:
        assert qc.check_color_tags(row()) == []


class TestSourceCodec:
    def test_a_decodable_codec_is_clean(self) -> None:
        assert qc.check_source_codec(row(codec="prores"), frozenset({"prores", "h264"})) == []

    def test_an_unknown_codec_is_qc_022(self) -> None:
        results = qc.check_source_codec(row(codec="cineform"), frozenset({"prores"}))
        assert ids(results) == ["QC-022"]
        assert results[0].severity == "error"
        assert "cineform" in results[0].message

    def test_an_empty_decoder_set_stays_silent(self) -> None:
        """A build that could not be asked must not fail every row in the batch."""
        assert qc.check_source_codec(row(codec="cineform"), frozenset()) == []


class TestSourceResolution:
    def test_the_target_resolution_is_clean(self) -> None:
        assert qc.check_source_resolution(row(), qc.DEFAULT_SETTINGS) == []

    def test_anything_else_is_qc_023(self) -> None:
        """`render._fit` would resample it to the target and squash it."""
        results = qc.check_source_resolution(row(size=(1920, 1080)), qc.DEFAULT_SETTINGS)
        assert ids(results) == ["QC-023"]
        assert results[0].severity == "error"
        assert "1920x1080" in results[0].message

    def test_the_setting_downgrades_it_to_a_warning(self) -> None:
        settings = qc.RuleSettings(allow_non_4k=True)
        results = qc.check_source_resolution(row(size=(4096, 2160)), settings)
        assert ids(results) == ["QC-023"]
        assert results[0].severity == "warning"

    def test_a_still_is_not_asked(self) -> None:
        """An aux still is delivered at its own size and has no 4k contract."""
        still = row(clip_name="MELT0001_pl01_colorChart_01", size=(2048, 1152))
        assert qc.check_source_resolution(still, qc.DEFAULT_SETTINGS) == []


class TestTimecode:
    def test_embedded_timecode_is_clean(self) -> None:
        assert qc.check_timecode(row()) == []

    def test_no_timecode_is_qc_028(self) -> None:
        results = qc.check_timecode(row(start_timecode=None))
        assert ids(results) == ["QC-028"]
        assert results[0].severity == "warning"


class TestRange:
    def test_a_range_inside_the_media_is_clean(self) -> None:
        assert qc.check_range(row()) == []

    def test_out_beyond_the_media_is_qc_031(self) -> None:
        results = qc.check_range(row(current=InOut(1009, 9999)))
        assert ids(results) == ["QC-031"]
        assert results[0].severity == "error"

    def test_in_before_the_media_is_qc_031(self) -> None:
        assert ids(qc.check_range(row(current=InOut(1, 1248)))) == ["QC-031"]

    def test_in_after_out_is_qc_032(self) -> None:
        """Reported alone: an inverted range makes every other range answer nonsense."""
        results = qc.check_range(row(current=InOut(1248, 1009)))
        assert ids(results) == ["QC-032"]
        assert results[0].severity == "error"

    def test_the_last_available_frame_is_still_inside(self) -> None:
        assert qc.check_range(row(current=InOut(1001, 1264))) == []


class TestHandles:
    def test_room_at_both_ends_is_clean(self) -> None:
        assert qc.check_handles(row(), qc.DEFAULT_SETTINGS) == []

    def test_nothing_left_after_out_is_qc_030(self) -> None:
        results = qc.check_handles(row(current=InOut(1009, 1264)), qc.DEFAULT_SETTINGS)
        assert ids(results) == ["QC-030"]
        assert "after Out" in results[0].message
        assert "before In" not in results[0].message

    def test_short_at_both_ends_says_so_once(self) -> None:
        results = qc.check_handles(row(current=InOut(1001, 1264)), qc.DEFAULT_SETTINGS)
        assert ids(results) == ["QC-030"]
        assert "before In" in results[0].message and "after Out" in results[0].message

    def test_the_expectation_is_a_setting(self) -> None:
        tight = row(current=InOut(1009, 1264))
        assert qc.check_handles(tight, qc.RuleSettings(expected_handle_frames=0)) == []


class TestDuration:
    def test_a_normal_shot_is_clean(self) -> None:
        assert qc.check_duration(row(), qc.DEFAULT_SETTINGS) == []

    def test_too_short_is_qc_033(self) -> None:
        results = qc.check_duration(row(current=InOut(1009, 1050)), qc.DEFAULT_SETTINGS)
        assert ids(results) == ["QC-033"]
        assert results[0].severity == "error", "must-fix since 2026-09-25 (user)"

    def test_too_long_is_qc_034(self) -> None:
        results = qc.check_duration(row(current=InOut(1001, 1264)), qc.DEFAULT_SETTINGS)
        assert ids(results) == ["QC-034"]
        assert results[0].severity == "error", "must-fix since 2026-09-25 (user)"

    def test_the_limits_are_settings(self) -> None:
        settings = qc.RuleSettings(min_duration_frames=1, max_duration_frames=10_000)
        assert qc.check_duration(row(current=InOut(1009, 1010)), settings) == []

    def test_the_boundaries_are_inclusive(self) -> None:
        settings = qc.RuleSettings(min_duration_frames=240, max_duration_frames=240)
        assert qc.check_duration(row(), settings) == []


class TestEdits:
    def test_an_untouched_row_says_nothing(self) -> None:
        assert qc.check_edits(row()) == []

    def test_a_moved_out_is_qc_035(self) -> None:
        results = qc.check_edits(row(current=InOut(1009, 1260)))
        assert ids(results) == ["QC-035"]
        assert results[0].severity == "info"
        assert "1009-1248" in results[0].message and "1009-1260" in results[0].message

    def test_a_corrected_shot_code_is_qc_036(self) -> None:
        target = row()
        target.shot_code_override = "MELT0002"
        results = qc.check_edits(target)
        assert ids(results) == ["QC-036"]
        assert "MELT0001" in results[0].message and "MELT0002" in results[0].message

    def test_an_override_that_changes_nothing_is_not_an_edit(self) -> None:
        target = row()
        target.shot_code_override = "MELT0001"
        assert qc.check_edits(target) == []


class TestAudioPresence:
    def test_a_plate_with_audio_is_clean(self) -> None:
        assert qc.check_audio_presence(row(audio=audio_of(240))) == []

    def test_a_plate_without_audio_is_qc_040(self) -> None:
        results = qc.check_audio_presence(row())
        assert ids(results) == ["QC-040"]
        assert results[0].severity == "warning"

    def test_audio_inside_the_plate_s_own_file_counts(self) -> None:
        """F20: every real plate carries its sound embedded, and was told it had none."""
        embedded = row()
        assert embedded.media is not None
        embedded.media.has_audio = True
        assert qc.check_audio_presence(embedded) == []

    def test_only_the_plate_owes_audio(self) -> None:
        """An element or witness clip delivers no wav, so silence is expected."""
        assert qc.check_audio_presence(row(clip_name="MELT0001_el01")) == []

    def test_several_matching_audio_files_is_qc_041(self) -> None:
        target = row(audio=audio_of(240))
        target.audio_clip_count = 3
        results = qc.check_audio_presence(target)
        assert ids(results) == ["QC-041"]
        assert "3 audio files" in results[0].message


class TestAudioFormat:
    def test_sixteen_bit_is_clean(self) -> None:
        assert qc.check_audio_format(row(audio=audio_of(240))) == []

    def test_twenty_four_bit_is_qc_044(self) -> None:
        deep = audio_of(240)
        deep.bit_depth = 24
        results = qc.check_audio_format(row(audio=deep))
        assert ids(results) == ["QC-044"]
        assert results[0].severity == "warning"

    def test_a_source_that_states_no_depth_is_left_alone(self) -> None:
        unknown = audio_of(240)
        unknown.bit_depth = 0
        assert qc.check_audio_format(row(audio=unknown)) == []

    def test_no_audio_is_not_a_format_problem(self) -> None:
        assert qc.check_audio_format(row()) == []


class TestAuxStill:
    def test_a_single_frame_still_is_clean(self) -> None:
        chart = row(clip_name="MELT0001_pl01_colorChart_01", frame_count=1, current=InOut(0, 0))
        assert qc.check_aux_still(chart) == []

    def test_a_still_cut_as_a_clip_is_qc_055(self) -> None:
        chart = row(clip_name="MELT0001_pl01_greyBall_01", frame_count=90, current=InOut(0, 89))
        results = qc.check_aux_still(chart)
        assert ids(results) == ["QC-055"]
        assert "90 frames" in results[0].message

    def test_one_frame_cut_out_of_a_longer_file_is_clean(self) -> None:
        """Every real still: the EDL picks one frame of a 49 or 88 frame file."""
        chart = row(clip_name="MELT0001_pl01_greyBall_01", frame_count=88, current=InOut(38, 38))
        assert qc.check_aux_still(chart) == []

    def test_bts_is_not_an_aux_still(self) -> None:
        assert qc.check_aux_still(row(clip_name="MELT0001_pl01_BTS_01", frame_count=90)) == []

    def test_a_plate_is_not_an_aux_still(self) -> None:
        assert qc.check_aux_still(row()) == []


class TestSourceEncodingRule:
    """QC-046 and QC-047. COLOR_AND_FORMAT section 1: an error only where the tool converts."""

    def chart(self, **kwargs: object) -> ShotRow:
        return row(clip_name="MELT0001_pl01_colorChart_01", **kwargs)  # type: ignore[arg-type]

    def test_a_resolvable_encoding_raises_nothing(self) -> None:
        assert qc.check_source_encoding(row(source_encoding="C-Log3")) == []

    def test_a_plate_that_names_none_is_qc_046_error(self) -> None:
        """The grade is applied in ACEScct and this is what gets the clip there."""
        results = qc.check_source_encoding(row(source_encoding=None))
        assert ids(results) == ["QC-046"]
        assert results[0].severity == "error"

    def test_an_aux_still_that_names_none_is_qc_046_error(self) -> None:
        """The one picture the tool converts on its own authority, so it cannot be delivered."""
        results = qc.check_source_encoding(self.chart(source_encoding=None))
        assert ids(results) == ["QC-046"]
        assert results[0].severity == "error"

    def test_a_plate_naming_something_unresolvable_is_qc_047_error(self) -> None:
        results = qc.check_source_encoding(row(source_encoding="S-Log3"))
        assert ids(results) == ["QC-047"]
        assert results[0].severity == "error"

    def test_an_aux_still_naming_something_unresolvable_is_qc_047_error(self) -> None:
        results = qc.check_source_encoding(self.chart(source_encoding="Arri LogC9"))
        assert ids(results) == ["QC-047"]
        assert results[0].severity == "error"

    def test_the_message_quotes_what_was_written_and_what_it_could_not_be(self) -> None:
        """The fix is somebody retyping a field, so the message has to name both ends."""
        message = qc.check_source_encoding(row(source_encoding="S-Log3"))[0].message
        assert "'S-Log3'" in message
        assert "S-Log3 S-Gamut3.Cine" in message

    def test_a_bts_still_is_not_blocked(self) -> None:
        """It is copied byte for byte and never transformed."""
        bts = row(clip_name="MELT0001_pl01_BTS_01", source_encoding=None)
        assert qc.check_source_encoding(bts)[0].severity == "info"


class TestColorChain:
    """QC-048: what the row was rendered through, recorded rather than inferred (OQ-46)."""

    def test_a_row_with_a_cdl_names_the_three_legs(self) -> None:
        graded = row(source_encoding="C-Log3")
        graded.cdl = CDL((1.0,) * 3, (0.0,) * 3, (1.0,) * 3, 1.0, "", "")
        results = qc.check_color_chain(graded)
        assert ids(results) == ["QC-048"]
        assert results[0].severity == "info"
        assert "CanonLog3 CinemaGamut D55 to ACEScct, the CDL, ACEScct to ACEScg" in results[0].message

    def test_an_ungraded_row_names_the_input_transform(self) -> None:
        message = qc.check_color_chain(row(source_encoding="C-Log3"))[0].message
        assert "no grade" in message
        assert "CanonLog3 CinemaGamut D55 to ACEScg" in message

    def test_an_aux_still_says_it_is_never_graded(self) -> None:
        chart = row(clip_name="MELT0001_pl01_colorChart_01", source_encoding="BM Film")
        message = qc.check_color_chain(chart)[0].message
        assert "aux still" in message
        assert "never graded" in message
        assert "BMDFilm WideGamut Gen5" in message

    def test_a_row_with_neither_says_so(self) -> None:
        message = qc.check_color_chain(row(source_encoding=None))[0].message
        assert "no source encoding: nothing to render through" in message

    def test_it_is_recorded_by_a_preflight(self, tmp_path: Path) -> None:
        """Here rather than with the model rules: the CLF is resolved by the planner."""
        batch = Batch(delivery_root=tmp_path, rows=[row(source_encoding="ACEScct")])
        qc.preflight(batch)
        assert "QC-048" in ids(batch.rows[0].qc)


class TestDuplicateNames:
    """QC-011, must-fix since 2026-09-23 (D6): keyed on what the files are named from."""

    def test_a_unique_identity_is_clean(self) -> None:
        assert qc.check_duplicate_name(row(), {"MELT0001 pl01": 1}) == []

    def test_a_repeated_identity_is_qc_011(self) -> None:
        results = qc.check_duplicate_name(row(), {"MELT0001 pl01": 2})
        assert ids(results) == ["QC-011"]
        assert results[0].severity == "error"

    def test_counts_come_from_the_batch(self) -> None:
        batch = Batch(rows=[row(), row(), row(clip_name="MELT0002_pl01")])
        assert qc.clip_name_counts(batch) == {"MELT0001 pl01": 2, "MELT0002 pl01": 1}

    def test_the_same_clip_twice_as_two_shots_is_fine(self) -> None:
        """D3: a clip used twice is two rows with two shot codes, and that is normal (F2)."""
        second = row()
        second.shot_code_override = "MELT0002"
        batch = Batch(rows=[row(), second])
        assert qc.clip_name_counts(batch) == {"MELT0001 pl01": 1, "MELT0002 pl01": 1}

    def test_a_skipped_row_collides_with_nothing(self) -> None:
        skipped = row()
        skipped.skipped = True
        assert qc.clip_name_counts(Batch(rows=[row(), skipped])) == {"MELT0001 pl01": 1}


class TestRuleSettings:
    def test_defaults_round_trip(self) -> None:
        assert qc.RuleSettings.from_dict(qc.DEFAULT_SETTINGS.to_dict()) == qc.DEFAULT_SETTINGS

    def test_a_partial_override_keeps_the_other_defaults(self) -> None:
        settings = qc.RuleSettings.from_dict({"min_duration_frames": 48})
        assert settings.min_duration_frames == 48
        assert settings.max_duration_frames == qc.DEFAULT_SETTINGS.max_duration_frames

    def test_an_unknown_key_is_refused(self) -> None:
        """A typo that silently changed nothing is what this exists to prevent."""
        with pytest.raises(ValueError, match="unknown rule settings: min_duraiton_frames"):
            qc.RuleSettings.from_dict({"min_duraiton_frames": 48})

    def test_a_batch_carries_its_own_settings(self) -> None:
        batch = Batch()
        batch.settings_overrides[qc.RULES_OVERRIDE_KEY] = {"allow_non_4k": True}
        assert qc.settings_for(batch).allow_non_4k is True

    def test_a_batch_without_overrides_gets_the_defaults(self) -> None:
        assert qc.settings_for(Batch()) == qc.DEFAULT_SETTINGS


class TestApplyBatchRules:
    def test_duplicates_are_found_across_the_batch(self) -> None:
        batch = Batch(rows=[row(audio=audio_of(240)), row(audio=audio_of(240))])
        qc.apply_batch_rules(batch)
        assert all("QC-011" in ids(target.qc) for target in batch.rows)

    def test_settings_reach_every_row(self) -> None:
        batch = Batch(rows=[row(audio=audio_of(240), size=(1920, 1080))])
        qc.apply_batch_rules(batch, qc.RuleSettings(target_resolution=(1920, 1080)))
        assert "QC-023" not in ids(batch.rows[0].qc)


class TestDeliverableRuleTable:
    """The QC log columns one sheet per rule, so the list has to be complete."""

    def test_every_deliverable_rule_the_module_raises_has_a_column(self) -> None:
        source = Path(qc.__file__).read_text()
        raised = set(re.findall(r'"(QC-1\d\d)"', source))
        not_deliverable = {"QC-150", "QC-151"}
        assert raised - not_deliverable <= set(qc.DELIVERABLE_RULES)

    def test_the_table_names_no_rule_that_does_not_exist(self) -> None:
        source = Path(qc.__file__).read_text()
        for rule_id in qc.DELIVERABLE_RULES:
            assert f'"{rule_id}"' in source, f"{rule_id} has a column but is never raised"

    def test_every_kind_the_renderer_writes_owes_some_rule(self) -> None:
        assert set(qc.DELIVERABLE_RULES_BY_KIND) >= {"raw_dir", "aux_still", "ref_mp4", "audio"}

    def test_no_kind_claims_a_rule_that_is_not_in_the_table(self) -> None:
        for owed in qc.DELIVERABLE_RULES_BY_KIND.values():
            assert set(owed) <= set(qc.DELIVERABLE_RULES)


class TestDestinationWritable:
    def test_a_writable_root_is_clean(self, tmp_path: Path) -> None:
        assert qc.check_destination_writable(tmp_path) == []

    def test_no_root_is_qc_062(self) -> None:
        results = qc.check_destination_writable(None)
        assert ids(results) == ["QC-062"]
        assert results[0].severity == "error"

    def test_a_root_the_run_will_create_is_clean(self, tmp_path: Path) -> None:
        """The run makes the show and shot folders, so an absent root is not a failure."""
        assert qc.check_destination_writable(tmp_path / "absent" / "deeper") == []

    def test_an_unreachable_root_is_qc_062(self) -> None:
        assert ids(qc.check_destination_writable(Path("/nonexistent-volume/x"))) == ["QC-062"]

    def test_a_mount_that_refuses_to_answer_is_qc_062_rather_than_a_crash(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def refuse(self: Path) -> bool:
            raise PermissionError(f"{self}: not permitted")

        monkeypatch.setattr(Path, "exists", refuse)
        assert ids(qc.check_destination_writable(Path("/mnt/g/x"))) == ["QC-062"]

    def test_a_read_only_root_is_qc_062(self, tmp_path: Path) -> None:
        """Existence is not permission, which is the whole point on a network mount."""
        locked = tmp_path / "locked"
        locked.mkdir(mode=0o500)
        try:
            assert ids(qc.check_destination_writable(locked)) == ["QC-062"]
            assert ids(qc.check_destination_writable(locked / "MELT")) == ["QC-062"]
        finally:
            locked.chmod(0o700)

    def test_the_probe_file_is_cleaned_up(self, tmp_path: Path) -> None:
        qc.check_destination_writable(tmp_path)
        assert list(tmp_path.iterdir()) == []


class TestFreeSpace:
    def test_enough_room_is_clean(self, tmp_path: Path) -> None:
        batch = Batch(delivery_root=tmp_path, rows=[row()])
        assert qc.check_free_space(batch) == []

    def test_not_enough_room_is_qc_063(self, tmp_path: Path) -> None:
        batch = Batch(delivery_root=tmp_path, rows=[row()])
        assert batch.rows[0].media is not None
        batch.rows[0].media.size = 1 << 60
        results = qc.check_free_space(batch)
        assert ids(results) == ["QC-063"]
        assert results[0].severity == "error"
        assert results[0].scope == "batch"

    def test_no_delivery_root_is_qc_062s_business(self) -> None:
        assert qc.check_free_space(Batch(rows=[row()])) == []

    def test_the_estimate_charges_every_picture_deliverable(self) -> None:
        batch = Batch(rows=[row()])
        assert batch.rows[0].media is not None
        batch.rows[0].media.size = 264_000  # 1000 bytes a frame over 264 frames
        assert qc.estimate_output_bytes(batch) == 1000 * 240 * qc.PICTURE_DELIVERABLES_PER_ROW


class TestPreflight:
    def test_it_records_what_the_disk_says(self, tmp_path: Path) -> None:
        delivery = tmp_path / "delivery"
        delivery.mkdir()
        batch = Batch(delivery_root=delivery, turnovers=[Turnover("t1", tmp_path)], rows=[row()])
        qc.preflight(batch)
        assert ids(batch.qc) == []
        assert ids(batch.turnovers[0].qc) == ["QC-008"]

    def test_rerunning_does_not_duplicate(self, tmp_path: Path) -> None:
        batch = Batch(turnovers=[Turnover("t1", tmp_path)], rows=[row()])
        qc.preflight(batch)
        qc.preflight(batch)
        assert ids(batch.qc) == ["QC-062"]
        assert ids(batch.turnovers[0].qc) == ["QC-008"]

    def test_model_rules_survive_a_preflight(self, tmp_path: Path) -> None:
        """The two registries own different IDs and must not clear each other."""
        batch = Batch(delivery_root=tmp_path, rows=[row()])
        qc.apply_batch_rules(batch)
        qc.preflight(batch)
        assert "QC-040" in ids(batch.rows[0].qc)


class TestBlockingResults:
    """D8: every must-fix stops the run, wherever it is (`qc.must_fix`)."""

    def test_a_batch_scope_error_blocks(self) -> None:
        batch = Batch(rows=[row()])
        qc.preflight(batch)
        assert [result.rule_id for result in qc.blocking_results(batch)] == ["QC-062"]

    def test_a_batch_scope_warning_does_not(self, tmp_path: Path) -> None:
        batch = Batch(delivery_root=tmp_path, rows=[row()])
        batch.qc.append(QCResult("QC-063", "warning", "batch", "not much room left"))
        assert qc.blocking_results(batch) == []

    def test_a_turnover_scope_error_stops_the_run(self, tmp_path: Path) -> None:
        batch = Batch(delivery_root=tmp_path, turnovers=[Turnover("t1", tmp_path)], rows=[row()])
        qc.preflight(batch)
        assert (tmp_path.name, "QC-008") in [(where, result.rule_id) for where, result in qc.must_fix(batch)]

    def test_a_row_scope_error_stops_the_run_and_says_which_row(self, tmp_path: Path) -> None:
        broken = row()
        broken.qc.append(QCResult("QC-012", "error", "row", "no such file"))
        found = qc.must_fix(Batch(delivery_root=tmp_path, rows=[broken]))
        assert [(where, result.rule_id) for where, result in found] == [("MELT0001_pl01", "QC-012")]

    def test_a_skipped_row_s_error_does_not(self, tmp_path: Path) -> None:
        broken = row()
        broken.skipped = True
        broken.qc.append(QCResult("QC-012", "error", "row", "no such file"))
        assert qc.must_fix(Batch(delivery_root=tmp_path, rows=[broken])) == []

    def test_phase_b_is_not_a_reason_to_refuse_the_next_run(self, tmp_path: Path) -> None:
        """QC-150 says the last run failed a deliverable; the fix is to run again (D11)."""
        failed = row()
        failed.qc.append(QCResult("QC-150", "error", "row", "1 deliverable is not done"))
        assert qc.must_fix(Batch(delivery_root=tmp_path, rows=[failed])) == []


def ingested_batch(tmp_path: Path, *rows: ShotRow, edl_name: str = "MELT_FINAL.edl") -> Batch:
    """A batch whose one turnover has had a colour session ingested into it.

    The EDL is written rather than matched against, because these rules read what the
    ingest left on the model rather than the package: QC-008's own file check is the
    one exception and it has its own test.
    """
    edl = tmp_path / edl_name
    edl.touch()
    turnover = Turnover("t1", tmp_path, color_session_edl=edl)
    return Batch(delivery_root=tmp_path, turnovers=[turnover], rows=list(rows))


class TestColorSessionRule:
    """QC-008: the turnover has no colour session behind it, so nothing final can run."""

    def test_a_turnover_nothing_was_ingested_into_is_an_error(self, tmp_path: Path) -> None:
        batch = Batch(delivery_root=tmp_path, turnovers=[Turnover("t1", tmp_path)], rows=[row()])
        results = qc.check_color_session(batch.turnovers[0], batch.rows)
        assert ids(results) == ["QC-008"]
        assert results[0].severity == "error"
        assert "ingested" in results[0].message

    def test_an_archived_package_is_not_an_error(self, tmp_path: Path) -> None:
        """Ingest put what the session said on the rows, so nothing reads the EDL again."""
        graded = row()
        graded.cdl = CDL((1.0,) * 3, (0.0,) * 3, (1.0,) * 3, 1.0, "", "")
        batch = ingested_batch(tmp_path, graded)
        edl = batch.turnovers[0].color_session_edl
        assert edl is not None
        edl.unlink()
        assert qc.check_color_session(batch.turnovers[0], batch.rows) == []

    def test_a_session_that_delivered_no_clf_at_all_is_an_error(self, tmp_path: Path) -> None:
        """Distinct from QC-009: no row with one is a package that was never exported."""
        batch = ingested_batch(tmp_path, row())
        results = qc.check_color_session(batch.turnovers[0], batch.rows)
        assert ids(results) == ["QC-008"]
        assert "no CDL for any row" in results[0].message

    def test_one_graded_row_is_enough_to_satisfy_it(self, tmp_path: Path) -> None:
        graded, ungraded = row(), row(clip_name="MELT0002_pl01")
        graded.cdl = CDL((1.0,) * 3, (0.0,) * 3, (1.0,) * 3, 1.0, "", "")
        batch = ingested_batch(tmp_path, graded, ungraded)
        assert qc.check_color_session(batch.turnovers[0], batch.rows) == []

    def test_it_is_scoped_per_turnover(self, tmp_path: Path) -> None:
        """One turnover can wait on colour while another renders, which is the point."""
        graded = row()
        graded.cdl = CDL((1.0,) * 3, (0.0,) * 3, (1.0,) * 3, 1.0, "", "")
        batch = ingested_batch(tmp_path, graded)
        waiting = Turnover("t2", tmp_path)
        batch.turnovers.append(waiting)
        batch.rows.append(row(clip_name="MELT0002_pl01"))
        batch.rows[-1].turnover_id = "t2"
        qc.preflight(batch)
        assert "QC-008" not in ids(batch.turnovers[0].qc)
        assert "QC-008" in ids(batch.turnovers[1].qc)


class TestClfRule:
    """QC-009: this row has no usable CLF, and an ungraded plate is the wrong pixels."""

    def test_a_row_the_session_matched_no_clf_to_is_an_error(self, tmp_path: Path) -> None:
        results = qc.check_clf(row(), has_session=True)
        assert ids(results) == ["QC-009"]
        assert results[0].severity == "error"

    def test_it_is_silent_until_a_session_has_been_ingested(self, tmp_path: Path) -> None:
        """With none the whole turnover is QC-008, and repeating it per row buries it."""
        assert qc.check_clf(row(), has_session=False) == []

    def test_an_aux_still_owes_no_clf(self, tmp_path: Path) -> None:
        """It is delivered ungraded by design, so this would fire on every colour chart."""
        chart = row(clip_name="MELT0001_pl01_colorChart_01")
        assert qc.check_clf(chart, has_session=True) == []

    def test_a_graded_row_passes(self) -> None:
        graded = row()
        graded.cdl = CDL((1.0,) * 3, (0.0,) * 3, (1.0,) * 3, 1.0, "", "")
        assert qc.check_clf(graded, has_session=True) == []


class TestApprovedRule:
    """QC-045: the row will be delivered at an In/Out the colour session did not approve."""

    def test_a_trim_away_from_the_approved_cut_is_a_warning(self) -> None:
        trimmed = row(current=InOut(20, 200))
        trimmed.approved = InOut(8, 223)
        results = qc.check_approved(trimmed)
        assert ids(results) == ["QC-045"]
        assert results[0].severity == "warning"
        assert "20-200" in results[0].message and "8-223" in results[0].message

    def test_a_row_still_at_the_approved_cut_is_silent(self) -> None:
        conformed = row(current=InOut(8, 223))
        conformed.approved = InOut(8, 223)
        assert qc.check_approved(conformed) == []

    def test_it_is_silent_until_a_session_has_been_ingested(self) -> None:
        """`approved` is what an ingest writes, and nothing else has an opinion on it."""
        assert qc.check_approved(row()) == []

    def test_it_re_runs_with_the_row_rules(self) -> None:
        """A pure function of the model, so it follows an edit rather than a run."""
        trimmed = row(current=InOut(20, 200))
        trimmed.approved = InOut(8, 223)
        qc.apply_row_rules(trimmed, RATE_24)
        assert "QC-045" in ids(trimmed.qc)


def test_a_digest_is_stable_and_content_dependent(tmp_path: Path) -> None:
    """QC-106 and QC-130 both rest on this, so it is asserted across a chunk boundary."""
    one = tmp_path / "one.bin"
    two = tmp_path / "two.bin"
    one.write_bytes(b"x" * (qc.DIGEST_CHUNK + 17))
    two.write_bytes(b"x" * (qc.DIGEST_CHUNK + 17) + b"y")
    assert qc.file_digest(one) == qc.file_digest(one)
    assert qc.file_digest(one) != qc.file_digest(two)


# --- phase B ----------------------------------------------------------------------

ONE_HOUR = 86400


def picture_job(
    source: Path,
    destination: Path,
    in_frame: int,
    out_frame: int,
    kind: str = "raw_dir",
    **extra: object,
) -> DeliverableJob:
    """A job pointed at fixture media, sized so nothing is resampled."""
    return DeliverableJob(
        kind=kind,  # type: ignore[arg-type]
        source=source,
        destination=destination,
        version=1,
        shot_code="MELT0001",
        elem="pl01",
        in_frame=in_frame,
        out_frame=out_frame,
        source_is_sequence=True,
        source_size=fixtures.SMALL,
        rate=RATE_24,
        source_start_frame=in_frame,
        source_start_timecode=ONE_HOUR,
        shot_color=color_fixtures.UNGRADED,
        **extra,  # type: ignore[arg-type]
    )


def rendered_sequence(tmp_path: Path, count: int = 4) -> tuple[DeliverableJob, Deliverable]:
    """A real delivered sequence, already through phase B once and clean."""
    fixture = fixtures.make_exr_sequence(tmp_path / "src", count=count, first=1001)
    job = picture_job(
        fixture.path_for(1001),
        tmp_path / "out" / "MELT0001_pl01_raw_4k_v01",
        1001,
        1000 + count,
    )
    deliverable = render.render_job(job)
    assert deliverable.status == "done", "the fixture render itself has to be clean"
    return job, deliverable


def fabricated_sequence(tmp_path: Path, sizes: dict[int, int]) -> DeliverableJob:
    """A destination folder built by hand, so a single check can be cornered.

    Real renders cannot be made to fail one rule at a time; this can, and the files
    are plain bytes because the rules under test only count and stat them.
    """
    destination = tmp_path / "out" / "MELT0001_pl01_raw_4k_v01"
    destination.mkdir(parents=True)
    for frame, size in sizes.items():
        (destination / f"MELT0001_pl01_raw_4k_v01.{frame}.exr").write_bytes(b"x" * size)
    job = picture_job(tmp_path / "src" / "x.1001.exr", destination, 1001, 1004)
    return job


def empty_deliverable(job: DeliverableJob) -> Deliverable:
    return job.to_deliverable()


class TestPhaseBSequence:
    def test_a_clean_sequence_passes_everything(self, tmp_path: Path) -> None:
        job, deliverable = rendered_sequence(tmp_path)
        assert qc.run_phase_b(job, deliverable) == []
        assert deliverable.qc == []

    def test_a_missing_frame_is_qc_101_and_qc_102(self, tmp_path: Path) -> None:
        job, deliverable = rendered_sequence(tmp_path, count=4)
        job.frame_path(1003).unlink()
        found = ids(qc.run_phase_b(job, deliverable))
        assert "QC-101" in found and "QC-102" in found

    def test_numbering_must_start_at_1001(self, tmp_path: Path) -> None:
        job = fabricated_sequence(tmp_path, {frame: 1000 for frame in (1002, 1003, 1004, 1005)})
        results = qc.run_phase_b(job, empty_deliverable(job))
        assert "QC-102" in ids(results)

    def test_frames_delivered_for_a_job_that_planned_none_are_qc_102(self, tmp_path: Path) -> None:
        """An In that was cleared after planning leaves a job with no range and a folder
        with files; that is a fault to report, not an IndexError."""
        job = replace(fabricated_sequence(tmp_path, {1001: 10}), in_frame=None, out_frame=None)
        assert "QC-102" in ids(qc.run_phase_b(job, empty_deliverable(job)))

    def test_a_stray_file_in_the_folder_is_qc_102(self, tmp_path: Path) -> None:
        job, deliverable = rendered_sequence(tmp_path)
        (job.destination / "notes.exr").write_bytes(b"")
        assert "QC-102" in ids(qc.run_phase_b(job, deliverable))

    def test_an_unreadable_frame_is_qc_103(self, tmp_path: Path) -> None:
        job, deliverable = rendered_sequence(tmp_path)
        job.frame_path(1002).write_bytes(b"not an exr at all")
        results = qc.run_phase_b(job, deliverable)
        assert "QC-103" in ids(results)
        assert "1002" in next(r for r in results if r.rule_id == "QC-103").message

    def test_the_wrong_compression_is_qc_105(self, tmp_path: Path) -> None:
        """Fixture media is ZIP; the delivery spec pins DWAA."""
        job, deliverable = rendered_sequence(tmp_path)
        zipped = fixtures.make_exr_sequence(tmp_path / "zip", base="other", count=1, first=1001)
        shutil.copyfile(zipped.path_for(1001), job.frame_path(1002))
        assert "QC-105" in ids(qc.run_phase_b(job, deliverable))

    def test_a_changed_frame_is_qc_106(self, tmp_path: Path) -> None:
        """DWAA is lossy but deterministic, so the written file's digest is stable."""
        job, deliverable = rendered_sequence(tmp_path)
        original = job.frame_path(1002).read_bytes()
        job.frame_path(1002).write_bytes(original[:-8] + b"\x00" * 8)
        assert "QC-106" in ids(qc.run_phase_b(job, deliverable))

    def test_a_batch_with_no_recorded_checksums_skips_qc_106(self, tmp_path: Path) -> None:
        """An older batch carries none, and a missing record is not a mismatch."""
        job, deliverable = rendered_sequence(tmp_path)
        deliverable.frame_checksums = []
        assert "QC-106" not in ids(qc.run_phase_b(job, deliverable))

    def test_a_tiny_frame_is_a_qc_107_warning(self, tmp_path: Path) -> None:
        sizes = {1001: 10_000, 1002: 10_000, 1003: 10_000, 1004: 50}
        job = fabricated_sequence(tmp_path, sizes)
        results = qc.run_phase_b(job, empty_deliverable(job))
        small = [result for result in results if result.rule_id == "QC-107"]
        assert len(small) == 1
        assert small[0].severity == "warning"
        assert "1004" in small[0].message

    def test_even_sized_frames_raise_no_qc_107(self, tmp_path: Path) -> None:
        job = fabricated_sequence(tmp_path, {frame: 10_000 for frame in range(1001, 1005)})
        assert "QC-107" not in ids(qc.run_phase_b(job, empty_deliverable(job)))

    def test_a_destination_that_is_not_there_is_qc_100(self, tmp_path: Path) -> None:
        job = picture_job(tmp_path / "src.exr", tmp_path / "gone", 1001, 1004)
        results = qc.run_phase_b(job, empty_deliverable(job))
        assert ids(results) == ["QC-100"]

    def test_a_failed_render_is_not_checked_again(self, tmp_path: Path) -> None:
        """QC-100 already said there is no file; every other rule is NA."""
        job = picture_job(tmp_path / "src.exr", tmp_path / "gone", 1001, 1004)
        deliverable = empty_deliverable(job)
        deliverable.status = "failed"
        assert qc.run_phase_b(job, deliverable) == []


class TestPhaseBStill:
    def test_a_clean_still_passes(self, tmp_path: Path) -> None:
        fixture = fixtures.make_exr_sequence(tmp_path / "src", count=4, first=1001)
        job = picture_job(
            fixture.path_for(1001),
            tmp_path / "out" / "MELT0001_pl01_colorChart_01_4k_v01.exr",
            1002,
            1002,
            kind="aux_still",
        )
        deliverable = render.render_job(job)
        assert qc.run_phase_b(job, deliverable) == []

    def test_a_tampered_still_is_qc_106(self, tmp_path: Path) -> None:
        fixture = fixtures.make_exr_sequence(tmp_path / "src", count=4, first=1001)
        job = picture_job(
            fixture.path_for(1001),
            tmp_path / "out" / "MELT0001_pl01_greyBall_01_4k_v01.exr",
            1002,
            1002,
            kind="aux_still",
        )
        deliverable = render.render_job(job)
        job.destination.write_bytes(job.destination.read_bytes()[:-4] + b"\x00\x00\x00\x00")
        assert "QC-106" in ids(qc.run_phase_b(job, deliverable))


class TestPhaseBReference:
    def reference(self, tmp_path: Path, audio: Path | None = None) -> tuple[DeliverableJob, Deliverable]:
        fixture = fixtures.make_exr_sequence(tmp_path / "src", count=6, first=1001)
        job = picture_job(
            fixture.path_for(1001),
            tmp_path / "out" / "MELT0001_pl01_ref_4k_v01.mp4",
            1001,
            1006,
            kind="ref_mp4",
            audio_source=audio,
        )
        return job, render.render_job(job)

    def test_a_clean_reference_passes_everything(self, tmp_path: Path) -> None:
        job, deliverable = self.reference(tmp_path)
        assert qc.run_phase_b(job, deliverable) == []

    def test_a_reference_with_audio_passes_qc_114(self, tmp_path: Path) -> None:
        wav = fixtures.make_wav(tmp_path / "src" / "plate.wav", seconds=0.25)
        job, deliverable = self.reference(tmp_path, audio=wav)
        assert qc.run_phase_b(job, deliverable) == []

    def test_expected_audio_that_is_missing_is_qc_114(self, tmp_path: Path) -> None:
        """The job says there was audio to mux and the file has none, so it is silent."""
        job, deliverable = self.reference(tmp_path)
        claims_audio = replace(job, audio_source=tmp_path / "src" / "plate.wav")
        results = qc.run_phase_b(claims_audio, deliverable)
        assert ids(results) == ["QC-114"]
        assert results[0].severity == "warning"

    def test_the_wrong_frame_count_is_qc_111(self, tmp_path: Path) -> None:
        job, deliverable = self.reference(tmp_path)
        longer = replace(job, out_frame=1020)
        results = qc.run_phase_b(longer, deliverable)
        assert "QC-111" in ids(results)

    def test_the_wrong_resolution_is_qc_112(self, tmp_path: Path) -> None:
        job, deliverable = self.reference(tmp_path)
        claims_4k = replace(job, res="4k")
        assert "QC-112" in ids(qc.run_phase_b(claims_4k, deliverable))

    def test_the_wrong_rate_is_qc_113(self, tmp_path: Path) -> None:
        job, deliverable = self.reference(tmp_path)
        claims_ntsc = replace(job, rate=NTSC)
        assert "QC-113" in ids(qc.run_phase_b(claims_ntsc, deliverable))

    def test_a_file_that_will_not_open_is_qc_110(self, tmp_path: Path) -> None:
        job, deliverable = self.reference(tmp_path)
        job.destination.write_bytes(b"not an mp4")
        assert ids(qc.run_phase_b(job, deliverable)) == ["QC-110"]

    def test_the_moov_atom_is_at_the_head(self, tmp_path: Path) -> None:
        """QC-115: `-movflags +faststart` is a request, so the boxes are read back."""
        job, _ = self.reference(tmp_path)
        boxes = qc._top_level_boxes(job.destination)
        assert "moov" in boxes
        assert boxes.index("moov") < boxes.index("mdat")

    def test_a_trailing_moov_is_qc_115(self, tmp_path: Path) -> None:
        job, deliverable = self.reference(tmp_path)
        plain = tmp_path / "out" / "trailing.mp4"
        fixtures.make_mp4(plain, count=6)
        moved = replace(job, destination=plain)
        boxes = qc._top_level_boxes(plain)
        if boxes.index("moov") < boxes.index("mdat"):
            pytest.skip("this ffmpeg writes a leading moov even without faststart")
        assert "QC-115" in ids(qc.run_phase_b(moved, deliverable))


class TestPhaseBAudio:
    def wav_job(self, tmp_path: Path) -> tuple[DeliverableJob, Deliverable]:
        source = fixtures.make_wav(tmp_path / "src" / "plate.wav", seconds=0.25)
        job = DeliverableJob(
            kind="audio",
            source=source,
            destination=tmp_path / "out" / "MELT0001_pl01_audio_v01.wav",
            version=1,
            shot_code="MELT0001",
            elem="pl01",
        )
        return job, render.render_job(job)

    def test_a_byte_copied_wav_passes(self, tmp_path: Path) -> None:
        job, deliverable = self.wav_job(tmp_path)
        assert qc.run_phase_b(job, deliverable) == []

    def test_a_delivered_wav_that_differs_is_qc_120(self, tmp_path: Path) -> None:
        job, deliverable = self.wav_job(tmp_path)
        job.destination.write_bytes(job.destination.read_bytes() + b"\x00\x00")
        assert "QC-120" in ids(qc.run_phase_b(job, deliverable))

    def test_audio_extracted_from_a_container_passes(self, tmp_path: Path) -> None:
        source = fixtures.make_mov(tmp_path / "src" / "plate.mov", count=8, with_audio=True)
        job = DeliverableJob(
            kind="audio",
            source=source,
            destination=tmp_path / "out" / "MELT0001_pl01_audio_v01.wav",
            version=1,
            shot_code="MELT0001",
            elem="pl01",
        )
        deliverable = render.render_job(job)
        assert qc.run_phase_b(job, deliverable) == []

    def test_a_wav_that_is_not_pcm16_is_reported(self, tmp_path: Path) -> None:
        """A 24 bit source is delivered as it is, so QC-121 says so without blocking."""
        source = fixtures.make_wav(tmp_path / "src" / "deep.wav", seconds=0.25, bit_depth=24)
        job = DeliverableJob(
            kind="audio",
            source=source,
            destination=tmp_path / "out" / "MELT0001_pl01_audio_v01.wav",
            version=1,
            shot_code="MELT0001",
            elem="pl01",
        )
        deliverable = render.render_job(job)
        results = qc.run_phase_b(job, deliverable)
        assert ids(results) == ["QC-121"]
        assert results[0].severity == "warning"


def delivered(name: str, kind: str, version: int = 1, res: str | None = None) -> Deliverable:
    return Deliverable(kind=kind, name=name, path=Path("/d") / name, version=version, res=res, status="done")


class TestRowComplete:
    def test_a_row_whose_deliverables_all_landed_is_clean(self) -> None:
        target = row()
        target.deliverables = [delivered("MELT0001_pl01_audio_v01.wav", "audio")]
        assert qc.check_row_complete(target) == []

    def test_an_unfinished_deliverable_is_qc_150(self) -> None:
        target = row()
        item = delivered("MELT0001_pl01_audio_v01.wav", "audio")
        item.status = "failed"
        target.deliverables = [item]
        results = qc.check_row_complete(target)
        assert ids(results) == ["QC-150"]
        assert results[0].severity == "error"

    def test_a_deliverable_that_failed_its_own_checks_is_qc_150(self) -> None:
        target = row()
        item = delivered("MELT0001_pl01_audio_v01.wav", "audio")
        item.qc.append(QCResult("QC-120", "error", "deliverable", "does not match"))
        target.deliverables = [item]
        assert ids(qc.check_row_complete(target)) == ["QC-150"]

    def test_a_row_that_planned_nothing_is_not_incomplete(self) -> None:
        assert qc.check_row_complete(row()) == []

    def test_a_row_re_scan_put_back_is_not_incomplete(self) -> None:
        """Its failed output is being replaced by the next Run (user, 2026-09-25)."""
        target = row()
        item = delivered("MELT0001_pl01_audio_v01.wav", "audio")
        item.status = "failed"
        target.deliverables = [item]
        target.rerun = True
        assert qc.check_row_complete(target) == []


class TestNamesReparse:
    def batch_with(self, *items: Deliverable) -> Batch:
        target = row()
        target.deliverables = list(items)
        return Batch(rows=[target])

    def test_every_planned_name_reads_back(self) -> None:
        batch = self.batch_with(
            delivered("MELT0001_pl01_raw_4k_v01", "raw_dir", res="4k"),
            delivered("MELT0001_pl01_ref_HD_v01.mp4", "ref_mp4", res="HD"),
            delivered("MELT0001_pl01_audio_v01.wav", "audio"),
        )
        assert qc.check_names_reparse(batch) == []

    def test_a_name_that_does_not_parse_is_qc_151(self) -> None:
        batch = self.batch_with(delivered("MELT0001_plate_4k.exr", "raw_dir"))
        results = qc.check_names_reparse(batch)
        assert ids(results) == ["QC-151"]
        assert results[0].scope == "batch"

    def test_a_well_formed_name_for_the_wrong_version_is_qc_151(self) -> None:
        """The shape is right and the content is wrong, which is what this catches."""
        batch = self.batch_with(delivered("MELT0001_pl01_audio_v02.wav", "audio", version=1))
        results = qc.check_names_reparse(batch)
        assert ids(results) == ["QC-151"]
        assert "v02" in results[0].message

    def test_a_name_at_the_wrong_resolution_is_qc_151(self) -> None:
        batch = self.batch_with(delivered("MELT0001_pl01_raw_HD_v01", "raw_dir", res="4k"))
        assert ids(qc.check_names_reparse(batch)) == ["QC-151"]

    def test_a_well_formed_name_for_another_shot_is_qc_151(self) -> None:
        """F22: the shape was checked and the shot was not."""
        batch = self.batch_with(delivered("MELT0002_pl01_raw_4k_v01", "raw_dir", res="4k"))
        results = qc.check_names_reparse(batch)
        assert ids(results) == ["QC-151"]
        assert "MELT0002" in results[0].message

    def test_a_well_formed_name_for_another_element_is_qc_151(self) -> None:
        batch = self.batch_with(delivered("MELT0001_pl02_raw_4k_v01", "raw_dir", res="4k"))
        assert "pl02" in qc.check_names_reparse(batch)[0].message

    def test_a_deliverable_that_never_landed_is_not_asked(self) -> None:
        """QC-150 owns an unwritten deliverable; this rule is about delivered names."""
        item = delivered("nonsense", "raw_dir")
        item.status = "planned"
        assert qc.check_names_reparse(self.batch_with(item)) == []


class TestApplyPhaseB:
    def test_it_records_both_rules(self) -> None:
        target = row()
        target.deliverables = [delivered("nonsense", "raw_dir")]
        batch = Batch(rows=[target])
        qc.apply_phase_b(batch)
        assert ids(batch.qc) == ["QC-151"]
        assert ids(target.qc) == []

    def test_rerunning_does_not_duplicate(self) -> None:
        target = row()
        item = delivered("MELT0001_pl01_audio_v01.wav", "audio")
        item.status = "failed"
        target.deliverables = [item]
        batch = Batch(rows=[target])
        qc.apply_phase_b(batch)
        qc.apply_phase_b(batch)
        assert ids(target.qc) == ["QC-150"]

    def test_phase_a_results_survive(self) -> None:
        target = row()
        qc.apply_row_rules(target, RATE_24)
        qc.apply_phase_b(Batch(rows=[target]))
        assert "QC-040" in ids(target.qc)


class TestTurnoverFolder:
    """QC-069 (D16): a turnover whose folder has gone cannot run from nowhere."""

    def test_a_missing_folder_is_an_error_on_the_turnover(self, tmp_path: Path) -> None:
        moved = Batch(turnovers=[Turnover("t1", tmp_path / "gone")])
        qc.check_folders(moved)
        assert [(r.rule_id, r.severity, r.scope) for r in moved.turnovers[0].qc] == [
            ("QC-069", "error", "turnover")
        ]

    def test_a_folder_that_is_there_says_nothing_and_clears_it(self, tmp_path: Path) -> None:
        here = Batch(turnovers=[Turnover("t1", tmp_path)])
        here.turnovers[0].qc.append(QCResult("QC-069", "error", "turnover", "stale"))
        qc.check_folders(here)
        assert here.turnovers[0].qc == []


class TestDropFrame:
    """QC-027 (F24): drop-frame timecode is must-fix, and no longer passes for none."""

    def test_a_drop_frame_source_is_qc_027_not_qc_028(self) -> None:
        dropped = row(start_timecode=None)
        assert dropped.media is not None
        dropped.media.drop_frame = True
        results = qc.check_timecode(dropped)
        assert [(r.rule_id, r.severity) for r in results] == [("QC-027", "error")]


class TestCancelRerunRefusal:
    """User, 2026-09-25: a mark is withdrawn only while the files still carry the shot's name."""

    def armed(self) -> ShotRow:
        target = row()
        target.deliverables = [delivered("MELT0001_pl01_ref_HD_v01.mp4", "ref_mp4", res="HD")]
        target.rerun = True
        return target

    def test_a_shot_whose_files_carry_its_name_can_be_cancelled(self) -> None:
        assert qc.cancel_rerun_refusal(self.armed()) is None

    def test_a_new_shot_code_refuses(self) -> None:
        target = self.armed()
        target.shot_code_override = "MELT0042"
        refusal = qc.cancel_rerun_refusal(target)
        assert refusal is not None and "MELT0042" in refusal and "put it back" in refusal

    def test_a_trim_since_the_delivery_refuses(self) -> None:
        target = self.armed()
        target.delivered_range = target.current
        assert qc.cancel_rerun_refusal(target) is None
        assert target.current is not None
        target.current = InOut(target.current.in_frame + 2, target.current.out_frame)
        refusal = qc.cancel_rerun_refusal(target)
        assert refusal is not None and "put the range back" in refusal

    def test_a_new_shot_type_refuses(self) -> None:
        target = self.armed()
        target.identity = identity_of("MELT0001_pl02")
        refusal = qc.cancel_rerun_refusal(target)
        assert refusal is not None and "pl02" in refusal
