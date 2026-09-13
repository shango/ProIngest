# UI Spec

PySide6 6.7+. Dark theme in the spirit of DaVinci Resolve: near-black panels, thin 1px separators, muted grey text, one accent color for selection and primary actions, amber for warnings, red for errors, green for done. No gradients, no drop shadows on panels, no rounded cards. Density is professional, not spacious.

## 1. Layout

```
+------------------------------------------------------------------+
| Toolbar: [New] [Open] [Save]  | [Add Turnover] [Scan] [Run] [Stop] | [Export] [Settings]   |
+------------------------------------------------------------------+
| Batch bar: batch name, delivery root path (click to change), In/Out toggle [Frames|Source TC|Record TC], search box |
+------------------------------------------------------------------+
|                                            |                     |
|   SHOT LIST (hero)                         |  METADATA           |
|                                            |  (selected row,     |
|   > turnover001  02_23_2026  danielluckett |   read only,        |
|     MELT0001_pl01  ...                     |   collapsible)      |
|     MELT0001_cp01  ...                     |                     |
|   > turnover002  ...                       |  section 12         |
|                                            |                     |
+------------------------------------------------------------------+
| Bottom dock (collapsible, tabs): Issues | Log | Deliverables (for selected row) |
+------------------------------------------------------------------+
| Status bar: scan/render progress bar, jobs running, ETA, GPU on/off |
+------------------------------------------------------------------+
```

The list is still the hero. The metadata pane is a fixed-width reading surface beside it, not a
second workspace: it is read only, it never takes focus, and it collapses to nothing. See
section 12.

**The list is the only thing that writes to the model.** No viewers, no colour controls, no
editable metadata pane: In, Out, Shot Code, Notes and Skip are edited in their cells and
nowhere else. That was true in the original spec, briefly untrue on 2026-09-11 when the
viewers were given trim buttons, and is true again.

Nothing opens a modal during review except Settings and file dialogs.

**Every toolbar button carries a hover tooltip** (asked for 2026-09-12, not yet built): one
short sentence saying what the button does, in present tense, naming what changes, plus its
keyboard shortcut. Not a restatement of the label - "Scan" saying "Scans" is a tooltip nobody
reads twice.

**A disabled button keeps its tooltip and says why it is disabled**, which is the half that
earns the feature: the toolbar is deliberately full of buttons that are not available yet
(every action exists from the first launch and the ones with nothing behind them are greyed),
so "Run: add a turnover first" is the difference between a tool that looks broken and one that
is telling you what to do next. The tooltip is the only place the window explains itself in
words, and the wording should match the user guide's button reference (PRD FR-17) so the two
cannot drift.

## 2. Shot list columns

Frozen left: status dot, Shot Code (editable), Elem.
Scrolling: Source file, Res, FPS, In (editable), Out (editable), Duration, Max Avail, Audio (icon: none / one / many), Side files (icons: HDRI, camData, stills), Version, Progress, Notes (editable, free text, goes to tracker).

- **The In/Out display toggle in the batch bar has three states, not two: `Frames`, `Source TC`, `Record TC`.** It sets what the In and Out cells show as their primary value for the whole list, and it sets how a typed timecode is interpreted (source or record) when either TC state is selected.
- **`Frames` is the default.** The frame number is what the model actually holds: frame math is integer throughout, In and Out *are* frame numbers, the QC rules quote them, the delivered EXR sequence is numbered by them, and the viewers step by them. Timecode is derived at the boundary and never stored. Opening on the derived value would show the editor a translation of the thing they are about to edit rather than the thing itself. The choice is remembered per batch, so an editor who works in source TC sets it once.
- Secondary line: whichever representation is not primary sits under it in smaller text, so nothing is ever hidden, only demoted. In `Frames` the secondary is source TC; in either TC state it is the source frame number. Row height accommodates two lines.
- The editor reads frames and timecode at different moments, which is why frames is a first-class state of this control rather than only the secondary line: a frame number is what gets typed into the In/Out cells and what a VFX vendor quotes back, and a timecode is what the AD and the edit talk in. Section 5 accepts both as input whatever this is set to.
- Turnover group headers are rows in the same view (QTreeView with a flat two-level model), collapsible, showing counts and aggregate status.
- Sorting is fixed to timeline order within a turnover. A search box filters rows by shot code substring.

## 3. Row colors and status dot

| state | dot | row tint |
|---|---|---|
| ok, not rendered | grey | none |
| warning | amber | faint amber |
| error (blocked) | red | faint red |
| skipped by user | hollow | dimmed text |
| rendering | accent, animated | none |
| done | green | none |
| failed render | red | faint red |

Hovering the dot or the row shows a tooltip listing rule IDs and messages. Clicking the dot focuses the Issues dock on that row.

## 4. Keyboard model

- Arrow Up/Down: move between shot rows (skips group headers).
- Tab / Shift+Tab: move between editable cells in the current row (Shot Code, In, Out, Notes), wrapping to next row's first editable cell.
- Enter: commit edit and stay. Escape: revert cell.
- Ctrl+K: toggle skip on current row (prompts for reason on first skip; Escape cancels).
- Ctrl+T: cycle the In/Out display, `Frames` to `Source TC` to `Record TC` and round again.
- Ctrl+I: show or hide the metadata pane (section 12). Focus stays in the list.
- Ctrl+F: focus search. Ctrl+S: save batch. Ctrl+R: run. Ctrl+.: stop.
- Typing into a selected cell starts editing immediately (no F2 required).
- Space on a group header collapses/expands.

**Ctrl means Cmd.** Qt maps the `Ctrl` portable modifier onto Cmd on macOS on its own, so the
shortcuts above are written as `Ctrl+` in both the spec and the code and reach the user as
Cmd+. Do not special-case them per platform, and do not use `Qt.MetaModifier` to mean Cmd:
on macOS Qt swaps Control and Meta, so `MetaModifier` is the physical Control key. Where a
standard action exists (`QKeySequence.Save`, `Find`, `Quit`) prefer it, because it also gets
the platform's second binding for free.

`Ctrl+.` is Cmd+. on macOS, which is the long-standing system idiom for cancel. It is the
right key for Stop and needs no change.

## 5. In/Out input parsing

Auto-detected in this order:
1. `^[+-]\d+$` relative offset in frames
2. `^\d{1,2}:\d{2}:\d{2}[:;]\d{2}$` timecode (`;` is rejected with QC-027 message)
3. `^\d+$` absolute source frame
4. Anything else: cell shows inline red text "unrecognized" and reverts on Escape

After commit, Duration and Max Avail recompute, validation reruns for the row only, autosave fires.

## 6. Issues dock

Table: row, rule ID, severity, message, "Fix" hint where applicable (e.g. "Rename shot code", "Locate media" opens a file picker and writes a path override into the batch). Double-click selects the row in the list.

## 7. Run and progress

- Run opens no dialog if the delivery root is set; otherwise it prompts once.
- Each row shows a slim progress bar in the Progress column with job count (e.g. 3/5).
- Status bar shows overall percent, jobs running, throughput (frames/s), and ETA.
- Stop finishes in-flight frames, discards `.part` outputs, and leaves rows in their previous state.
- On completion a non-modal banner above the list reads "Batch complete: 27 done, 1 failed, 2 skipped. Exports written to ...". Click opens the folder.

**Two things about a stopped run that this list said too simply** (M5.5, 2026-09-12). The
records of a stopped run **are** applied to the rows, because a job that finished before Stop
was pressed wrote a real file and a row that did not record it would be wrong about the
delivery folder. What follows is that a stopped row is not literally in "its previous state":
its unfinished deliverables read `skipped` and QC-150 says how many did not land. That is the
honest record of a run that was stopped part way, and the alternative - rows still claiming a
plan nothing fulfilled - is the state QC-150 exists to refuse. The banner on a stopped run
reads "Run stopped: ..." rather than "Batch complete: ...", because the counts alone read as a
batch that finished with most of it skipped.

**The run writes the two spreadsheets** (FR-10), which is what makes the banner's second
sentence true, and the path in it is the link: clicking it opens `_reports` in the Finder. A
batch whose rows have no shot code has no show to file reports under, and the banner then says
no exports were written rather than naming a folder that does not exist.

### 7.1 The strip above the list

The user asked for the run to be readable without looking down at the status bar. Two things
are added above the list, in the strip the completion banner already occupies:

- **A thin progress bar spanning the width of the list**, carrying the **whole batch**, shown
  only while a run is going. Thin: four pixels, no text in it, no percentage written on it, the
  same height as the per row bar in the Progress column.
- **A progress text line under it saying what is being done, in words**, one step at a time:
  "Checking the batch", "Planning 42 shots", "Starting the render pool",
  "Rendering MELT0001_pl01_raw_4k_v01", "Checking what landed",
  "Writing the QC log and the shot tracker". One line, replaced in place, never a scrollback.

**The strip has three states and only ever one of them**: empty when no run has happened, the
bar and its line during a run, the completion banner after one. That is why they share a strip
rather than stacking: a banner from the last run sitting above the bar of this one is two
answers to the same question. Empty is the strip hidden rather than an empty band, so a window
that has never run a batch gives the height back to the list.

**Four surfaces now report a run and each has to say something the others do not.** The
Progress column says how far **this shot** has got and is the only per row answer. The strip's
bar says how far **the batch** has got. The text line says **what is happening now**, which no
bar can say. The status bar says **the numbers**: percent, jobs running, throughput and ETA.
Every one of them reads from the same run state, so they cannot disagree about the percentage.

**The per row indication exists already** (M5.5): a slim bar in the Progress column under the
job count, the count being `3/5` of that row's deliverables. What 7.1 adds is the batch bar,
the text line, and the naming of each step as it happens.

**The line names the longest running job, not the newest message** (M5.10, 2026-09-12). Four
workers report several times a second and a line that followed the newest message would be a
flicker rather than a sentence, so the job named holds still until it finishes and the line
then moves to the next one still going.

**There is no "Verifying" step**, which an earlier draft of this section listed. Post-render
QC runs inside the worker between the rename and the record coming back, and the pool reports
no message for it, so a line claiming it would be the tool guessing at its own state. Adding
one is a new `render.ProgressState` and a publish in `render_job`, and it can be built when
the wait is long enough for anyone to notice it.

## 8. Stringout burn-ins: dropped

**The tool no longer builds a stringout** (PRD FR-9, decided 2026-09-11), so there are no
burn-ins to specify. The colour session exports a reference QT with the look and burn-ins
already on it.

The section number is kept rather than renumbered, because every other section is referenced
by number from the PRD, from `QC_RULES.md` and from `PROGRESS.md`, and renumbering would
silently redirect all of them.

## 9. Settings page

A single window with a left section list and right form, like Resolve's project settings. Sections and fields as listed in `PRD.md` FR-12. Apply/Cancel at bottom; changes to rule thresholds re-run validation on the open batch when applied.

## 10. Empty and first-run states

- No batch open: centered text "New batch or open one", with the two buttons.
- Batch with no turnovers: "Add a turnover folder to begin".
- After Scan with zero rows: "No clips found in timeline" plus a link to the Issues dock.

## 11. macOS details

- Native title bar and app icon. Progress during render goes on the **Dock tile**, not a
  taskbar. Qt 6 exposes no API for it, so it needs a small `NSDockTile` shim through PyObjC,
  isolated in a macOS-only helper under `ui/`. It is decoration: if the shim is not built, the
  status bar progress in section 7 still carries the information and nothing else changes.
- The menu bar is the system menu bar at the top of the screen, not a window menu bar. Qt does
  this automatically, but it means About and Settings must be created with the right roles
  (`QAction.AboutRole`, `PreferencesRole`) or macOS will not move them into the application
  menu where users look for them.
- The metadata pane is a **right dock** rather than a splitter pane (M5.6), which is what
  gives it three of the things section 12 asks for without building any of them: it collapses
  to nothing, its width and whether it is showing travel in `saveState` beside the bottom
  dock, and `toggleViewAction` is Ctrl+I. It is closable but **not movable or floatable**:
  section 1 calls it a fixed width reading surface, not a second workspace. Which sections
  the editor has collapsed is the one thing Qt's blob cannot hold, so it is a settings field
  of its own, storing **titles of the shut ones**: a section a later chunk adds then arrives
  open, and reordering the sections cannot collapse a different one.
- Settings is reached by Cmd+, as well as from the toolbar. That shortcut is a macOS
  convention strong enough that its absence reads as a bug.
- Remembers window geometry and dock state per user, in
  `~/Library/Application Support/ProIngest` (see PACKAGING.md).
- **Nothing detects where Google Drive is mounted.** OQ-25 is resolved: the editor points at
  the two roots in section 13 and both happen to be on a Drive mount. File dialogs open at the
  last used folder. There is no `G:` on macOS and there is also no probing of
  `~/Library/CloudStorage` or `/Volumes`: a wrong guess is worse than no guess, because it
  opens the dialog somewhere plausible and empty.
- Use `QStandardPaths` rather than building any of these paths by hand.

## 12. Metadata pane

A read-only pane on the right of the shot list showing everything known about the current
selection. Clicking a row fills it; arrowing down the list refills it as the selection moves.

**Its job is to show what has no column.** Section 2 gives the list columns for the fields the
editor works with (shot code, In, Out, duration, max available, audio and side file icons).
Repeating them here would waste the space and give the editor two places to read the same
number. The pane exists for the rest: codec, pixel format, start timecode, file size, camera
data, turnover details, and the paths themselves.

### 12.1 Behaviour

- **Read only.** The list owns every edit (FR-5). A second editable surface for the same
  fields means two code paths writing the same model and two places for validation to
  disagree. The pane never writes.
- **Never takes focus.** Tab cycles the editable cells of the row (section 4) and must keep
  doing so. The pane is reachable by mouse and by Ctrl+I only.
- **Every value is selectable and copyable**, paths and checksums especially. An editor
  chasing a media problem needs to paste a path into a terminal or a Resolve dialog. A
  copy button on each path row, and the whole pane copyable as `key: value` text.
  Selecting is by mouse only and the labels are `NoFocus`, because `TextSelectableByKeyboard`
  would put the pane back into the Tab order the list owns.
- **Live.** Values recompute as In/Out are typed, the same as Duration and Max Available in
  the row.
- **Collapsible sections**, each remembering its open state, and a remembered pane width.
  Both live with the rest of the window state (section 11).
- Long paths elide in the middle, never at the end: the filename is the part that identifies
  the file, and the middle of a Google Drive path is the least informative part of it.
- **Every value is one line and elides to fit** (M5.6, 2026-09-12), paths in the middle and
  everything else at the end, with the whole value in the tooltip. Not a style choice: a
  wrapping label reports a one line minimum height whatever it will actually need, so a
  column of them inside a scroll area gives the scroll area a minimum far too small and the
  sections are squashed to fit the viewport instead of scrolling. One line per field makes
  every height exact, and it also stops one unbreakable long value setting the pane's minimum
  width. What is given up is reading a long message here, which is why the Issues dock carries
  the full text of every one and why a rule ID in the pane clicks straight through to it.

### 12.2 Sections, and the fields in each

Fields come from `core/models.py` and are shown only when present. A section with nothing in
it is hidden rather than shown empty.

| section | fields |
|---|---|
| Identity | timeline clip name, shot code (and whether it is an editor override), show, shot number, element type and index, aux type and index, track, turnover id |
| Source media | path, codec, pixel format, resolution, single file or image sequence, sequence frame range and padding, frame count, first frame number, start timecode, file size, modified time |
| Frame rate | timeline rate (authoritative), rate stated by the media, and an explicit disagreement note when they differ. COLOR_AND_FORMAT section 5 explains why the timeline wins; QC-026 is the rule |
| Range | record In/Out, source In/Out in frames and timecode, turnover snapshot In/Out, current In/Out, duration, max available out, and whether the editor has moved it off the snapshot (QC-035) |
| Audio | path, sample rate, channels, bit depth, duration in samples and in frames, and the sync difference against the video range (QC-043) |
| Colour | source encoding as the shooter wrote it, which carrier named it, and the CLF the colour session delivered. **Added 2026-09-12 with M5.6**: M4.6 put all three on the row after this table was written, none has a column in the list, and the encoding is shown verbatim because the string is what has to be corrected when it is wrong |
| Side files | HDRI path, camData path, and the parsed camData key/values once OQ-11 is settled. This is the single most useful thing in the pane for an AD sitting with the editor, because it is the only place lens, filter and camera body ever appear. **The pane never reads the file itself**: the parsed pairs arrive through a lookup the window caches per batch, because the pane redraws on every arrow key and a turnover sits on a Drive mount |
| Turnover | number, date, shooter, folder, timeline file. Shown alone when a turnover group header is the selection |
| QC | count by severity with the rule IDs, each clicking through to that row in the Issues dock. **Built across the whole selection rather than merged field by field**, unlike every other section: two rows with different problems agree on nothing, so a merge would reduce this to "mixed", which is the one answer that helps nobody |

### 12.3 Empty and edge states

- **Nothing selected**: "Select a shot to see its metadata". Not a blank panel.
- **More than one row selected**: show only the fields the selection agrees on, with a count
  ("12 shots selected"). Fields that differ read "mixed". This is what makes the pane useful
  for spotting one clip at the wrong resolution in a turnover of thirty.
- **Turnover header selected**: the Turnover section alone. The turnover's own results are
  fields inside it rather than a QC section beside it, so "alone" stays literally true; the
  rows' results are not rolled up here because the group header in the list already counts
  them and the Issues dock lists every one.
- **Media unresolved** (QC-011, QC-012): the Identity and Range sections still populate from
  the timeline, and Source media reads why it is missing rather than vanishing. An unresolved
  row is exactly when someone wants to see what the timeline claimed the path was.
  **Where that sentence comes from** (M5.6): the pane reads the QC result rather than
  re-deriving anything, because the scan is the only thing that knows what it looked for.
  Nothing stores the claimed path once a row has no media, so **QC-012's message names it**,
  which is the one record of what the timeline asked for.
- **Media on a Drive placeholder** that has not downloaded yet: show the download-wait state
  rather than blocking the pane, matching the scan behaviour in PRD section 8.

### 12.4 What it is not

- **Not the Deliverables tab.** That stays in the bottom dock (section 1). The pane describes
  the source; the dock describes what was written from it, with versions, paths and checksums,
  which is a table and wants the width. Keep the boundary: nothing about an output file
  belongs in the pane except the QC summary.
- **Not the frame viewer.** That is the v02 item in PRD section 10 and needs a decoded frame
  cache. The pane is text.

## 13. Source root and delivery root

Two folder choosers, and they are the only thing the tool knows about where files live.
OQ-25.

| root | chosen where | what it means |
|---|---|---|
| Source root | toolbar, `Add Turnover` | The folder turnovers are added from. The chooser opens here, and the turnover folder the editor picks beneath it is what gets scanned and indexed |
| Delivery root | batch bar, click the path | Where `<show>/<shot>/` is written, and where the tracker and QC spreadsheets land |

- Both are remembered **per batch**, so reopening a `.pibatch` restores them and a second batch
  on another drive does not disturb the first.
- Both are plain paths. Nothing validates that they are on a Drive mount, because nothing
  needs to be: a local disk, an external volume and a Drive folder behave the same here.
- A root that has gone missing when a batch is reopened (drive not mounted, folder moved) is
  reported and the chooser reopens. It is not silently recreated: writing a delivery tree into
  a stale path is how deliverables get lost.
- Adding a turnover from outside the source root is allowed and just updates the remembered
  root. The root is a starting point, not a fence.

## 14. Viewers: dropped

**There are no image viewers in the tool** (PRD FR-16, decided 2026-09-11). This section
specified three, In / Center / Out, steppable, with stepping trimming the row, and four colour
controls beside them. All of it is removed and a frame viewer is a v02 item again.

The section number is kept rather than renumbered, because the other sections are referenced by
number from the PRD, from `QC_RULES.md` and from `PROGRESS.md`.

**Why it went:** the viewers existed so an editor could judge a cut point and act on it. That
judgement now happens in the colour session, with the AD present, a real viewer and a calibrated
monitor. What is left in this tool is the occasional one-off trim of an already approved edit
(PRD FR-5), and that is done by typing a number, which the In/Out cells have always supported in
four formats (section 5).
