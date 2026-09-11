# UI Spec

PySide6 6.7+. Dark theme in the spirit of DaVinci Resolve: near-black panels, thin 1px separators, muted grey text, one accent color for selection and primary actions, amber for warnings, red for errors, green for done. No gradients, no drop shadows on panels, no rounded cards. Density is professional, not spacious.

## 1. Layout

```
+------------------------------------------------------------------+
| Toolbar: [New] [Open] [Save]  | [Add Turnover] [Scan] [Run] [Stop] | [Export] [Settings]   |
+------------------------------------------------------------------+
| Batch bar: batch name, delivery root path (click to change), TC toggle [Source|Record], search box |
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

Nothing opens a modal during review except Settings and file dialogs.

## 2. Shot list columns

Frozen left: status dot, Shot Code (editable), Elem.
Scrolling: Source file, Res, FPS, In (editable), Out (editable), Duration, Max Avail, Audio (icon: none / one / many), Side files (icons: HDRI, camData, stills), Version, Progress, Notes (editable, free text, goes to tracker).

- **The In/Out display toggle in the batch bar has three states, not two: `Frames`, `Source TC`, `Record TC`.** It sets what the In and Out cells show as their primary value for the whole list, and it sets how a typed timecode is interpreted (source or record) when either TC state is selected.
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

## 8. Stringout burn-ins

Rendered with ffmpeg `drawtext`, monospace font bundled with the app, white text with 60% black box. Layout on 1920x1080:

- Top left: shot code, element (e.g. `MELT0001  pl01`)
- Top center: source filename
- Top right: fps, resolution (`24 fps  3840x2160`)
- Bottom left: source TC (running)
- Bottom center: record TC (running)
- Bottom right: frame `1001 + k` of duration, then color label. The label is the source color space from Settings (`sRGB display` or `scene linear sRGB`, see COLOR_AND_FORMAT section 1), or the LUT name when one is set

Each burn-in is a toggle in Settings. Text size scales with a single Settings value.

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
- **Live.** Values recompute as In/Out are typed, the same as Duration and Max Available in
  the row.
- **Collapsible sections**, each remembering its open state, and a remembered pane width.
  Both live with the rest of the window state (section 11).
- Long paths elide in the middle, never at the end: the filename is the part that identifies
  the file, and the middle of a Google Drive path is the least informative part of it.

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
| Side files | HDRI path, camData path, and the parsed camData key/values once OQ-11 is settled. This is the single most useful thing in the pane for an AD sitting with the editor, because it is the only place lens, filter and camera body ever appear |
| Turnover | number, date, shooter, folder, timeline file. Shown alone when a turnover group header is the selection |
| QC | count by severity with the rule IDs, each clicking through to that row in the Issues dock |

### 12.3 Empty and edge states

- **Nothing selected**: "Select a shot to see its metadata". Not a blank panel.
- **More than one row selected**: show only the fields the selection agrees on, with a count
  ("12 shots selected"). Fields that differ read "mixed". This is what makes the pane useful
  for spotting one clip at the wrong resolution in a turnover of thirty.
- **Turnover header selected**: the Turnover section alone.
- **Media unresolved** (QC-011, QC-012): the Identity and Range sections still populate from
  the timeline, and Source media reads why it is missing rather than vanishing. An unresolved
  row is exactly when someone wants to see what the timeline claimed the path was.
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
