"""The colour session package: the final EDL with the CDL per event, and any cube (M4.5.2).

COLOR_AND_FORMAT section 1. Two failures are what these tests exist for and neither
looks like a failure: a row conformed from a neighbour's event delivers the wrong
frames, and a row paired with a neighbour's cube delivers the wrong grade under the
right filename. So the matching tests mostly ask what does **not** match, and the cube
tests ask a written file what it actually does to a pixel rather than what it is called.
"""

from __future__ import annotations

import hashlib
import pickle
from pathlib import Path

import numpy as np
import PyOpenColorIO as ocio
import pytest

from proingest.core import clf, color, naming
from proingest.core.models import (
    CDL,
    FrameRate,
    InOut,
    MediaInfo,
    ShotRow,
    SourceEncodingOrigin,
    Turnover,
)
from tests.fixtures import color as color_fixtures

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
    return ShotRow(
        turnover_id="turnover001",
        clip_name=clip_name,
        identity=naming.parse_clip_name(clip_name),
        source_encoding=source_encoding,
        source_encoding_origin=source_encoding_origin,
        media=MediaInfo(
            path=Path(f"/turnover/{clip_name}.mov"),
            codec="prores",
            pixel_format="yuv444p12le",
            width=3840,
            height=2160,
            rate=RATE_24,
            frame_count=240,
            start_frame=0,
            start_timecode=86400,
            **kwargs,  # type: ignore[arg-type]
        ),
    )


def write_clf(path: Path, *transforms: ocio.Transform) -> Path:
    """A real CLF, written by OpenColorIO rather than typed out here.

    Written rather than committed for the same reason test media is: a fixture that
    describes a transform is a second implementation of one, and this one is the tool's
    own library answering what it would actually load.
    """
    group = ocio.GroupTransform()
    for transform in transforms:
        group.appendTransform(transform)
    baked = color.config().getProcessor(group).createGroupTransform()
    baked.write(formatName="Academy/ASC Common LUT Format", config=color.config(), fileName=str(path))
    return path


GRADE = ocio.CDLTransform(slope=[1.05, 1.0, 0.95], offset=[0.0, 0.0, 0.0], power=[1.0, 1.0, 1.0], sat=1.1)


def plate_clf(path: Path) -> Path:
    """What Generate LUT writes out of an ACEScct session: the grade alone, log in, log out."""
    return write_clf(path, GRADE)


def display_clf(path: Path, size: int = 9) -> Path:
    """A CLF with the ACES output transform baked into it, which is QC-039's failure.

    Sampled into a 3D LUT because that is the only way such a CLF exists: the output
    transform uses ops CLF cannot express, so a session that exported one would have
    had to bake it, exactly as here.
    """
    view = ocio.DisplayViewTransform(src=CLF_SOURCE, display="sRGB - Display", view="ACES 1.0 - SDR Video")
    cpu = color.config().getProcessor(view).getDefaultCPUProcessor()
    lut = ocio.Lut3DTransform(gridSize=size, interpolation=color.INTERPOLATION)
    for red in range(size):
        for green in range(size):
            for blue in range(size):
                sample = [value / (size - 1) for value in (red, green, blue)]
                lut.setValue(red, green, blue, *cpu.applyRGB(sample))
    return write_clf(path, lut)


def probe_step(path: Path) -> float:
    """The number `_probe_grade_only` works from: how far apart the two top samples still
    are after the cube, widest channel."""
    cpu = color.processor(ocio.FileTransform(src=str(path), interpolation=color.INTERPOLATION))
    samples = np.array([[[clf.LOG_WHITE] * 3, [clf.LOG_NEAR_WHITE] * 3]], dtype=np.float32)
    color.apply(samples, cpu)
    return float(np.max(samples[0, 0] - samples[0, 1]))


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


class TestEventMatching:
    def test_a_row_matches_on_the_field_the_naming_spec_rests_on(self, tmp_path: Path) -> None:
        session = clf.load_session(edl(tmp_path), RATE_24)
        assert clf.MATCH_FIELD == "FROM CLIP NAME"
        matched = session.event_for(row())
        assert matched is not None and matched.event_id == "001"

    def test_case_alone_does_not_lose_a_match(self, tmp_path: Path) -> None:
        text = FINAL_EDL.replace("MELT0001_pl01.mov", "melt0001_PL01.MOV")
        session = clf.load_session(edl(tmp_path, text), RATE_24)
        matched = session.event_for(row())
        assert matched is not None and matched.event_id == "001"

    def test_an_unmatched_row_gets_nothing_rather_than_the_nearest(self, tmp_path: Path) -> None:
        session = clf.load_session(edl(tmp_path), RATE_24)
        assert session.event_for(row("MELT0007_pl01")) is None

    def test_the_fallback_wants_the_reel_and_the_timecode_together(self, tmp_path: Path) -> None:
        """OQ-30's fallback: a reel alone repeats, and timecode alone is not jam synced."""
        text = FINAL_EDL.replace("* FROM CLIP NAME: MELT0001_pl01.mov\n", "")
        session = clf.load_session(edl(tmp_path, text), RATE_24)
        matched = session.event_for(row())
        assert matched is not None and matched.event_id == "001"

    def test_the_fallback_refuses_an_event_outside_the_media(self, tmp_path: Path) -> None:
        text = FINAL_EDL.replace("* FROM CLIP NAME: MELT0001_pl01.mov\n", "").replace(
            "01:00:00:08 01:00:09:08", "05:00:00:08 05:00:09:08"
        )
        session = clf.load_session(edl(tmp_path, text), RATE_24)
        assert session.event_for(row()) is None

    def test_the_fallback_refuses_two_events_on_one_reel(self, tmp_path: Path) -> None:
        text = FINAL_EDL.replace("* FROM CLIP NAME: MELT0001_pl01.mov\n", "").replace(
            "002  MELT0002 V     C        02:00:00:00 02:00:04:00",
            "002  MELT0001 V     C        01:00:02:00 01:00:04:00",
        )
        session = clf.load_session(edl(tmp_path, text), RATE_24)
        assert session.event_for(row()) is None

    def test_media_with_no_timecode_cannot_use_the_fallback(self, tmp_path: Path) -> None:
        text = FINAL_EDL.replace("* FROM CLIP NAME: MELT0001_pl01.mov\n", "")
        session = clf.load_session(edl(tmp_path, text), RATE_24)
        blank = row()
        assert blank.media is not None
        blank.media = blank.media.__class__(**{**blank.media.__dict__, "start_timecode": None})
        assert session.event_for(blank) is None


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


class TestClfIndex:
    def test_a_clf_is_found_by_the_shot_code_in_its_name(self, tmp_path: Path) -> None:
        (tmp_path / "MELT0001_final_v02.clf").touch()
        (tmp_path / "grades").mkdir()
        (tmp_path / "grades" / "MELT0002.clf").touch()
        index = clf.index_clfs(tmp_path)
        assert sorted(index) == ["MELT0001", "MELT0002"]

    def test_a_file_naming_no_shot_is_simply_not_anybody_s(self, tmp_path: Path) -> None:
        (tmp_path / "show_look.clf").touch()
        assert clf.index_clfs(tmp_path) == {}

    def test_other_files_are_ignored(self, tmp_path: Path) -> None:
        (tmp_path / "MELT0001.dctl").touch()
        assert clf.index_clfs(tmp_path) == {}

    def test_a_row_with_no_clf_gets_none(self, tmp_path: Path) -> None:
        session = clf.load_session(edl(tmp_path), RATE_24)
        assert session.clf_for("MELT0001") is None

    def test_the_session_pairs_a_row_with_its_own_clf(self, tmp_path: Path) -> None:
        first = tmp_path / "MELT0001_final_v02.clf"
        first.touch()
        (tmp_path / "MELT0002_final_v02.clf").touch()
        session = clf.load_session(edl(tmp_path), RATE_24)
        assert session.clf_for("MELT0001") == first

    def test_two_clfs_for_one_shot_is_refused_rather_than_picked(self, tmp_path: Path) -> None:
        """Picking either one is picking a grade, and both filenames look plausible."""
        (tmp_path / "MELT0001_final_v02.clf").touch()
        (tmp_path / "MELT0001_final_v03.clf").touch()
        session = clf.load_session(edl(tmp_path), RATE_24)
        with pytest.raises(clf.AmbiguousClfError, match="MELT0001"):
            session.clf_for("MELT0001")


class TestLoadClf:
    def test_a_session_clf_loads(self, tmp_path: Path) -> None:
        loaded = clf.load_clf(plate_clf(tmp_path / "MELT0001.clf"))
        assert loaded.path.name == "MELT0001.clf"
        assert not color.processor(loaded.transform).isNoOp()

    def test_the_digest_identifies_the_grade(self, tmp_path: Path) -> None:
        """A re-exported CLF gets a new one, so old deliverables stay findable."""
        path = plate_clf(tmp_path / "MELT0001.clf")
        assert clf.load_clf(path).digest == hashlib.sha256(path.read_bytes()).hexdigest()

    def test_a_re_export_changes_the_digest(self, tmp_path: Path) -> None:
        first = clf.load_clf(plate_clf(tmp_path / "MELT0001.clf")).digest
        regraded = write_clf(
            tmp_path / "MELT0001_v03.clf",
            ocio.CDLTransform(slope=[1.4, 1.0, 0.7], sat=1.0),
            ocio.ColorSpaceTransform(src=CLF_SOURCE, dst=color.PLATE_SPACE),
        )
        assert clf.load_clf(regraded).digest != first

    def test_a_grade_only_cube_passes(self, tmp_path: Path) -> None:
        assert clf.load_clf(plate_clf(tmp_path / "MELT0001.clf")).is_grade_only

    def test_a_baked_display_rendering_is_caught(self, tmp_path: Path) -> None:
        """QC-039. The file is well formed and the filename says nothing (COLOR_AND_FORMAT 1)."""
        assert not clf.load_clf(display_clf(tmp_path / "MELT0002.clf")).is_grade_only

    def test_a_dark_grade_is_not_mistaken_for_a_display_rendering(self, tmp_path: Path) -> None:
        """Four stops down leaves the step at the top exactly where it was.

        The offset is in ACEScct, where the grade lives: four stops is `4 / 17.52` of the
        range, and an offset moves both probe samples together. That is the whole reason
        the probe measures a difference and not a ratio.
        """
        dark = write_clf(tmp_path / "MELT0003.clf", ocio.CDLTransform(offset=[-4 / 17.52] * 3, sat=1.0))
        assert clf.load_clf(dark).is_grade_only
        assert probe_step(dark) == pytest.approx(clf.LOG_WHITE - clf.LOG_NEAR_WHITE, abs=1e-3)

    def test_a_grade_that_halves_the_contrast_still_passes(self, tmp_path: Path) -> None:
        """Slope 0.5 in log is a brutal grade and it still leaves twice the display's step."""
        flat = write_clf(tmp_path / "MELT0004.clf", ocio.CDLTransform(slope=[0.5] * 3))
        assert clf.load_clf(flat).is_grade_only

    @pytest.mark.parametrize(
        "encoding",
        [
            "ACEScct",
            "BMDFilm WideGamut Gen5",
            "DaVinci Intermediate WideGamut",
            "S-Log3 S-Gamut3.Cine",
            "CanonLog3 CinemaGamut D55",
        ],
    )
    def test_a_display_rendering_is_caught_whatever_the_clip_was_shot_on(
        self, tmp_path: Path, encoding: str
    ) -> None:
        """A viewing transform left on the clip in a session that was fed camera log
        rather than ACEScct: the cube still flattens the top, and the step still says so."""
        view = ocio.GroupTransform()
        view.appendTransform(ocio.ColorSpaceTransform(src=color.WORKING_SPACE, dst=encoding))
        view.appendTransform(ocio.ColorSpaceTransform(src=encoding, dst=color.WORKING_SPACE))
        view.appendTransform(
            ocio.DisplayViewTransform(src=color.WORKING_SPACE, display=color.DISPLAY, view=color.VIEW)
        )
        cpu = color.config().getProcessor(view).getDefaultCPUProcessor()
        size = 9
        lut = ocio.Lut3DTransform(gridSize=size, interpolation=color.INTERPOLATION)
        for red in range(size):
            for green in range(size):
                for blue in range(size):
                    sample = [value / (size - 1) for value in (red, green, blue)]
                    lut.setValue(red, green, blue, *cpu.applyRGB(sample))
        baked = write_clf(tmp_path / f"{encoding.split()[0]}_display.clf", lut)
        assert not clf.load_clf(baked).is_grade_only

    def test_the_floor_sits_between_the_two_populations(self, tmp_path: Path) -> None:
        """The margin, stated as a test rather than only in a docstring: a grade-only cube
        and one with the output transform in it are far apart on this measurement, and
        the floor is at least half again away from each."""
        plate = probe_step(plate_clf(tmp_path / "plate.clf"))
        display = probe_step(display_clf(tmp_path / "display.clf"))
        assert display < clf.TONE_MAP_STEP_FLOOR < plate
        assert display * 1.5 < clf.TONE_MAP_STEP_FLOOR < plate / 1.5

    def test_a_file_that_is_not_a_clf_is_refused(self, tmp_path: Path) -> None:
        """QC-019: colour that is unknown is worse than colour that is missing."""
        junk = tmp_path / "MELT0004.clf"
        junk.write_text("this is not a process list")
        with pytest.raises(clf.ClfError, match="will not load"):
            clf.load_clf(junk)

    def test_a_missing_clf_is_refused(self, tmp_path: Path) -> None:
        with pytest.raises(clf.ClfError, match="does not exist"):
            clf.load_clf(tmp_path / "gone.clf")


class TestSession:
    def test_it_reads_the_edl_and_the_clfs_beside_it(self, tmp_path: Path) -> None:
        plate_clf(tmp_path / "MELT0001_final.clf")
        session = clf.load_session(edl(tmp_path), RATE_24)
        assert len(session.events) == 2
        assert session.clf_for("MELT0001") is not None
        assert session.clf_for("MELT0002") is None


class TestShotColor:
    """What rides on a render job: a path, a colour space name and the CDL.

    The failure these guard against is the one COLOR_AND_FORMAT section 1 warns about
    under the chain diagram: a grade applied in the wrong space, or a conversion applied
    twice. It raises nothing and looks like a grade. So these ask **which** transforms a
    chain contains as well as what it does to a pixel, because two arrangements agree on
    a pixel whenever the tool's own leg happens to be identity.
    """

    def applied(self, shot_color: clf.ShotColor, value: float) -> float:
        """One neutral ACEScct value through the plate branch, green channel out."""
        loaded = shot_color.load()
        pixels = np.array([[[value, value, value]]], dtype=np.float32)
        color.apply(pixels, color.processor(*shot_color.plate_transforms(loaded)))
        return float(pixels[0, 0, 1])

    def viewed(self, shot_color: clf.ShotColor, value: float) -> float:
        loaded = shot_color.load()
        pixels = np.array([[[value, value, value]]], dtype=np.float32)
        color.apply(pixels, color.processor(*shot_color.view_transforms(loaded)))
        return float(pixels[0, 0, 1])

    def test_with_no_clf_the_chain_supplies_the_conversion_itself(self) -> None:
        """ACEScct mid grey is 0.18 scene linear, and nothing else is."""
        assert self.applied(UNGRADED, ACESCCT_MID_GREY) == pytest.approx(0.18, abs=1e-3)

    def test_a_cube_sits_between_the_two_legs(self, tmp_path: Path) -> None:
        """Into ACEScct from the clip's encoding, the cube, out to ACEScg."""
        shot_color = clf.ShotColor(
            source_encoding="S-Log3 S-Gamut3.Cine", clf_path=plate_clf(tmp_path / "MELT0001.clf")
        )
        loaded = shot_color.load()
        assert loaded is not None
        legs_in, grade, legs_out = shot_color.plate_transforms(loaded)
        assert (legs_in.getSrc(), legs_in.getDst()) == ("S-Log3 S-Gamut3.Cine", color.WORKING_SPACE)
        assert grade is loaded.transform
        assert (legs_out.getSrc(), legs_out.getDst()) == (color.WORKING_SPACE, color.PLATE_SPACE)

    def test_the_cdl_sits_in_the_same_slot_when_there_is_no_cube(self) -> None:
        shot_color = clf.ShotColor(source_encoding="S-Log3 S-Gamut3.Cine", cdl=ONE_STOP_UP)
        legs_in, grade, legs_out = shot_color.plate_transforms(None)
        assert isinstance(grade, ocio.CDLTransform)
        assert grade.getOffset() == pytest.approx([1 / 17.52] * 3)
        assert legs_in.getDst() == legs_out.getSrc() == color.WORKING_SPACE

    def test_a_cube_takes_the_cdl_s_place(self, tmp_path: Path) -> None:
        """Never both: the cube out of the session already has the grade in it."""
        shot_color = clf.ShotColor(
            source_encoding="ACEScct", clf_path=plate_clf(tmp_path / "MELT0001.clf"), cdl=ONE_STOP_UP
        )
        loaded = shot_color.load()
        assert loaded is not None
        transforms = shot_color.plate_transforms(loaded)
        assert len(transforms) == 3
        assert transforms[1] is loaded.transform

    def test_an_ungraded_plate_chain_is_one_leg_to_acescg(self) -> None:
        """The aux still's chain, and every row the session has no grade for."""
        transforms = UNGRADED.plate_transforms(None)
        assert len(transforms) == 1
        assert transforms[0].getDst() == color.PLATE_SPACE

    def test_a_graded_row_with_no_encoding_is_refused(self, tmp_path: Path) -> None:
        """The grade is applied in ACEScct and the encoding is what gets the clip there,
        so a graded row cannot render without it. QC-046 is an error on every plate."""
        shot_color = clf.ShotColor(clf_path=plate_clf(tmp_path / "MELT0001.clf"), cdl=ONE_STOP_UP)
        with pytest.raises(clf.ClfError, match="no source encoding"):
            shot_color.plate_transforms(shot_color.load())

    def test_no_clf_and_no_encoding_is_refused_rather_than_guessed(self) -> None:
        """The one chain that cannot be built. Nothing turns those pixels into ACEScg.

        Passing them through would deliver a log frame under a header claiming ACEScg,
        which is the silent wrong image this module is written to make impossible.
        QC-046 and QC-047 stop the row long before a worker reaches this.
        """
        with pytest.raises(clf.ClfError, match="no source encoding"):
            clf.DEFAULT_SHOT_COLOR.plate_transforms(None)

    def test_the_cdl_is_applied_in_acescct_whatever_the_clip_was_shot_on(self) -> None:
        """One stop up in ACEScct doubles the plate, from a camera log as from ACEScct.

        S-Log3 puts 18% grey at 10 bit code 420. Applied in the camera's own log instead,
        the same offset would be a different number of stops and nothing would say so.
        """
        shot_color = clf.ShotColor(source_encoding="S-Log3 S-Gamut3.Cine", cdl=ONE_STOP_UP)
        assert self.applied(shot_color, 420 / 1023) == pytest.approx(0.36, abs=2e-3)
        from_acescct = clf.ShotColor(source_encoding="ACEScct", cdl=ONE_STOP_UP)
        assert self.applied(from_acescct, ACESCCT_MID_GREY) == pytest.approx(0.36, abs=1e-3)

    def test_the_grade_in_the_cube_is_what_reaches_the_plate(self, tmp_path: Path) -> None:
        """The fixture lifts red and drops blue, so an ungraded chain cannot pass this."""
        shot_color = clf.ShotColor(source_encoding="ACEScct", clf_path=plate_clf(tmp_path / "MELT0001.clf"))
        loaded = shot_color.load()
        pixels = np.array([[[ACESCCT_MID_GREY] * 3]], dtype=np.float32)
        color.apply(pixels, color.processor(*shot_color.plate_transforms(loaded)))
        red, _, blue = (float(value) for value in pixels[0, 0])
        assert red > blue

    def test_the_plate_branch_is_unbounded_and_the_view_branch_is_not(self) -> None:
        """ACEScct 1.0 is 222 in scene linear; every display rendering tone maps it.

        Display range rather than clamped: OCIO clamps nothing, and what finally bounds
        the reference is ffmpeg's own pixel format. 1.03 against 222 is the difference
        the branch exists for.
        """
        assert self.applied(UNGRADED, clf.LOG_WHITE) > 200.0
        assert self.viewed(UNGRADED, clf.LOG_WHITE) < 1.1

    def test_the_view_branch_is_the_plate_branch_plus_one_leg(self) -> None:
        """Compared by what each transform says it is: OCIO transforms compare by identity."""
        ungraded = UNGRADED
        plate = [str(item) for item in ungraded.plate_transforms(None)]
        view = [str(item) for item in ungraded.view_transforms(None)]
        assert view[: len(plate)] == plate
        assert len(view) == len(plate) + 1

    def test_a_graded_view_branch_is_the_three_legs_and_the_output_transform(self, tmp_path: Path) -> None:
        """Four transforms, which is what `view_lut` bakes into a shot's viewing cube."""
        shot_color = clf.ShotColor(source_encoding="ACEScct", clf_path=plate_clf(tmp_path / "MELT0001.clf"))
        loaded = shot_color.load()
        assert loaded is not None
        view = shot_color.view_transforms(loaded)
        assert view[1] is loaded.transform
        assert len(view) == 4

    def test_no_clf_path_loads_nothing(self) -> None:
        assert clf.DEFAULT_SHOT_COLOR.load() is None

    def test_a_loaded_clf_carries_the_digest_of_the_file_on_disk(self, tmp_path: Path) -> None:
        path = plate_clf(tmp_path / "MELT0001.clf")
        loaded = clf.ShotColor(clf_path=path).load()
        assert loaded is not None
        assert loaded.digest == hashlib.sha256(path.read_bytes()).hexdigest()

    def test_it_pickles(self) -> None:
        """A job crosses a spawn boundary, so everything it carries has to survive one."""
        shot_color = clf.ShotColor(clf_path=Path("/session/MELT0001.clf"))
        assert pickle.loads(pickle.dumps(shot_color)) == shot_color


def ingested(tmp_path: Path, *rows: ShotRow) -> Turnover:
    """Ingest the fixture session into a turnover holding `rows`, and hand it back."""
    turnover = Turnover(turnover_id="turnover001", folder=tmp_path)
    clf.ingest(turnover, list(rows), clf.load_session(edl(tmp_path), RATE_24))
    return turnover


class TestIngest:
    """What the session writes onto the model, which is the only thing a run reads."""

    def test_it_records_where_the_session_was(self, tmp_path: Path) -> None:
        turnover = ingested(tmp_path, row())
        assert turnover.color_session_edl == edl(tmp_path)

    def test_a_matched_row_takes_the_approved_in_out(self, tmp_path: Path) -> None:
        scanned = row()
        ingested(tmp_path, scanned)
        assert scanned.approved == InOut(8, 223)
        assert scanned.current == scanned.approved

    def test_the_approved_cut_overwrites_a_trim_and_says_so(self, tmp_path: Path) -> None:
        """PRD section 6 step 4: the cut the AD signed off wins, and the editor is told."""
        scanned = row()
        scanned.current = InOut(10, 200)
        turnover = Turnover(turnover_id="turnover001", folder=tmp_path)
        report = clf.ingest(turnover, [scanned], clf.load_session(edl(tmp_path), RATE_24))
        assert report.overwritten == ["MELT0001_pl01"]
        assert scanned.current == InOut(8, 223)

    def test_a_trim_that_already_agrees_is_not_reported(self, tmp_path: Path) -> None:
        scanned = row()
        scanned.current = InOut(8, 223)
        turnover = Turnover(turnover_id="turnover001", folder=tmp_path)
        report = clf.ingest(turnover, [scanned], clf.load_session(edl(tmp_path), RATE_24))
        assert report.overwritten == []

    def test_a_matched_row_records_the_cdl(self, tmp_path: Path) -> None:
        scanned = row()
        ingested(tmp_path, scanned)
        assert scanned.cdl is not None
        assert scanned.cdl.saturation == pytest.approx(1.05)

    def test_a_matched_row_records_its_clf(self, tmp_path: Path) -> None:
        path = plate_clf(tmp_path / "MELT0001_grade.clf")
        scanned = row()
        ingested(tmp_path, scanned)
        assert scanned.clf_path == path

    def test_a_row_the_session_never_heard_of_is_left_alone_and_reported(self, tmp_path: Path) -> None:
        """Nothing here conforms a row to its neighbour's event."""
        scanned = row("MELT0009_pl01")
        scanned.current = InOut(5, 100)
        turnover = Turnover(turnover_id="turnover001", folder=tmp_path)
        report = clf.ingest(turnover, [scanned], clf.load_session(edl(tmp_path), RATE_24))
        assert report.unmatched == ["MELT0009_pl01"]
        assert scanned.approved is None
        assert scanned.current == InOut(5, 100)

    def test_two_clfs_naming_one_shot_leave_the_row_ungraded_and_report_it(self, tmp_path: Path) -> None:
        """Picking either is picking a grade, and one bad shot does not stop the ingest."""
        plate_clf(tmp_path / "MELT0001_v01.clf")
        plate_clf(tmp_path / "MELT0001_v02.clf")
        scanned = row()
        turnover = Turnover(turnover_id="turnover001", folder=tmp_path)
        report = clf.ingest(turnover, [scanned], clf.load_session(edl(tmp_path), RATE_24))
        assert report.ambiguous == ["MELT0001_pl01"]
        assert scanned.clf_path is None

    def test_a_row_with_a_cdl_and_no_cube_counts_as_graded(self, tmp_path: Path) -> None:
        """The CDL is the grade; the cube is the exception (decided 2026-09-18)."""
        scanned = row()
        turnover = Turnover(turnover_id="turnover001", folder=tmp_path)
        report = clf.ingest(turnover, [scanned], clf.load_session(edl(tmp_path), RATE_24))
        assert scanned.clf_path is None
        assert report.graded == ["MELT0001_pl01"]
        assert report.counts == "1 rows matched, 1 graded"

    def test_it_counts_what_it_matched_and_what_it_graded(self, tmp_path: Path) -> None:
        plate_clf(tmp_path / "MELT0001_grade.clf")
        turnover = Turnover(turnover_id="turnover001", folder=tmp_path)
        rows = [row(), row("MELT0009_pl01")]
        report = clf.ingest(turnover, rows, clf.load_session(edl(tmp_path), RATE_24))
        assert report.matched == ["MELT0001_pl01"]
        assert report.graded == ["MELT0001_pl01"]
        assert report.events == 2


class TestShotColorFromRow:
    """`clf.shot_color` is the one place a row becomes a chain, ingested or not."""

    def test_a_row_gets_its_own_clf_and_its_own_cdl(self, tmp_path: Path) -> None:
        path = plate_clf(tmp_path / "MELT0001_grade.clf")
        scanned = row()
        ingested(tmp_path, scanned)
        shot_color = clf.shot_color(scanned)
        assert shot_color.clf_path == path
        assert shot_color.cdl is not None
        assert shot_color.cdl.saturation == pytest.approx(1.05)

    def test_a_row_with_an_event_but_no_clf_still_records_the_cdl(self, tmp_path: Path) -> None:
        """They are two different matches: a CDL is a record and costs a header line."""
        scanned = row()
        ingested(tmp_path, scanned)
        shot_color = clf.shot_color(scanned)
        assert shot_color.clf_path is None
        assert shot_color.cdl is not None

    def test_a_row_the_session_never_heard_of_gets_the_ungraded_chain(self, tmp_path: Path) -> None:
        scanned = row("MELT0009_pl01")
        ingested(tmp_path, scanned)
        shot_color = clf.shot_color(scanned)
        assert shot_color.clf_path is None
        assert shot_color.cdl is None

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


class TestFindSession:
    """OQ-53: a session exported by convention is found without a chooser."""

    def turnover(self, tmp_path: Path) -> Path:
        folder = tmp_path / "turnovers" / "turnover001_02_23_2026_danielluckett"
        folder.mkdir(parents=True)
        return folder

    def edl_in(self, folder: Path) -> Path:
        folder.mkdir(parents=True, exist_ok=True)
        return edl(folder)

    def test_it_looks_in_the_color_folder_beside_the_turnover(self, tmp_path: Path) -> None:
        folder = self.turnover(tmp_path)
        written = self.edl_in(tmp_path / "turnovers" / "_color" / folder.name)
        assert clf.find_session(folder) == written

    def test_the_edl_may_sit_in_a_subfolder(self, tmp_path: Path) -> None:
        folder = self.turnover(tmp_path)
        written = self.edl_in(tmp_path / "turnovers" / "_color" / folder.name / "exports")
        assert clf.find_session(folder) == written

    def test_the_settings_folder_is_looked_in_first(self, tmp_path: Path) -> None:
        folder = self.turnover(tmp_path)
        self.edl_in(tmp_path / "turnovers" / "_color" / folder.name)
        preferred = self.edl_in(tmp_path / "sessions" / folder.name)
        assert clf.find_session(folder, tmp_path / "sessions") == preferred

    def test_a_settings_folder_with_nothing_for_this_turnover_falls_through(self, tmp_path: Path) -> None:
        folder = self.turnover(tmp_path)
        beside = self.edl_in(tmp_path / "turnovers" / "_color" / folder.name)
        (tmp_path / "sessions").mkdir()
        assert clf.find_session(folder, tmp_path / "sessions") == beside

    def test_nothing_by_convention_is_none(self, tmp_path: Path) -> None:
        assert clf.find_session(self.turnover(tmp_path)) is None

    def test_two_edls_is_none_rather_than_a_guess(self, tmp_path: Path) -> None:
        """Choosing between two cuts is choosing a cut; the editor points at the right one."""
        folder = self.turnover(tmp_path)
        session = tmp_path / "turnovers" / "_color" / folder.name
        self.edl_in(session)
        (session / "MELT_FINAL_v02.edl").write_text(FINAL_EDL)
        assert clf.find_session(folder) is None

    def test_a_folder_named_for_another_turnover_is_not_this_one_s(self, tmp_path: Path) -> None:
        folder = self.turnover(tmp_path)
        self.edl_in(tmp_path / "turnovers" / "_color" / "turnover002_02_24_2026_danielluckett")
        assert clf.find_session(folder) is None


class TestACubeInTheClfRole:
    """OQ-54: Resolve writes `.cube`, not CLF, and the tool takes either as the grade file."""

    def test_a_cube_is_indexed_by_the_shot_code_in_its_name(self, tmp_path: Path) -> None:
        written = color_fixtures.plate_cube(tmp_path / "MELT0001_grade_v01.cube")
        assert clf.index_clfs(tmp_path) == {"MELT0001": [written]}

    def test_a_cube_loads_and_is_a_grade_alone(self, tmp_path: Path) -> None:
        """The same probe that judges a CLF: a sampled grade still leaves the top open."""
        loaded = clf.load_clf(color_fixtures.plate_cube(tmp_path / "MELT0001_grade_v01.cube"))
        assert loaded.is_grade_only
        assert loaded.digest

    def test_a_cube_and_a_clf_naming_one_shot_is_ambiguous(self, tmp_path: Path) -> None:
        """Two files, two grades, and choosing either is choosing a grade."""
        plate_clf(tmp_path / "MELT0001_grade_v01.clf")
        color_fixtures.plate_cube(tmp_path / "MELT0001_grade_v02.cube")
        session = clf.ColorSession(edl_path=tmp_path / "x.edl", events=[], clfs=clf.index_clfs(tmp_path))
        with pytest.raises(clf.AmbiguousClfError):
            session.clf_for("MELT0001")

    def test_the_session_ingests_a_cube_onto_the_row(self, tmp_path: Path) -> None:
        color_fixtures.plate_cube(tmp_path / "MELT0001_grade_v01.cube")
        session = clf.load_session(edl(tmp_path), RATE_24)
        found = session.clf_for("MELT0001")
        assert found is not None and found.suffix == ".cube"
