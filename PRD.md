# ProIngest PRD v01

Working name: ProIngest. Version target: v01 (macOS, Apple Silicon). v02 items are listed at the end and must not block v01.

## 1. Problem

A small VFX studio receives shot turnovers from three shooters. Each turnover is a DaVinci Resolve project consolidated to HQ media, one clip per shot with handles, plus the colourist's EDL and metadata CSV. Today the VFX editor conforms the stringout, renames and transcodes every deliverable by hand, and checks them by eye. This is slow, error prone, and the naming spec is strict.

ProIngest turns that into: point at the turnover folder, scan it, review and adjust In/Out with the AD and supervisor in the same list, press Run, get correctly named and verified deliverables plus tracker and QC spreadsheets.

## 2. Users

- VFX Editor (primary). Runs the tool, owns the batch.
- AD / VFX Supervisor. Sits with the editor during review; does not operate the tool.
- Colourist. Runs the final colour session in Resolve with the AD, and exports the updated final
  EDL, which is **the cut**, and **one AMF per EDL event with the CLFs it names, which is the colour** (user, 2026-09-28; the ASC CDL in the EDL was the grade from 2026-09-18 and is no longer read). The tool reads all of it from the turnover folder at scan (`docs/COLOR_AND_FORMAT.md` section 1). Does not operate
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
- Authoring colour. The tool applies colour, it never invents any: the look is decided in the AD meeting, built in the colour session, and arrives as each clip's AMF and its CLFs (2026-09-28). **There are no colour controls in the tool.** An earlier version of this PRD, from the same morning, specified four per clip sliders for the AD's notes; they are removed, because two places to author a grade is one place too many and the Resolve session is the one that has the AD in the room.
- Lidar deliverables.
- Lens grid delivery. **Ben delivers the lens grid** and the tool does not look for one (2026-09-22, OQ-20 closed).
- Frame viewer. Specified on the morning of 2026-09-11 as three steppable viewers, removed that afternoon, and back in the v02 backlog where it started (FR-16).
- Any Google Drive API use. The Drive mount is a normal mounted folder.
- Windows build (design for it, do not ship it). v01 is Apple Silicon only, and a Windows 11 build is a v02 intention (OQ-24).

## 4. Inputs

Per turnover, in one folder on the Google Drive mount (structure configurable in Settings, see `docs/OPEN_QUESTIONS.md` OQ-1):

- **The turnover folder**: consolidated media, one file per timeline clip, as the shooters' Copy with trim wrote it - the camera's filename, the camera's start timecode, handles both sides, and **nothing recompressed**. The encoding is camera native, or, where the camera system records RAW, a debayered basic file type with **no colours baked in**. RAW itself never arrives, which matters because ffmpeg decodes no RAW format. Resolve also writes a `.drt` beside the media as a by-product of the trim; **the tool does not read it**.
- **Ben's EDL, required**: **the cut**, the approved In/Out from his trims with the AD, and any retimes. Its `*ASC_SOP` / `*ASC_SAT` lines are **not read** since 2026-09-28 (they were the grade from 2026-09-18). An EDL states **no frame rate**, so the project rate is asserted rather than read (see section 9 and `docs/WORKFLOW.md` rule 5).
- **Ben's metadata CSV, required**: `File Name`, `Shot`, `Shot Type`. **This is identity only** since 2026-09-28, and the scan cannot build a row without it. `Shot` carries the shot code and `Shot Type` says what the clip is. Its colour columns (`Gamma Notes`, `Color Space Notes`, `Input Color Space`) are no longer read.
- **One AMF per EDL event, and the CLFs each names, required before anything final renders** (user, 2026-09-28): exported from Ben's Resolve session, matched to its event by the timeline index in its file name (the event number less one) and required to name the row's file. It is **the colour**: the input transform, the looks in order (the Reference Gamut Compress, then a CLF per corrector node) and the output transform, every ID resolved through the pinned OCIO config. There is no fallback to the CDL or the CSV. QC-075 to QC-079 and QC-008. The `.otio` and `.drt` beside them are ignored.
- Audio per main plate (pl), in the turnover. No other clip type comes with audio (2026-09-23), and any a cp or el carries, beside it or inside its own file, is ignored: its reference mp4 is silent.
- Per shot in the turnover: HDRI `.exr`, camera data `.txt`/`.rtf`, lens grid, BTS stills. **The tool reads none of these and delivers none of them** (2026-09-22): they carry no `Shot Type`. An HDRI that is on the timeline with `Shot Type` `HDRI` is still the shooters' to deliver: its row is skipped at scan and its clip shows in the stringout only (QC-080, user 2026-09-28). The **reference stills** - colour chart, mirror ball, grey ball, size reference - are different: they arrive as **single-frame clips on the timeline** with a `Shot Type` of their own, confirmed in `Turnover199`, and the tool does deliver those.
- The shooters' own offline **stringout** may be present. It is a record of intent, superseded by Ben's refined one, and the tool reads it never.

**Identity is metadata, never a filename.** Camera filenames are delivered unchanged and nothing parses one to learn what a clip is (`docs/NAMING_SPEC.md` section 1, 2026-09-21).

> **One folder, one phase (OQ-74, settled 2026-09-22).** Identity arrives in Ben's CSV, the
> conform in Ben's EDL, and since 2026-09-28 the colour in his AMFs and CLFs. All of it comes from
> Ben, so there is nothing to scan before he has finished: he hands over one folder holding the
> media and his exports, and a single scan reads them all. There is no separate colour session
> step.

## 5. Outputs

Per shot, into a delivery root the user chooses (default proposed layout in `docs/NAMING_SPEC.md` section 5):

- 4k and HD raw EXR sequences (DWAA 45, start frame 1001) in their own subfolders. **ACEScg, scene linear, graded with the looks of the clip's AMF**, with the source encoding, the AMF's file name and the looks applied in order in the header so the grade in the pixels can be identified later without the session
- 4k and HD H.264 reference mp4s, the same graded chain plus **the AMF's output transform** (turnover097: Gamma 2.2 Rec.709; a fixed sRGB until 2026-09-28)
- Audio wav for main plate clips, 16 bit PCM, **trimmed to the same EDL event as the picture and retimed to follow the 24 fps video** (2026-09-23, D2)
- Single 4k EXR per reference still (`colorChart`, `mirrorBall`, `greyBall`, `sizeRef`), converted and **never graded**, keyed to the shot code
- **Nothing else.** Decided 2026-09-22: the tool delivers exactly what a `Shot Type` row names. **HDRI, camData, BTS and the lens grid are not tool deliverables** - they carry no `Shot Type`, so the tool ignores them, and they are delivered by Ben or by hand. QC-050 to QC-054, QC-056 and QC-057 retire with them, and so do `core/camdata.py` and `naming.lens_grid_png`. **The stringout is the one exception**: it has no row, and the tool builds it per turnover (FR-9)
- `shot_tracker.xlsx` for paste into the studio tracker (the studio's own 39 columns, OQ-2)
- `qc_ingest_log.xlsx` with one row per deliverable, rule results, and turnover-vs-final In/Out diff

## 6. User flow

1. New Batch or Open Batch (`.pibatch` JSON).
2. Add Turnover: pick the folder Ben handed over, which holds **the media, his EDL and his CSV together**. The chooser opens at the batch's source root and picking outside it just moves the root. Repeat for up to N turnovers in a batch. A folder missing the EDL or the CSV cannot be scanned and says so (QC-001).
3. Scan. Tool reads Ben's CSV for identity, reads his EDL for the approved In/Out and each event's AMF for its colour, matches each row to media by `File Name`, probes media with ffprobe, resolves audio, runs pre-flight QC. List populates, grouped by turnover. Problem rows are colored with a tooltip and a QC panel entry.
4. Correct and re-scan, when Ben revises or a check needs a fix (2026-09-23, D8). There is no separate ingest step: the corrected EDL, CSV, AMF, CLF or clip is dropped into the turnover folder and Scan reads it again, carrying the editor's trims, shot code corrections, skips, notes and delivered state over by `File Name` (`scan.carry_over`). A trim the editor never made follows the new EDL, and QC-070 says when the EDL or CSV changed. Rows no event matches cannot render (QC-066, QC-067), nor can rows no AMF grades (QC-075) or a turnover with no AMF at all (QC-008). A clip whose AMF has no CLF renders ungraded and says so (QC-009, info).
5. Review. Editor works down the list with the keyboard, checking the rows, fixing names, marking clips as skipped, and making the occasional one-off trim that is not worth a trip back to Resolve (FR-5). Duration and validation update live. Selecting a row fills the metadata pane on the right with everything known about that clip (FR-14). Everything autosaves to the batch file.
6. Run. Editor picks the delivery root (remembered per batch, the second of the two folder choosers in `docs/UI_SPEC.md` section 13), presses Run. Progress per row and overall. Rows go green when all their deliverables pass post-render QC.
7. Export. Tracker and QC spreadsheets are written to the delivery root. Editor can re-open the batch later and re-run only what failed.

## 7. Functional requirements

FR-1 Conform import

- **There is no timeline file.** The shooters export nothing for the tool and never did; Resolve's `.drt`, written beside consolidated media as a by-product, is not read either. The conform comes from Ben's EDL and identity from Ben's CSV (2026-09-21, reversing the OTIO design).
- **Ben's CSV is the shot list.** One row per consolidated clip: `File Name`, `Shot`, `Shot Type` (its colour columns are not read since 2026-09-28). UTF-16 with a BOM, and the column set is dynamic - Resolve writes only the columns that carry a value - so a reader must not assume a fixed schema. A row whose `Shot` or `Shot Type` is blank is QC-010 and still appears, so the editor can see it.
- **Ben's EDL is the conform.** Per event: the approved In/Out from his trims with the AD. Read by `core/clf.py`'s own parser. Its `*ASC_SOP` / `*ASC_SAT` lines are passed over since 2026-09-28; each event's colour is its AMF (`core/amf.py`, FR-15). **An event belongs to the row whose file's timecode range contains its source range** (OQ-30, answered 2026-09-23: the real EDL names no clip and reels every event `AX`); where an event does name its clip, the name has to agree. No event is QC-066, an ambiguous match QC-067, and an event with no row QC-068.
- **An EDL states no frame rate.** CMX 3600 has no field for one, so the project rate is asserted at 24, a constant rather than a setting (`docs/WORKFLOW.md` rule 5). Every source is rendered at 24 frame for frame; a file at 24000/1001 is the normal conform and is silent, and any other rate is a QC-026 must-fix (D1).
- **A freeze is rendered; any other motion effect is refused** (OQ-63, 2026-09-23). An `M2` at speed 0 holds one source frame: the row is that frame, delivered as a one-frame EXR and a reference that holds it for five seconds, with no audio. A retime or a reversal (any other `M2` speed) is QC-073.
- **The ALE names the events when the EDL does not** (2026-09-23, Turnover121). Ben's EDL names no clips, and matching by timecode fails when cameras do not record time of day: the iPhone clips all start within the first minute. The ALE beside it is one row per timeline event in order, so its `Name` column names each event (`core/ale.py`); an ALE that does not line up is QC-071. **One CSV row per use of a clip**: Resolve lists a clip once for each distinct source range it is cut at, and the scan pairs them in order. **A reference still is delivered once per shot code** and any clip cut twice at the same frames once (QC-072).
- Audio: the EDL carries no audio association, so the tool searches the turnover folder for a wav matching the clip's file name. **Only for a main plate (pl)**: no other clip type has an associated audio clip (user, 2026-09-23), so a wav named for a cp or el is not looked for. Zero or more than one is a QC result.

FR-2 Media resolution
- **Match each CSV row to its media by `File Name`, in the folder Ben handed over.** Camera filenames are delivered unchanged, so the row and the file agree by construction. Comparison is casefolded, because APFS and a Drive mount are not case sensitive and Ben's EDL is not either (OQ-67). Nothing parses a filename to learn what a clip is.
- The turnover folder is indexed once, recursively, and a row's media is the file or image sequence whose base name matches its `File Name`. Exactly one hit resolves silently; none is QC-012 and more than one QC-013. The CSV's `Clip Directory` is not used: it points at the pre-consolidation originals.
- Image sequences are detected by the `name.####.ext` pattern and treated as one media item with a frame range.

FR-3 Probing
- ffprobe every resolved media item once: codec, pixel format, width, height, frame rate, duration in frames, start timecode, audio streams. Cache in the batch file keyed by path, size, and mtime.

FR-4 Shot model
Each row holds: turnover id, clip name (the CSV's `File Name`), identity (shot code from `Shot`, type and index from `Shot Type`), source encoding, source path, source fps, source resolution, source frame count and start TC, record In/Out TC, source In/Out (frames and TC), turnover snapshot of In/Out (immutable after scan), current In/Out, duration, max available Out, audio path, the grade from the event's AMF (input transform, looks, display and view, preset), skip flag, per-deliverable status, QC results.

FR-5 Editing
- Editable fields: Shot Code, In, Out, Notes. No handle controls on rows. **The plate is the cut only** (user, 2026-09-23): the EDL event's source In/Out, with the handles outside it in the file (`C0145` is 24 + 232 + 24), and the editor extends a clip into them by moving Out. A Settings value "expected handle frames" exists only for the QC-030 warning.
- In/Out accept four formats, auto-detected: source TC `HH:MM:SS:FF`, record TC (when the display toggle is on record), absolute source frame number, relative offset `+12` / `-8` applied to the current value.
- Duration recalculates on every edit. Max Available shows the last usable source frame.
- Shot Code edits are validated against the naming regex live. A renamed shot code is a diff entry in the QC log.
- Skip flag excludes the row from render and marks it in the QC log with a required reason field.
- **Trimming in the tool is an exception path, not the main way a cut is decided.** In and Out arrive already approved: Ben and the AD set them in the colour session and they come in on its final EDL (FR-15). The tool keeps its In/Out editing for **the quick one-off**, the trim that would otherwise mean asking Ben to reopen Resolve and export a new EDL for one shot. That is worth having and it is not a licence to re-edit a turnover.
- **A trim in the tool is a deviation from an approved edit, and is reported as one.** QC-045, warning. QC-035 keeps its own meaning, which is the difference between what the shooters delivered and what is being rendered, and most of that difference is now Ben's own work rather than the editor's.
- **Trimming does not invalidate the grade.** The AMF's looks are one static transform for the whole shot, not an animated one, so moving In or Out carries them unchanged. The caveat, which is why this is a one-off facility: **extending into the handles applies the approved grade to frames Ben never looked at.** Usually fine for a static primary, and worth knowing before extending a long way.
- **The list owns every edit.** There is no second surface that writes to a row: no viewers, no colour controls, no editable metadata pane.

FR-6 Validation (pre-flight)
All rules in `docs/QC_RULES.md` with prefix `QC-0xx`. **Two tiers since 2026-09-23 (D8, D9)**: an error is must-fix, and any must-fix in the batch stops the run until the folder is corrected and re-scanned; a skipped row's errors do not count. Warnings and info never block.

FR-7 Render
- Per row, generate a plan of deliverable jobs from the clip type table in `docs/NAMING_SPEC.md`.
- Jobs execute in a process pool. Concurrency default = physical cores / 2, editable. EXR jobs are CPU and IO heavy; refs are ffmpeg heavy. The scheduler interleaves them.
- Every job writes to `<final>.part` (files) or `<folder>.part/` (sequences) then renames on success.
- Versioning: before writing, scan the destination for existing versions of the same deliverable and use max+1. All deliverables of one shot in one run share the same version number. **What the last run left decides the next one** (2026-09-23, D11 and D12): a row whose deliverables all landed is skipped (QC-061) unless the editor right-clicks **Re-run**, which writes the next version; what a stopped run never wrote is rendered at the same version; a row with a failed output waits until the editor fixes the cause and right-clicks **Reset**, which runs what failed again at the same version. A worker that dies loses only what was in flight, which gets one more pool.
- Hardware encoding (`h264_videotoolbox`) is optional: detected at startup, used for H.264 when available and enabled in Settings. Output must be visually equivalent; quality mapping in `docs/COLOR_AND_FORMAT.md`. NVENC was the Windows equivalent and does not exist on macOS.

FR-8 Post-render QC
Rules `QC-1xx` in `docs/QC_RULES.md`: frame count, first/last frame numbers, resolution, fps, EXR header integrity, checksum of every frame written, mp4 duration, audio duration.

FR-9 Stringout: **the tool builds it** (OQ-38, back 2026-09-25, built the same day in `core/stringout.py`). **Ben does not export one** (user, 2026-09-29): anything saying he does is wrong.
- One HD mp4 per turnover, cut to **Ben's final EDL** (the approved ranges, not the editor's trims), in record order. Each event is cut from its row's **delivered HD reference**; an event with none is **the ungraded source**, and one with no known source is **black**.
- **Any held frame plays for one second** (user, 2026-09-29): a reference still (a chart, ball or size ref, which is one frame of a video), a frame hold (`M2` at 0) or any one frame cut, held for 24 frames whatever the EDL gives it, so the stringout runs longer than the EDL by that much. Taken from the source, such a frame is **coloured through its AMF** (input transform, CLF nodes, output transform) as Resolve shows it; a still's delivered EXR stays ungraded. An event with no known source is black for the same second.
- Burn-ins copied from Ben's frame (`burn-ins.png`): the name top centre, `Frame:` (the delivered frame number from 1001) bottom left, `Primary Effect: <CSV Scene>` bottom centre, `SHOT_elem` bottom right. Audio from `pl` events only. The file's own timecode starts at the EDL's record start.
- Named `turnover###_MM_DD_YYYY_<shooter>_SO_v##.mp4` (`naming.stringout_stem`), dated as the turnover folder, in `<show>/_reports/`, and named in the tracker's `Turnover Stringout (Edit)` column.
- **Picture in picture on a plate** (user, 2026-09-29): over each `pl` event, the shot's **cp top left** and **wit top right**, each 480x270 flush in its corner (Resolve's zoom 0.25 at X -720/+720, Y 405). The first cp and the first wit of the shot in EDL order, from their **delivered HD references**, each playing from its own cut In at the plate's first frame, and **gone** when it runs out or at the plate's Out, whichever is first. No cp or wit, or none delivered: no inset in that corner. The top centre name sits between them (x 499 to 1411 on turnover097). Each inset carries its own element (`cp01`, `wit01`) burned in bottom left inside it, Open Sans 32 px against the frame's 42 (user, 2026-09-29), and it goes when the inset does.
- Built at the end of a Run for every turnover it delivered to, and from **Build Stringout** on a turnover heading. Checked before its rename (QC-142, which never blocks a run); events not cut from a reference are listed (QC-143).
- History: dropped 2026-09-11 and again 2026-09-22 on the belief that the colour session exported one. That belief was wrong and the decision is reversed.

FR-10 Exports
- `shot_tracker.xlsx` via openpyxl, **rows to paste into the studio's own tracker**: its 39 columns in its own order, nine of them written and the other thirty left empty because the vendor's team owns them (OQ-2, answered 2026-09-11 from the real sheet). The column layout was to be loaded from a template file in Settings, which was right while nobody knew the columns and is a configuration point standing where a fact belongs now that they are known.
- `qc_ingest_log.xlsx` with sheets: Summary, Shots (**two In/Out pairs: Delivered, the range the turnover's EDL and CSV state, and Final, the range that rendered**; the colourist's export is the turnover since 2026-09-22, so the shooters' range and the approved one are the same range, plus duration, shot code changes, skip reasons), Deliverables (one row each with path, version, size, checksum, every QC rule result). Three sheets since 2026-09-22: Side Files and Camera Data went with the deliverables they described.

FR-11 Batch file
- `.pibatch` JSON, schema versioned. Contains everything needed to reopen: turnovers, rows, snapshots, edits, probe cache, delivery root, render status, settings overrides. Autosave on every edit (debounced 500 ms). Backup copy kept on open.

FR-12 Settings page
Sections: General (delivery root default, path map, concurrency, GPU), Rules (min/max duration frames, expected handle frames, allowed fps, expected resolutions), **Colour (read only since 2026-09-28: the ACES config, "each clip's AMF and its CLFs" as where colour comes from, and "each clip's AMF" as the output transform; the input transform table is gone)**. **The EDL's location is not a setting**: it is the one in the turnover folder, read at scan and recorded on the turnover (`Turnover.color_session_edl`), because it is a record of what this work was rendered from rather than a preference. **No source encoding mode**: the clip's AMF names the encoding per clip and DaVinci Wide Gamut is one more input transform rather than a mode to switch into, Naming (show prefix regex, type table overrides), Output (mp4 quality, EXR compression level), Advanced (ffmpeg path override, OCIO config override, log level).

FR-13 Logging
- Rotating log file in the app data folder. Every ffmpeg command line logged. In-app log panel with filter by row.
- **Save Logs as CSV** (2026-09-23): every kept log file as one CSV, headed by the build and machine, for the editor to send for diagnostics (UI_SPEC section 6.1). It carries every QC result at its own severity, with what blocks the run marked (2026-09-28).

FR-14 Metadata pane
- A read-only pane to the right of the shot list. Selecting a row shows everything known about that clip: identity, source media, frame rate, ranges, colour, audio, turnover, and a QC summary. Full field list and behaviour in `docs/UI_SPEC.md` section 12.
- It shows what the list has no column for (codec, pixel format, start timecode, file size, the paths themselves), rather than repeating the columns.
- Read only. The list owns every edit per FR-5, so the pane never writes to the model and never takes keyboard focus. Ctrl+I toggles it.
- Multi-selection shows the fields the selection agrees on and marks the rest "mixed", which is how an editor spots one clip at the wrong resolution in a turnover of thirty.
- Values are individually copyable, paths and checksums especially.
- Primarily serves the AD and VFX supervisor described in section 2, who sit with the editor during review and read rather than operate. camData is not read (2026-09-22), so lens, filter and body do not surface in the UI.

FR-15 Colour pipeline
- **Since 2026-09-28 (user) the colour is each clip's AMF and the CLFs it names**, and the CDL and the CSV encoding are not read; there is no fallback. The bullets after this one that name the CDL, ACEScct or the input transform table record the 2026-09-12 to 2026-09-27 design and are superseded where they disagree with this one.
- Per shot the chain is: decode to float, override the container's colour tags and confirm range, then **the AMF's input transform into ACES2065-1, the AMF's looks in order (the Reference Gamut Compress, then each CLF, every Resolve CLF being ACES2065-1 in and out), then ACES2065-1 to linear ACEScg** for the plate. The reference adds **the AMF's output transform** (turnover097: `ACES 2.0 - SDR 100 nits (Rec.709)` on `Gamma 2.2 Rec.709 - Display`). The aux still gets the input transform alone. A look marked `applied="true"` is skipped. The tool has no working space of its own.
- **Every AMF transform ID is resolved by the pinned config** through its own `interchange: amf_transform_ids`; there is no table. An input ID it lacks is QC-047, none at all QC-046, an output ID it lacks QC-079, and a look it cannot apply (a look ID it lacks, an embedded CDL, anything not an ID or a CLF) is ignored with a warning, QC-077. A CLF missing, changed since the export (md5) or unreadable is QC-076.
- **Grades are primaries plus simple sky secondaries** (user, 2026-09-28). A window or other spatial operation inside a node does not survive into a CLF and cannot be detected from one.
- **Not verified**: that the tool's render matches Resolve's own (no Resolve frame has been provided; the graded EXR in the repo is Turnover121's), how Resolve names an EXR sequence plate in the CSV against the AMF, and what the `VFX Request` preset does differently from `Dailies Request` (QC-078).
- Working space is **ACEScg**. Every deliverable is graded, with the approved look applied from the **CDL on the shot's event in the final EDL, in ACEScct** (decided 2026-09-18, superseded 2026-09-28 above). There are no per-shot grade files (2026-09-21): the CDL is the only carrier. The EXR header records the CDL that was applied. Full policy, both branches and the reasoning are in `docs/COLOR_AND_FORMAT.md` section 1, which is the spec. This entry records that the pipeline exists and what it owes.
- Transforms come from **OpenColorIO** as a single `GroupTransform` per shot, interpolated **tetrahedrally**, using a pinned ACES 2.0 built-in config so no config files ship and no dependency bump changes what a reference looks like (OQ-29). Curves and matrices are never hand written.
- *(Superseded 2026-09-28.)* Per shot the chain is: decode to float, **override the container's colour tags** with the encoding the clip's metadata names and confirm range, then the input transform that encoding names **into ACEScct**, the shot's CDL, then ACEScct to linear ACEScg (decided 2026-09-18, OQ-46). This reverses OQ-37's 2026-09-12 answer: Resolve's CDL export carries node one's primaries and means something only in the timeline space, so the tool converts on both sides of it.
- *(Superseded 2026-09-28.)* **The source encoding is named in the clip's metadata, per clip, and there is no mode** (`docs/COLOR_AND_FORMAT.md` section 1, decided 2026-09-12). Camera native log is the expectation; **DaVinci Wide Gamut / DaVinci Intermediate is one more entry in the input transform table**, not a batch-wide setting, so a turnover may mix a shooter on a house template with two on their cameras and nothing has to be switched before it is scanned.
- *(Superseded 2026-09-28.)* **On every plate the source encoding is a transform**, the leg into ACEScct ahead of the grade (2026-09-18). It goes in the EXR header so a delivered frame says what it was made from, and it is what QC-018 and QC-021 check against. A wrong one grades the wrong pixels, so QC-046 and QC-047 block a plate as they block an aux still.
- *(Superseded 2026-09-28.)* **The tool carries multiple input transforms and picks one per shot from the clip's metadata** (required 2026-09-12). It is an explicit table from the string a shooter wrote to one OpenColorIO colour space, extensible by adding a row, naming a curve and a gamut together because a curve alone does not identify one, and refusing anything it cannot resolve to exactly one entry (QC-047) rather than reaching for the nearest. OQ-34 is that table and OQ-44 is what its keys are.
- *(Superseded 2026-09-28.)* **Where that transform is applied is a correctness rule, not a diagram detail.** Since 2026-09-18 it is applied on **every** row the tool transforms: into ACEScct ahead of the grade on a plate or reference, and straight to ACEScg on the **aux still**, which is delivered ungraded, and on any row with no grade at all. The grade is never applied in any other space and never applied twice, and `ShotColor.plate_transforms` builds the whole chain so a caller cannot assemble half of one. OQ-46 recorded the earlier uncertainty and is decided.
- **The aux still is the sharpest case and the reason the table is load bearing regardless.** A mis-converted colour chart still looks exactly like a chart and is the one thing a compositor matches against, so an unresolvable encoding blocks that deliverable rather than approximating it. Whether the colour session should hand the stills over already converted, deleting the tool's last transform of its own, is OQ-45.
- The plate branch takes the graded ACEScg and resizes unbounded in numpy. The view branch adds the AMF's output transform to the same chain (the ACES output transform on the same three legs until 2026-09-28) and collapses the pair into **one 3D LUT per shot**, generated in core and applied by ffmpeg `lut3d` for the reference. It has one consumer since the viewers were dropped (FR-16); the cube is the thing to hand a viewer if one ever returns.
- The EXR header records the source encoding (`proingest/source_encoding`, origin `AMF`), the AMF's file name (`proingest/amf`) and the looks applied in order (`proingest/looks`, CLFs by file name), so a delivered plate can be traced to the session's export. The seven `proingest/cdl_*` attributes that recorded the CDL until 2026-09-28 are gone.
- ~~**A cube that contains a display rendering is refused**, QC-039~~ **Retired 2026-09-21 with the per-shot grade file.** A CDL is four numbers per channel and cannot hide a tone map. The failure it guarded against - a display referred file claiming to be scene linear - is real and returns with any future grade file, and nothing downstream would notice until the comp was wrong.
- ~~A row whose event carries no CDL cannot render. QC-009, error~~ **Since 2026-09-28 QC-009 is info**: a clip whose AMF carries no CLF is one Ben left ungraded, his decision rather than a fault, and it renders through its input transform and the Reference Gamut Compress. A row no AMF grades cannot render (QC-075).

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
M6 Stringout with burn-ins. **Dropped 2026-09-11, back and built 2026-09-25** (`core/stringout.py`, FR-9). Ben does not export one.
M7 Packaging: PyInstaller `.app`, disk image, bundled ffmpeg, first-run experience, icon.
M8 Polish pass against `docs/UI_SPEC.md`, performance on a real turnover, docs.
M9 The user guide (FR-17, added 2026-09-12): install guide, quickstart, a reference section per surface of the window, screenshots from a harness, delivered as one document the studio can keep.

## 10. v02 backlog (do not build in v01, but do not design against it)

- Frame viewer. Removed from v01 twice now, which is worth noting before anyone adds it a third time: it was a v02 item from the start, was promoted into v01 on 2026-09-11 as three steppable viewers, and was removed again on 2026-09-11 because the review that needed pictures moved to Resolve. It needs a decoded frame cache per row and the viewing LUT that M4.5 builds anyway.
- Per shot colour controls in the tool, if the round trip through the colour session ever proves too slow for a review session. Removed from v01 deliberately (section 3).
- Burn-ins on reference mp4s.
- Windows 11 build. Intended, not committed (OQ-24).
- Google Apps Script hyperlink export for the tracker.
