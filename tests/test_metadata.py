"""The metadata pane. `ui/metadata.py` and `ui/metadata_pane.py`, M5.6.

Two halves and two ways of testing them, the same split as the runner. The description
is plain Python over the models, so it is driven with hand built rows and asserted as
text: what is in the pane is a list, and a list is what the review session with the AD
will argue about (OQ-26). The widget is asserted on the three things section 12 calls
structural - it never writes, it never takes focus, and it redraws only when its answer
moved - rather than on how it looks, which is what `docs/MAC_SESSION.md` is for.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from proingest.core.models import AudioInfo, FrameRate, InOut, MediaInfo, QCResult, SideFiles
from proingest.ui.metadata import (
    MIXED,
    NO_SELECTION,
    Field,
    Section,
    as_text,
    describe,
    describe_row,
    describe_turnover,
    format_date,
    format_rate,
    format_size,
    selection_summary,
)
from proingest.ui.metadata_pane import COPY, ElidedLabel, MetadataPane, SectionBox
from tests.fixtures.batches import batch, fail, row, turnover, warn, with_sides


def section(sections: list[Section], title: str) -> Section:
    found = next((item for item in sections if item.title == title), None)
    assert found is not None, f"{title} is not in {[item.title for item in sections]}"
    return found


def value(sections: list[Section], title: str, label: str) -> str:
    found = next((f for f in section(sections, title).fields if f.label == label), None)
    assert found is not None, f"{label} is not in {title}"
    return found.value


def titles(sections: list[Section]) -> list[str]:
    return [item.title for item in sections]


class TestWhatOneRowSays:
    def test_identity_comes_off_the_parsed_clip_name(self) -> None:
        sections = describe([row()], batch(row()))
        assert value(sections, "Identity", "Clip name") == "MELT0001_pl01"
        assert value(sections, "Identity", "Show") == "MELT"
        assert value(sections, "Identity", "Shot") == "0001"
        assert value(sections, "Identity", "Element") == "pl 01"

    def test_an_edited_shot_code_says_that_it_was_edited(self) -> None:
        """The list shows the code; only the pane can say the editor supplied it."""
        edited = row(shot_code_override="MELT0009")
        assert "editor override" in value(describe([edited], batch(edited)), "Identity", "Shot code")

    def test_the_media_fields_are_the_ones_the_list_has_no_column_for(self) -> None:
        """Section 12: the pane is for codec, pixel format, start timecode and size."""
        probed = row()
        assert probed.media is not None
        probed.media.size = 1_500_000_000
        probed.media.mtime = 1_757_000_000.0
        sections = describe([probed], batch(probed))
        media = section(sections, "Source media")
        assert {"Codec", "Pixel format", "Start timecode", "Size", "Modified"} <= {
            f.label for f in media.fields
        }

    def test_a_size_nobody_probed_is_left_out_rather_than_shown_as_zero(self) -> None:
        """Shown only when present (section 12.2). `0 bytes` reads as an empty file."""
        labels = {f.label for f in section(describe([row()], batch(row())), "Source media").fields}
        assert "Size" not in labels

    def test_a_sequence_says_its_range_and_shows_its_padding(self) -> None:
        sequence = row()
        assert sequence.media is not None
        sequence.media.path = Path("/turnover/MELT0001_pl01.1001.exr")
        sequence.media.is_sequence = True
        sequence.media.start_frame = 1001
        sequence.media.frame_count = 8
        sections = describe([sequence], batch(sequence))
        assert value(sections, "Source media", "Frames") == "1001-1008"
        assert value(sections, "Source media", "Pattern") == "MELT0001_pl01.%04d.exr"

    def test_a_single_file_has_no_frame_range_of_its_own(self) -> None:
        sections = describe([row()], batch(row()))
        assert value(sections, "Source media", "Kind") == "single file"
        assert "Frames" not in {f.label for f in section(sections, "Source media").fields}

    def test_a_rate_the_media_disagrees_with_is_called_out(self) -> None:
        """QC-026 is the rule; the pane is where the two numbers sit side by side."""
        stale = row()
        assert stale.media is not None
        stale.media.stated_rate = FrameRate(30)
        sections = describe([stale], batch(stale))
        assert value(sections, "Frame rate", "Stated by the media") == "30"
        assert "timeline wins" in value(sections, "Frame rate", "Disagreement")

    def test_a_rate_the_media_agrees_with_raises_nothing(self) -> None:
        agreed = row()
        assert agreed.media is not None
        agreed.media.stated_rate = FrameRate(24)
        labels = {f.label for f in section(describe([agreed], batch(agreed)), "Frame rate").fields}
        assert "Disagreement" not in labels

    def test_the_range_carries_both_timecodes_and_the_duration(self) -> None:
        sections = describe([row()], batch(row()))
        assert value(sections, "Range", "Current in/out") == "8 - 231"
        assert value(sections, "Range", "Duration") == "224 frames"
        assert ":" in value(sections, "Range", "Source timecode")
        assert ":" in value(sections, "Range", "Record timecode")

    def test_a_trimmed_shot_says_so(self) -> None:
        trimmed = row()
        trimmed.current = InOut(20, 231)
        assert "QC-045" in value(describe([trimmed], batch(trimmed)), "Range", "Trimmed")

    def test_an_untrimmed_shot_does_not(self) -> None:
        labels = {f.label for f in section(describe([row()], batch(row())), "Range").fields}
        assert "Trimmed" not in labels

    def test_the_colour_section_carries_what_m4_6_put_on_the_row(self) -> None:
        """Not in section 12.2's original table: the encoding, where it came from and
        the CLF arrived with M4.6 and have no column in the list either."""
        graded = row(
            source_encoding="Sony S-Log3/S-Gamut3.Cine",
            source_encoding_origin="clip metadata",
            clf_path=Path("/session/MELT0001.clf"),
        )
        sections = describe([graded], batch(graded))
        assert value(sections, "Colour", "Source encoding") == "Sony S-Log3/S-Gamut3.Cine"
        assert value(sections, "Colour", "Named by") == "clip metadata"
        assert value(sections, "Colour", "CLF") == "/session/MELT0001.clf"

    def test_a_row_with_no_colour_facts_has_no_colour_section(self) -> None:
        assert "Colour" not in titles(describe([row()], batch(row())))

    def test_audio_reports_its_own_length_against_the_picture(self) -> None:
        sounded = with_sides(row())
        sounded.audio = AudioInfo(
            path=Path("/turnover/MELT0001_pl01.wav"),
            duration_samples=48000 * 224 // 24,
            sample_rate=48000,
            channels=2,
            bit_depth=24,
        )
        sections = describe([sounded], batch(sounded))
        assert value(sections, "Audio", "Bit depth") == "24 bit"
        assert value(sections, "Audio", "Sync") == "matches the picture (224 frames)"

    def test_audio_longer_than_the_picture_says_by_how_much(self) -> None:
        sounded = with_sides(row())
        sounded.audio = AudioInfo(
            path=Path("/a.wav"), duration_samples=48000 * 236 // 24, sample_rate=48000
        )
        assert "12 frames longer" in value(describe([sounded], batch(sounded)), "Audio", "Sync")

    def test_a_row_with_no_audio_has_no_audio_section(self) -> None:
        assert "Audio" not in titles(describe([row()], batch(row())))

    def test_camdata_is_read_through_the_lookup_and_its_pairs_are_fields(self) -> None:
        """Section 12.2: the only place lens, filter and camera body appear in the UI."""
        sided = with_sides(row())
        asked: list[Path] = []

        def lookup(path: Path) -> dict[str, str]:
            asked.append(path)
            return {"Lens": "Zeiss Supreme Prime 35mm", "Filter": "ND 0.6"}

        sections = describe([sided], batch(sided), lookup)
        assert asked == [Path("/turnover/MELT0001_pl01_camdata.txt")]
        assert value(sections, "Side files", "Lens") == "Zeiss Supreme Prime 35mm"

    def test_nothing_reads_a_file_without_a_lookup(self) -> None:
        """The default is a stub, so a pane built without one cannot touch a Drive mount."""
        sided = with_sides(row())
        labels = {f.label for f in section(describe([sided], batch(sided)), "Side files").fields}
        assert labels == {"HDRI", "camData"}

    def test_the_turnover_the_row_belongs_to_is_shown(self) -> None:
        sections = describe([row()], batch(row()))
        assert "turnover001" in value(sections, "Turnover", "Folder")

    def test_qc_counts_by_severity_and_lists_every_rule(self) -> None:
        flagged = warn(fail(row()))
        sections = describe([flagged], batch(flagged))
        assert value(sections, "QC", "Results") == "1 error, 1 warning"
        rules = [f.rule_id for f in section(sections, "QC").fields if f.rule_id]
        assert rules == ["QC-012", "QC-030"]

    def test_a_clean_row_says_none_rather_than_hiding_the_section(self) -> None:
        assert value(describe([row()], batch(row())), "QC", "Results") == "none"


class TestTheEdgeStates:
    def test_nothing_selected_describes_nothing(self) -> None:
        assert describe([], batch(row())) == []

    def test_unresolved_media_says_why_rather_than_vanishing(self) -> None:
        """Section 12.3. The reason comes off the rule that raised it, because the scan
        is the only thing that knows what it looked for."""
        missing = fail(row(), "QC-012")
        missing.media = None
        sections = describe([missing], batch(missing))
        assert "not resolved" in value(sections, "Source media", "Media")
        assert "media not found" in value(sections, "Source media", "Media")

    def test_ambiguous_media_says_why_too(self) -> None:
        """QC-013 is the other rule that leaves a row without media."""
        ambiguous = fail(row(), "QC-013")
        ambiguous.media = None
        sections = describe([ambiguous], batch(ambiguous))
        assert "media not found" in value(sections, "Source media", "Media")

    def test_unresolved_media_keeps_identity_and_range(self) -> None:
        missing = row()
        missing.media = None
        sections = describe([missing], batch(missing))
        assert value(sections, "Identity", "Clip name") == "MELT0001_pl01"
        assert value(sections, "Range", "Current in/out") == "8 - 231"

    def test_a_turnover_header_shows_the_turnover_alone(self) -> None:
        held = turnover(number=1, month=2, day=23, year=2026, shooter="danielluckett")
        sections = describe_turnover(held)
        assert titles(sections) == ["Turnover"]
        assert value(sections, "Turnover", "Date") == "02_23_2026"
        assert value(sections, "Turnover", "Shooter") == "danielluckett"

    def test_a_turnover_s_own_results_go_in_that_one_section(self) -> None:
        """Alone means alone: a QC section beside it would be a second section, and the
        rows' results are already counted on the group header and listed in the dock."""
        held = turnover()
        held.qc.append(QCResult("QC-054", "warning", "turnover", "no lens grid folder"))
        sections = describe_turnover(held)
        assert titles(sections) == ["Turnover"]
        assert value(sections, "Turnover", "QC-054") == "no lens grid folder"

    def test_a_section_with_nothing_in_it_is_dropped(self) -> None:
        assert "Colour" not in titles(describe([row()], batch(row())))


class TestMoreThanOneRow:
    def test_a_field_they_agree_on_shows_its_value(self) -> None:
        """The whole point: one clip at the wrong resolution in a turnover of thirty."""
        rows = [row(), row("MELT0002_pl01")]
        sections = describe(rows, batch(*rows))
        assert value(sections, "Source media", "Resolution") == "3840x2160"

    def test_a_field_they_differ_on_reads_mixed(self) -> None:
        rows = [row(), row("MELT0002_pl01")]
        assert value(describe(rows, batch(*rows)), "Identity", "Clip name") == MIXED

    def test_one_row_at_a_different_resolution_makes_the_field_mixed(self) -> None:
        odd = row("MELT0002_pl01")
        assert odd.media is not None
        odd.media.width, odd.media.height = 1920, 1080
        rows = [row(), odd]
        assert value(describe(rows, batch(*rows)), "Source media", "Resolution") == MIXED

    def test_a_field_only_one_row_has_is_a_disagreement(self) -> None:
        rows = [row(clf_path=Path("/session/a.clf")), row("MELT0002_pl01")]
        assert value(describe(rows, batch(*rows)), "Colour", "CLF") == MIXED

    def test_qc_is_counted_across_the_selection_rather_than_merged(self) -> None:
        """Two rows with different problems agree on nothing, and `mixed` would be the
        one answer that helps nobody."""
        rows = [fail(row()), warn(row("MELT0002_pl01"))]
        sections = describe(rows, batch(*rows))
        assert value(sections, "QC", "Results") == "1 error, 1 warning"
        assert {f.rule_id for f in section(sections, "QC").fields if f.rule_id} == {
            "QC-012",
            "QC-030",
        }

    def test_the_count_is_what_the_pane_says_above_the_fields(self) -> None:
        assert selection_summary(12) == "12 shots selected"
        assert selection_summary(1) == "1 shot selected"


class TestTheFormatting:
    @pytest.mark.parametrize(
        ("size", "text"),
        [(93, "93 bytes"), (7400, "7.2 KB"), (359_000_000, "342.4 MB"), (1_500_000_000, "1.4 GB")],
    )
    def test_a_size_reads_at_a_glance(self, size: int, text: str) -> None:
        assert format_size(size) == text

    def test_a_whole_rate_is_one_number_and_an_ntsc_one_is_both(self) -> None:
        assert format_rate(FrameRate(24)) == "24"
        assert format_rate(FrameRate(24000, 1001)) == "23.976 (24000/1001)"

    def test_a_turnover_with_no_parsed_date_says_nothing_rather_than_guessing(self) -> None:
        assert format_date(turnover()) == ""

    def test_the_whole_pane_copies_as_key_and_value(self) -> None:
        text = as_text(describe([row()], batch(row())))
        assert "[Identity]" in text
        assert "Clip name: MELT0001_pl01" in text


class TestTheWidget:
    @pytest.fixture
    def pane(self, qt_app: QApplication) -> MetadataPane:
        return MetadataPane()

    def test_an_empty_pane_says_what_to_do_rather_than_nothing(self, pane: MetadataPane) -> None:
        assert pane.placeholder.text() == NO_SELECTION
        assert not pane.placeholder.isHidden()

    def test_showing_a_selection_builds_one_box_per_section(self, pane: MetadataPane) -> None:
        pane.show_sections(describe([row()], batch(row())))
        assert [box.title for box in pane._boxes] == titles(describe([row()], batch(row())))
        assert pane.placeholder.isHidden()

    def test_nothing_is_redrawn_when_the_answer_has_not_moved(self, pane: MetadataPane) -> None:
        """What lets the window wire this to every signal that can change a value
        without counting how often they fire."""
        sections = describe([row()], batch(row()))
        assert pane.show_sections(sections) is True
        boxes = list(pane._boxes)
        assert pane.show_sections(describe([row()], batch(row()))) is False
        assert list(pane._boxes) == boxes

    def test_an_answer_that_moved_is_redrawn(self, pane: MetadataPane) -> None:
        pane.show_sections(describe([row()], batch(row())))
        assert pane.show_sections(describe([row("MELT0002_pl01")], batch(row()))) is True

    def test_clearing_goes_back_to_the_sentence(self, pane: MetadataPane) -> None:
        pane.show_sections(describe([row()], batch(row())))
        pane.clear()
        assert not pane.placeholder.isHidden()
        assert pane._boxes == []

    def test_nothing_in_it_can_be_reached_by_tab(self, pane: MetadataPane) -> None:
        """Section 12.1: Tab cycles the row's editable cells and must keep doing so."""
        pane.show_sections(describe([with_sides(row())], batch(row())))
        for widget in pane.findChildren(type(pane.placeholder)) + list(pane._boxes):
            assert not (widget.focusPolicy() & Qt.FocusPolicy.TabFocus)

    def test_a_path_gets_a_copy_button_and_a_plain_value_does_not(
        self, pane: MetadataPane
    ) -> None:
        box = _box(pane, describe([row()], batch(row())), "Source media")
        buttons = [b for b in box.findChildren(type(pane.copy_all)) if b.text() == COPY]
        paths = [f for f in box.findChildren(ElidedLabel) if f.full_text.startswith("/")]
        assert len(buttons) == len(paths) == 1

    def test_a_copied_path_is_the_whole_one_not_the_elided_one(self, pane: MetadataPane) -> None:
        copied: list[str] = []
        pane.copy = copied.append  # type: ignore[assignment]
        pane.show_sections(describe([row()], batch(row())))
        box = next(b for b in pane._boxes if b.title == "Source media")
        button = next(b for b in box.findChildren(type(pane.copy_all)) if b.text() == COPY)
        button.click()
        assert copied == ["/turnover/MELT0001_pl01.mov"]

    def test_copy_all_puts_the_whole_pane_on_the_clipboard(self, pane: MetadataPane) -> None:
        copied: list[str] = []
        pane.copy = copied.append  # type: ignore[assignment]
        pane.show_sections(describe([row()], batch(row())))
        pane.copy_all.click()
        assert copied and "Clip name: MELT0001_pl01" in copied[0]

    def test_a_rule_id_asks_for_the_issues_dock(self, pane: MetadataPane) -> None:
        asked: list[str] = []
        pane.issue_clicked.connect(asked.append)
        flagged = fail(row())
        pane.show_sections(describe([flagged], batch(flagged)))
        box = next(b for b in pane._boxes if b.title == "QC")
        box.link_clicked.emit("QC-012")
        assert asked == ["QC-012"]

    def test_a_shut_section_is_remembered_by_title(self, pane: MetadataPane) -> None:
        """Titles rather than indexes, so a section a later chunk adds does not
        silently collapse a different one."""
        pane.show_sections(describe([row()], batch(row())))
        next(b for b in pane._boxes if b.title == "Range").set_open(False)
        assert pane.collapsed == ["Range"]

    def test_what_was_shut_stays_shut_across_a_redraw(self, pane: MetadataPane) -> None:
        pane.set_collapsed(["Range"])
        pane.show_sections(describe([row()], batch(row())))
        assert not next(b for b in pane._boxes if b.title == "Range").is_open
        assert next(b for b in pane._boxes if b.title == "Identity").is_open

    def test_a_long_value_is_elided_and_keeps_the_whole_thing_in_its_tooltip(
        self, qt_app: QApplication
    ) -> None:
        label = ElidedLabel(
            "/Volumes/GoogleDrive/shows/melt/turnover001/media/MELT0001_pl01.1001.exr",
            Qt.TextElideMode.ElideMiddle,
        )
        label.resize(220, 16)
        label.show()
        qt_app.processEvents()
        assert label.text() != label.full_text
        assert label.text().endswith(".1001.exr"), "elided in the middle, never at the end"
        assert label.toolTip() == label.full_text

    def test_a_value_that_fits_is_left_exactly_as_it_is(self, qt_app: QApplication) -> None:
        """Which is what makes selecting a short value with the mouse copy the real one."""
        label = ElidedLabel("prores")
        label.resize(400, 16)
        label.show()
        qt_app.processEvents()
        assert label.text() == "prores"


def _box(pane: MetadataPane, sections: list[Section], title: str) -> SectionBox:
    pane.show_sections(sections)
    return next(box for box in pane._boxes if box.title == title)


def test_a_field_and_a_section_compare_by_value() -> None:
    """What `show_sections` relies on to know that nothing moved."""
    assert Field("Codec", "prores") == Field("Codec", "prores")
    assert Section("a", (Field("x", "1"),)) == Section("a", (Field("x", "1"),))
    assert Section("a", (Field("x", "1"),)) != Section("a", (Field("x", "2"),))


def test_describe_row_keeps_empty_sections_so_a_merge_can_line_them_up() -> None:
    """`describe` drops them; `describe_row` must not, or two rows would merge fields
    from sections that are not the same section."""
    assert titles(describe_row(row(), batch(row()))) == [
        "Identity",
        "Source media",
        "Frame rate",
        "Range",
        "Colour",
        "Audio",
        "Side files",
        "Turnover",
        "QC",
    ]


def test_a_media_info_that_is_not_a_numbered_frame_has_no_pattern() -> None:
    odd = row()
    odd.media = MediaInfo(
        path=Path("/turnover/plate.mov"),
        codec="prores",
        pixel_format="yuv444p12le",
        width=1920,
        height=1080,
        rate=FrameRate(24),
        frame_count=24,
        is_sequence=True,
    )
    odd.side_files = SideFiles()
    assert value(describe([odd], batch(odd)), "Source media", "Pattern") == ""
