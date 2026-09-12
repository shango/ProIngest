"""The colour session package: the final EDL, and the CLF per row (M4.5.2).

COLOR_AND_FORMAT section 1. Two failures are what these tests exist for and neither
looks like a failure: a row conformed from a neighbour's event delivers the wrong
frames, and a row paired with a neighbour's CLF delivers the wrong grade under the
right filename. So the matching tests mostly ask what does **not** match, and the CLF
tests ask a written file what it actually does to a pixel rather than what it is called.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import PyOpenColorIO as ocio
import pytest

from proingest.core import clf, color, naming
from proingest.core.models import FrameRate, MediaInfo, ShotRow

RATE_24 = FrameRate(24)

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


def row(clip_name: str = "MELT0001_pl01", **kwargs: object) -> ShotRow:
    """A scanned row: 240 frames of ProRes starting at 01:00:00:00."""
    return ShotRow(
        turnover_id="turnover001",
        clip_name=clip_name,
        identity=naming.parse_clip_name(clip_name),
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


def plate_clf(path: Path) -> Path:
    """What the colour session is specified to export: ACEScct in, linear ACEScg out."""
    return write_clf(
        path,
        ocio.CDLTransform(slope=[1.05, 1.0, 0.95], offset=[0.0, 0.0, 0.0], power=[1.0, 1.0, 1.0], sat=1.1),
        ocio.ColorSpaceTransform(src=color.WORKING_SPACE, dst=color.PLATE_SPACE),
    )


def display_clf(path: Path, size: int = 9) -> Path:
    """A CLF with the ACES output transform baked into it, which is QC-039's failure.

    Sampled into a 3D LUT because that is the only way such a CLF exists: the output
    transform uses ops CLF cannot express, so a session that exported one would have
    had to bake it, exactly as here.
    """
    view = ocio.DisplayViewTransform(
        src=color.WORKING_SPACE, display="sRGB - Display", view="ACES 1.0 - SDR Video"
    )
    cpu = color.config().getProcessor(view).getDefaultCPUProcessor()
    lut = ocio.Lut3DTransform(gridSize=size, interpolation=color.INTERPOLATION)
    for red in range(size):
        for green in range(size):
            for blue in range(size):
                sample = [value / (size - 1) for value in (red, green, blue)]
                lut.setValue(red, green, blue, *cpu.applyRGB(sample))
    return write_clf(path, lut)


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

    def test_a_comment_under_an_audio_event_does_not_reach_the_one_before(
        self, tmp_path: Path
    ) -> None:
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
            "*ASC_SOP (1.020000 0.990000 1.010000)"
            "(0.001000 -0.002000 0.000000)(0.980000 1.000000 1.020000)"
        )
        assert cdl.sat_text == "*ASC_SAT 1.050000"

    def test_an_event_with_no_cdl_carries_none(self, tmp_path: Path) -> None:
        text = "\n".join(
            line for line in FINAL_EDL.splitlines() if not line.startswith("*ASC")
        )
        assert clf.read_final_edl(edl(tmp_path, text), RATE_24)[0].cdl is None

    def test_half_a_cdl_is_none_rather_than_a_neutral_grade(self, tmp_path: Path) -> None:
        """Slope 1 offset 0 power 1 is a real grade that says do nothing, not a default."""
        text = "\n".join(
            line for line in FINAL_EDL.splitlines() if not line.startswith("*ASC_SAT")
        )
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
        (tmp_path / "MELT0001.cube").touch()
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
            ocio.ColorSpaceTransform(src=color.WORKING_SPACE, dst=color.PLATE_SPACE),
        )
        assert clf.load_clf(regraded).digest != first

    def test_a_clf_that_lands_in_scene_linear_passes(self, tmp_path: Path) -> None:
        assert clf.load_clf(plate_clf(tmp_path / "MELT0001.clf")).is_scene_linear

    def test_a_baked_display_rendering_is_caught(self, tmp_path: Path) -> None:
        """QC-039. The file is well formed and the filename says nothing (COLOR_AND_FORMAT 1)."""
        assert not clf.load_clf(display_clf(tmp_path / "MELT0002.clf")).is_scene_linear

    def test_a_dark_grade_is_not_mistaken_for_a_display_rendering(self, tmp_path: Path) -> None:
        """Four stops down still answers 13.9 at white, where a display render answers 1.

        The offset is in ACEScct, which is where a CLF's grade lives: four stops is
        `4 / 17.52` of the log range, and the same number as a slope would be a far
        heavier change than any colourist means by it.
        """
        dark = write_clf(
            tmp_path / "MELT0003.clf",
            ocio.CDLTransform(offset=[-4 / 17.52] * 3, sat=1.0),
            ocio.ColorSpaceTransform(src=color.WORKING_SPACE, dst=color.PLATE_SPACE),
        )
        assert clf.load_clf(dark).is_scene_linear

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
