"""The shot list's model. `ui/shot_model.py`, M5.2.

UI_SPEC section 2 for the columns and section 3 for the colouring. These ask what a cell
says rather than what it looks like: the model is the half of the list that can be
checked without a screen, and it is where every fact in the list comes from.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from PySide6.QtCore import QModelIndex, Qt
from PySide6.QtWidgets import QApplication

from proingest.core.models import Deliverable, FrameRate, InOut, QCResult
from proingest.core.planner import DeliverableJob
from proingest.core.render import Progress
from proingest.ui import shot_model
from proingest.ui.runner import RunProgress
from proingest.ui.shot_model import (
    AUDIO,
    COLUMNS,
    DURATION,
    ELEM,
    FPS,
    IN,
    MAX_AVAIL,
    NOTES,
    OUT,
    PROGRESS,
    PROGRESS_ROLE,
    RES,
    SECONDARY_ROLE,
    SHOT,
    SIDE_FILES,
    SOURCE,
    STATUS,
    VERSION,
    DisplayMode,
    RowState,
    ShotListModel,
    row_state,
    turnover_state,
)
from tests.fixtures import batches
from tests.fixtures.batches import batch, delivered, fail, row, turnover, warn, with_sides


@pytest.fixture
def model(qt_app: QApplication) -> ShotListModel:
    built = ShotListModel()
    built.set_batch(batch(with_sides(row()), row("MELT0002_pl01", record_in=224)))
    return built


def text(model: ShotListModel, row_index: int, column: int, turnover_index: int = 0) -> str:
    parent = model.index(turnover_index, 0, QModelIndex())
    return str(model.index(row_index, column, parent).data(Qt.ItemDataRole.DisplayRole) or "")


def cell(model: ShotListModel, row_index: int, column: int, role: int, turnover_index: int = 0) -> Any:
    parent = model.index(turnover_index, 0, QModelIndex())
    return model.index(row_index, column, parent).data(role)


class TestTheTree:
    """Two levels and no more: a turnover, then its rows in timeline order."""

    def test_the_top_level_is_one_row_per_turnover(self, model: ShotListModel) -> None:
        assert model.rowCount(QModelIndex()) == 1

    def test_the_children_are_that_turnover_s_rows(self, model: ShotListModel) -> None:
        parent = model.index(0, 0, QModelIndex())
        assert model.rowCount(parent) == 2

    def test_a_shot_row_has_no_children_of_its_own(self, model: ShotListModel) -> None:
        parent = model.index(0, 0, QModelIndex())
        assert model.rowCount(model.index(0, 0, parent)) == 0

    def test_a_child_index_finds_its_way_back_to_its_turnover(self, model: ShotListModel) -> None:
        parent = model.index(0, 0, QModelIndex())
        child = model.index(1, SHOT, parent)
        assert model.parent(child) == parent

    def test_a_turnover_has_no_parent(self, model: ShotListModel) -> None:
        assert not model.parent(model.index(0, 0, QModelIndex())).isValid()

    def test_the_columns_are_the_ones_section_2_lists(self, model: ShotListModel) -> None:
        assert model.columnCount(QModelIndex()) == len(COLUMNS)
        titles = [
            model.headerData(i, Qt.Orientation.Horizontal, Qt.ItemDataRole.DisplayRole)
            for i in range(len(COLUMNS))
        ]
        assert titles[SHOT : ELEM + 1] == ["Shot", "Elem"]
        assert (titles[IN], titles[OUT]) == ("In", "Out")

    def test_rows_belong_to_their_own_turnover(self, qt_app: QApplication) -> None:
        """Two turnovers, and neither shows the other's shots."""
        built = ShotListModel()
        built.set_batch(
            batch(
                row(),
                row("MELT0009_pl01", turnover_id="turnover002"),
                turnovers=[turnover(), turnover("turnover002")],
            )
        )
        assert [built.rowCount(built.index(i, 0, QModelIndex())) for i in (0, 1)] == [1, 1]
        assert text(built, 0, SHOT, turnover_index=1) == "MELT0009"

    def test_what_is_behind_an_index(self, model: ShotListModel) -> None:
        parent = model.index(0, 0, QModelIndex())
        assert model.row_at(model.index(0, 0, parent)) is model.batch.rows[0]
        assert model.row_at(parent) is None
        assert model.turnover_at(parent) is model.batch.turnovers[0]


class TestWhatACellSays:
    def test_the_columns_that_read_straight_off_the_row(self, model: ShotListModel) -> None:
        assert text(model, 0, SHOT) == "MELT0001"
        assert text(model, 0, ELEM) == "pl01"
        assert text(model, 0, SOURCE) == "MELT0001_pl01.mov"
        assert text(model, 0, RES) == "3840x2160"
        assert text(model, 0, FPS) == "24"
        assert text(model, 0, DURATION) == "224"
        assert text(model, 0, MAX_AVAIL) == "239"

    def test_audio_and_side_files(self, model: ShotListModel) -> None:
        assert text(model, 0, AUDIO) == "1"
        assert text(model, 0, SIDE_FILES) == "HDRI, camData"

    def test_a_row_with_neither_says_nothing_rather_than_a_dash(self, model: ShotListModel) -> None:
        assert text(model, 1, AUDIO) == ""
        assert text(model, 1, SIDE_FILES) == ""

    def test_more_than_one_audio_clip_says_how_many(self, qt_app: QApplication) -> None:
        """QC-041 is the rule; the column is where the editor sees it without opening it."""
        built = ShotListModel()
        built.set_batch(batch(row(audio_path=Path("/a.wav"), audio_clip_count=3)))
        assert text(built, 0, AUDIO) == "3"

    def test_an_unparsed_clip_name_still_names_the_row(self, qt_app: QApplication) -> None:
        """QC-010 leaves no shot code, and a blank row cannot be found in the list."""
        built = ShotListModel()
        built.set_batch(batch(row("garbage name", identity=None)))
        assert text(built, 0, SHOT) == "garbage name"

    def test_a_row_with_no_media_leaves_the_media_columns_empty(self, qt_app: QApplication) -> None:
        built = ShotListModel()
        built.set_batch(batch(row(media=None, snapshot=None, current=None)))
        assert [text(built, 0, c) for c in (SOURCE, RES, FPS, IN, OUT)] == ["", "", "", "", ""]

    def test_version_and_progress_come_from_the_deliverables(self, qt_app: QApplication) -> None:
        built = ShotListModel()
        built.set_batch(batch(delivered(row(), version=3)))
        assert text(built, 0, VERSION) == "v03"
        assert text(built, 0, PROGRESS) == "2/2"

    def test_a_row_nothing_has_been_planned_for_says_nothing(self, model: ShotListModel) -> None:
        assert text(model, 0, VERSION) == ""
        assert text(model, 0, PROGRESS) == ""

    def test_progress_counts_what_has_landed(self, qt_app: QApplication) -> None:
        built = ShotListModel()
        planned = delivered(row(), status="planned")
        planned.deliverables[0].status = "done"
        built.set_batch(batch(planned))
        assert text(built, 0, PROGRESS) == "1/2"

    def test_notes_are_shown_and_are_the_editor_s_own_words(self, qt_app: QApplication) -> None:
        built = ShotListModel()
        built.set_batch(batch(row(notes="watch the flare")))
        assert text(built, 0, NOTES) == "watch the flare"


def run_of(*names: str, frames: int = 10) -> RunProgress:
    """A `RunProgress` over jobs named after deliverables the fixtures make."""
    return RunProgress(
        [
            DeliverableJob(
                kind="raw_dir",
                source=Path("/turnover/MELT0001_pl01.mov"),
                destination=Path("/delivery") / name,
                version=1,
                shot_code="MELT0001",
                elem="pl01",
                in_frame=0,
                out_frame=frames - 1,
                rate=FrameRate(24),
            )
            for name in names
        ]
    )


class TestTheProgressColumnDuringARun:
    """The run is the only thing that knows where a row has got to.

    `render.apply_results` does not write the statuses back onto the rows until the run
    finishes, so during one the row still says `planned` and the count and the bar would
    both sit at zero if the model read only the row.
    """

    def test_a_live_run_outranks_the_recorded_statuses(self, qt_app: QApplication) -> None:
        built = ShotListModel()
        planned = delivered(row(), status="planned")
        built.set_batch(batch(planned))
        names = [item.name for item in planned.deliverables]
        progress = run_of(*names)
        progress.update(Progress(names[0], "done", 10, 10))
        built.set_run(progress)

        assert text(built, 0, PROGRESS) == "1/2"

    def test_the_bar_follows_the_frames_of_the_job_in_flight(self, qt_app: QApplication) -> None:
        built = ShotListModel()
        planned = delivered(row(), status="planned")
        built.set_batch(batch(planned))
        names = [item.name for item in planned.deliverables]
        progress = run_of(*names)
        progress.update(Progress(names[0], "done", 10, 10))
        progress.update(Progress(names[1], "frame", 5, 10))
        built.set_run(progress)

        # One finished and one half way: three quarters of the row.
        assert cell(built, 0, PROGRESS, PROGRESS_ROLE) == pytest.approx(0.75)

    def test_a_row_in_flight_is_rendering(self, qt_app: QApplication) -> None:
        built = ShotListModel()
        planned = delivered(row(), status="planned")
        built.set_batch(batch(planned))
        progress = run_of(*[item.name for item in planned.deliverables])
        progress.update(Progress(planned.deliverables[0].name, "started", 0, 10))
        built.set_run(progress)

        assert shot_model.row_state(planned) is RowState.OK, "the row itself cannot know"
        assert built.state_for(planned) is RowState.RENDERING

    def test_a_skipped_row_stays_skipped(self, qt_app: QApplication) -> None:
        """Skipped is the one state the editor chose rather than the tool."""
        built = ShotListModel()
        planned = delivered(row(skipped=True, skip_reason="not needed"), status="planned")
        built.set_batch(batch(planned))
        progress = run_of(*[item.name for item in planned.deliverables])
        progress.update(Progress(planned.deliverables[0].name, "started", 0, 10))
        built.set_run(progress)

        assert built.state_for(planned) is RowState.SKIPPED

    def test_a_deliverable_this_run_never_planned_keeps_its_own_status(
        self, qt_app: QApplication
    ) -> None:
        """A row left out of a run still shows what a previous run wrote."""
        built = ShotListModel()
        old = delivered(row(), status="done")
        built.set_batch(batch(old))
        built.set_run(run_of("something_else_v01"))

        assert text(built, 0, PROGRESS) == "2/2"
        assert cell(built, 0, PROGRESS, PROGRESS_ROLE) == pytest.approx(1.0)

    def test_ending_the_run_goes_back_to_the_rows(self, qt_app: QApplication) -> None:
        built = ShotListModel()
        planned = delivered(row(), status="planned")
        built.set_batch(batch(planned))
        names = [item.name for item in planned.deliverables]
        progress = run_of(*names)
        progress.update(Progress(names[0], "done", 10, 10))
        built.set_run(progress)
        built.set_run(None)

        assert text(built, 0, PROGRESS) == "0/2"

    def test_a_repaint_touches_every_column_but_leaves_the_rows_alone(
        self, model: ShotListModel
    ) -> None:
        """A reset would lose the selection, the scroll and which turnovers are open."""
        changed: list[tuple[int, int]] = []
        model.dataChanged.connect(
            lambda top, bottom, roles: changed.append((top.column(), bottom.column()))
        )
        resets: list[int] = []
        model.modelReset.connect(lambda: resets.append(1))
        model.refresh_rows()

        assert changed == [(STATUS, PROGRESS)]
        assert resets == []


class TestTheInOutDisplay:
    """Section 2's three state toggle. Frames is the default and it is not arbitrary."""

    def test_frames_is_what_it_opens_on(self, model: ShotListModel) -> None:
        assert model.display_mode is DisplayMode.FRAMES
        assert (text(model, 0, IN), text(model, 0, OUT)) == ("8", "231")

    def test_under_frames_the_second_line_is_source_timecode(self, model: ShotListModel) -> None:
        assert cell(model, 0, IN, SECONDARY_ROLE) == "01:00:00:08"

    def test_source_tc_promotes_the_timecode_and_demotes_the_frame(self, model: ShotListModel) -> None:
        model.set_display_mode(DisplayMode.SOURCE_TC)
        assert text(model, 0, IN) == "01:00:00:08"
        assert cell(model, 0, IN, SECONDARY_ROLE) == "8"

    def test_record_tc_is_read_against_the_timeline_s_own_start(self, model: ShotListModel) -> None:
        """The clip sits at the top of an edit starting at an hour, so its In is that hour.

        Source TC and record TC differ by eight frames here on purpose: the turnover
        trimmed eight frames of handle off the head, and only the source side counts them.
        """
        model.set_display_mode(DisplayMode.RECORD_TC)
        assert text(model, 0, IN) == "01:00:00:00"
        assert text(model, 0, OUT) == "01:00:09:07"

    def test_the_second_clip_sits_after_the_first_in_record(self, model: ShotListModel) -> None:
        model.set_display_mode(DisplayMode.RECORD_TC)
        assert text(model, 1, IN) == "01:00:09:08"

    def test_a_timeline_starting_at_zero_says_so(self, qt_app: QApplication) -> None:
        """A batch saved before turnovers remembered their start reads back as zero."""
        built = ShotListModel()
        built.set_batch(batch(row(), turnovers=[turnover(timeline_start=0)]))
        built.set_display_mode(DisplayMode.RECORD_TC)
        assert text(built, 0, IN) == "00:00:00:00"

    def test_the_toggle_cycles_and_comes_round(self) -> None:
        mode = DisplayMode.FRAMES
        seen = [mode]
        for _ in range(3):
            mode = mode.next()
            seen.append(mode)
        assert seen == [
            DisplayMode.FRAMES,
            DisplayMode.SOURCE_TC,
            DisplayMode.RECORD_TC,
            DisplayMode.FRAMES,
        ]

    def test_changing_it_repaints_in_and_out_and_nothing_else(self, model: ShotListModel) -> None:
        """Fifteen columns of a hundred shot list is a redraw worth not asking for."""
        changed: list[tuple[int, int]] = []
        model.dataChanged.connect(
            lambda top, bottom, roles: changed.append((top.column(), bottom.column()))
        )
        model.set_display_mode(DisplayMode.SOURCE_TC)
        assert changed == [(IN, OUT)]

    def test_setting_the_mode_it_is_already_in_changes_nothing(self, model: ShotListModel) -> None:
        changed: list[object] = []
        model.dataChanged.connect(lambda *args: changed.append(args))
        model.set_display_mode(DisplayMode.FRAMES)
        assert changed == []


class TestRowState:
    """Section 3's table, and the order it is read in when a row is several at once."""

    def test_a_plain_row_is_ok(self) -> None:
        assert row_state(row()) is RowState.OK

    def test_a_warning_and_an_error(self) -> None:
        assert row_state(warn(row())) is RowState.WARNING
        assert row_state(fail(row())) is RowState.ERROR

    def test_an_error_outranks_a_warning(self) -> None:
        assert row_state(fail(warn(row()))) is RowState.ERROR

    def test_skipped_outranks_everything_because_the_editor_chose_it(self) -> None:
        assert row_state(fail(row(skipped=True))) is RowState.SKIPPED

    def test_a_failed_render_outranks_the_rules(self) -> None:
        assert row_state(delivered(warn(row()), status="failed")) is RowState.FAILED

    def test_rendering_outranks_a_failure_because_it_is_still_happening(self) -> None:
        rendering = delivered(row(), status="failed")
        rendering.deliverables[0].status = "rendering"
        assert row_state(rendering) is RowState.RENDERING

    def test_everything_written_is_done(self) -> None:
        assert row_state(delivered(row())) is RowState.DONE

    def test_a_file_that_was_already_there_still_counts_as_done(self) -> None:
        assert row_state(delivered(row(), status="exists")) is RowState.DONE

    def test_a_warning_on_a_delivered_row_still_shows_as_delivered(self) -> None:
        """The rules ran before the render; a warning that did not stop it is history."""
        assert row_state(delivered(warn(row()))) is RowState.WARNING


class TestTheGroupHeader:
    def test_it_names_the_folder_and_counts_what_is_under_it(self, model: ShotListModel) -> None:
        header = str(model.index(0, 0, QModelIndex()).data(Qt.ItemDataRole.DisplayRole))
        assert "turnover001_02_23_2026_danielluckett" in header
        assert "2 shots" in header

    def test_it_counts_errors_and_warnings(self, qt_app: QApplication) -> None:
        built = ShotListModel()
        built.set_batch(batch(fail(row()), warn(row("MELT0002_pl01"))))
        header = str(built.index(0, 0, QModelIndex()).data(Qt.ItemDataRole.DisplayRole))
        assert "1 error" in header and "1 warning" in header

    def test_one_shot_is_not_one_shots(self, qt_app: QApplication) -> None:
        built = ShotListModel()
        built.set_batch(batch(row()))
        header = str(built.index(0, 0, QModelIndex()).data(Qt.ItemDataRole.DisplayRole))
        assert "1 shot" in header and "1 shots" not in header

    def test_its_state_is_the_worst_thing_under_it(self) -> None:
        assert turnover_state(turnover(), [warn(row()), fail(row())]) is RowState.ERROR
        assert turnover_state(turnover(), [row(), warn(row())]) is RowState.WARNING
        assert turnover_state(turnover(), [row(), row()]) is RowState.OK

    def test_a_turnover_that_failed_to_parse_carries_its_own_colour(self) -> None:
        """QC-001 and QC-002 leave no rows at all, so nothing else could carry it."""
        broken = turnover()
        broken.qc.append(QCResult("QC-002", "error", "turnover", "failed to parse"))
        assert turnover_state(broken, []) is RowState.ERROR

    def test_an_empty_turnover_with_nothing_wrong_is_ok(self) -> None:
        assert turnover_state(turnover(), []) is RowState.OK


class TestHowARowIsPainted:
    def test_every_row_carries_a_status_dot(self, model: ShotListModel) -> None:
        dot = cell(model, 0, STATUS, Qt.ItemDataRole.DecorationRole)
        assert dot is not None and not dot.isNull()

    def test_the_dot_is_cached_per_state_rather_than_drawn_per_cell(
        self, model: ShotListModel
    ) -> None:
        first = cell(model, 0, STATUS, Qt.ItemDataRole.DecorationRole)
        second = cell(model, 1, STATUS, Qt.ItemDataRole.DecorationRole)
        # Qt hands back a new Python wrapper each time; the cache key is what says
        # whether it drew a second pixmap, and a hundred shot list asks per repaint.
        assert first.cacheKey() == second.cacheKey()

    def test_a_warning_row_is_tinted_and_a_plain_one_is_not(self, qt_app: QApplication) -> None:
        built = ShotListModel()
        built.set_batch(batch(warn(row()), row("MELT0002_pl01")))
        assert cell(built, 0, SHOT, Qt.ItemDataRole.BackgroundRole) is not None
        assert cell(built, 1, SHOT, Qt.ItemDataRole.BackgroundRole) is None

    def test_a_skipped_row_is_dimmed_rather_than_tinted(self, qt_app: QApplication) -> None:
        built = ShotListModel()
        built.set_batch(batch(row(skipped=True, skip_reason="blocked")))
        assert cell(built, 0, SHOT, Qt.ItemDataRole.ForegroundRole) is not None
        assert cell(built, 0, SHOT, Qt.ItemDataRole.BackgroundRole) is None

    def test_the_frame_columns_are_right_aligned(self, model: ShotListModel) -> None:
        """Numbers that do not line up are numbers nobody scans down a column of."""
        alignment = cell(model, 0, IN, Qt.ItemDataRole.TextAlignmentRole)
        assert alignment is not None and int(alignment) & int(Qt.AlignmentFlag.AlignRight)


class TestTooltips:
    def test_a_row_stop_skipped_is_not_done(self) -> None:
        """`skipped` is what Stop writes on a job it reached; the Progress cell reads
        0/2 beside it and the dot must not say otherwise."""
        assert row_state(delivered(row(), status="skipped")) is not RowState.DONE

    def test_the_dot_lists_the_rules_that_fired(self, qt_app: QApplication) -> None:
        """Section 3: hovering the dot names the rule IDs and their messages."""
        built = ShotListModel()
        built.set_batch(batch(fail(warn(row()))))
        tip = str(cell(built, 0, STATUS, Qt.ItemDataRole.ToolTipRole))
        assert "QC-030" in tip and "QC-012" in tip

    def test_a_row_with_nothing_wrong_has_no_dot_tooltip(self, model: ShotListModel) -> None:
        assert cell(model, 0, STATUS, Qt.ItemDataRole.ToolTipRole) is None

    def test_the_shot_cell_always_names_the_clip_it_came_from(self, model: ShotListModel) -> None:
        assert cell(model, 0, SHOT, Qt.ItemDataRole.ToolTipRole) == "MELT0001_pl01"

    def test_the_source_cell_carries_the_whole_path(self, model: ShotListModel) -> None:
        assert cell(model, 0, SOURCE, Qt.ItemDataRole.ToolTipRole) == "/turnover/MELT0001_pl01.mov"

    def test_the_group_header_falls_back_to_its_folder(self, model: ShotListModel) -> None:
        tip = model.index(0, 0, QModelIndex()).data(Qt.ItemDataRole.ToolTipRole)
        assert str(tip).startswith("/source/")


class TestReplacingTheBatch:
    def test_the_model_resets_rather_than_patching(self, model: ShotListModel) -> None:
        resets: list[int] = []
        model.modelReset.connect(lambda: resets.append(1))
        model.set_batch(batch(row()))
        assert resets == [1]
        assert model.rowCount(model.index(0, 0, QModelIndex())) == 1

    def test_an_empty_batch_shows_nothing_and_does_not_raise(self, qt_app: QApplication) -> None:
        built = ShotListModel()
        assert built.rowCount(QModelIndex()) == 0
        assert built.data(QModelIndex(), Qt.ItemDataRole.DisplayRole) is None


class TestTheFrozenColumnCount:
    def test_status_shot_and_elem_are_the_ones_that_stay(self) -> None:
        """Section 2's frozen left. The view that does it is a later chunk; the count
        lives here so the two cannot disagree about which columns it means."""
        assert shot_model.FROZEN_COLUMNS == 3
        assert (STATUS, SHOT, ELEM) == (0, 1, 2)


class TestEditContext:
    """`ShotRow.edit_context` is core's, and it is what both the display and, later,
    the typed edit read. Its record anchor is the pairing the turnover arrived with."""

    def test_the_record_anchor_does_not_slide_when_the_editor_trims(self) -> None:
        trimmed = row()
        context = trimmed.edit_context(batches.RATE_24, batches.ONE_HOUR, "record")
        trimmed.current = InOut(0, 231)
        after = trimmed.edit_context(batches.RATE_24, batches.ONE_HOUR, "record")
        assert context.timecode_origin() == after.timecode_origin()

    def test_a_row_with_no_media_still_produces_one(self) -> None:
        """QC-011 rows appear in the list, so nothing may raise on the way to a cell."""
        context = row(media=None, snapshot=None, current=None).edit_context(batches.RATE_24)
        assert context.fps == 24.0


def test_no_deliverable_status_is_unaccounted_for() -> None:
    """Every status a deliverable can hold has to land in a state, or a row goes blank."""
    for status in ("planned", "rendering", "done", "failed", "exists", "skipped"):
        built = row()
        built.deliverables = [
            Deliverable(kind="raw_dir", name="n", path=Path("/d/n"), version=1, status=status)
        ]
        assert isinstance(row_state(built), RowState)


class TestWhichCellsCanBeEdited:
    """Section 2 marks four of them editable and FR-5 says why: they are the ones the
    list owns. Everything else is read off the media, derived, or written by a run."""

    def index_of(self, model: ShotListModel, column: int, row_index: int = 0) -> QModelIndex:
        return model.index(row_index, column, model.index(0, 0, QModelIndex()))

    def test_shot_in_out_and_notes_are_the_editable_ones(self, model: ShotListModel) -> None:
        editable = [
            column
            for column in range(len(COLUMNS))
            if self.index_of(model, column).flags() & Qt.ItemFlag.ItemIsEditable
        ]
        assert editable == [SHOT, IN, OUT, NOTES]

    def test_a_turnover_header_is_not_editable(self, model: ShotListModel) -> None:
        header = model.index(0, SHOT, QModelIndex())
        assert not header.flags() & Qt.ItemFlag.ItemIsEditable

    def test_a_row_with_no_range_cannot_have_one_typed_into_it(
        self, qt_app: QApplication
    ) -> None:
        """QC-020 rows appear in the list; a relative offset has nothing to be relative to."""
        built = ShotListModel()
        built.set_batch(batch(row(media=None, snapshot=None, current=None)))
        assert not self.index_of(built, IN).flags() & Qt.ItemFlag.ItemIsEditable
        assert built.index(0, NOTES, built.index(0, 0, QModelIndex())).flags() & Qt.ItemFlag.ItemIsEditable

    def test_an_editor_opens_on_the_shot_code_and_not_on_the_clip_name(
        self, qt_app: QApplication
    ) -> None:
        """Prefilled with the clip name, Enter commits the clip name as an override."""
        built = ShotListModel()
        built.set_batch(batch(row("not a shot name")))
        assert built.index(0, SHOT, built.index(0, 0, QModelIndex())).data(
            Qt.ItemDataRole.DisplayRole
        ) == "not a shot name"
        assert self.index_of(built, SHOT).data(Qt.ItemDataRole.EditRole) == ""

    def test_an_editor_opens_on_what_the_cell_is_showing(self, model: ShotListModel) -> None:
        model.set_display_mode(DisplayMode.SOURCE_TC)
        assert self.index_of(model, IN).data(Qt.ItemDataRole.EditRole) == "01:00:00:08"


class TestCommittingAnEdit:
    """Section 5: what a typed value does to the row behind the cell."""

    def index_of(self, model: ShotListModel, column: int, row_index: int = 0) -> QModelIndex:
        return model.index(row_index, column, model.index(0, 0, QModelIndex()))

    def commit(self, model: ShotListModel, column: int, text: str, row_index: int = 0) -> bool:
        index = self.index_of(model, column, row_index)
        return bool(model.setData(index, text, Qt.ItemDataRole.EditRole))

    def test_a_shot_code_becomes_an_override(self, model: ShotListModel) -> None:
        assert self.commit(model, SHOT, "MELT0009")
        assert model.batch.rows[0].shot_code_override == "MELT0009"
        assert text(model, 0, SHOT) == "MELT0009"

    def test_emptying_the_shot_code_puts_the_parsed_one_back(self, model: ShotListModel) -> None:
        """Withdrawing a correction means the original stands, not that the row is nameless."""
        self.commit(model, SHOT, "MELT0009")
        assert self.commit(model, SHOT, "   ")
        assert model.batch.rows[0].shot_code_override is None
        assert text(model, 0, SHOT) == "MELT0001"

    def test_notes_are_free_text(self, model: ShotListModel) -> None:
        assert self.commit(model, NOTES, "lens grid missing, asked Ben")
        assert model.batch.rows[0].notes == "lens grid missing, asked Ben"

    def test_an_absolute_frame_moves_in(self, model: ShotListModel) -> None:
        assert self.commit(model, IN, "20")
        assert model.batch.rows[0].current == InOut(20, 231)

    def test_a_relative_offset_moves_out_from_where_it_was(self, model: ShotListModel) -> None:
        assert self.commit(model, OUT, "-6")
        assert model.batch.rows[0].current == InOut(8, 225)

    def test_a_timecode_is_read_against_the_source_by_default(self, model: ShotListModel) -> None:
        assert self.commit(model, IN, "01:00:00:12")
        assert model.batch.rows[0].current == InOut(12, 231)

    def test_a_timecode_is_read_against_the_record_when_that_is_what_is_shown(
        self, model: ShotListModel
    ) -> None:
        """Section 2: the toggle sets how a typed timecode is interpreted, not only what
        is shown. The second row sits 224 frames into the timeline, so its own frame 8
        is record 01:00:09:08 and four frames later is frame 12."""
        model.set_display_mode(DisplayMode.RECORD_TC)
        assert self.commit(model, IN, "01:00:09:12", row_index=1)
        assert model.batch.rows[1].current == InOut(12, 231)

    def test_an_unrecognized_value_writes_nothing(self, model: ShotListModel) -> None:
        assert not self.commit(model, IN, "sometime tuesday")
        assert model.batch.rows[0].current == InOut(8, 231)

    def test_drop_frame_is_refused_where_it_is_typed_too(self, model: ShotListModel) -> None:
        """QC-027 is the rule; this is the cell saying the same thing before it is one."""
        assert not self.commit(model, IN, "01:00:00;12")
        assert model.batch.rows[0].current == InOut(8, 231)

    def test_the_same_value_again_is_not_a_change(self, model: ShotListModel) -> None:
        """False here means nothing was written, so nothing repaints and nothing saves."""
        assert not self.commit(model, IN, "8")
        assert not self.commit(model, NOTES, "")

    def test_a_range_the_media_cannot_satisfy_is_stored_and_then_reported(
        self, model: ShotListModel
    ) -> None:
        """QC-031 says it about the row. Refusing the keystroke would stop an editor who
        is typing Out before In on the way to a range that is fine."""
        assert self.commit(model, OUT, "900")
        assert [result.rule_id for result in model.batch.rows[0].errors()] == ["QC-031"]

    def test_a_range_before_the_media_s_timecode_still_renders(self, model: ShotListModel) -> None:
        """The stored value can sit before the media's own timecode; the cell that shows
        it must not raise, because Qt would swallow that and paint nothing."""
        model.set_display_mode(DisplayMode.SOURCE_TC)
        assert self.commit(model, IN, "-90000")
        assert str(cell(model, 0, IN, Qt.ItemDataRole.DisplayRole)).startswith("-")

    def test_the_row_s_rules_re_run_on_commit(self, model: ShotListModel) -> None:
        assert not model.batch.rows[0].qc
        self.commit(model, IN, "40")
        assert "QC-035" in [result.rule_id for result in model.batch.rows[0].qc]

    def test_a_rule_that_no_longer_holds_goes_away_again(self, model: ShotListModel) -> None:
        """`apply_row_rules` replaces its own results rather than appending to them."""
        self.commit(model, OUT, "900")
        self.commit(model, OUT, "231")
        assert not model.batch.rows[0].errors()

    def test_the_whole_row_repaints_because_more_than_one_cell_moved(
        self, model: ShotListModel
    ) -> None:
        """An In moves Duration, Max Avail, the dot and the tint."""
        seen: list[tuple[int, int]] = []
        model.dataChanged.connect(
            lambda first, last, roles=None: seen.append((first.column(), last.column()))
        )
        self.commit(model, IN, "40")
        assert (0, len(COLUMNS) - 1) in seen
        assert text(model, 0, DURATION) == "192"

    def test_the_turnover_header_repaints_too(self, model: ShotListModel) -> None:
        """Its summary counts the errors and warnings that just changed."""
        self.commit(model, OUT, "900")
        header = model.index(0, 0, QModelIndex()).data(Qt.ItemDataRole.DisplayRole)
        assert "1 error" in str(header)

    def test_a_commit_says_so_once(self, model: ShotListModel) -> None:
        """What autosave listens to. The row rather than the index, because what gets
        written is the batch."""
        edited: list[object] = []
        model.row_edited.connect(edited.append)
        self.commit(model, NOTES, "checked")
        assert edited == [model.batch.rows[0]]

    def test_nothing_but_the_edit_role_writes(self, model: ShotListModel) -> None:
        index = self.index_of(model, NOTES)
        assert not model.setData(index, "x", Qt.ItemDataRole.DisplayRole)
        assert model.batch.rows[0].notes == ""


class TestSkipping:
    """Ctrl+K, section 4. The reason is the view's to ask for; this is what it does."""

    def index_of(self, model: ShotListModel, column: int = SHOT) -> QModelIndex:
        return model.index(0, column, model.index(0, 0, QModelIndex()))

    def test_a_skipped_row_says_so_and_shows_it(self, model: ShotListModel) -> None:
        assert model.set_skipped(self.index_of(model), True, "reshoot")
        assert model.batch.rows[0].skipped
        assert model.batch.rows[0].skip_reason == "reshoot"
        assert row_state(model.batch.rows[0]) is RowState.SKIPPED

    def test_un_skipping_keeps_the_reason_it_was_given(self, model: ShotListModel) -> None:
        """A row toggled off and on again is not a second interrogation."""
        model.set_skipped(self.index_of(model), True, "reshoot")
        model.set_skipped(self.index_of(model), False)
        assert not model.batch.rows[0].skipped
        assert model.batch.rows[0].skip_reason == "reshoot"

    def test_skipping_a_skipped_row_changes_nothing(self, model: ShotListModel) -> None:
        model.set_skipped(self.index_of(model), True, "reshoot")
        assert not model.set_skipped(self.index_of(model), True, "something else")
        assert model.batch.rows[0].skip_reason == "reshoot"

    def test_it_saves_like_any_other_edit(self, model: ShotListModel) -> None:
        edited: list[object] = []
        model.row_edited.connect(edited.append)
        model.set_skipped(self.index_of(model), True, "reshoot")
        assert edited == [model.batch.rows[0]]

    def test_a_turnover_header_cannot_be_skipped(self, model: ShotListModel) -> None:
        assert not model.set_skipped(model.index(0, 0, QModelIndex()), True, "no")
