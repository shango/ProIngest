# ProIngest PRD v01

Working name: ProIngest. Version target: v01 (macOS, Apple Silicon). v02 items are listed at the end and must not block v01.

## 1. Problem

A small VFX studio receives shot turnovers from three shooters. Each turnover is a DaVinci Resolve project consolidated to HQ media, one clip per shot with handles, plus a timeline export. Today the VFX editor conforms the stringout, renames and transcodes every deliverable by hand, and checks them by eye. This is slow, error prone, and the naming spec is strict.

ProIngest turns that into: point at the turnover folder, load the timeline, review and adjust In/Out with the AD and supervisor in the same list, press Run, get correctly named and verified deliverables plus tracker and QC spreadsheets.

## 2. Users

- VFX Editor (primary). Runs the tool, owns the batch.
- AD / VFX Supervisor. Sits with the editor during review; does not operate the tool.
- Colourist. Runs the final colour session in Resolve with the AD, and exports the updated final
  EDL and the per shot CLF the tool ingests (`docs/COLOR_AND_FORMAT.md` section 1). Does not operate
  the tool, but nothing final renders until their session has happened.
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
- Authoring colour. The tool applies colour, it never invents any: the look is decided in the AD meeting, built in the colour session, and arrives as one CLF per shot alongside its final EDL. **There are no colour controls in the tool.** An earlier version of this PRD specified four per clip sliders for the AD's notes; they are removed, because two places to author a grade is one place too many and the Resolve session is the one that has the AD in the room.
- Lidar deliverables.
- Lens grid delivery. The tool reports whether a turnover has one; moving and renaming it is manual in v01 (OQ-20).
- Frame viewer. Specified on 2026-09-11 as three steppable viewers, removed 2026-09-12, and back in the v02 backlog where it started (FR-16).
- Any Google Drive API use. The Drive mount is a normal mounted folder.
- Windows build (design for it, do not ship it). v01 is Apple Silicon only, and a Windows 11 build is a v02 intention (OQ-24).

## 4. Inputs

Per turnover, in one folder on the Google Drive mount (structure configurable in Settings, see `docs/OPEN_QUESTIONS.md` OQ-1):

- One `.otio` exported from Resolve (required), with an `.edl` accepted as a reduced fallback. It conforms the timeline: clip names, ranges and audio association. **The colour session supersedes it** with an updated final EDL (below), which is the conform the run actually uses.
- Consolidated media: one file or image sequence per timeline clip, **ProRes 4444 in the studio standard log encoding**, the same encoding on every file whatever anybody shot on (`docs/COLOR_AND_FORMAT.md` sections 1 and 2, OQ-39), with extra frames beyond the timeline In/Out (handles are already in the timeline range; the extra frames only exist so Out can be extended).
- **The colour session package, required before anything final renders** (`docs/COLOR_AND_FORMAT.md` section 1): the **updated final EDL**, carrying timecode, shot identity, the approved In/Out and the CDL as `*ASC_SOP` / `*ASC_SAT` lines, and **a `.clf` per shot**, which is the transform the tool actually applies (OQ-33 covers how a CLF is matched to a shot). Scan and review work without it; Run does not.
- The shooter's offline **string-out and CDL** may also be present. They are a record of intent and the starting point for the colour session, and both are superseded by its final versions. **The tool reads neither and renders from neither.**
- Audio clips synced on the timeline, referenced by the OTIO on audio tracks.
- Optional per shot: HDRI `.exr`, camera data `.txt`/`.rtf`, lens grid `.png`, BTS stills, reference stills (color chart, mirror ball, grey ball, size reference).

Timeline clip names are the contract: `MELT0001_pl01` style (see `docs/NAMING_SPEC.md`). The tool derives every output name from the clip name.

## 5. Outputs

Per shot, into a delivery root the user chooses (default proposed layout in `docs/NAMING_SPEC.md` section 5):

- 4k and HD raw EXR sequences (DWAA 45, start frame 1001) in their own subfolders. **ACEScg, scene linear, graded with the shot's CLF**, with the source encoding, the CLF name and hash, and the CDL as a readable record, in the header so the grade in the pixels can be identified later without the session
- 4k and HD H.264 reference mp4s, sRGB display, the same CLF plus the ACES output transform
- Audio wav for plate clips (as delivered, 16 bit PCM)
- Copied and renamed HDRI, BTS, reference stills where present. **Not the lens grid**: it arrives as a folder in the turnover and the editor moves and renames it by hand in v01 (OQ-20)
- `shot_tracker.xlsx` for paste into the studio tracker (columns supplied by studio, OQ-2)
- `qc_ingest_log.xlsx` with one row per deliverable, rule results, and turnover-vs-final In/Out diff

## 6. User flow

1. New Batch or Open Batch (`.pibatch` JSON).
2. Add Turnover: pick the turnover folder, tool finds the `.otio` (or user picks it). The chooser opens at the batch's source root and picking outside it just moves the root. Repeat for up to N turnovers in a batch.
3. Scan. Tool parses the timeline, matches each clip to media, probes media with ffprobe, resolves audio, discovers side files, runs pre-flight QC. List populates, grouped by turnover. Problem rows are colored with a tooltip and a QC panel entry.
4. Ingest the colour session. Editor points at Ben's updated final EDL. The tool matches each event to a row, takes **its In/Out as the approved edit**, reads its CDL, and pairs the row with its CLF (OQ-30, OQ-33). Rows it could not match cannot render (QC-008, QC-009). **This normally comes before review**, because it is what the review is reviewing; doing it after a trim overwrites that trim and says so (FR-5).
5. Review. Editor works down the list with the keyboard, checking the rows, fixing names, marking clips as skipped, and making the occasional one-off trim that is not worth a trip back to Resolve (FR-5). Duration and validation update live. Selecting a row fills the metadata pane on the right with everything known about that clip (FR-14). Everything autosaves to the batch file.
6. Run. Editor picks the delivery root (remembered per batch, the second of the two folder choosers in `docs/UI_SPEC.md` section 13), presses Run. Progress per row and overall. Rows go green when all their deliverables pass post-render QC.
7. Export. Tracker and QC spreadsheets are written to the delivery root. Editor can re-open the batch later and re-run only what failed.

## 7. Functional requirements

FR-1 Timeline import
- Parse `.otio` with `opentimelineio`. Support Resolve output from 18.5 onward.
- Iterate all video tracks. Each `Clip` becomes a shot candidate. Gaps and transitions are ignored. A clip on a track other than V1 is still a shot.
- Record range = clip range in the timeline. Source range = clip `source_range` relative to the media's start timecode.
- Audio: for each video clip, find audio clips on any audio track whose record range overlaps the video clip's record range. Associate them (usually one). Report zero or more than one as QC results.
- EDL fallback via otio's `cmx_3600` adapter. Clip name comes from `FROM CLIP NAME` comments. No media paths, so matching is by filename search in the turnover folder (FR-2). Audio association is not available from EDL; the tool searches for a wav with the same base name.
- **The colour session's final EDL is the conform and it is the one that counts.** It carries timecode, shot identity and the approved In/Out from Ben and the AD's trims, plus the CDL as `*ASC_SOP` / `*ASC_SAT` comment lines, because Resolve exports no `.cdl` or `.ccc` file. The shooters' own EDL and CDL are superseded by it and the tool reads neither. Matching an event to a row is OQ-30.

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
- **Trimming in the tool is an exception path, not the main way a cut is decided.** In and Out arrive already approved: Ben and the AD set them in the colour session and they come in on its final EDL (FR-15). The tool keeps its In/Out editing for **the quick one-off**, the trim that would otherwise mean asking Ben to reopen Resolve and export a new EDL for one shot. That is worth having and it is not a licence to re-edit a turnover.
- **A trim in the tool is a deviation from an approved edit, and is reported as one.** QC-045, warning. QC-035 keeps its own meaning, which is the difference between what the shooters delivered and what is being rendered, and most of that difference is now Ben's own work rather than the editor's.
- **Trimming does not invalidate the grade.** A CLF is one static transform for the whole shot, not an animated one, so moving In or Out carries it unchanged. The caveat, which is why this is a one-off facility: **extending into the handles applies the approved grade to frames Ben never looked at.** Usually fine for a static primary, and worth knowing before extending a long way.
- **The list owns every edit.** There is no second surface that writes to a row: no viewers, no colour controls, no editable metadata pane.

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

FR-9 Stringout: **dropped from v01, 2026-09-12.**
- The tool does not build a stringout. The colour session exports a reference QT with the look and burn-ins, and that is the stringout. Two tools building the same artifact from the same decisions is one too many, and the one with the colourist in front of it wins.
- What went with it: milestone M6, `core/stringout.py`, the burn-in specification in `docs/UI_SPEC.md` section 8, QC-140 and QC-141, and OQ-12 and OQ-15.
- **What this gives up, recorded so it is a decision and not an oversight**: the tool's stringout would have been the only one cut to the **edited** In/Out. The session's QT and the shooters' offline are both cut to the turnover as delivered. If it turns out the vendor needs a stringout that reflects the review session, this comes back, and it comes back as a milestone rather than a patch.

FR-10 Exports
- `shot_tracker.xlsx` via openpyxl. Column layout loaded from a template file in Settings so the studio can change it without a code change.
- `qc_ingest_log.xlsx` with sheets: Summary, Shots (**three In/Out columns: as the shooters delivered it, as Ben approved it, as it rendered**, plus duration, shot code changes, skip reasons), Deliverables (one row each with path, version, size, checksum, every QC rule result), Side Files, Camera Data (parsed key/values from camData files).

FR-11 Batch file
- `.pibatch` JSON, schema versioned. Contains everything needed to reopen: turnovers, rows, snapshots, edits, probe cache, delivery root, render status, settings overrides. Autosave on every edit (debounced 500 ms). Backup copy kept on open.

FR-12 Settings page
Sections: General (delivery root default, path map, concurrency, GPU), Rules (min/max duration frames, expected handle frames, allowed fps, expected resolutions), **Colour (colour session package location, studio standard source encoding, ACES config version, output transform)**, Naming (show prefix regex, type table overrides), Output (mp4 quality, EXR compression level), Exports (tracker template path), Advanced (ffmpeg path override, OCIO config override, log level).

FR-13 Logging
- Rotating log file in the app data folder. Every ffmpeg command line logged. In-app log panel with filter by row.

FR-14 Metadata pane
- A read-only pane to the right of the shot list. Selecting a row shows everything known about that clip: identity, source media, frame rate, ranges, audio, side files, turnover, and a QC summary. Full field list and behaviour in `docs/UI_SPEC.md` section 12.
- It shows what the list has no column for (codec, pixel format, start timecode, file size, parsed camera data, the paths themselves), rather than repeating the columns.
- Read only. The list owns every edit per FR-5, so the pane never writes to the model and never takes keyboard focus. Ctrl+I toggles it.
- Multi-selection shows the fields the selection agrees on and marks the rest "mixed", which is how an editor spots one clip at the wrong resolution in a turnover of thirty.
- Values are individually copyable, paths and checksums especially.
- Primarily serves the AD and VFX supervisor described in section 2, who sit with the editor during review and read rather than operate. Parsed camera data (OQ-11) is the only place lens, filter and body ever surface in the UI.

FR-15 Colour pipeline
- Working space is **ACEScg**. Every deliverable is graded, with the approved look applied from the shot's **CLF**. The CDL from the final EDL is carried and recorded, never applied: **the CLF is what is in the pixels.** `docs/COLOR_AND_FORMAT.md` section 1 says why both exist. Full policy, both branches and the reasoning are in `docs/COLOR_AND_FORMAT.md` section 1, which is the spec. This entry records that the pipeline exists and what it owes.
- Transforms come from **OpenColorIO** as a single `GroupTransform` per shot, interpolated **tetrahedrally**, using a pinned ACES 1.3 built-in config so no config files ship and no dependency bump changes what a reference looks like (OQ-29). Curves and matrices are never hand written.
- Per shot the chain is: decode to float, **override the container's colour tags** with the studio standard from Settings and confirm range, the **input transform** to ACEScct (one constant, identity if the standard is ACEScct itself), then the shot's **CLF**.
- The plate branch converts to linear ACEScg and resizes unbounded in numpy. The view branch stays in ACEScct and collapses the CLF and the ACES output transform into **one 3D LUT per shot**, generated in core, applied by ffmpeg `lut3d` for the reference and in numpy by the viewers. One definition, two consumers, so they cannot disagree.
- The EXR header records the source encoding, the **CLF name and hash** (which identifies the grade exactly), and the CDL as a readable approximation of it, so a delivered plate can be understood by someone with neither the session nor an OCIO install.
- **A CLF that contains a display rendering is refused**, QC-039: it would produce a display referred file that claims to be scene linear, and nothing downstream would notice until the comp was wrong.
- A row with no CLF cannot render. QC-009, error, not a warning: an ungraded plate is not a lesser deliverable here, it is the wrong pixels under the right filename.

FR-16 Viewers: **dropped from v01, 2026-09-12.**
- There are no image viewers in the tool. The three steppable In / Center / Out viewers specified on 2026-09-11 are removed, along with the four colour controls that were specified beside them and already removed earlier the same day.
- A frame viewer returns to the v02 backlog where it started (section 10), and section 3 lists it as a non-goal again.
- What went with it: `docs/UI_SPEC.md` section 14, `core/preview.py` and M4.5.5, and the single frame fetch and cache they needed. In/Out are edited by typing, per FR-5, which is now the only way a row is edited at all.
- **What this gives up**: an editor judging a cut point reads frame numbers and timecode rather than pictures. That is what the review session with the AD was for, and that session now happens in Resolve with Ben, where there is a proper viewer and a calibrated monitor.

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
M4.5 Colour pipeline, core only: OCIO wired in, the final EDL's In/Out and CDL read and matched per row, the CLF matched and loaded, input transform plus CLF as one GroupTransform, the viewing LUT. Reopens M3's render for the plate/view split. No Qt, testable headless, which is what makes M5's viewers a thin layer rather than a second implementation.
M5 UI: main window, list view with keyboard model, metadata pane, validation coloring, settings page, log panel, batch open/save.
M6 **Dropped 2026-09-12.** Was: stringout with burn-ins. The colour session exports it instead (FR-9). The number is not reused.
M7 Packaging: PyInstaller `.app`, disk image, bundled ffmpeg, first-run experience, icon.
M8 Polish pass against `docs/UI_SPEC.md`, performance on a real turnover, docs.

## 10. v02 backlog (do not build in v01, but do not design against it)

- Frame viewer. Removed from v01 twice now, which is worth noting before anyone adds it a third time: it was a v02 item from the start, was promoted into v01 on 2026-09-11 as three steppable viewers, and was removed again on 2026-09-12 because the review that needed pictures moved to Resolve. It needs a decoded frame cache per row and the viewing LUT that M4.5 builds anyway.
- Per shot colour controls in the tool, if the round trip through the colour session ever proves too slow for a review session. Removed from v01 deliberately (section 3).
- Burn-ins on reference mp4s.
- Windows 11 build. Intended, not committed (OQ-24).
- Google Apps Script hyperlink export for the tracker.
