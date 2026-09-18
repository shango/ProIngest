"""Ingesting a colour session from the window. PRD section 6 step 4.

`core/clf.py` reads the session and writes what it says onto a turnover's rows; this is
the window's half of it, which is which turnover, which EDL, at what rate, and what the
editor is told afterwards. Split out of `ui/main_window.py` beside the run, for the same
reason (REVIEW.md S1): it is a sequence of its own, and the strings it says are half of
what it is.

**The dialogs stay on the window.** `ask_edl_path`, `ask_turnover`, `report_ingest` and
`report_problem` are each their own method there so a test can answer one, and an
offscreen modal is a hung suite rather than a failed assertion. What moved here is the
order they are asked in and what is done with the answers.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING

from proingest.core import clf, qc
from proingest.core.models import FrameRate, Turnover
from proingest.ui import settings_form

if TYPE_CHECKING:
    from proingest.ui.main_window import MainWindow

INGEST_TITLE = "Colour session ingested"
INGEST_READ = "Read from {name}, which holds {events} events."
INGEST_MIXED_RATES = "This turnover carries more than one rate; the EDL was read at {rate}."
NO_RATE_TITLE = "Nothing to read the EDL at"
NO_RATE = "No row in {name} has media, so there is no rate to read the EDL's timecode at. Scan it first."
CANNOT_READ_SESSION = "Could not read the colour session"
WHICH_TURNOVER = "Ingest a colour session into which turnover?"
SESSION_FOUND_TITLE = "Colour session found"
SESSION_FOUND = "{name} has a colour session at\n{folder}\n\nIngest it now?"
"""What the window asks after a scan finds a session by convention (OQ-53).

Asked rather than done: an ingest overwrites any trim already on the rows and the
question is the moment to say which session it is going to read. The folder rather
than the EDL's name, because the folder is the convention and is what to check.
"""


def turnover_labels(turnovers: Sequence[Turnover]) -> list[str]:
    """Folder names, with the parent folder added where two turnovers share one."""
    names = [turnover.folder.name for turnover in turnovers]
    return [
        f"{turnover.folder.parent.name}/{name}" if names.count(name) > 1 else name
        for turnover, name in zip(turnovers, names, strict=True)
    ]


def ingest_text(report: clf.IngestReport, turnover_name: str, rates: Sequence[FrameRate]) -> str:
    """What one ingest did, in the words `proingest run --color-session` prints.

    The counts and the three labelled lists come off the report itself
    (`IngestReport.counts` and `notices`), so the two surfaces cannot drift apart. What
    is said here and not there is the turnover's folder name, because the window ingests
    one turnover rather than all of them.
    """
    lines = [
        f"{turnover_name}: {report.counts}",
        "",
        INGEST_READ.format(name=report.edl_path.name, events=report.events),
    ]
    if len({str(rate) for rate in rates}) > 1:
        lines.append(INGEST_MIXED_RATES.format(rate=rates[0]))
    for label, names in report.notices():
        lines += ["", f"{label}: {', '.join(names)}"]
    return "\n".join(lines)


def ingest(window: MainWindow) -> None:
    """Point at the session's final EDL and write what it says onto one turnover.

    PRD section 6 step 4, and the window's half of what `run --color-session` does.
    **One turnover**, because that is the scope the session is recorded at
    (`Turnover.color_session_edl`, OQ-50) and the scope QC-008 holds a run back at: a
    turnover still waiting on colour is a different turnover from this one.

    **The rate the EDL is read at is the first row with media's**, which is the CLI's
    answer and for the CLI's reason: an EDL's timecode is read at one rate and a batch
    can carry more than one (OQ-19). A turnover whose rows have no media has no rate to
    read it at, and that is said before the chooser opens rather than after it.

    The rules re-run afterwards because the ingest moves In and Out on the rows it
    matched, so the durations the thresholds are judged against have changed. QC-008
    and QC-009 are pre-flight and clear at the next Run.
    """
    if not window.batch_open or window.scanner.busy or window.run.busy:
        return
    turnover = which_turnover(window)
    if turnover is None:
        return
    if not rates_of(window, turnover):
        window.report_problem(NO_RATE_TITLE, NO_RATE.format(name=turnover.folder.name))
        return
    edl = window.ask_edl_path()
    if edl is None:
        return
    # Where the chooser opens next time, which is a per user starting point and not
    # a record of what this batch was graded from: that is on the turnover (FR-12).
    window.settings.color_session_folder = str(edl.parent)
    ingest_edl(window, turnover, edl)


def offer_found(window: MainWindow, turnover: Turnover) -> None:
    """After a scan: a session exported by convention is offered, once, with one click.

    OQ-53. `clf.find_session` looks under the folder Settings names and in the `_color`
    folder beside the turnover, and only a turnover that has rows with media and no
    session yet is asked about: one already ingested keeps what it has, and one with
    nothing to read an EDL at would only be told so. Declining changes nothing, and
    the toolbar's Ingest Colour Session is the same ingest pointed at by hand.
    """
    if turnover.color_session_edl is not None or not rates_of(window, turnover):
        return
    preferred = window.settings.color_session_folder
    edl = clf.find_session(turnover.folder, Path(preferred) if preferred else None)
    if edl is None:
        return
    if window.ask_ingest_found(turnover, edl.parent):
        ingest_edl(window, turnover, edl)


def ingest_edl(window: MainWindow, turnover: Turnover, edl: Path) -> None:
    """Read this EDL and the CLFs around it onto one turnover, and say what happened.

    The half the two routes share: the chooser and the offer both end here. The rules
    re-run afterwards because the ingest moves In and Out on the rows it matched, so
    the durations the thresholds are judged against have changed.
    """
    rows = window.batch.rows_for(turnover.turnover_id)
    rates = rates_of(window, turnover)
    try:
        session = clf.load_session(edl, rates[0], settings_form.show_pattern_of(window.settings))
    except clf.ColorSessionError as exc:
        window.report_problem(CANNOT_READ_SESSION, str(exc))
        return

    report = clf.ingest(turnover, rows, session)
    qc.apply_batch_rules(window.batch, qc.settings_for(window.batch))
    window.shot_model.refresh_rows()
    window.show_results()
    window.autosave.schedule()
    window.report_ingest(ingest_text(report, turnover.folder.name, rates))


def rates_of(window: MainWindow, turnover: Turnover) -> list[FrameRate]:
    """The rates of the turnover's rows with media: the first is what the EDL is read at."""
    return [row.media.rate for row in window.batch.rows_for(turnover.turnover_id) if row.media is not None]


def which_turnover(window: MainWindow) -> Turnover | None:
    """Which turnover the ingest is for: the selection when it says, else asked for.

    A batch of one turnover never asks, because there is nothing to choose between.
    A selected group header says which, and so does a selection of rows that are all
    in the same one; a selection spanning two turnovers says nothing, so it asks.
    """
    batch = window.batch
    turnovers = [t for t in batch.turnovers if batch.rows_for(t.turnover_id)]
    if len(turnovers) == 1:
        return turnovers[0]
    chosen = window.shot_list.selected_turnover()
    if chosen is None:
        selected = {row.turnover_id for row in window.shot_list.selected_rows()}
        if len(selected) == 1:
            one = next(iter(selected))
            chosen = next((t for t in turnovers if t.turnover_id == one), None)
    return chosen if chosen is not None else window.ask_turnover(turnovers)
