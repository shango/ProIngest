# ProIngest PRD v01

Working name: ProIngest. Version target: v01 (macOS, Apple Silicon). v02 items are listed at the end and must not block v01.

## 1. Problem

A small VFX studio receives shot turnovers from three shooters. Each turnover is a DaVinci Resolve project consolidated to HQ media, one clip per shot with handles, plus a timeline export. Today the VFX editor conforms the stringout, renames and transcodes every deliverable by hand, and checks them by eye. This is slow, error prone, and the naming spec is strict.

ProIngest turns that into: point at the turnover folder, load the timeline, review and adjust In/Out with the AD and supervisor in the same list, press Run, get correctly named and verified deliverables plus tracker and QC spreadsheets.

## 2. Users

- VFX Editor (primary). Runs the tool, owns the batch.
- AD / VFX Supervisor. Sits with the editor during review; does not operate the tool.
- Colourist. Runs the final colour session in Resolve with the AD, and exports the updated final
  EDL, whose events carry the ASC CDL that **is the grade** (decided 2026-09-18), and nothing else: there are no per-shot grade files (2026-09-21), which the tool ingests (`docs/COLOR_AND_FORMAT.md` section 1). Does not operate
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

- **The turnover folder**: consolidated media, one file per timeline clip, as the shooters' Copy with trim wrote it - the camera's filename, the camera's start timecode, handles both sides, and **nothing recompressed**. The encoding is camera native, or, where the camera system records RAW, a debayered basic file type with **no colours baked in**. RAW itself never arrives, which matters because ffmpeg decodes no RAW format. Resolve also writes a `.drt` beside the media as a by-product of the trim; **the tool does not read it**.
- **Ben's EDL with the CDL in it, required before anything final renders**: shot identity, the approved In/Out from his trims with the AD, and the grade as `*ASC_SOP` / `*ASC_SAT` lines per event. **That CDL is the grade the tool applies, in ACEScct** (2026-09-18). There are no per-shot grade files (2026-09-21). An EDL states **no frame rate**, so the project rate is asserted rather than read (see section 9 and `docs/WORKFLOW.md` rule 5).
- **Ben's metadata CSV, required**: `File Name`, `Shot`, `Shot Type`, `Gamma Notes`, `Color Space Notes`. **This is identity and encoding**, and the scan cannot build a row without it. `Shot` carries the shot code, `Shot Type` says what the clip is, and the two encoding fields join in that order into one input transform name.
- Audio per shot, in the turnover.
- Per shot in the turnover: HDRI `.exr`, camera data `.txt`/`.rtf`, lens grid, BTS stills. **The tool reads none of these and delivers none of them** (2026-09-22): they carry no `Shot Type`. The **reference stills** - colour chart, mirror ball, grey ball, size reference - are different: they arrive as **single-frame clips on the timeline** with a `Shot Type` of their own, confirmed in `Turnover199`, and the tool does deliver those.
- The shooters' own offline **stringout** may be present. It is a record of intent, superseded by Ben's refined one, and the tool reads it never.

**Identity is metadata, never a filename.** Camera filenames are delivered unchanged and nothing parses one to learn what a clip is (`docs/NAMING_SPEC.md` section 1, 2026-09-21).

> **Sequencing consequence, raised 2026-09-21 and not yet resolved (OQ-74).** Identity and encoding
> now arrive in Ben's CSV, and the conform and grade in Ben's EDL. Both come from Ben. So a turnover
> scanned before Ben has finished yields media with no shot codes, no clip types and no encoding -
> where the old flow could scan and review off the shooters' timeline and add Ben's work later. The
> two-phase user flow in section 6 assumes the first phase works without him, and it no longer does.

## 5. Outputs

Per shot, into a delivery root the user chooses (default proposed layout in `docs/NAMING_SPEC.md` section 5):

- 4k and HD raw EXR sequences (DWAA 45, start frame 1001) in their own subfolders. **ACEScg, scene linear, graded with the shot's grade file**, with the source encoding, the grade file name and hash, and the CDL as a readable record, in the header so the grade in the pixels can be identified later without the session
- 4k and HD H.264 reference mp4s, sRGB display, the same grade file plus the ACES output transform
- Audio wav for plate clips (as delivered, 16 bit PCM)
- Single 4k EXR per reference still (`colorChart`, `mirrorBall`, `greyBall`, `sizeRef`), converted and **never graded**, keyed to the shot code
- **Nothing else.** Decided 2026-09-22: the tool delivers exactly what a `Shot Type` row names. **HDRI, camData, BTS, the lens grid and the stringout are not tool deliverables** - they carry no `Shot Type`, so the tool ignores them, and they are delivered by Ben or by hand. QC-050 to QC-054, QC-056 and QC-057 retire with them, and so do `core/camdata.py`, `naming.lens_grid_png` and `naming.stringout_mp4`
- `shot_tracker.xlsx` for paste into the studio tracker (the studio's own 39 columns, OQ-2)
- `qc_ingest_log.xlsx` with one row per deliverable, rule results, and turnover-vs-final In/Out diff

## 6. User flow

1. New Batch or Open Batch (`.pibatch` JSON).
2. Add Turnover: pick the folder Ben handed over, which holds **the media, his EDL and his CSV together**. The chooser opens at the batch's source root and picking outside it just moves the root. Repeat for up to N turnovers in a batch. A folder missing the EDL or the CSV cannot be scanned and says so (QC-001).
3. Scan. Tool reads Ben's CSV for identity and encoding, reads his EDL for the approved In/Out and the CDL, matches each row to media by `File Name`, probes media with ffprobe, resolves audio, discovers side files, runs pre-flight QC. List populates, grouped by turnover. Problem rows are colored with a tooltip and a QC panel entry.
4. Re-ingest, when Ben revises. The conform and the grade are read at scan, so this is not a separate step in the normal case. It stays for a **revised EDL**: the editor points at the new one and the tool rewrites the approved In/Out and the CDL onto the rows without a full re-scan, reporting the trims it overwrote (FR-5). Rows it cannot match cannot render (QC-008, QC-009).
5. Review. Editor works down the list with the keyboard, checking the rows, fixing names, marking clips as skipped, and making the occasional one-off trim that is not worth a trip back to Resolve (FR-5). Duration and validation update live. Selecting a row fills the metadata pane on the right with everything known about that clip (FR-14). Everything autosaves to the batch file.
6. Run. Editor picks the delivery root (remembered per batch, the second of the two folder choosers in `docs/UI_SPEC.md` section 13), presses Run. Progress per row and overall. Rows go green when all their deliverables pass post-render QC.
7. Export. Tracker and QC spreadsheets are written to the delivery root. Editor can re-open the batch later and re-run only what failed.

## 7. Functional requirements

FR-1 Conform import

- **There is no timeline file.** The shooters export nothing for the tool and never did; Resolve's `.drt`, written beside consolidated media as a by-product, is not read either. The conform comes from Ben's EDL and identity from Ben's CSV (2026-09-21, reversing the OTIO design).
- **Ben's CSV is the shot list.** One row per consolidated clip: `File Name`, `Shot`, `Shot Type`, `Gamma Notes`, `Color Space Notes`. UTF-16 with a BOM, and the column set is dynamic - Resolve writes only the columns that carry a value - so a reader must not assume a fixed schema. A row whose `Shot` or `Shot Type` is blank is QC-010 and still appears, so the editor can see it.
- **Ben's EDL is the conform and the grade.** Per event: shot identity, the approved In/Out from his trims with the AD, and `*ASC_SOP` / `*ASC_SAT` comment lines, because Resolve exports no `.cdl` or `.ccc` file. Read with otio's `cmx_3600` adapter. Matching an event to a row is OQ-30.
- **An EDL states no frame rate.** CMX 3600 has no field for one and the adapter takes the rate as an argument, so the project rate is a setting defaulting to 24 and QC-026 reports any file whose own rate disagrees.
- **Refuse rather than mis-render a motion effect.** A retime is an `M2` line and a reversed clip a negative speed on it; an event carrying one is refused and says so (OQ-63).
- Audio: the EDL carries no audio association, so the tool searches the turnover folder for a wav matching the clip's file name. Zero or more than one is a QC result.

FR-2 Media resolution
- **Match each CSV row to its media by `File Name`, in the folder Ben handed over.** Camera filenames are delivered unchanged, so the row and the file agree by construction. Comparison is casefolded, because APFS and a Drive mount are not case sensitive and Ben's EDL is not either (OQ-67). Nothing parses a filename to learn what a clip is.
- If the referenced file is missing, search the turnover folder recursively for a file or image sequence whose base name matches the clip name. Exactly one hit resolves silently; zero or many is a QC error on the row.
- Image sequences are detected by the `name.####.ext` pattern and treated as one media item with a frame range.

FR-3 Probing
- ffprobe every resolved media item once: codec, pixel format, width, height, frame rate, duration in frames, start timecode, audio streams. Cache in the batch file keyed by path, size, and mtime.

FR-4 Shot model
Each row holds: turnover id, clip name (parsed into show, shot number, type, index), source path, source fps, source resolution, source frame count and start TC, record In/Out TC, source In/Out (frames and TC), turnover snapshot of In/Out (immutable after scan), current In/Out, duration, max available Out, audio path, side files, skip flag, per-deliverable status, QC results.

FR-5 Editing
- Editable fields: Shot Code, In, Out, Notes. No handle controls on rows. **The plate is the cut only** (user, 2026-09-23): the EDL event's source In/Out, with the handles outside it in the file (`C0145` is 24 + 232 + 24), and the editor extends a clip into them by moving Out. A Settings value "expected handle frames" exists only for the QC-030 warning.
- In/Out accept four formats, auto-detected: source TC `HH:MM:SS:FF`, record TC (when the display toggle is on record), absolute source frame number, relative offset `+12` / `-8` applied to the current value.
- Duration recalculates on every edit. Max Available shows the last usable source frame.
- Shot Code edits are validated against the naming regex live. A renamed shot code is a diff entry in the QC log.
- Skip flag excludes the row from render and marks it in the QC log with a required reason field.
- **Trimming in the tool is an exception path, not the main way a cut is decided.** In and Out arrive already approved: Ben and the AD set them in the colour session and they come in on its final EDL (FR-15). The tool keeps its In/Out editing for **the quick one-off**, the trim that would otherwise mean asking Ben to reopen Resolve and export a new EDL for one shot. That is worth having and it is not a licence to re-edit a turnover.
- **A trim in the tool is a deviation from an approved edit, and is reported as one.** QC-045, warning. QC-035 keeps its own meaning, which is the difference between what the shooters delivered and what is being rendered, and most of that difference is now Ben's own work rather than the editor's.
- **Trimming does not invalidate the grade.** A grade file is one static transform for the whole shot, not an animated one, so moving In or Out carries it unchanged. The caveat, which is why this is a one-off facility: **extending into the handles applies the approved grade to frames Ben never looked at.** Usually fine for a static primary, and worth knowing before extending a long way.
- **The list owns every edit.** There is no second surface that writes to a row: no viewers, no colour controls, no editable metadata pane.

FR-6 Validation (pre-flight)
All rules in `docs/QC_RULES.md` with prefix `QC-0xx`. **Two tiers since 2026-09-23 (D8, D9)**: an error is must-fix, and any must-fix in the batch stops the run until the folder is corrected and re-scanned; a skipped row's errors do not count. Warnings and info never block.

FR-7 Render
- Per row, generate a plan of deliverable jobs from the clip type table in `docs/NAMING_SPEC.md`.
- Jobs execute in a process pool. Concurrency default = physical cores / 2, editable. EXR jobs are CPU and IO heavy; refs are ffmpeg heavy. The scheduler interleaves them.
- Every job writes to `<final>.part` (files) or `<folder>.part/` (sequences) then renames on success.
- Versioning: before writing, scan the destination for existing versions of the same deliverable and use max+1. All deliverables of one shot in one run share the same version number. If a shot already has a complete, QC-passing set at the highest version and "Force re-render" is off, skip with status "Exists".
- Hardware encoding (`h264_videotoolbox`) is optional: detected at startup, used for H.264 when available and enabled in Settings. Output must be visually equivalent; quality mapping in `docs/COLOR_AND_FORMAT.md`. NVENC was the Windows equivalent and does not exist on macOS.

FR-8 Post-render QC
Rules `QC-1xx` in `docs/QC_RULES.md`: frame count, first/last frame numbers, resolution, fps, EXR header integrity, checksum of every frame written, mp4 duration, audio duration.

FR-9 Stringout: **dropped from v01, 2026-09-11. Dropped entirely 2026-09-22.**
- **The tool does nothing with the stringout at all** (user, 2026-09-22): it does not build one, read one, transcode one, rename one or check a name. Ben produces and exports it, cut on the same timeline his EDL comes off, and it is his deliverable end to end. `naming.stringout_mp4` and OQ-41's filename checker go with this.
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
- Working space is **ACEScg**. Every deliverable is graded, with the approved look applied from the **CDL on the shot's event in the final EDL, in ACEScct** (decided 2026-09-18). There are no per-shot grade files (2026-09-21): the CDL is the only carrier. The EXR header says which was applied. `docs/COLOR_AND_FORMAT.md` section 1 says why both exist. Full policy, both branches and the reasoning are in `docs/COLOR_AND_FORMAT.md` section 1, which is the spec. This entry records that the pipeline exists and what it owes.
- Transforms come from **OpenColorIO** as a single `GroupTransform` per shot, interpolated **tetrahedrally**, using a pinned ACES 1.3 built-in config so no config files ship and no dependency bump changes what a reference looks like (OQ-29). Curves and matrices are never hand written.
- Per shot the chain is: decode to float, **override the container's colour tags** with the encoding the clip's metadata names and confirm range, then the input transform that encoding names **into ACEScct**, the shot's CDL, then ACEScct to linear ACEScg (decided 2026-09-18, OQ-46). This reverses OQ-37's 2026-09-12 answer: Resolve's CDL export carries node one's primaries and means something only in the timeline space, so the tool converts on both sides of it.
- **The source encoding is named in the clip's metadata, per clip, and there is no mode** (`docs/COLOR_AND_FORMAT.md` section 1, decided 2026-09-12). Camera native log is the expectation; **DaVinci Wide Gamut / DaVinci Intermediate is one more entry in the input transform table**, not a batch-wide setting, so a turnover may mix a shooter on a house template with two on their cameras and nothing has to be switched before it is scanned.
- **On every plate the source encoding is a transform**, the leg into ACEScct ahead of the grade (2026-09-18). It goes in the EXR header so a delivered frame says what it was made from, and it is what QC-018 and QC-021 check against. A wrong one grades the wrong pixels, so QC-046 and QC-047 block a plate as they block an aux still.
- **The tool carries multiple input transforms and picks one per shot from the clip's metadata** (required 2026-09-12). It is an explicit table from the string a shooter wrote to one OpenColorIO colour space, extensible by adding a row, naming a curve and a gamut together because a curve alone does not identify one, and refusing anything it cannot resolve to exactly one entry (QC-047) rather than reaching for the nearest. OQ-34 is that table and OQ-44 is what its keys are.
- **Where that transform is applied is a correctness rule, not a diagram detail.** Since 2026-09-18 it is applied on **every** row the tool transforms: into ACEScct ahead of the grade on a plate or reference, and straight to ACEScg on the **aux still**, which is delivered ungraded, and on any row with no grade at all. The grade is never applied in any other space and never applied twice, and `ShotColor.plate_transforms` builds the whole chain so a caller cannot assemble half of one. OQ-46 recorded the earlier uncertainty and is decided.
- **The aux still is the sharpest case and the reason the table is load bearing regardless.** A mis-converted colour chart still looks exactly like a chart and is the one thing a compositor matches against, so an unresolvable encoding blocks that deliverable rather than approximating it. Whether the colour session should hand the stills over already converted, deleting the tool's last transform of its own, is OQ-45.
- The plate branch takes the graded ACEScg and resizes unbounded in numpy. The view branch adds the ACES output transform to the same three legs and collapses the pair into **one 3D LUT per shot**, generated in core and applied by ffmpeg `lut3d` for the reference. It has one consumer since the viewers were dropped (FR-16); the cube is the thing to hand a viewer if one ever returns.
- The EXR header records the source encoding, the CDL as numbers and as its original lines with a note saying it was applied in ACEScct, so a delivered plate can be understood by someone with neither the session nor an OCIO install.
- ~~**A cube that contains a display rendering is refused**, QC-039~~ **Retired 2026-09-21 with the per-shot grade file.** A CDL is four numbers per channel and cannot hide a tone map. The failure it guarded against - a display referred file claiming to be scene linear - is real and returns with any future grade file, and nothing downstream would notice until the comp was wrong.
- A row whose event carries no CDL cannot render. QC-009, error, not a warning: an ungraded plate is not a lesser deliverable here, it is the wrong pixels under the right filename.

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

M1 Core: EDL and metadata CSV parse, naming, media resolution, ffprobe cache, shot model, batch JSON. Headless CLI `proingest scan <folder>` prints the row table. Tests.
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
