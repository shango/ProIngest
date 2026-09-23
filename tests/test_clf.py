"""The colour session package: the final EDL with the CDL per event, and any cube (M4.5.2).

COLOR_AND_FORMAT section 1. Two failures are what these tests exist for and neither
looks like a failure: a row conformed from a neighbour's event delivers the wrong
frames, and a row paired with a neighbour's cube delivers the wrong grade under the
right filename. So the matching tests mostly ask what does **not** match, and the cube
tests ask a written file what it actually does to a pixel rather than what it is called.
"""

from __future__ import annotations

import pickle
from pathlib import Path

import numpy as np
import PyOpenColorIO as ocio
import pytest

from proingest.core import clf, color
from proingest.core.models import (
    CDL,
    FrameRate,
    MediaInfo,
    ShotRow,
    SourceEncodingOrigin,
)
from tests.fixtures.names import identity_of

RATE_24 = FrameRate(24)

ACESCCT_MID_GREY = 0.413588
"""The ACEScct encoding of 0.18 scene linear, as `tests/test_color.py` derives it."""

CLF_SOURCE = color.WORKING_SPACE
"""Where a cube starts and ends: the session's timeline space, ACEScct by the standard
decided on 2026-09-18. The tool's own legs get the clip there and carry the result on."""

ONE_STOP_UP = CDL(
    slope=(1.0, 1.0, 1.0),
    offset=(1 / 17.52,) * 3,
    power=(1.0, 1.0, 1.0),
    saturation=1.0,
    sop_text="*ASC_SOP (1.0 1.0 1.0)(0.0571 0.0571 0.0571)(1.0 1.0 1.0)",
    sat_text="*ASC_SAT 1.0",
)
"""A CDL that opens the plate by one stop: `1 / 17.52` of the ACEScct range."""

UNGRADED = clf.ShotColor(source_encoding="ACEScct")
"""A row the session left no grade for, in a clip whose metadata named ACEScct.

The encoding has to be stated now that no default stands in for one (M4.6.1), and
ACEScct keeps the numeric anchors here where they were.
"""

FINAL_EDL = """TITLE: MELT_FINAL_v03
FCM: NON-DROP FRAME

001  MELT0001 V     C        01:00:00:08 01:00:09:08 01:00:00:00 01:00:09:00
* FROM CLIP NAME: MELT0001_pl01.mov
*ASC_SOP (1.020000 0.990000 1.010000)(0.001000 -0.002000 0.000000)(0.980000 1.000000 1.020000)
*ASC_SAT 1.050000

002  MELT0002 V     C        02:00:00:00 02:00:04:00 01:00:09:00 01:00:13:00
* FROM CLIP NAME: MELT0002_pl01.mov
*ASC_SOP (1.000000 1.000000 1.000000)(0.000000 0.000000 0.000000)(1.000000 1.000000 1.000000)
*ASC_SAT 1.000000
"""


def edl(tmp_path: Path, text: str = FINAL_EDL) -> Path:
    path = tmp_path / "MELT_FINAL_v03.edl"
    path.write_text(text)
    return path


def row(
    clip_name: str = "MELT0001_pl01",
    source_encoding: str | None = None,
    source_encoding_origin: SourceEncodingOrigin | None = None,
    **kwargs: object,
) -> ShotRow:
    """A scanned row: 240 frames of ProRes starting at 01:00:00:00. `kwargs` are the media's."""
    media: dict[str, object] = {"frame_count": 240, "start_timecode": 86400, **kwargs}
    return ShotRow(
        turnover_id="turnover001",
        clip_name=clip_name,
        identity=identity_of(clip_name),
        source_encoding=source_encoding,
        source_encoding_origin=source_encoding_origin,
        media=MediaInfo(
            path=Path(f"/turnover/{clip_name}.mov"),
            codec="prores",
            pixel_format="yuv444p12le",
            width=3840,
            height=2160,
            rate=RATE_24,
            start_frame=0,
            **media,  # type: ignore[arg-type]
        ),
    )


class TestReadFinalEdl:
    def test_it_reads_every_video_event(self, tmp_path: Path) -> None:
        events = clf.read_final_edl(edl(tmp_path), RATE_24)
        assert [event.event_id for event in events] == ["001", "002"]
        assert [event.reel for event in events] == ["MELT0001", "MELT0002"]

    def test_the_clip_name_is_the_from_clip_name_comment(self, tmp_path: Path) -> None:
        first = clf.read_final_edl(edl(tmp_path), RATE_24)[0]
        assert first.clip_name == "MELT0001_pl01.mov"
        assert first.clip_stem == "MELT0001_pl01"

    def test_ranges_are_inclusive_where_the_edl_is_not(self, tmp_path: Path) -> None:
        """An EDL's out is the first frame after the cut. Ours is the last one in it."""
        first = clf.read_final_edl(edl(tmp_path), RATE_24)[0]
        assert (first.source_in, first.source_out) == (86408, 86623)
        assert (first.record_in, first.record_out) == (86400, 86615)
        assert first.duration == 216

    def test_the_rate_is_the_project_rate(self, tmp_path: Path) -> None:
        """An EDL states no rate anywhere, so reading one at 24 by default is a guess."""
        first = clf.read_final_edl(edl(tmp_path), FrameRate(30))[0]
        assert first.source_in == 108008

    def test_a_dissolve_still_yields_four_timecodes(self, tmp_path: Path) -> None:
        """A transition puts a duration field ahead of the timecodes on the same line."""
        text = FINAL_EDL.replace(
            "002  MELT0002 V     C        02:00:00:00",
            "002  MELT0002 V     D    024 02:00:00:00",
        )
        second = clf.read_final_edl(edl(tmp_path, text), RATE_24)[1]
        assert second.source_in == 172800

    def test_audio_only_events_are_skipped(self, tmp_path: Path) -> None:
        text = FINAL_EDL + (
            "\n003  MELT0002 A     C        02:00:00:00 02:00:04:00 01:00:09:00 01:00:13:00\n"
        )
        assert len(clf.read_final_edl(edl(tmp_path, text), RATE_24)) == 2

    def test_an_audio_and_video_event_is_kept(self, tmp_path: Path) -> None:
        text = FINAL_EDL.replace("001  MELT0001 V ", "001  MELT0001 B ")
        assert clf.read_final_edl(edl(tmp_path, text), RATE_24)[0].event_id == "001"

    def test_a_comment_under_an_audio_event_does_not_reach_the_one_before(self, tmp_path: Path) -> None:
        text = FINAL_EDL + (
            "\n003  MELT0009 A     C        02:00:00:00 02:00:04:00 01:00:09:00 01:00:13:00\n"
            "* FROM CLIP NAME: MELT0009_pl01.wav\n"
        )
        assert clf.read_final_edl(edl(tmp_path, text), RATE_24)[1].clip_name == "MELT0002_pl01.mov"

    def test_drop_frame_is_refused_rather_than_misread(self, tmp_path: Path) -> None:
        text = FINAL_EDL.replace("01:00:00:08", "01:00:00;08")
        with pytest.raises(clf.ColorSessionError, match="QC-027"):
            clf.read_final_edl(edl(tmp_path, text), RATE_24)

    def test_an_edl_with_no_video_events_is_refused(self, tmp_path: Path) -> None:
        with pytest.raises(clf.ColorSessionError, match="no video events"):
            clf.read_final_edl(edl(tmp_path, "TITLE: EMPTY\nFCM: NON-DROP FRAME\n"), RATE_24)

    def test_a_missing_file_is_refused(self, tmp_path: Path) -> None:
        with pytest.raises(clf.ColorSessionError, match="could not read"):
            clf.read_final_edl(tmp_path / "nothing.edl", RATE_24)

    def test_an_event_short_of_timecodes_is_refused(self, tmp_path: Path) -> None:
        text = "001  MELT0001 V     C        01:00:00:08 01:00:09:08\n"
        with pytest.raises(clf.ColorSessionError, match="not four"):
            clf.read_final_edl(edl(tmp_path, text), RATE_24)


class TestCdl:
    def test_the_numbers_come_off_the_asc_lines(self, tmp_path: Path) -> None:
        cdl = clf.read_final_edl(edl(tmp_path), RATE_24)[0].cdl
        assert cdl is not None
        assert cdl.slope == (1.02, 0.99, 1.01)
        assert cdl.offset == (0.001, -0.002, 0.0)
        assert cdl.power == (0.98, 1.0, 1.02)
        assert cdl.saturation == 1.05

    def test_the_original_text_is_kept_verbatim(self, tmp_path: Path) -> None:
        """The EXR header carries the lines as written, for a reader with no OCIO."""
        cdl = clf.read_final_edl(edl(tmp_path), RATE_24)[0].cdl
        assert cdl is not None
        assert cdl.sop_text == (
            "*ASC_SOP (1.020000 0.990000 1.010000)(0.001000 -0.002000 0.000000)(0.980000 1.000000 1.020000)"
        )
        assert cdl.sat_text == "*ASC_SAT 1.050000"

    def test_an_event_with_no_cdl_carries_none(self, tmp_path: Path) -> None:
        text = "\n".join(line for line in FINAL_EDL.splitlines() if not line.startswith("*ASC"))
        assert clf.read_final_edl(edl(tmp_path, text), RATE_24)[0].cdl is None

    def test_half_a_cdl_is_none_rather_than_a_neutral_grade(self, tmp_path: Path) -> None:
        """Slope 1 offset 0 power 1 is a real grade that says do nothing, not a default."""
        text = "\n".join(line for line in FINAL_EDL.splitlines() if not line.startswith("*ASC_SAT"))
        assert clf.read_final_edl(edl(tmp_path, text), RATE_24)[0].cdl is None

    def test_an_unparseable_sop_line_is_none(self, tmp_path: Path) -> None:
        text = FINAL_EDL.replace("1.020000 0.990000 1.010000", "one 0.990000 1.010000")
        assert clf.read_final_edl(edl(tmp_path, text), RATE_24)[0].cdl is None


RESOLVE_EDL = """TITLE: Turnover199
FCM: NON-DROP FRAME

001  AX       V     C        01:00:00:08 01:00:09:08 01:00:00:00 01:00:09:00
*ASC_SOP (1.020000 0.990000 1.010000)(0.001000 -0.002000 0.000000)(0.980000 1.000000 1.020000)
*ASC_SAT 1.050000

002  AX       V     C        02:00:00:00 02:00:04:00 01:00:09:00 01:00:13:00
*ASC_SOP (1.000000 1.000000 1.000000)(0.000000 0.000000 0.000000)(1.000000 1.000000 1.000000)
*ASC_SAT 1.000000
"""
"""The shape Resolve's CDL export actually writes (`Turnover199/Turnover199.edl`, 2026-09-23):
no `FROM CLIP NAME` on any event, and `AX` for every reel."""


class TestEventMatching:
    def test_a_named_event_matches_its_clip_by_name(self, tmp_path: Path) -> None:
        session = clf.load_session(edl(tmp_path), RATE_24)
        matched = session.event_for(row())
        assert matched is not None and matched.event_id == "001"

    def test_case_alone_does_not_lose_a_match(self, tmp_path: Path) -> None:
        text = FINAL_EDL.replace("MELT0001_pl01.mov", "melt0001_PL01.MOV")
        session = clf.load_session(edl(tmp_path, text), RATE_24)
        matched = session.event_for(row())
        assert matched is not None and matched.event_id == "001"

    def test_a_named_event_never_matches_another_clip(self, tmp_path: Path) -> None:
        """The name has to agree even when the timecode would fit."""
        session = clf.load_session(edl(tmp_path), RATE_24)
        assert session.event_for(row("MELT0007_pl01")) is None

    def test_an_unnamed_event_matches_the_file_whose_timecode_holds_it(self, tmp_path: Path) -> None:
        """OQ-30, answered by the real export: timecode is the only thing it states."""
        session = clf.load_session(edl(tmp_path, RESOLVE_EDL), RATE_24)
        matched = session.event_for(row("C0145"))
        assert matched is not None and matched.event_id == "001"
        later = row("C0152", start_timecode=2 * 86400)
        matched = session.event_for(later)
        assert matched is not None and matched.event_id == "002"

    def test_the_reel_is_never_read(self, tmp_path: Path) -> None:
        text = RESOLVE_EDL.replace("001  AX", "001  ZZ")
        session = clf.load_session(edl(tmp_path, text), RATE_24)
        assert session.event_for(row("C0145")) is not None

    def test_an_unnamed_event_outside_the_media_matches_nothing(self, tmp_path: Path) -> None:
        text = RESOLVE_EDL.replace("01:00:00:08 01:00:09:08", "05:00:00:08 05:00:09:08")
        session = clf.load_session(edl(tmp_path, text), RATE_24)
        assert session.event_for(row("C0145")) is None

    def test_an_event_running_past_the_end_of_the_file_matches_nothing(self, tmp_path: Path) -> None:
        session = clf.load_session(edl(tmp_path, RESOLVE_EDL), RATE_24)
        assert session.event_for(row("C0145", frame_count=100)) is None

    def test_two_events_inside_one_file_are_both_candidates_and_neither_is_chosen(
        self, tmp_path: Path
    ) -> None:
        text = RESOLVE_EDL.replace("02:00:00:00 02:00:04:00", "01:00:02:00 01:00:04:00")
        session = clf.load_session(edl(tmp_path, text), RATE_24)
        assert [event.event_id for event in session.candidates(row("C0145"))] == ["001", "002"]
        assert session.event_for(row("C0145")) is None

    def test_media_with_no_timecode_matches_no_unnamed_event(self, tmp_path: Path) -> None:
        session = clf.load_session(edl(tmp_path, RESOLVE_EDL), RATE_24)
        assert session.event_for(row("C0145", start_timecode=None)) is None


class TestEdlLayouts:
    def test_resolves_real_export_reads_with_crlf(self, tmp_path: Path) -> None:
        events = clf.read_final_edl(edl(tmp_path, RESOLVE_EDL.replace("\n", "\r\n")), RATE_24)
        assert [event.event_id for event in events] == ["001", "002"]
        assert all(event.clip_name == "" and event.cdl is not None for event in events)

    def test_an_audio_line_under_the_same_event_keeps_the_pictures_comments(self, tmp_path: Path) -> None:
        text = FINAL_EDL.replace(
            "* FROM CLIP NAME: MELT0001_pl01.mov",
            "001  MELT0001 A     C        01:00:00:08 01:00:09:08 01:00:00:00 01:00:09:00\n"
            "* FROM CLIP NAME: MELT0001_pl01.mov",
        )
        first = clf.read_final_edl(edl(tmp_path, text), RATE_24)[0]
        assert first.clip_name == "MELT0001_pl01.mov"
        assert first.cdl is not None

    def test_a_wipe_is_an_event_not_a_comment(self, tmp_path: Path) -> None:
        text = FINAL_EDL.replace("002  MELT0002 V     C       ", "002  MELT0002 V     W001 030")
        events = clf.read_final_edl(edl(tmp_path, text), RATE_24)
        assert [event.event_id for event in events] == ["001", "002"]
        assert events[0].clip_name == "MELT0001_pl01.mov"

    def test_a_zero_length_event_conforms_nothing(self, tmp_path: Path) -> None:
        """The outgoing side of a dissolve is written as a cut covering no frames."""
        text = FINAL_EDL.replace("02:00:00:00 02:00:04:00", "02:00:00:00 02:00:00:00")
        events = clf.read_final_edl(edl(tmp_path, text), RATE_24)
        assert [event.event_id for event in events] == ["001"]


class TestApprovedInOut:
    def test_the_event_becomes_frames_in_this_media(self, tmp_path: Path) -> None:
        event = clf.read_final_edl(edl(tmp_path), RATE_24)[0]
        media = row().media
        assert media is not None
        approved = clf.approved_in_out(event, media)
        assert approved is not None
        assert (approved.in_frame, approved.out_frame) == (8, 223)
        assert approved.duration == event.duration

    def test_a_sequence_keeps_its_own_frame_numbers(self, tmp_path: Path) -> None:
        event = clf.read_final_edl(edl(tmp_path), RATE_24)[0]
        media = row().media
        assert media is not None
        numbered = MediaInfo(**{**media.__dict__, "start_frame": 1001, "is_sequence": True})
        approved = clf.approved_in_out(event, numbered)
        assert approved is not None
        assert (approved.in_frame, approved.out_frame) == (1009, 1224)

    def test_media_with_no_timecode_gives_nothing(self, tmp_path: Path) -> None:
        """An origin guessed here would conform every row to the wrong frames."""
        event = clf.read_final_edl(edl(tmp_path), RATE_24)[0]
        media = row().media
        assert media is not None
        blank = MediaInfo(**{**media.__dict__, "start_timecode": None})
        assert clf.approved_in_out(event, blank) is None


class TestSession:
    def test_it_reads_the_edl(self, tmp_path: Path) -> None:
        session = clf.load_session(edl(tmp_path), RATE_24)
        assert len(session.events) == 2
        assert session.edl_path == edl(tmp_path)


class TestShotColor:
    """What rides on a render job: a colour space name and the CDL.

    The failure these guard against is the one COLOR_AND_FORMAT section 1 warns about
    under the chain diagram: a grade applied in the wrong space, or a conversion applied
    twice. It raises nothing and looks like a grade. So these ask **which** transforms a
    chain contains as well as what it does to a pixel, because two arrangements agree on
    a pixel whenever the tool's own leg happens to be identity.
    """

    def applied(self, shot_color: clf.ShotColor, value: float) -> float:
        """One neutral ACEScct value through the plate branch, green channel out."""
        pixels = np.array([[[value, value, value]]], dtype=np.float32)
        color.apply(pixels, color.processor(*shot_color.plate_transforms()))
        return float(pixels[0, 0, 1])

    def viewed(self, shot_color: clf.ShotColor, value: float) -> float:
        pixels = np.array([[[value, value, value]]], dtype=np.float32)
        color.apply(pixels, color.processor(*shot_color.view_transforms()))
        return float(pixels[0, 0, 1])

    def test_with_no_grade_the_chain_supplies_the_conversion_itself(self) -> None:
        """ACEScct mid grey is 0.18 scene linear, and nothing else is."""
        assert self.applied(UNGRADED, ACESCCT_MID_GREY) == pytest.approx(0.18, abs=1e-3)

    def test_the_cdl_sits_between_the_two_legs(self) -> None:
        """Into ACEScct from the clip's encoding, the CDL, out to ACEScg."""
        shot_color = clf.ShotColor(source_encoding="S-Log3 S-Gamut3.Cine", cdl=ONE_STOP_UP)
        legs_in, grade, legs_out = shot_color.plate_transforms()
        assert (legs_in.getSrc(), legs_in.getDst()) == ("S-Log3 S-Gamut3.Cine", color.WORKING_SPACE)
        assert isinstance(grade, ocio.CDLTransform)
        assert grade.getOffset() == pytest.approx([1 / 17.52] * 3)
        assert (legs_out.getSrc(), legs_out.getDst()) == (color.WORKING_SPACE, color.PLATE_SPACE)

    def test_an_ungraded_plate_chain_is_one_leg_to_acescg(self) -> None:
        """The reference still's chain, and every row the session has no grade for."""
        transforms = UNGRADED.plate_transforms()
        assert len(transforms) == 1
        assert transforms[0].getDst() == color.PLATE_SPACE

    def test_a_graded_row_with_no_encoding_is_refused(self) -> None:
        """The grade is applied in ACEScct and the encoding is what gets the clip there,
        so a graded row cannot render without it. QC-046 is an error on every plate."""
        with pytest.raises(clf.ClfError, match="no source encoding"):
            clf.ShotColor(cdl=ONE_STOP_UP).plate_transforms()

    def test_no_grade_and_no_encoding_is_refused_rather_than_guessed(self) -> None:
        """The one chain that cannot be built. Nothing turns those pixels into ACEScg.

        Passing them through would deliver a log frame under a header claiming ACEScg,
        which is the silent wrong image this module is written to make impossible.
        QC-046 and QC-047 stop the row long before a worker reaches this.
        """
        with pytest.raises(clf.ClfError, match="no source encoding"):
            clf.DEFAULT_SHOT_COLOR.plate_transforms()

    def test_the_cdl_is_applied_in_acescct_whatever_the_clip_was_shot_on(self) -> None:
        """One stop up in ACEScct doubles the plate, from a camera log as from ACEScct.

        S-Log3 puts 18% grey at 10 bit code 420. Applied in the camera's own log instead,
        the same offset would be a different number of stops and nothing would say so.
        """
        shot_color = clf.ShotColor(source_encoding="S-Log3 S-Gamut3.Cine", cdl=ONE_STOP_UP)
        assert self.applied(shot_color, 420 / 1023) == pytest.approx(0.36, abs=2e-3)
        from_acescct = clf.ShotColor(source_encoding="ACEScct", cdl=ONE_STOP_UP)
        assert self.applied(from_acescct, ACESCCT_MID_GREY) == pytest.approx(0.36, abs=1e-3)

    def test_the_plate_branch_is_unbounded_and_the_view_branch_is_not(self) -> None:
        """ACEScct 1.0 is 222 in scene linear; every display rendering tone maps it.

        Display range rather than clamped: OCIO clamps nothing, and what finally bounds
        the reference is ffmpeg's own pixel format. 1.03 against 222 is the difference
        the branch exists for.
        """
        assert self.applied(UNGRADED, 1.0) > 200.0
        assert self.viewed(UNGRADED, 1.0) < 1.1

    def test_the_view_branch_is_the_plate_branch_plus_one_leg(self) -> None:
        """Compared by what each transform says it is: OCIO transforms compare by identity."""
        plate = [str(item) for item in UNGRADED.plate_transforms()]
        view = [str(item) for item in UNGRADED.view_transforms()]
        assert view[: len(plate)] == plate
        assert len(view) == len(plate) + 1

    def test_a_graded_view_branch_is_the_three_legs_and_the_output_transform(self) -> None:
        """Four transforms, which is what `view_lut` bakes into a shot's viewing cube."""
        shot_color = clf.ShotColor(source_encoding="ACEScct", cdl=ONE_STOP_UP)
        assert len(shot_color.view_transforms()) == 4

    def test_it_pickles(self) -> None:
        """A job crosses a spawn boundary, so everything it carries has to survive one."""
        shot_color = clf.ShotColor(source_encoding="ACEScct", cdl=ONE_STOP_UP)
        assert pickle.loads(pickle.dumps(shot_color)) == shot_color


class TestShotColorFromRow:
    """`clf.shot_color` is the one place a row becomes a chain, ingested or not."""

    def test_a_matched_row_carries_its_cdl(self, tmp_path: Path) -> None:
        scanned = row()
        event = clf.load_session(edl(tmp_path), RATE_24).event_for(scanned)
        assert event is not None
        scanned.cdl = event.cdl
        assert clf.shot_color(scanned).cdl is not None

    def test_a_row_with_no_cdl_gets_the_ungraded_chain(self) -> None:
        assert clf.shot_color(row("MELT0009_pl01")).cdl is None

    def test_the_source_encoding_comes_off_the_row(self, tmp_path: Path) -> None:
        """A per clip fact, so the session neither carries it nor is asked for it."""
        assert clf.shot_color(row(source_encoding="ACEScc")).source_encoding == "ACEScc"

    def test_the_encoding_is_resolved_through_the_table_on_the_way(self, tmp_path: Path) -> None:
        """What the shooter wrote in, a colour space out (M4.6.3)."""
        shot_color = clf.shot_color(row(source_encoding="BM Film"))
        assert shot_color.source_encoding == "BMDFilm WideGamut Gen5"

    def test_a_name_the_table_cannot_resolve_is_carried_as_none(self, tmp_path: Path) -> None:
        """QC-047 is where this is reported. A graded row renders regardless."""
        assert clf.shot_color(row(source_encoding="S-Log3")).source_encoding is None

    def test_the_origin_of_the_name_travels_with_it(self, tmp_path: Path) -> None:
        scanned = row(source_encoding="BM Film", source_encoding_origin="container tag")
        assert clf.shot_color(scanned).source_encoding_origin == "container tag"

    def test_a_name_that_resolved_to_nothing_still_says_where_it_came_from(self, tmp_path: Path) -> None:
        """Which is the case the origin exists for: QC-047 names a string to correct."""
        scanned = row(source_encoding="S-Log3", source_encoding_origin="clip metadata")
        shot_color = clf.shot_color(scanned)
        assert shot_color.source_encoding is None
        assert shot_color.source_encoding_origin == "clip metadata"

    def test_a_row_naming_no_encoding_gets_a_chain_that_names_none(self, tmp_path: Path) -> None:
        """Renderable where the CLF is the whole chain, and QC-046 where it is not."""
        assert clf.shot_color(row()).source_encoding is None
