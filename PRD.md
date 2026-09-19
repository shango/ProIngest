# ProIngest PRD v01

Working name: ProIngest. Version target: v01 (macOS, Apple Silicon). v02 items are listed at the end and must not block v01.

## 1. Problem

A small VFX studio receives shot turnovers from three shooters. Each turnover is a DaVinci Resolve project consolidated to HQ media, one clip per shot with handles, plus a timeline export. Today the VFX editor conforms the stringout, renames and transcodes every deliverable by hand, and checks them by eye. This is slow, error prone, and the naming spec is strict.

ProIngest turns that into: point at the turnover folder, load the timeline, review and adjust In/Out with the AD and supervisor in the same list, press Run, get correctly named and verified deliverables plus tracker and QC spreadsheets.

## 2. Users

- VFX Editor (primary). Runs the tool, owns the batch.
- AD / VFX Supervisor. Sits with the editor during review; does not operate the tool.
- Colourist. Runs the final colour session in Resolve with the AD, and exports the updated final
  EDL, whose events carry the ASC CDL that **is the grade** (decided 2026-09-18), plus a `.cube` only for a shot the wheels could not do, which the tool ingests (`docs/COLOR_AND_FORMAT.md` section 1). Does not operate
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
- Authoring colour. The tool applies colour, it never invents any: the look is decided in the AD meeting, built in the colour session, and arrives as one grade file per shot alongside its final EDL. **There are no colour controls in the tool.** An earlier version of this PRD, from the same morning, specified four per clip sliders for the AD's notes; they are removed, because two places to author a grade is one place too many and the Resolve session is the one that has the AD in the room.
- Lidar deliverables.
- Lens grid delivery. The tool reports whether a turnover has one; moving and renaming it is manual in v01 (OQ-20).
- Frame viewer. Specified on the morning of 2026-09-11 as three steppable viewers, removed that afternoon, and back in the v02 backlog where it started (FR-16).
- Any Google Drive API use. The Drive mount is a normal mounted folder.
- Windows build (design for it, do not ship it). v01 is Apple Silicon only, and a Windows 11 build is a v02 intention (OQ-24).

## 4. Inputs

Per turnover, in one folder on the Google Drive mount (structure configurable in Settings, see `docs/OPEN_QUESTIONS.md` OQ-1):

- One `.otio` exported from Resolve (required), with an `.edl` accepted as a reduced fallback. It conforms the timeline: clip names, ranges and audio association. **The colour session supersedes it** with an updated final EDL (below), which is the conform the run actually uses.
- Consolidated media: one file or image sequence per timeline clip, **ProRes 4444**, with the log encoding **written into the clip's metadata by the shooter** (`docs/COLOR_AND_FORMAT.md` sections 1 and 2, OQ-44). Camera native log is the expectation, S-Log3, C-Log3 and BM Film today with more to be added; DaVinci Wide Gamut / DaVinci Intermediate is one more valid value rather than a separate arrangement. Extra frames beyond the timeline In/Out (handles are already in the timeline range; the extra frames only exist so Out can be extended).
- **The colour session package, required before anything final renders** (`docs/COLOR_AND_FORMAT.md` section 1): the **updated final EDL**, carrying timecode, shot identity, the approved In/Out and the CDL as `*ASC_SOP` / `*ASC_SAT` lines, **that CDL is the grade the tool applies, in ACEScct** (decided 2026-09-18); a `.cube` per shot is optional and takes the CDL's place for that shot (OQ-33 covers how it is matched). Scan and review work without it; Run does not.
- The shooter's offline **string-out and CDL** may also be present. They are a record of intent and the starting point for the colour session, and both are superseded by its final versions. **The tool reads neither and renders from neither.**
- Audio clips synced on the timeline, referenced by the OTIO on audio tracks.
- Optional per shot: HDRI `.exr`, camera data `.txt`/`.rtf`, lens grid `.png`, BTS stills, reference stills (color chart, mirror ball, grey ball, size reference).

Timeline clip names are the contract: `MELT0001_pl01` style (see `docs/NAMING_SPEC.md`). The tool derives every output name from the clip name.

## 5. Outputs

Per shot, into a delivery root the user chooses (default proposed layout in `docs/NAMING_SPEC.md` section 5):

- 4k and HD raw EXR sequences (DWAA 45, start frame 1001) in their own subfolders. **ACEScg, scene linear, graded with the shot's grade file**, with the source encoding, the grade file name and hash, and the CDL as a readable record, in the header so the grade in the pixels can be identified later without the session
- 4k and HD H.264 reference mp4s, sRGB display, the same grade file plus the ACES output transform
- Audio wav for plate clips (as delivered, 16 bit PCM)
- Copied and renamed HDRI, BTS, reference stills where present. **Not the lens grid**: it arrives as a folder in the turnover and the editor moves and renames it by hand in v01 (OQ-20)
- `shot_tracker.xlsx` for paste into the studio tracker (the studio's own 39 columns, OQ-2)
- `qc_ingest_log.xlsx` with one row per deliverable, rule results, and turnover-vs-final In/Out diff

## 6. User flow

1. New Batch or Open Batch (`.pibatch` JSON).
2. Add Turnover: pick the turnover folder, tool finds the `.otio` (or user picks it). The chooser opens at the batch's source root and picking outside it just moves the root. Repeat for up to N turnovers in a batch.
3. Scan. Tool parses the timeline, matches each clip to media, probes media with ffprobe, resolves audio, discovers side files, runs pre-flight QC. List populates, grouped by turnover. Problem rows are colored with a tooltip and a QC panel entry.
4. Ingest the colour session, per turnover. Editor points at Ben's updated final EDL. The tool matches each event to a row, takes **its In/Out as the approved edit**, reads its CDL, and pairs the row with its grade file (OQ-30, OQ-33), writing all three onto the rows so the batch file is what a later run reads rather than the package. Rows it could not match cannot render (QC-008, QC-009), and a turnover with no session at all is held back while the rest of the batch delivers. **This normally comes before review**, because it is what the review is reviewing; doing it after a trim overwrites that trim and says so (FR-5).
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
- **Trimming does not invalidate the grade.** A grade file is one static transform for the whole shot, not an animated one, so moving In or Out carries it unchanged. The caveat, which is why this is a one-off facility: **extending into the handles applies the approved grade to frames Ben never looked at.** Usually fine for a static primary, and worth knowing before extending a long way.
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

FR-9 Stringout: **dropped from v01, 2026-09-11.**
- The tool does not build a stringout. The colour session exports a reference QT with the look and burn-ins, and that is the stringout. Two tools building the same artifact from the same decisions is one too many, and the one with the colourist in front of it wins.
- What went with it: milestone M6, `core/stringout.py`, the burn-in specification in `docs/UI_SPEC.md` section 8, QC-140 and QC-141, and OQ-12 and OQ-15.
- **What this gives up, recorded so it is a decision and not an oversight**: the tool's stringout would have been the only one cut to the **edited** In/Out. The session's QT and the shooters' offline are both cut to the turnover as delivered. If it turns out the vendor needs a stringout that reflects the review session, this comes back, and it comes back as a milestone rather than a patch.

FR-10 Exports
- `shot_tracker.xlsx` via openpyxl, **rows to paste into the studio's own tracker**: its 39 columns in its own order, nine of them written and the other thirty left empty because the vendor's team owns them (OQ-2, answered 2026-09-11 from the real sheet). The column layout was to be loaded from a template file in Settings, which was right while nobody knew the columns and is a configuration point standing where a fact belongs now that they are known.
- `qc_ingest_log.xlsx` with sheets: Summary, Shots (**three In/Out columns: as the shooters delivered it, as Ben approved it, as it rendered**, plus duration, shot code changes, skip reasons), Deliverables (one row each with path, version, size, checksum, every QC rule result), Side Files, Camera Data (parsed key/values from camData files).

FR-11 Batch file
- `.pibatch` JSON, schema versioned. Contains everything needed to reopen: turnovers, rows, snapshots, edits, probe cache, delivery root, render status, settings overrides. Autosave on every edit (debounced 500 ms). Backup copy kept on open.

FR-12 Settings page
Sections: General (delivery root default, path map, concurrency, GPU), Rules (min/max duration frames, expected handle frames, allowed fps, expected resolutions), **Colour (where the ingest chooser opens, the input transform table and its overrides, ACES config version, output transform)**. **The session package's own location is not a setting**: it is ingested per turnover and recorded on the batch (`Turnover.color_session_edl`, OQ-50), because it is a record of what this work was rendered from rather than a preference, and because QC-008 is turnover scope so one turnover can wait on colour while another renders. **No source encoding mode**: the clip's metadata names the encoding per clip and DaVinci Wide Gamut is one more entry in the table rather than a mode to switch into, Naming (show prefix regex, type table overrides), Output (mp4 quality, EXR compression level), Advanced (ffmpeg path override, OCIO config override, log level).

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
- Working space is **ACEScg**. Every deliverable is graded, with the approved look applied from the **CDL on the shot's event in the final EDL, in ACEScct** (decided 2026-09-18). A `.cube` delivered for a shot takes the CDL's place for that shot, and the EXR header says which was applied. `docs/COLOR_AND_FORMAT.md` section 1 says why both exist. Full policy, both branches and the reasoning are in `docs/COLOR_AND_FORMAT.md` section 1, which is the spec. This entry records that the pipeline exists and what it owes.
- Transforms come from **OpenColorIO** as a single `GroupTransform` per shot, interpolated **tetrahedrally**, using a pinned ACES 1.3 built-in config so no config files ship and no dependency bump changes what a reference looks like (OQ-29). Curves and matrices are never hand written.
- Per shot the chain is: decode to float, **override the container's colour tags** with the encoding the clip's metadata names and confirm range, then the input transform that encoding names **into ACEScct**, the shot's grade (the CDL, or its cube), then ACEScct to linear ACEScg (decided 2026-09-18, OQ-46). This reverses OQ-37's 2026-09-12 answer: Resolve's CDL export carries node one's primaries and means something only in the timeline space, so the tool converts on both sides of it.
- **The source encoding is named in the clip's metadata, per clip, and there is no mode** (`docs/COLOR_AND_FORMAT.md` section 1, decided 2026-09-12). Camera native log is the expectation; **DaVinci Wide Gamut / DaVinci Intermediate is one more entry in the input transform table**, not a batch-wide setting, so a turnover may mix a shooter on a house template with two on their cameras and nothing has to be switched before it is scanned.
- **On every plate the source encoding is a transform**, the leg into ACEScct ahead of the grade (2026-09-18). It goes in the EXR header so a delivered frame says what it was made from, and it is what QC-018 and QC-021 check against. A wrong one grades the wrong pixels, so QC-046 and QC-047 block a plate as they block an aux still.
- **The tool carries multiple input transforms and picks one per shot from the clip's metadata** (required 2026-09-12). It is an explicit table from the string a shooter wrote to one OpenColorIO colour space, extensible by adding a row, naming a curve and a gamut together because a curve alone does not identify one, and refusing anything it cannot resolve to exactly one entry (QC-047) rather than reaching for the nearest. OQ-34 is that table and OQ-44 is what its keys are.
- **Where that transform is applied is a correctness rule, not a diagram detail.** Since 2026-09-18 it is applied on **every** row the tool transforms: into ACEScct ahead of the grade on a plate or reference, and straight to ACEScg on the **aux still**, which is delivered ungraded, and on any row with no grade at all. The grade is never applied in any other space and never applied twice, and `ShotColor.plate_transforms` builds the whole chain so a caller cannot assemble half of one. OQ-46 recorded the earlier uncertainty and is decided.
- **The aux still is the sharpest case and the reason the table is load bearing regardless.** A mis-converted colour chart still looks exactly like a chart and is the one thing a compositor matches against, so an unresolvable encoding blocks that deliverable rather than approximating it. Whether the colour session should hand the stills over already converted, deleting the tool's last transform of its own, is OQ-45.
- The plate branch takes the graded ACEScg and resizes unbounded in numpy. The view branch adds the ACES output transform to the same three legs and collapses the pair into **one 3D LUT per shot**, generated in core and applied by ffmpeg `lut3d` for the reference. It has one consumer since the viewers were dropped (FR-16); the cube is the thing to hand a viewer if one ever returns.
- The EXR header records the source encoding, the CDL as numbers and as its original lines with a note saying it was applied in ACEScct, or, where a cube took its place, the **cube's name and hash** (which identifies that grade exactly), so a delivered plate can be understood by someone with neither the session nor an OCIO install.
- **A cube that contains a display rendering is refused**, QC-039: it would produce a display referred file that claims to be scene linear, and nothing downstream would notice until the comp was wrong.
- A row with no grade, neither a CDL on its event nor a cube, cannot render. QC-009, error, not a warning: an ungraded plate is not a lesser deliverable here, it is the wrong pixels under the right filename.

FR-16 Viewers: **dropped from v01, 2026-09-11.**
- There are no image viewers in the tool. The three steppable In / Center / Out viewers specified on the morning of 2026-09-11 are removed, along with the four colour controls that were specified beside them and removed a little earlier the same day.
- A frame viewer returns to the v02 backlog where it started (section 10), and section 3 lists it as a non-goal again.
- What went with it: `docs/UI_SPEC.md` section 14, `core/preview.py` and M4.5.5, and the single frame fetch and cache they needed. In/Out are edited by typing, per FR-5, which is now the only way a row is edited at all.
- **What this gives up**: an editor judging a cut point reads frame numbers and timecode rather than pictures. That is what the review session with the AD was for, and that session now happens in Resolve with Ben, where there is a proper viewer and a calibrated monitor.

FR-17 User documentation (asked for 2026-09-12)
- **One document the editor can be handed**, covering three things in this order: **how to install it**, a **quickstart** that takes one turnover from Add Turnover to the exports in about a page, and a **reference guide with one section per surface of the window** - the list and its columns, editing, the Issues dock, the run, Settings, the log, the metadata pane.
- **Screenshots wherever a screenshot says it faster than a sentence.** They are taken by a harness that builds a demo batch and grabs the window, not by hand, so a changed interface is a re-run rather than a re-shoot, and the demo data is the synthetic `MELT` show rather than anything from a production.
- **Delivered as something the studio can read and keep**: a PDF, or a file that pastes whole into Google Docs. One source rather than two exports that drift; OQ-49 is which, with a default.
- It is written against the built app rather than the spec, and its button reference and the toolbar tooltips (UI_SPEC section 1) share their wording.
- This is M9, and it is deliberately **not** the same thing as M8.4's handover notes, which are what the studio keeps about the *build* - the rule IDs, what to do when a check fires. FR-17 is what somebody reads to use the tool.

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
M4.5 Colour pipeline, core only: OCIO wired in, the final EDL's In/Out and CDL read and matched per row, the grade file matched and loaded, the chain composed as one GroupTransform, the viewing LUT. Reopens M3's render for the plate/view split. No Qt, testable headless. It was built with an input transform ahead of the grade file, which OQ-37 removed on 2026-09-12; taking it back out is M4.6.
M4.6 Per shot source encoding: read from the clip metadata, the input transform table it selects from, the input transform removed from the plate and view chains, the source-to-ACEScg conversion kept for the aux still alone, QC-046, QC-047 and QC-048.
M5 UI: main window, list view with keyboard model, metadata pane, validation coloring, settings page, log panel, batch open/save.
M6 **Dropped 2026-09-11.** Was: stringout with burn-ins. The colour session exports it instead (FR-9). The number is not reused.
M7 Packaging: PyInstaller `.app`, disk image, bundled ffmpeg, first-run experience, icon.
M8 Polish pass against `docs/UI_SPEC.md`, performance on a real turnover, docs.
M9 The user guide (FR-17, added 2026-09-12): install guide, quickstart, a reference section per surface of the window, screenshots from a harness, delivered as one document the studio can keep.

## 10. v02 backlog (do not build in v01, but do not design against it)

- Frame viewer. Removed from v01 twice now, which is worth noting before anyone adds it a third time: it was a v02 item from the start, was promoted into v01 on 2026-09-11 as three steppable viewers, and was removed again on 2026-09-11 because the review that needed pictures moved to Resolve. It needs a decoded frame cache per row and the viewing LUT that M4.5 builds anyway.
- Per shot colour controls in the tool, if the round trip through the colour session ever proves too slow for a review session. Removed from v01 deliberately (section 3).
- Burn-ins on reference mp4s.
- Windows 11 build. Intended, not committed (OQ-24).
- Google Apps Script hyperlink export for the tracker.
