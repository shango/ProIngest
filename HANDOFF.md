# Session close, 12 September 2026 (night)

**This file is disposable and it is not the handoff record.** `PROGRESS.md` section 1 is, and it
is written to be picked up cold. This is a note about what one session did, kept because context
is being cleared. Delete it once it has been read. **If it disagrees with `PROGRESS.md` or the
docs, they win.**

It replaces the previous session's file of the same name, which closed on M4.6.4.

## The one paragraph version

**M4.6 is finished and M5 has started.** Three chunks landed: M4.6.5 recorded the source
encoding where it can be read back, M5.1 built the window, and M5.2 put the shot list in it, so
**the tool now shows a batch on screen for the first time**. 1061 tests, `ruff` and
`mypy --strict` clean, everything committed and pushed. **M5.3, editing in the list, is next**,
and section 5 of `PROGRESS.md` has the seven chunks of M5 that follow it.

## What each chunk did, in one line

| chunk | what changed |
|---|---|
| M4.6.5 | `ShotRow.source_encoding_origin`, `proingest/source_encoding_origin` in the EXR header, and the Source encoding column in the QC log |
| M5.1 | `ui/app.py`, `ui/main_window.py`, `ui/theme.qss`, `ui/paths.py`, `core/settings.py`, and the offscreen Qt test harness |
| M5.2 | `ui/shot_model.py`, `ui/shot_list.py`, `ui/batch_bar.py`, plus `Turnover.timeline_start` and `ShotRow.edit_context` in core |

## The decisions worth knowing about

- **The header and the QC log record different strings on purpose** (M4.6.5). The header names
  the **resolved colour space**, because that is what the pixels went through; the log names
  **what the clip said, verbatim**, because that is the string QC-047 asks somebody to correct.
  Neither is derivable from the other: four names resolve to one Sony space and one resolves to
  nothing.
- **Qt tests run on the `offscreen` platform**, through one session scoped `QApplication`
  fixture in `tests/conftest.py`. That is the whole reason the UI is checkable on either CI
  runner. The Linux job needed `libegl1`, `libxkbcommon0` and `libdbus-1-3` added: the platform
  plugin has to load even though it draws nothing.
- **Where the settings file lives is `ui/paths.py`'s answer, through `QStandardPaths`.**
  `core/settings.py` takes a path in every function and works out nothing, because core imports
  no Qt and a core copy of that path could never check Qt's.
- **Every toolbar action exists from M5.1 and the ones with nothing behind them are disabled**,
  each noting the chunk that wires it. The shape of the tool is reviewable before it works, and
  no button is a live-looking no-op.
- **`ShotRow.edit_context` is core's and there is exactly one of it.** The list renders a frame
  as timecode through it and M5.3's typed edit reads a timecode back through the same object.
  Two of them is how a display and its editor come to disagree about which frame an hour is.
- **The frozen left columns were deferred to M5.9, deliberately.** QTreeView has no such
  feature; it takes a second view overlaid on the first sharing model, selection and scroll, and
  it has to survive editing and filtering, which are M5.3 and M5.4. Building it first means
  building it twice.

## Three things that would have passed unnoticed

- **The settings file was landing one folder too deep.** Qt appends the organisation **and** the
  application to `AppDataLocation`, so setting both gave
  `Application Support/ProIngest/ProIngest` where PACKAGING.md specifies one level. The
  organisation name is now left unset and two tests pin the depth. **It was found by launching
  the window with a real event loop, not by a test**, which is the argument for doing that once
  per UI chunk.
- **`main([])` went from printing help to launching the app, which hung the suite rather than
  failing it.** An existing CLI test called it and the run never came back. It now stubs
  `ui.app.run` and asserts the launch. **Nothing in the suite may ever call the real one.**
- **Record timecode needed a fact the batch was not keeping.** `ShotRow.record_in` is measured
  from the timeline's own zero and edits start at an hour, so every row would have read an hour
  early. `Turnover.timeline_start` is new and additive, filled by the scan from
  `Timeline.global_start`, which was already being parsed and then thrown away.

## Next task

**M5.3, editing in the list**: the cells the list owns and nothing else does (FR-5) - shot code,
In, Out and Notes - with `frames.parse_in_out` behind them, Ctrl+K skip and its reason, the
row's rules re-run on commit, and autosave.

**The one thing to decide first** is what a commit re-runs. `qc.apply_row_rules` is per row and
cheap, which is what UI_SPEC section 5 asks for; what it cannot see is the batch level rules.
Re-running everything on every keystroke is the thing not to do.

**Nothing is blocked.** OQ-46 still wants one real export before a delivery depends on it, and
OQ-44's field name is a line on `docs/MAC_SESSION.md` rather than a question holding anything
up. The Mac checklist gained three lines this session: geometry restored under a different
display arrangement, the two line In/Out cell at 2x, and the status dot against its row tint.
