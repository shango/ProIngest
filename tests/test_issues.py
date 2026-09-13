"""The Issues dock. `ui/issues.py`, M5.4.

UI_SPEC section 6: every QC result in the batch, in the order the list shows the things
they are about, with the rule ID in its own column and a double-click that selects the
shot in the list.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from proingest.core.models import Batch, Deliverable, QCResult, Turnover
from proingest.ui.issues import BATCH_SCOPE, COLUMNS, FIX_HINTS, IssuesDock, issues_for
from tests.fixtures.batches import batch, fail, row, turnover, warn


@pytest.fixture
def dock(qt_app: QApplication) -> IssuesDock:
    return IssuesDock()


def texts(dock: IssuesDock, column: str) -> list[str]:
    position = COLUMNS.index(column)
    items = [dock.topLevelItem(i) for i in range(dock.count)]
    return [item.text(position) for item in items if item is not None]


class TestClickingThroughFromThePane:
    """`select_result`, which the metadata pane's rule IDs land on (UI_SPEC 12.2)."""

    def test_a_rule_selects_its_line(self, dock: IssuesDock) -> None:
        dock.show_batch(batch(warn(row())))
        assert dock.select_result("QC-030")
        current = dock.currentItem()
        assert current is not None and current.text(COLUMNS.index("Rule")) == "QC-030"

    def test_a_rule_that_fired_on_several_shots_prefers_the_selected_one(self, dock: IssuesDock) -> None:
        """QC-023 clicked while MELT0007 is selected should land on MELT0007's line."""
        first, second = warn(row(), "QC-023"), warn(row("MELT0007_pl01"), "QC-023")
        dock.show_batch(batch(first, second))
        assert dock.select_result("QC-023", [second])
        current = dock.currentItem()
        assert current is not None and current.text(COLUMNS.index("Shot")) == "MELT0007"

    def test_it_falls_back_to_the_first_line_carrying_that_rule(self, dock: IssuesDock) -> None:
        first, second = warn(row(), "QC-023"), warn(row("MELT0007_pl01"), "QC-023")
        dock.show_batch(batch(first, second))
        assert dock.select_result("QC-023", [])
        current = dock.currentItem()
        assert current is not None and current.text(COLUMNS.index("Shot")) == "MELT0001"

    def test_a_rule_the_dock_no_longer_holds_selects_nothing(self, dock: IssuesDock) -> None:
        dock.show_batch(batch(row()))
        assert not dock.select_result("QC-030")


class TestWhatIsCollected:
    def test_a_row_s_results_are_labelled_with_its_shot_code(self) -> None:
        found = issues_for(batch(warn(row())))
        assert [(issue.label, issue.result.rule_id) for issue in found] == [("MELT0001", "QC-030")]

    def test_a_row_with_no_shot_code_falls_back_to_the_clip_name(self) -> None:
        nameless = warn(row("not a shot name"))
        nameless.identity = None
        assert issues_for(batch(nameless))[0].label == "not a shot name"

    def test_a_batch_result_is_first_and_belongs_to_no_row(self) -> None:
        held = batch(warn(row()))
        held.qc.append(QCResult("QC-057", "error", "batch", "no space on the delivery volume"))
        found = issues_for(held)

        assert found[0].label == BATCH_SCOPE
        assert found[0].row is None

    def test_a_turnover_result_is_labelled_with_its_folder(self) -> None:
        held = batch(turnovers=[turnover()])
        held.turnovers[0].qc.append(QCResult("QC-003", "warning", "turnover", "EDL used"))
        assert issues_for(held)[0].label == "turnover001_02_23_2026_danielluckett"

    def test_a_deliverable_s_results_are_attributed_to_its_row(self) -> None:
        """Phase B reports against the file; the editor still wants to know which shot."""
        held = row()
        held.deliverables = [
            Deliverable(
                kind="raw_dir",
                name="x",
                path=Path("/d/x"),
                version=1,
                qc=[QCResult("QC-101", "error", "deliverable", "frame count is short")],
            )
        ]
        found = issues_for(batch(held))
        assert (found[0].label, found[0].row) == ("MELT0001", held)

    def test_the_order_follows_the_list_rather_than_the_severity(self) -> None:
        """The dock is read beside the list, and the two agreeing about where a shot is
        is worth more than the errors being at the top of a table already coloured."""
        found = issues_for(
            batch(
                warn(row("MELT0001_pl01"), "QC-030"),
                fail(row("MELT0002_pl01"), "QC-012"),
            )
        )
        assert [issue.result.rule_id for issue in found] == ["QC-030", "QC-012"]


class TestTheTable:
    def test_it_has_section_6_s_columns(self, dock: IssuesDock) -> None:
        assert COLUMNS == ("Shot", "Rule", "Severity", "Message", "Fix")

    def test_every_result_becomes_a_row(self, dock: IssuesDock) -> None:
        dock.show_batch(batch(warn(row()), fail(row("MELT0002_pl01"))))
        assert dock.count == 2

    def test_the_rule_id_is_its_own_column(self, dock: IssuesDock) -> None:
        """It is the thing that survives: a log line, a spreadsheet cell and a
        conversation with the studio all quote the ID."""
        dock.show_batch(batch(warn(row(), "QC-030")))
        assert texts(dock, "Rule") == ["QC-030"]

    def test_a_rule_with_an_obvious_answer_says_what_it_is(self, dock: IssuesDock) -> None:
        dock.show_batch(batch(fail(row(), "QC-012")))
        assert texts(dock, "Fix") == [FIX_HINTS["QC-012"]]

    def test_a_rule_with_no_obvious_answer_says_nothing(self, dock: IssuesDock) -> None:
        dock.show_batch(batch(warn(row(), "QC-030")))
        assert texts(dock, "Fix") == [""]

    def test_showing_a_second_batch_replaces_the_first(self, dock: IssuesDock) -> None:
        dock.show_batch(batch(warn(row())))
        dock.show_batch(batch(row()))
        assert dock.count == 0

    def test_an_empty_batch_is_an_empty_table(self, dock: IssuesDock) -> None:
        dock.show_batch(Batch())
        assert dock.count == 0


class TestClickingThrough:
    def test_activating_a_row_asks_for_that_shot(self, dock: IssuesDock) -> None:
        wanted = warn(row())
        dock.show_batch(batch(wanted))
        asked: list[object] = []
        dock.row_activated.connect(asked.append)
        dock.itemDoubleClicked.emit(dock.topLevelItem(0), 0)

        assert asked == [wanted]

    def test_activating_a_batch_result_asks_for_nothing(self, dock: IssuesDock) -> None:
        held = Batch(qc=[QCResult("QC-057", "error", "batch", "no space")])
        dock.show_batch(held)
        asked: list[object] = []
        dock.row_activated.connect(asked.append)
        dock.itemDoubleClicked.emit(dock.topLevelItem(0), 0)

        assert asked == []

    def test_the_right_shot_is_asked_for_when_two_rows_are_alike(self, dock: IssuesDock) -> None:
        """Identity, not equality: two rows of a turnover can agree in every field."""
        first, second = warn(row()), warn(row())
        held = Batch(turnovers=[turnover()], rows=[first, second])
        for held_row in held.rows:
            held_row.turnover_id = "turnover001"
        dock.show_batch(held)
        asked: list[object] = []
        dock.row_activated.connect(asked.append)
        dock.itemDoubleClicked.emit(dock.topLevelItem(1), 0)

        assert asked[0] is second


def test_turnover_results_come_before_the_rows_under_them() -> None:
    held = batch(warn(row(turnover_id="turnover001")), turnovers=[turnover()])
    held.turnovers[0].qc.append(QCResult("QC-003", "warning", "turnover", "EDL used"))
    assert [issue.result.rule_id for issue in issues_for(held)] == ["QC-003", "QC-030"]


def test_a_row_whose_turnover_is_not_in_the_batch_is_not_shown() -> None:
    """`rows_for` groups by turnover, exactly as the list does, so a row with no
    turnover has no home in either. It cannot happen from a scan, where the turnover
    and its rows arrive together, and the two surfaces agreeing matters more here than
    catching it: a row nobody can see in the list is not a row to report about."""
    held = Batch(turnovers=[Turnover("t1", Path("/s/t1"))], rows=[warn(row(turnover_id="t9"))])
    assert issues_for(held) == []
