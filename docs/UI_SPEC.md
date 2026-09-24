# UI Spec

PySide6 6.7+. Dark theme in the spirit of DaVinci Resolve: near-black panels, thin 1px separators, muted grey text, one accent color for selection and primary actions, amber for warnings, red for errors, green for done. No gradients, no drop shadows on panels, no rounded cards. Density is professional, not spacious.

## 1. Layout

```
+------------------------------------------------------------------+
| Toolbar: [New] [Open] [Save] | [Add Turnover] [Scan] [Run] [Stop] | [Export] [Settings] |
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

**Every toolbar button carries a hover tooltip** (asked for 2026-09-12, built in M5.11): one
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

What M5.11 settled, beyond the wording:

- **The reason is a second line, and one reason at a time.** They are ordered from the most
  fundamental to the most specific, because "no batch is open" is a truer answer than "a scan is
  going" and only one is shown.
- **One enabled button carries a note too, and it is the case the feature was asked for.** A
  batch whose EDL carries no CDL runs, is refused by QC-008 and writes nothing,
  which is correct and reads as a dead button. Run says so before it is pressed. It is the plain
  question - has any turnover's EDL been read at scan - rather than a second implementation of
  QC-008, which needs pre-flight and the disk.
- **A line may not exceed `toolbar_help.MAX_LINE` characters**, and a test holds every line of
  every tooltip in every state under it. Qt word-wraps a tooltip **only** when the text looks
  like rich text, so plain text is drawn on one line however long it is: the first draft had a
  sentence at 104 characters and it read as a strip across the screen. Nothing about that fails.
- **Nothing about tooltips decides whether a button is enabled.** The window is the one
  authority on that and hands the answer over, so the two cannot drift into disagreeing.

## 2. Shot list columns

Frozen left: status dot, Shot Code (editable), Elem.
Scrolling: Source file, Res, FPS, In (editable), Out (editable), Duration, Max Avail, Audio (icon: none / one / many), Version, Progress, Notes (editable, free text; kept in the batch and the QC log. The studio tracker has no Notes column, 2026-09-23).

- **The In/Out display toggle in the batch bar has three states, not two: `Frames`, `Source TC`, `Record TC`.** It sets what the In and Out cells show as their primary value for the whole list, and it sets how a typed timecode is interpreted (source or record) when either TC state is selected.
- **`Frames` is the default.** The frame number is what the model actually holds: frame math is integer throughout, In and Out *are* frame numbers, the QC rules quote them, the delivered EXR sequence is numbered by them, and the viewers step by them. Timecode is derived at the boundary and never stored. Opening on the derived value would show the editor a translation of the thing they are about to edit rather than the thing itself. The choice is remembered per batch, so an editor who works in source TC sets it once.
- Secondary line: whichever representation is not primary sits under it in smaller text, so nothing is ever hidden, only demoted. In `Frames` the secondary is source TC; in either TC state it is the source frame number. Row height accommodates two lines.
- The editor reads frames and timecode at different moments, which is why frames is a first-class state of this control rather than only the secondary line: a frame number is what gets typed into the In/Out cells and what a VFX vendor quotes back, and a timecode is what the AD and the edit talk in. Section 5 accepts both as input whatever this is set to.
- Turnover group headers are rows in the same view (QTreeView with a flat two-level model), collapsible, showing counts and aggregate status.
- Sorting is fixed to the metadata CSV's row order within a turnover. A search box filters rows by shot code substring.

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

## 6.1 Log tab

The second tab of the same dock, built in M5.8.2 against PRD FR-13. Table: time, level, shot, message, over a filter bar of a minimum level, a search box and a "Selected row only" tick.

- **The message is never abbreviated and never re-wrapped**, and Ctrl+C copies the selected lines. CLAUDE.md logs every ffmpeg command verbatim *so the user can reproduce a render*, and a command the editor cannot get out of the window has only half kept that promise.
- **"Selected row only" is FR-13's filter by row.** Only a line a render worker stamped carries a shot, so it hides what the window itself logged too: it answers "what happened to this shot", not "what happened while this shot was selected". It is unavailable with no selection and with a selection spanning two shots, and a selection going away unticks it rather than leaving a tick that filters nothing.
- **The panel is bounded and the file is not.** It keeps the last `MAX_LINES`; the complete record is the rotating file in `~/Library/Logs/ProIngest` (PACKAGING.md). A hidden line ages out with the rest, so a filter can never be the thing that makes the window grow.
- **It follows the tail only when it is already at the tail.** Somebody who has scrolled up is reading something.
- **Save Logs as CSV...**, at the right of the filter bar and in the File menu (2026-09-23), writes **every kept log file**, not the panel's tail, to one CSV the editor can send for diagnostics: columns Time, Level, Source, Message, File, a traceback kept inside its record's Message. It opens with ABOUT rows naming the ProIngest version, the platform, Python, the ffmpeg build and the batch, so the file says where it came from. Always enabled: it is the one action that has to work when nothing else does.

## 6.2 Deliverables tab

The third tab of the same dock, built 2026-09-17 against section 1's layout, which had listed it
from the start. Table, for the **selected rows**: shot, deliverable name, kind, resolution,
version, status, frames, size, the rule IDs it failed, and the path. Read only, like the metadata
pane: a deliverable is written by a run and by nothing else.

- **It answers what the list and the Issues dock do not.** The Progress column says how many of
  a row's outputs have landed and the dock says which failed a check; this says *what* a row
  delivers, where each one went and at which version, which is the question somebody asks
  before opening a Finder window.
- **Double-click opens the folder the file is in.** A path in a table is something a person can
  read and cannot type.
- **It is redrawn with the metadata pane**, from the same selection and for the same reasons,
  so a finished run reaches it the moment the statuses are written back. It is not redrawn on
  the run's five-a-second timer: a status of `rendering` appears on the next selection change or
  when the run ends, and the row's own bar is the live surface.
- **A selected shot with nothing planned says so** in one line, so an empty table under a shot
  that has never run reads as not yet rather than as broken.

## 7. Run and progress

- Run opens no dialog if the delivery root is set; otherwise it prompts once.
- Each row shows a slim progress bar in the Progress column with job count (e.g. 3/5).
- Status bar shows overall percent, jobs running, throughput (frames/s), and ETA.
- Stop finishes in-flight frames, discards `.part` outputs, and leaves rows in their previous state.
- On completion a non-modal banner above the list reads "Batch complete: 27 done, 1 failed, 2 skipped. Exports written to ...". Click opens the folder.
- **A run with anything to fix does not start** (2026-09-23, D8). Run opens one dialog listing every must-fix with where it is - the batch, a turnover folder, or a clip - capped at twenty and pointing at the Issues dock for the rest, and says to correct the folder, press Scan and run. The held-back turnover of 2026-09-17 is gone: one turnover waiting on a fix holds the batch.

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

Built in M5.7.2. What that settled, beyond the layout:

- **Settings opens with no batch**, because it is where the thresholds a *new* batch starts from are set. It is the one toolbar action that does not wait for one.
- **The thresholds live in two places on purpose.** The app settings hold the defaults and a batch takes its own copy the moment it is created, for the reason section 13 gives for the two roots: what a delivery was checked against is a record of that work, so changing the defaults next month must not silently re-judge a batch that shipped last week. Apply writes both when a batch is open.
- **A value that will not parse changes nothing**, rather than being corrected to something plausible. Same rule as section 5's In and Out: a resolution typed as `3840` is somebody part way through typing.
- **A section with nothing behind it yet is listed and disabled**, and its page says what it is waiting on. Same rule as the toolbar in section 1. **Every section is live as of M5.12**; the rule stays because it is how the page was built and how the next section will arrive.
- **Advanced went live in M5.8.3**: the log level, the ffmpeg override, and a read-only line naming the log file. Both editable values are process wide rather than per batch, both take effect the moment they are applied, and both reach a render's worker processes when the next run starts them - a worker is told at its initialiser (`core/render.execute`), so a change made mid-run applies from the run after. The ffmpeg override takes the folder or the binary, and **a path that is not there is an error rather than a fallback**: an override quietly ignored is a render done with the wrong build of ffmpeg.
- **Output went live in M5.12**, last, because both its values are applied inside a render's worker processes and had to be able to get there first. They travel on the channel Advanced built, at the worker's initialiser, so a change reaches the next run rather than one already going. Reference quality is the x264 rate factor, bounded 0 to 51 by what the encoder accepts; the preset stays at `slow` and is not editable. EXR compression level is the DWAA level. **Both are pinned by the spec** (`COLOR_AND_FORMAT.md` section 3: CRF 18, DWAA 45) and the page opens on those values, read from `core/ffmpeg.py` and `core/exr.py` rather than typed in a second time: moving either is a decision about a delivery rather than a preference, and each field's help says what the spec is so the person moving it knows what they are leaving.
- **The Colour section carries no source encoding value and no mode** (2026-09-12): the encoding is a per clip fact. The ACES config, the output transform and the input transform table are shown **read only**, read from `core/color.py` rather than copied, because they are pinned by spec (OQ-29) and an override has nowhere to travel to yet. The EDL is not chosen here either: it is the one in the turnover folder, read at every scan (OQ-74), and the turnover records which file it read (`Turnover.color_session_edl`).

## 10. Empty and first-run states

- No batch open: centered text "New batch or open one", with the two buttons.
- **New batch opens the Add Turnover chooser straight away** (2026-09-17). A new batch has
  exactly one next step, and a second empty screen with the button for it somewhere in the
  toolbar read as the tool waiting for nothing. Cancelling the chooser lands on the next state.
- Batch with no turnovers: "Add a turnover folder to begin", with an Add Turnover button under
  it that follows the toolbar action.
- After Scan with zero rows: "No clips found in timeline" plus a link to the Issues dock. The
  same button stays under it.

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
editor works with (shot code, In, Out, duration, max available, audio).
Repeating them here would waste the space and give the editor two places to read the same
number. The pane exists for the rest: codec, pixel format, start timecode, file size,
turnover details, and the paths themselves.

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
| Identity | source file name, `Shot` and `Shot Type` as the metadata carried them, shot code (and whether it is an editor override), show, shot number, element type and index, reference-still type and index, turnover id |
| Source media | path, codec, pixel format, resolution, single file or image sequence, sequence frame range and padding, frame count, first frame number, start timecode, file size, modified time |
| Frame rate | the project rate, 24, asserted rather than read and labelled "Timeline rate"; the rate the file is conformed to when it differs; the rate stated by the media; and an explicit disagreement note when they differ. QC-026 is the rule |
| Range | record In/Out, source In/Out in frames and timecode, turnover snapshot In/Out, current In/Out, duration, max available out, and whether the editor has moved it off the snapshot (QC-035) |
| Audio | path, sample rate, channels, bit depth, duration in samples and in frames, and the sync difference against the video range (QC-043) |
| Colour | source encoding as the shooter wrote it (`Gamma Notes` + `Color Space Notes`), which carrier named it, and the CDL from the row's EDL event. **Added 2026-09-12 with M5.6**, corrected 2026-09-21 when per-shot grade files were removed: the encoding is shown verbatim because the string is what has to be corrected when it is wrong |
| Turnover | number, date, shooter, folder, EDL, metadata CSV, timeline start. Shown alone when a turnover group header is the selection |
| QC | count by severity with the rule IDs, each clicking through to that row in the Issues dock. **Built across the whole selection rather than merged field by field**, unlike every other section: two rows with different problems agree on nothing, so a merge would reduce this to "mixed", which is the one answer that helps nobody |

There is **no Side files section** since 2026-09-22: HDRI and camData carry no `Shot Type`, so
the tool reads neither and the pane has nothing to show for them.

### 12.3 Empty and edge states

- **Nothing selected**: "Select a shot to see its metadata". Not a blank panel.
- **More than one row selected**: show only the fields the selection agrees on, with a count
  ("12 shots selected"). Fields that differ read "mixed". This is what makes the pane useful
  for spotting one clip at the wrong resolution in a turnover of thirty.
- **Turnover header selected**: the Turnover section alone. The turnover's own results are
  fields inside it rather than a QC section beside it, so "alone" stays literally true; the
  rows' results are not rolled up here because the group header in the list already counts
  them and the Issues dock lists every one.
- **Media unresolved** (QC-012, QC-013): the Identity and Range sections still populate from
  the CSV and the EDL, and Source media reads why it is missing rather than vanishing. An
  unresolved row is exactly when someone wants to see which file the CSV named.
  **Where that sentence comes from** (M5.6): the pane reads the QC result rather than
  re-deriving anything, because the scan is the only thing that knows what it looked for.
  Nothing stores the named file once a row has no media, so **QC-012's message names it**,
  which is the one record of what the CSV asked for.
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
| Delivery root | batch bar, click the path | Where `<show>/<shot>/` is written, and where the tracker and QC spreadsheets land. **Drawn amber while there is none** (2026-09-17): it is the one thing Run stops to ask about, so it reads as unfinished before then |

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

## 15. Scan, re-scan and a moved turnover (2026-09-23)

**Ingest Colour Session is gone** (review 2026-09-23, chunk E). The cut and the grade are read at
scan from the EDL in the turnover folder, and a correction reaches the batch the way D8 says: the
editor drops the fixed EDL, CSV or clip into the folder and re-scans.

- **Scan re-scans every turnover in the batch.** Right-clicking a turnover's header offers
  **Re-scan** for that one turnover and **New Folder Location...** for one that has moved (D16).
- **What the editor did is carried over by File Name** (`scan.carry_over`), in CSV order, so a
  clip used twice pairs first with first: a trim the editor made, the shot code correction, the
  skip and its reason, the notes, and the delivered state. A trim never made follows the new EDL.
  **QC-070** says so when the EDL or CSV changed since the last scan.
- **A re-scan that finds no rows keeps the rows it had**, and the turnover's QC says why (QC-001,
  QC-002): the editor's work waits for the scan that follows the fix.
- **A moved turnover says so on its header when the batch is opened** (QC-069, an error that
  holds it back), and New Folder Location re-scans it from where it went.

## 15b. A shot's right-click (D11, D12)

- **Reset**, on a shot with a failed output: the editor has fixed the cause, and what failed
  runs again at the same version on the next Run. Greyed when nothing failed.
- **Re-run**, on a shot that has been planned: the next Run renders it again, whole, at the
  next version. A complete shot is otherwise left alone (QC-061).

## 15a. Locks (D15)

**While a scan or a run has the batch in hand, nothing may change it.** The list refuses every
edit and its right-click entries are greyed; New, Open, Settings, Skip, Add Turnover, Scan and the
delivery root wait. An edit made under a run changed the reports without changing the render (F14),
and New or Open under a scan took its result into the other batch (F13). A run's own disk work -
the pre-flight, the plan and the two spreadsheets - runs off the UI thread (`ui/background.py`)
under the same lock, so a slow mount is a busy window rather than a frozen one (F17).
