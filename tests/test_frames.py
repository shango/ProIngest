"""Frame math and In/Out input parsing.

Covers all four input formats in both timecode modes, per docs/ARCHITECTURE.md testing.
"""

from __future__ import annotations

import pytest

from proingest.core import frames
from proingest.core.frames import EditContext

FPS = 24

# A clip whose media starts at source frame 0 with timecode 01:00:00:00, placed on the
# timeline at record timecode 10:00:00:00 starting from source frame 120.
CONTEXT = EditContext(
    fps=FPS,
    source_start=0,
    source_start_timecode=frames.timecode_to_frames("01:00:00:00", FPS),
    record_start_timecode=frames.timecode_to_frames("10:00:00:00", FPS),
    record_start_source_frame=120,
)
RECORD_CONTEXT = EditContext(**{**CONTEXT.__dict__, "mode": "record"})


class TestBasicMath:
    def test_duration_is_inclusive(self) -> None:
        assert frames.duration(100, 100) == 1
        assert frames.duration(1000, 1239) == 240

    def test_max_available_out(self) -> None:
        assert frames.max_available_out(0, 300) == 299
        assert frames.max_available_out(1001, 240) == 1240

    def test_output_numbering_starts_at_1001(self) -> None:
        assert frames.output_frame_for(in_frame=500, source_frame=500) == 1001
        assert frames.output_frame_for(in_frame=500, source_frame=501) == 1002

    def test_output_and_source_are_inverses(self) -> None:
        in_frame = 733
        for offset in range(240):
            output = frames.output_frame_for(in_frame, in_frame + offset)
            assert frames.source_frame_for(in_frame, output) == in_frame + offset


class TestNominalRate:
    @pytest.mark.parametrize(("fps", "expected"), [(24, 24), (23.976, 24), (29.97, 30), (25, 25)])
    def test_rounds_to_counting_rate(self, fps: float, expected: int) -> None:
        assert frames.nominal_rate(fps) == expected

    def test_rejects_non_positive(self) -> None:
        with pytest.raises(ValueError):
            frames.nominal_rate(0)


class TestTimecode:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("00:00:00:00", 0),
            ("00:00:00:23", 23),
            ("00:00:01:00", 24),
            ("00:01:00:00", 1440),
            ("01:00:00:00", 86400),
            ("10:00:00:00", 864000),
        ],
    )
    def test_to_frames(self, text: str, expected: int) -> None:
        assert frames.timecode_to_frames(text, FPS) == expected

    @pytest.mark.parametrize(
        "total", [0, 1, 23, 24, 1439, 1440, 86400, 86400 + 240, 2073599]
    )
    def test_round_trip(self, total: int) -> None:
        rendered = frames.frames_to_timecode(total, FPS)
        assert frames.timecode_to_frames(rendered, FPS) == total

    def test_wraps_at_24_hours(self) -> None:
        day = 24 * 60 * 60 * FPS
        assert frames.frames_to_timecode(day, FPS) == "00:00:00:00"

    def test_drop_frame_is_rejected(self) -> None:
        """UI_SPEC section 5: `;` is rejected with the QC-027 message."""
        with pytest.raises(ValueError, match="QC-027"):
            frames.timecode_to_frames("01:00:00;12", FPS)

    @pytest.mark.parametrize(
        "text", ["01:00:00:24", "01:60:00:00", "01:00:60:00", "1:2:3:4", "abc", "01:00:00"]
    )
    def test_rejects_malformed(self, text: str) -> None:
        with pytest.raises(ValueError):
            frames.timecode_to_frames(text, FPS)

    def test_frame_number_must_be_below_rate(self) -> None:
        assert frames.timecode_to_frames("00:00:00:24", 25) == 24
        with pytest.raises(ValueError):
            frames.timecode_to_frames("00:00:00:24", 24)

    def test_negative_is_rejected(self) -> None:
        with pytest.raises(ValueError):
            frames.frames_to_timecode(-1, FPS)


class TestParseInOut:
    def test_absolute_frame(self) -> None:
        assert frames.parse_in_out("150", current=0, context=CONTEXT).frame == 150

    @pytest.mark.parametrize(("text", "expected"), [("+12", 112), ("-8", 92), ("+0", 100)])
    def test_relative_offset(self, text: str, expected: int) -> None:
        assert frames.parse_in_out(text, current=100, context=CONTEXT).frame == expected

    def test_relative_is_detected_before_absolute(self) -> None:
        """`+12` is an offset; `12` is an absolute frame. Order in section 5 matters."""
        assert frames.parse_in_out("+12", current=100, context=CONTEXT).frame == 112
        assert frames.parse_in_out("12", current=100, context=CONTEXT).frame == 12

    def test_source_timecode(self) -> None:
        """Media starts at 01:00:00:00 = source frame 0, so 01:00:00:10 is frame 10."""
        assert frames.parse_in_out("01:00:00:10", current=0, context=CONTEXT).frame == 10
        assert frames.parse_in_out("01:00:05:00", current=0, context=CONTEXT).frame == 120

    def test_record_timecode(self) -> None:
        """Record 10:00:00:00 anchors to source frame 120."""
        assert frames.parse_in_out("10:00:00:00", 0, RECORD_CONTEXT).frame == 120
        assert frames.parse_in_out("10:00:00:10", 0, RECORD_CONTEXT).frame == 130

    def test_same_timecode_means_different_frames_per_mode(self) -> None:
        text = "10:00:00:00"
        assert frames.parse_in_out(text, 0, CONTEXT).frame != frames.parse_in_out(
            text, 0, RECORD_CONTEXT
        ).frame

    def test_whitespace_is_tolerated(self) -> None:
        assert frames.parse_in_out("  150  ", current=0, context=CONTEXT).frame == 150

    @pytest.mark.parametrize("text", ["", "   ", "abc", "12.5", "1001a", "--5", "01:00:00"])
    def test_unrecognized_input_keeps_no_frame(self, text: str) -> None:
        result = frames.parse_in_out(text, current=100, context=CONTEXT)
        assert not result.ok
        assert result.frame is None
        assert result.error

    def test_drop_frame_reports_qc_027(self) -> None:
        result = frames.parse_in_out("01:00:00;12", current=0, context=CONTEXT)
        assert not result.ok
        assert result.error is not None
        assert "QC-027" in result.error

    def test_relative_offset_may_go_negative(self) -> None:
        """Out of range is QC-031's job; parsing keeps the value so the editor sees it."""
        assert frames.parse_in_out("-500", current=100, context=CONTEXT).frame == -400


class TestSourceFrameToTimecode:
    def test_source_mode(self) -> None:
        assert frames.source_frame_to_timecode(0, CONTEXT) == "01:00:00:00"
        assert frames.source_frame_to_timecode(24, CONTEXT) == "01:00:01:00"

    def test_record_mode(self) -> None:
        assert frames.source_frame_to_timecode(120, RECORD_CONTEXT) == "10:00:00:00"

    def test_inverts_parse_in_out(self) -> None:
        for source_frame in (0, 1, 120, 239, 1000):
            text = frames.source_frame_to_timecode(source_frame, CONTEXT)
            assert frames.parse_in_out(text, 0, CONTEXT).frame == source_frame
