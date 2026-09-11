# ProIngest PRD v01

Working name: ProIngest. Version target: v01 (macOS, Apple Silicon). v02 items are listed at the end and must not block v01.

## 1. Problem

A small VFX studio receives shot turnovers from three shooters. Each turnover is a DaVinci Resolve project consolidated to HQ media, one clip per shot with handles, plus a timeline export. Today the VFX editor conforms the stringout, renames and transcodes every deliverable by hand, and checks them by eye. This is slow, error prone, and the naming spec is strict.

ProIngest turns that into: point at the turnover folder, load the timeline, review and adjust In/Out with the AD and supervisor in the same list, press Run, get correctly named and verified deliverables plus tracker and QC spreadsheets.

## 2. Users

- VFX Editor (primary). Runs the tool, owns the batch.
- AD / VFX Supervisor. Sits with the editor during review; does not operate the tool.
- Shooters (indirect). Their output must match `docs/NAMING_SPEC.md`; the tool tells the editor when it does not.

Single user, single machine. No server, no multi-user state.

## 3. Goals and non-goals

Goals
- Zero hand-naming of deliverables.
- Every deliverable verified before it is reported as done.
- Review notes captured in the same list used to run the batch, keyboard driven.
- Clean, modern, dark UI at the level of a commercial tool.
- Installs from a single macOS disk image with no Python setup.

Non-goals for v01
- Color transforms of plates. Raw output is never transformed; the only transfer the tool ever applies is on the reference encodes, and only when the source is scene linear (see `docs/COLOR_AND_FORMAT.md` section 1).
- Lidar deliverables.
- Frame viewer (v02).
- Any Google Drive API use. The Drive mount is a normal mounted folder.
- Windows build (design for it, do not ship it).

## 4. Inputs

Per turnover, in one folder on the Google Drive mount (structure configurable in Settings, see `docs/OPEN_QUESTIONS.md` OQ-1):

- One `.otio` exported from Resolve (required). CMX3600 `.edl` accepted as fallback with reduced validation.
- Consolidated media: one file or image sequence per timeline clip, with the sRGB curve baked in today and scene linear sRGB expected later (`docs/COLOR_AND_FORMAT.md` section 1), with extra frames beyond the timeline In/Out (handles are already in the timeline range; the extra frames only exist so Out can be extended).
- Audio clips synced on the timeline, referenced by the OTIO on audio tracks.
- Optional per shot: HDRI `.exr`, camera data `.txt`/`.rtf`, lens grid `.png`, BTS stills, reference stills (color chart, mirror ball, grey ball, size reference).

Timeline clip names are the contract: `MELT0001_pl01` style (see `docs/NAMING_SPEC.md`). The tool derives every output name from the clip name.

## 5. Outputs

Per shot, into a delivery root the user chooses (default proposed layout in `docs/NAMING_SPEC.md` section 5):

- 4k and HD raw EXR sequences (DWAA 45, start frame 1001) in their own subfolders
- 4k and HD H.264 reference mp4s
- Audio wav for plate clips (as delivered, 16 bit PCM)
- Copied and renamed HDRI, lens grid, BTS, reference stills where present
- One turnover stringout mp4 (1920x1080, H.264) with burn-ins
- `shot_tracker.xlsx` for paste into the studio tracker (columns supplied by studio, OQ-2)
- `qc_ingest_log.xlsx` with one row per deliverable, rule results, and turnover-vs-final In/Out diff

## 6. User flow

1. New Batch or Open Batch (`.pibatch` JSON).
2. Add Turnover: pick the turnover folder, tool finds the `.otio` (or user picks it). Repeat for up to N turnovers in a batch.
3. Scan. Tool parses the timeline, matches each clip to media, probes media with ffprobe, resolves audio, discovers side files, runs pre-flight QC. List populates, grouped by turnover. Problem rows are colored with a tooltip and a QC panel entry.
4. Review. Editor works down the list with the keyboard, adjusting In/Out, fixing names, marking clips as skipped. Duration and validation update live. Selecting a row fills the metadata pane on the right with everything known about that clip (FR-14), which is what the AD and supervisor read over the editor's shoulder. Everything autosaves to the batch file.
5. Run. Editor picks the delivery root (remembered per batch), presses Run. Progress per row and overall. Rows go green when all their deliverables pass post-render QC.
6. Export. Tracker and QC spreadsheets are written to the delivery root. Editor can re-open the batch later and re-run only what failed.

## 7. Functional requirements

FR-1 Timeline import
- Parse `.otio` with `opentimelineio`. Support Resolve output from 18.5 onward.
- Iterate all video tracks. Each `Clip` becomes a shot candidate. Gaps and transitions are ignored. A clip on a track other than V1 is still a shot.
- Record range = clip range in the timeline. Source range = clip `source_range` relative to the media's start timecode.
- Audio: for each video clip, find audio clips on any audio track whose record range overlaps the video clip's record range. Associate them (usually one). Report zero or more than one as QC results.
- EDL fallback via otio's `cmx_3600` adapter. Clip name comes from `FROM CLIP NAME` comments. No media paths, so matching is by filename search in the turnover folder (FR-2). Audio association is not available from EDL; the tool searches for a wav with the same base name.

FR-2 Media resolution
- Prefer the OTIO `media_reference.target_url`. Rewrite Resolve paths to the local mount using a configurable path map (e.g. `/Volumes/GoogleDrive/...` to `~/Library/CloudStorage/GoogleDrive-<account>/...`). On a macOS-to-macOS turnover the map is often empty, because Resolve wrote paths this machine can already resolve; it earns its keep when the shooter's mount differs from the editor's.
- If the referenced file is missing, search the turnover folder recursively for a file or image sequence whose base name matches the clip name. Exactly one hit resolves silently; zero or many is a QC error on the row.
- Image sequences are detected by the `name.####.ext` pattern and treated as one media item with a frame range.

FR-3 Probing
- ffprobe every resolved media item once: codec, pixel format, width, height, frame rate, duration in frames, start timecode, audio streams. Cache in the batch file keyed by path, size, and mtime.

FR-4 Shot model
Each row holds: turnover id, clip name (parsed into show, shot number, type, index), source path, source fps, source resolution, source frame count and start TC, record In/Out TC, source In/Out (frames and TC), turnover snapshot of In/Out (immutable after scan), current In/Out, duration, max available Out, audio path, side files, skip flag, per-deliverable status, QC results.

FR-5 Editing
- Editable fields: Shot Code, In, Out, Notes. No handle controls on rows: handles are already inside the timeline range by convention, and the editor extends a clip by moving Out. A Settings value "expected handle frames" exists only for the QC-030 warning.
- In/Out accept four formats, auto-detected: source TC `HH:MM:SS:FF`, record TC (when the display toggle is on record), absolute source frame number, relative offset `+12` / `-8` applied to the current value.
- Duration recalculates on every edit. Max Available shows the last usable source frame.
- Shot Code edits are validated against the naming regex live. A renamed shot code is a diff entry in the QC log.
- Skip flag excludes the row from render and marks it in the QC log with a required reason field.

FR-6 Validation (pre-flight)
All rules in `docs/QC_RULES.md` with prefix `QC-0xx`. Warnings allow Run. Errors block the row (row is auto-skipped with reason "blocked by QC-nnn") but not the batch.

FR-7 Render
- Per row, generate a plan of deliverable jobs from the clip type table in `docs/NAMING_SPEC.md`.
- Jobs execute in a process pool. Concurrency default = physical cores / 2, editable. EXR jobs are CPU and IO heavy; refs are ffmpeg heavy. The scheduler interleaves them.
- Every job writes to `<final>.part` (files) or `<folder>.part/` (sequences) then renames on success.
- Versioning: before writing, scan the destination for existing versions of the same deliverable and use max+1. All deliverables of one shot in one run share the same version number. If a shot already has a complete, QC-passing set at the highest version and "Force re-render" is off, skip with status "Exists".
- Hardware encoding (`h264_videotoolbox`) is optional: detected at startup, used for H.264 when available and enabled in Settings. Output must be visually equivalent; quality mapping in `docs/COLOR_AND_FORMAT.md`. NVENC was the Windows equivalent and does not exist on macOS.

FR-8 Post-render QC
Rules `QC-1xx` in `docs/QC_RULES.md`: frame count, first/last frame numbers, resolution, fps, EXR header integrity, checksum of every frame written, mp4 duration, audio duration.

FR-9 Stringout
- One per turnover. Clips in timeline order using the current (edited) In/Out, no slate.
- 1920x1080, H.264, burn-ins per `docs/UI_SPEC.md` section 8 (shot code, source filename, fps, resolution, source TC, record TC, duration, LUT/color label).
- Named `turnover[###]_[MM_DD_YYYY]_[firstnamelastname]_v01.mp4`. Turnover number, date, and shooter name are turnover-level fields filled at Add Turnover time, prefilled from the folder name when it matches the pattern.

FR-10 Exports
- `shot_tracker.xlsx` via openpyxl. Column layout loaded from a template file in Settings so the studio can change it without a code change.
- `qc_ingest_log.xlsx` with sheets: Summary, Shots (turnover vs final In/Out, duration, shot code changes, skip reasons), Deliverables (one row each with path, version, size, checksum, every QC rule result), Side Files, Camera Data (parsed key/values from camData files).

FR-11 Batch file
- `.pibatch` JSON, schema versioned. Contains everything needed to reopen: turnovers, rows, snapshots, edits, probe cache, delivery root, render status, settings overrides. Autosave on every edit (debounced 500 ms). Backup copy kept on open.

FR-12 Settings page
Sections: General (delivery root default, path map, concurrency, GPU), Rules (min/max duration frames, expected handle frames, allowed fps, expected resolutions), Naming (show prefix regex, type table overrides), Output (mp4 quality, EXR compression level, stringout burn-in toggles), Exports (tracker template path), Advanced (ffmpeg path override, log level).

FR-13 Logging
- Rotating log file in the app data folder. Every ffmpeg command line logged. In-app log panel with filter by row.

FR-14 Metadata pane
- A read-only pane to the right of the shot list. Selecting a row shows everything known about that clip: identity, source media, frame rate, ranges, audio, side files, turnover, and a QC summary. Full field list and behaviour in `docs/UI_SPEC.md` section 12.
- It shows what the list has no column for (codec, pixel format, start timecode, file size, parsed camera data, the paths themselves), rather than repeating the columns.
- Read only. The list owns every edit per FR-5, so the pane never writes to the model and never takes keyboard focus. Ctrl+I toggles it.
- Multi-selection shows the fields the selection agrees on and marks the rest "mixed", which is how an editor spots one clip at the wrong resolution in a turnover of thirty.
- Values are individually copyable, paths and checksums especially.
- Primarily serves the AD and VFX supervisor described in section 2, who sit with the editor during review and read rather than operate. Parsed camera data (OQ-11) is the only place lens, filter and body ever surface in the UI.

## 8. Non-functional requirements

- 100 shots per batch, 30 per turnover, must scan in under 60 seconds from the Drive mount with warm cache.
- UI stays responsive during render; list edits allowed on rows not currently rendering.
- Crash safety: reopening a batch after a crash shows accurate per-deliverable state derived from the filesystem, not just the last saved status.
- Installer under 300 MB. First launch under 5 seconds on a typical workstation.
- Works with the Google Drive desktop client's streaming mode (files may be placeholders until read). The scan must trigger downloads only for files it actually needs to probe, and show download-wait state.

## 9. Milestones for implementation

M1 Core: OTIO parse, clip name parse, media resolution, ffprobe cache, shot model, batch JSON. Headless CLI `proingest scan <folder>` prints the row table. Tests.
M2 Naming and planning: deliverable plan per clip type, versioning, path layout. Tests against the spec examples.
M3 Render: EXR writer, mp4 encoder, audio copy, side file copy, atomic writes, pool, progress. CLI `proingest run <batch>`.
M4 QC: all rules, both phases, xlsx exports. CLI `proingest qc <batch>`.
M5 UI: main window, list view with keyboard model, metadata pane, validation coloring, settings page, log panel, batch open/save.
M6 Stringout with burn-ins.
M7 Packaging: PyInstaller `.app`, disk image, bundled ffmpeg, first-run experience, icon.
M8 Polish pass against `docs/UI_SPEC.md`, performance on a real turnover, docs.

## 10. v02 backlog (do not build in v01, but do not design against it)

- Frame viewer: two image panes (In, Out) bound to the selected row, updating live as In/Out are typed; frame forward/back buttons under each pane move the playhead and write back to the field. Requires a decoded frame cache per row.
- Optional color transform on ingest (OCIO).
- Burn-ins on reference mp4s.
- Windows build.
- Google Apps Script hyperlink export for the tracker.
