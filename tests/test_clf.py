"""The final EDL, which is the cut, and a shot's colour chain from its AMF.

COLOR_AND_FORMAT section 1. Two failures are what these tests exist for and neither
looks like a failure: a row conformed from a neighbour's event delivers the wrong
frames, and a chain with a look in the wrong place delivers the wrong grade under the
right filename. So the matching tests mostly ask what does **not** match, and the chain
tests ask what a written CLF actually does to a pixel rather than what it is called.
"""

from __future__ import annotations

import pickle
from pathlib import Path

import numpy as np
import PyOpenColorIO as ocio
import pytest

from proingest.core import clf, color
from proingest.core.models import (
    FrameRate,
    Grade,
    GradeLook,
    MediaInfo,
    ShotRow,
    SourceEncodingOrigin,
)
from tests.fixtures import color as color_fixtures
from tests.fixtures.names import identity_of

RATE_24 = FrameRate(24)

ACESCCT_MID_GREY = 0.413588
"""The ACEScct encoding of 0.18 scene linear, as `tests/test_color.py` derives it."""

UNGRADED = color_fixtures.UNGRADED
"""A clip whose AMF names ACEScct and no look, viewed on sRGB.

ACEScct keeps the numeric anchors here where they were before the AMF (2026-09-28).
"""

GAMUT_COMPRESS = GradeLook("look", "ACES 1.3 Reference Gamut Compression")


def doubled(tmp_path: Path) -> GradeLook:
    """A CLF that doubles scene linear, ACES2065-1 in and out."""
    return GradeLook("clf", str(color_fixtures.make_clf(tmp_path / "node_1.clf", gain=2.0)))


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
        assert all(event.clip_name == "" for event in events)

    def test_an_audio_line_under_the_same_event_keeps_the_pictures_comments(self, tmp_path: Path) -> None:
        text = FINAL_EDL.replace(
            "* FROM CLIP NAME: MELT0001_pl01.mov",
            "001  MELT0001 A     C        01:00:00:08 01:00:09:08 01:00:00:00 01:00:09:00\n"
            "* FROM CLIP NAME: MELT0001_pl01.mov",
        )
        first = clf.read_final_edl(edl(tmp_path, text), RATE_24)[0]
        assert first.clip_name == "MELT0001_pl01.mov"

    def test_a_wipe_is_an_event_not_a_comment(self, tmp_path: Path) -> None:
        text = FINAL_EDL.replace("002  MELT0002 V     C       ", "002  MELT0002 V     W001 030")
        events = clf.read_final_edl(edl(tmp_path, text), RATE_24)
        assert [event.event_id for event in events] == ["001", "002"]
        assert events[0].clip_name == "MELT0001_pl01.mov"

    def test_an_audio_only_event_takes_a_number_but_no_place(self, tmp_path: Path) -> None:
        """Turnover134 (2026-10-05): `002 AX A` between two pictures. Resolve's AMF index
        counts video clips only, so the picture after it is the second, not the third."""
        text = FINAL_EDL.replace(
            "002  MELT0002 V     C       ",
            "002  MELT0001 A     C        01:00:00:08 01:00:09:08 01:00:00:00 01:00:09:00\n"
            "* FROM CLIP NAME: MELT0001_pl01.mov\n\n"
            "003  MELT0002 V     C       ",
        )
        events = clf.read_final_edl(edl(tmp_path, text), RATE_24)
        assert [(event.event_id, event.position) for event in events] == [("001", 0), ("003", 1)]

    def test_the_outgoing_side_of_a_dissolve_takes_no_place(self, tmp_path: Path) -> None:
        text = FINAL_EDL.replace("02:00:00:00 02:00:04:00 01:00:09:00", "02:00:00:00 02:00:00:00 01:00:09:00")
        text += "003  MELT0003 V     C        03:00:00:00 03:00:01:00 01:00:13:00 01:00:14:00\n"
        events = clf.read_final_edl(edl(tmp_path, text), RATE_24)
        assert [(event.event_id, event.position) for event in events] == [("001", 0), ("003", 1)]

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
    """What rides on a render job: a colour space name, the AMF's looks and its display.

    The failure these guard against is the one COLOR_AND_FORMAT section 1 warns about
    under the chain diagram: a look applied in the wrong space, or a conversion applied
    twice. It raises nothing and looks like a grade. So these ask **which** transforms a
    chain contains as well as what it does to a pixel.
    """

    def applied(self, shot_color: clf.ShotColor, value: float) -> float:
        """One neutral value through the plate branch, green channel out."""
        pixels = np.array([[[value, value, value]]], dtype=np.float32)
        color.apply(pixels, color.processor(*shot_color.plate_transforms()))
        return float(pixels[0, 0, 1])

    def viewed(self, shot_color: clf.ShotColor, value: float) -> float:
        pixels = np.array([[[value, value, value]]], dtype=np.float32)
        color.apply(pixels, color.processor(*shot_color.view_transforms()))
        return float(pixels[0, 0, 1])

    def test_with_no_look_the_chain_supplies_the_conversion_itself(self) -> None:
        """ACEScct mid grey is 0.18 scene linear, and nothing else is."""
        assert self.applied(UNGRADED, ACESCCT_MID_GREY) == pytest.approx(0.18, abs=1e-3)

    def test_the_looks_sit_in_aces2065_1_in_the_amf_s_order(self, tmp_path: Path) -> None:
        """Into ACES2065-1 from the clip's encoding, each look, out to ACEScg."""
        shot_color = clf.ShotColor(
            source_encoding="S-Log3 S-Gamut3.Cine", looks=(GAMUT_COMPRESS, doubled(tmp_path))
        )
        into, compress, node, out = shot_color.plate_transforms()
        assert (into.getSrc(), into.getDst()) == ("S-Log3 S-Gamut3.Cine", color.ACES)
        assert isinstance(compress, ocio.LookTransform) and compress.getLooks() == GAMUT_COMPRESS.name
        assert isinstance(node, ocio.FileTransform) and node.getSrc().endswith("node_1.clf")
        assert (out.getSrc(), out.getDst()) == (color.ACES, color.PLATE_SPACE)

    def test_a_clf_does_to_a_pixel_what_it_says(self, tmp_path: Path) -> None:
        """Doubling in ACES2065-1 doubles the plate: the matrices either side are linear."""
        graded = clf.ShotColor(source_encoding="ACEScct", looks=(doubled(tmp_path),))
        assert self.applied(graded, ACESCCT_MID_GREY) == pytest.approx(0.36, abs=1e-3)

    def test_turnover097_s_node_changes_mid_grey(self) -> None:
        """A real CLF shape: AP0 to ACEScct, a 33 cube, back. Skipped where the sample is absent."""
        node = Path(__file__).parent.parent / "turnover097_09_28_26_danielluckett" / "collected files"
        node = node / "C4261_1_ClipGraph_CorrectorNode_1.clf"
        if not node.is_file():
            pytest.skip("turnover097 is not committed")
        graded = clf.ShotColor(source_encoding="ACEScct", looks=(GradeLook("clf", str(node)),))
        assert self.applied(graded, ACESCCT_MID_GREY) != pytest.approx(0.18, abs=1e-2)

    def test_an_ungraded_plate_chain_is_one_leg_to_acescg(self) -> None:
        """The reference still's chain, and every clip whose AMF lists no look."""
        transforms = UNGRADED.plate_transforms()
        assert len(transforms) == 1
        assert transforms[0].getDst() == color.PLATE_SPACE

    def test_a_graded_row_with_no_encoding_is_refused(self, tmp_path: Path) -> None:
        """The encoding is what gets the clip into ACES, so nothing renders without it."""
        with pytest.raises(clf.ClfError, match="no source encoding"):
            clf.ShotColor(looks=(doubled(tmp_path),)).plate_transforms()

    def test_no_look_and_no_encoding_is_refused_rather_than_guessed(self) -> None:
        """Passing the pixels through would deliver a log frame under a header claiming
        ACEScg. QC-046 and QC-047 stop the row long before a worker reaches this."""
        with pytest.raises(clf.ClfError, match="no source encoding"):
            clf.DEFAULT_SHOT_COLOR.plate_transforms()

    def test_the_plate_branch_is_unbounded_and_the_view_branch_is_not(self) -> None:
        """ACEScct 1.0 is 222 in scene linear; every display rendering tone maps it."""
        assert self.applied(UNGRADED, 1.0) > 200.0
        assert self.viewed(UNGRADED, 1.0) < 1.1

    def test_the_view_branch_is_the_plate_branch_plus_the_amf_s_output(self) -> None:
        """Compared by what each transform says it is: OCIO transforms compare by identity."""
        plate = [str(item) for item in UNGRADED.plate_transforms()]
        view = UNGRADED.view_transforms()
        assert [str(item) for item in view[: len(plate)]] == plate
        (output,) = view[len(plate) :]
        assert isinstance(output, ocio.DisplayViewTransform)
        assert (output.getDisplay(), output.getView()) == (color_fixtures.DISPLAY, color_fixtures.VIEW)

    def test_the_display_follows_the_amf(self) -> None:
        """Gamma 2.2 Rec.709 is turnover097's; it renders mid grey differently from sRGB."""
        gamma = clf.ShotColor(
            source_encoding="ACEScct", display="Gamma 2.2 Rec.709 - Display", view=color_fixtures.VIEW
        )
        assert self.viewed(gamma, ACESCCT_MID_GREY) != pytest.approx(
            self.viewed(UNGRADED, ACESCCT_MID_GREY), abs=1e-3
        )

    def test_no_output_transform_is_refused_for_a_reference(self) -> None:
        with pytest.raises(clf.ClfError, match="QC-079"):
            clf.ShotColor(source_encoding="ACEScct").view_transforms()

    def test_it_pickles(self, tmp_path: Path) -> None:
        """A job crosses a spawn boundary, so everything it carries has to survive one."""
        shot_color = clf.ShotColor(source_encoding="ACEScct", looks=(GAMUT_COMPRESS, doubled(tmp_path)))
        assert pickle.loads(pickle.dumps(shot_color)) == shot_color


class TestShotColorFromRow:
    """`clf.shot_color` is the one place a row becomes a chain."""

    def test_a_graded_row_carries_its_looks_and_display(self, tmp_path: Path) -> None:
        graded = row(source_encoding="ACEScct")
        graded.grade = Grade(
            amf=tmp_path / "x.amf",
            looks=(GAMUT_COMPRESS,),
            display=color_fixtures.DISPLAY,
            view=color_fixtures.VIEW,
        )
        shot_color = clf.shot_color(graded)
        assert shot_color.looks == (GAMUT_COMPRESS,)
        assert (shot_color.display, shot_color.view, shot_color.amf) == (
            color_fixtures.DISPLAY,
            color_fixtures.VIEW,
            "x.amf",
        )

    def test_a_row_with_no_amf_gets_no_looks(self) -> None:
        assert clf.shot_color(row("MELT0009_pl01")).looks == ()

    def test_the_source_encoding_comes_off_the_row(self) -> None:
        assert clf.shot_color(row(source_encoding="ACEScc")).source_encoding == "ACEScc"

    def test_a_name_the_config_lacks_is_carried_as_none(self) -> None:
        """QC-047 is where this is reported."""
        assert clf.shot_color(row(source_encoding="S-Log3")).source_encoding is None

    def test_the_origin_of_the_name_travels_with_it(self) -> None:
        scanned = row(source_encoding="ACEScc", source_encoding_origin="AMF")
        assert clf.shot_color(scanned).source_encoding_origin == "AMF"

    def test_a_row_naming_no_encoding_gets_a_chain_that_names_none(self) -> None:
        assert clf.shot_color(row()).source_encoding is None


class TestMotionEffects:
    """An M2 at speed 0 is a freeze: one source frame held (Turnover121, 2026-09-23)."""

    EDL = (
        "TITLE: T\nFCM: NON-DROP FRAME\n\n"
        "001  AX       V     C        00:00:40:10 00:00:50:10 01:00:10:00 01:00:20:00  \n"
        "M2   AX             000.0                00:00:40:10\n\n"
        "002  AX       V     C        00:00:06:04 00:00:16:04 01:00:20:00 01:00:30:00  \n"
    )

    def test_a_freeze_uses_one_frame(self, tmp_path: Path) -> None:
        path = tmp_path / "t.edl"
        path.write_text(self.EDL)
        frozen, cut = clf.read_final_edl(path, FrameRate(24))
        assert frozen.freeze and not cut.freeze
        assert frozen.used_out == frozen.source_in == 970
        assert frozen.duration == 1
        assert frozen.use == (970, 1209), "the stated out tells two holds of one frame apart"
        assert cut.duration == 240

    def test_a_retime_or_a_reversal_is_flagged_and_a_freeze_is_not(self, tmp_path: Path) -> None:
        path = tmp_path / "t.edl"
        path.write_text(
            self.EDL.replace("000.0", "048.0") + "M2   AX             -024.0                00:00:06:04\n"
        )
        fast, reversed_ = clf.read_final_edl(path, FrameRate(24))
        assert fast.retimed(FrameRate(24)) and reversed_.retimed(FrameRate(24))
        assert not fast.freeze

    def test_normal_speed_and_a_freeze_are_not_retimes(self, tmp_path: Path) -> None:
        path = tmp_path / "t.edl"
        path.write_text(self.EDL + "M2   AX             024.0                00:00:06:04\n")
        frozen, normal = clf.read_final_edl(path, FrameRate(24))
        assert not frozen.retimed(FrameRate(24)) and not normal.retimed(FrameRate(24))
