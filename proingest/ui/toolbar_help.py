"""What each toolbar button does, and why it is unavailable when it is.

UI_SPEC section 1. One short sentence per button in the present tense, naming what
changes, plus the keyboard shortcut; and **a disabled button keeps its tooltip and says
why it is disabled**, which is the half that earns the feature. The toolbar deliberately
shows every action from the first launch with the unfinished ones greyed, so "Run: add a
turnover first" is the difference between a tool that looks broken and one that is
telling you what to do next.

**Apart from the window, like `ui/metadata.py` and `ui/settings_form.py`**, and for the
third of the same reasons. The first two are that the wording is the part that gets
argued about and that it is assertable without a window. The third is specific to this
one: section 1 says the tooltips should share their wording with the user guide's button
reference (PRD FR-17, M9) **so the two cannot drift**, and a sentence buried in a widget
constructor cannot be shared. The guide reads this module.

**Nothing here decides whether a button is enabled.** `MainWindow._update_state` is the
one authority on that and it stays so; this is handed the answer. Two copies of that rule
would disagree the first time one of them grew a condition, and the copy that gets it
wrong is the one nobody presses.
"""

from __future__ import annotations

from dataclasses import dataclass

NEW = "new"
OPEN = "open"
SAVE = "save"
ADD_TURNOVER = "add_turnover"
SCAN = "scan"
INGEST = "ingest"
RUN = "run"
STOP = "stop"
EXPORT = "export"
SETTINGS = "settings"

MAX_LINE = 80
"""How wide a line of a tooltip may be, in characters, and it is a real constraint.

Qt word-wraps a tooltip **only** when the text looks like rich text; plain text is drawn
on one line however long it is. So a sentence that reads perfectly in this file becomes
a strip most of the way across the screen, and the first draft of these had one at 104.
A test holds every line of every tooltip, in every state, under this.
"""

WHAT_IT_DOES = {
    NEW: "Starts an empty batch, offering to save the one on screen first.",
    OPEN: "Opens a saved .pibatch file in place of what is on screen.",
    SAVE: "Writes the batch to its .pibatch file, asking where the first time.",
    ADD_TURNOVER: "Adds a turnover folder and scans it straight away.",
    SCAN: "Re-tries only the turnovers that came back with no shots.",
    INGEST: "Writes a colour session's approved cut, CDL and CLFs onto one turnover.",
    RUN: "Renders every shot that is not skipped, then writes both spreadsheets.",
    STOP: "Stops the run. What is in flight finishes; nothing further starts.",
    EXPORT: "Writes the QC log and the shot tracker without rendering.",
    SETTINGS: "Opens the settings page: thresholds, naming, colour and logging.",
}
"""One sentence each, in the order section 1 draws the toolbar.

Not a restatement of the label: section 1 says Scan saying "Scans" is a tooltip nobody
reads twice. Each names what it changes, which is why several of them mention the thing
the button is easiest to be wrong about - that Add Turnover scans, that Scan does not
re-scan, that an ingest writes onto one turnover.
"""

NO_BATCH = "No batch is open."
SCANNING = "A scan is going."
RENDERING = "A run is going."
RUN_FIRST = "A run is going; stop it before swapping the batch under it."
NOTHING_UNSCANNED = "Every turnover already has shots."
NO_ROWS_TO_INGEST = "Nothing to write onto yet; scan a turnover first."
NO_ROWS_TO_RUN = "Add a turnover first."
NO_ROWS_TO_EXPORT = "Nothing to report on yet; add a turnover first."
NOT_RUNNING = "No run is going."
ALREADY_STOPPING = "Already stopping; the deliverables in flight are finishing."

NO_SESSION = "No colour session ingested yet, so a run would write nothing (QC-008)."
"""The one note on a button that is **enabled**, and the reason section 1 wanted these.

A batch with shots and no ingested session runs, refuses every turnover and writes
nothing, which is the correct refusal and reads as a dead button (docs/MAC_SESSION.md).
QC-008 is the answer and the Issues dock carries it, but only after a run has been
attempted. This says it before.
"""


@dataclass(frozen=True)
class ToolbarState:
    """What the window knows that changes a tooltip. Facts, not decisions.

    Every field is read straight off the batch or off a worker, so a test can state one
    without building a window. `has_session` is deliberately the plain question - has
    **anything** been ingested - rather than a second implementation of QC-008: the
    tooltip it feeds says nothing has been ingested, which is exactly that question.
    """

    batch_open: bool = False
    has_rows: bool = False
    has_unscanned: bool = False
    has_session: bool = False
    scanning: bool = False
    rendering: bool = False
    stopping: bool = False


def note(key: str, state: ToolbarState, enabled: bool) -> str:
    """The second line: why the button is unavailable, or what it will not do.

    Ordered from the most fundamental reason to the most specific, because a batch that
    is not open is a truer answer than a scan that is going, and only one line is shown.
    """
    if enabled:
        return NO_SESSION if key == RUN and not state.has_session else ""

    if key in (NEW, OPEN):
        return RUN_FIRST
    if key == STOP:
        return ALREADY_STOPPING if state.rendering else NOT_RUNNING
    if not state.batch_open:
        return NO_BATCH
    if state.scanning:
        return SCANNING
    if state.rendering:
        return RENDERING
    if key == SCAN and not state.has_unscanned:
        return NOTHING_UNSCANNED
    if key == INGEST and not state.has_rows:
        return NO_ROWS_TO_INGEST
    if key == RUN and not state.has_rows:
        return NO_ROWS_TO_RUN
    if key == EXPORT and not state.has_rows:
        return NO_ROWS_TO_EXPORT
    return ""


def tooltip(key: str, state: ToolbarState, enabled: bool, shortcut: str = "") -> str:
    """The whole tooltip: the sentence, its shortcut, and the note when there is one.

    Plain text with a newline rather than rich text, because Qt renders anything that
    looks like markup as rich text and a tooltip containing a path or a `<` would then
    be drawn wrong by a wrapper nobody asked for.

    The note is a line of its own and comes last, so the eye that went to the button
    because it was greyed lands on the actionable half.
    """
    head = WHAT_IT_DOES[key]
    if shortcut:
        head = f"{head}  {shortcut}"
    second = note(key, state, enabled)
    return f"{head}\n{second}" if second else head
