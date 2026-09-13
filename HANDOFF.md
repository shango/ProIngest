# Session close, 12 September 2026 (late night)

**This file is disposable and it is not the handoff record.** `PROGRESS.md` section 1 is, and it
is written to be picked up cold. This is a note about what one session did, kept because context
is being cleared. Delete it once it has been read. **If it disagrees with `PROGRESS.md` or the
docs, they win.**

It replaces the previous session's file of the same name, which closed on M5.3.

## The one paragraph version

**M5.4 is built: a batch can be made, opened, saved, filled with turnovers and read.** The scan
runs on a `QThread`, Add Turnover scans immediately, Scan re-tries only the turnovers that came
back with no rows, and the Issues dock shows every QC result with a double-click that selects
the shot. 1199 tests, `ruff` and `mypy --strict` clean, committed. **M5.5, run and progress, is
next**, and section 5 of `PROGRESS.md` has the five chunks of M5 after it.

**The build track was also rewritten at the user's request**, mid-session: every unfinished
milestone now carries a chunk list, M6 is off the board, ten long-answered questions are gone
and the footer no longer accumulates. Published as version 41. The standing memory note about
the board was updated to say all of that, so it holds for the next session.

## What this chunk did, in one line

| file | what changed |
|---|---|
| `ui/scanner.py` | new: `core/scan.py` on a worker thread, one result per folder, cancel between folders, a shutdown that waits |
| `ui/issues.py` | new: `issues_for(batch)` and the section 6 table, with the fix hints |
| `ui/main_window.py` | New, Open, Save, the two roots, Add Turnover, Scan, the two list empty states, the close prompt, and the dialogs as overridable methods |
| `ui/batch_bar.py` | the delivery root button |
| `ui/autosave.py` | `adopt`, which is how Save tells the autosaver where the file went |
| `ui/shot_model.py` | `index_for_row`, by identity |
| `ui/shot_list.py` | `select_row`, which clears a filter that had hidden the row |
| `core/models.py` | `Batch.source_root`, `DEFAULT_BATCH_NAME` |
| `core/settings.py` | `AppSettings.last_folder` |

## The decisions worth knowing about

- **The scan runs on a `QThread` with a worker `QObject` moved onto it**, which is what the last
  handoff said to settle first. Core stays Qt-free. The worker gets a **copy** of the probe cache
  and emits a copy back per folder, so the UI thread's dictionary is only written by the UI
  thread; the batch never goes near the worker. Cancellation is between folders only.
- **Add Turnover scans straight away; Scan re-tries only the turnovers with no rows.** A folder
  that shows nothing until a second button is pressed is a dead click, and a turnover that has
  rows is never re-scanned because a scan rebuilds rows and the rows carry the editor's edits.
  That is **OQ-48**, new, and section 9 of `PROGRESS.md` carries it too.
- **Save writes the batch itself** rather than routing through the autosaver: it is the one write
  the editor is waiting on, so a failure is reported rather than logged and left pending.
- **Closing with a never-saved batch asks.** `autosave.flush()` first, and what is still pending
  after it is a batch with no file, which is the one case the editor has to answer for.
- **The Issues dock's Fix column is a hint and nothing more.** UI_SPEC section 6 has "Locate
  media" writing a path override into the batch, and section 1 says the list is the only thing
  that writes to the model. The two want reconciling before either is built further.

## Two things that came out of driving a real window

- **A batch saved as `melt_day1.pibatch` was still calling itself `untitled`**, and
  `exports.report_names` builds the QC log and tracker filenames from `batch.name`. The first
  save now names the batch from the file stem, and never overwrites a name somebody set. **Third
  chunk running that launching the app caught something no test would have.**
- **The tests grew a `DrivenWindow`** whose every dialog is overridden to an answer that changes
  nothing. Not tidiness: an offscreen modal is a hung suite rather than a failed assertion, so a
  test that forgets to stub one does not fail, it stops. That is exactly what happened the first
  time a test opened a batch whose delivery root did not exist, and it cost two long silent test
  runs to find. **Any new dialog goes on that subclass in the same commit.**

## Next task

**M5.5, run and progress**: the worker pool driven from the window, the Progress column, the
status bar's percent, throughput and ETA, Stop, and the completion banner.

**The thing to decide first** is how the pool reports into the window. `render.execute` takes an
`on_progress` callable and runs a process pool; the window needs those callbacks on the UI
thread. The scanner's shape (a worker `QObject` on a `QThread`, emitting signals) is the obvious
model to follow, and the pool already exists and already cancels, so this is a wiring chunk
rather than a new mechanism.

**Nothing is blocked.** OQ-46 still wants one real export before a delivery depends on it. The
Mac checklist gained three lines this session: the native file dialogs and where they open, the
unsaved prompt wanting to be a sheet, and a full Drive path on the delivery root button.
