# UI Spec

PySide6 6.7+. Dark theme in the spirit of DaVinci Resolve: near-black panels, thin 1px separators, muted grey text, one accent color for selection and primary actions, amber for warnings, red for errors, green for done. No gradients, no drop shadows on panels, no rounded cards. Density is professional, not spacious.

## 1. Layout

```
+------------------------------------------------------------------+
| Toolbar: [New] [Open] [Save]  | [Add Turnover] [Scan] [Run] [Stop] | [Export] [Settings]   |
+------------------------------------------------------------------+
| Batch bar: batch name, delivery root path (click to change), TC toggle [Source|Record], search box |
+------------------------------------------------------------------+
|                                                                  |
|   SHOT LIST (hero, fills the window)                             |
|                                                                  |
|   > turnover001  02_23_2026  danielluckett   28 shots  2 warn 1 err   [collapse]   |
|     MELT0001_pl01  ...                                           |
|     MELT0001_cp01  ...                                           |
|   > turnover002  ...                                             |
|                                                                  |
+------------------------------------------------------------------+
| Bottom dock (collapsible, tabs): Issues | Log | Deliverables (for selected row) |
+------------------------------------------------------------------+
| Status bar: scan/render progress bar, jobs running, ETA, GPU on/off |
+------------------------------------------------------------------+
```

The list is the whole product. Nothing opens a modal during review except Settings and file dialogs.

## 2. Shot list columns

Frozen left: status dot, Shot Code (editable), Elem.
Scrolling: Source file, Res, FPS, In (editable), Out (editable), Duration, Max Avail, Audio (icon: none / one / many), Side files (icons: HDRI, camData, stills), Version, Progress, Notes (editable, free text, goes to tracker).

- Secondary TC line: In and Out cells show the primary value (frame or TC per toggle) and the other representation in smaller secondary text underneath. Row height accommodates two lines.
- The TC toggle in the batch bar switches the whole list between Source TC and Record TC as the primary display and as the interpretation of typed TC.
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
- Ctrl+T: toggle Source/Record TC.
- Ctrl+F: focus search. Ctrl+S: save batch. Ctrl+R: run. Ctrl+.: stop.
- Typing into a selected cell starts editing immediately (no F2 required).
- Space on a group header collapses/expands.

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
- Bottom right: frame `1001 + k` of duration, then color label (`scene linear sRGB` or the LUT name from Settings)

Each burn-in is a toggle in Settings. Text size scales with a single Settings value.

## 9. Settings page

A single window with a left section list and right form, like Resolve's project settings. Sections and fields as listed in `PRD.md` FR-12. Apply/Cancel at bottom; changes to rule thresholds re-run validation on the open batch when applied.

## 10. Empty and first-run states

- No batch open: centered text "New batch or open one", with the two buttons.
- Batch with no turnovers: "Add a turnover folder to begin".
- After Scan with zero rows: "No clips found in timeline" plus a link to the Issues dock.

## 11. Windows details

- Native title bar, app icon, taskbar progress during render.
- Remembers window geometry and dock state per user.
- File dialogs default to G: if it exists.
