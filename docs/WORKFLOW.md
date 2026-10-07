# Workflow

Who does what, in order. Three entities: **Shooters**, **Ben** (colour), **Tool**.

This page is the one-line version, for checking that everyone means the same thing. The spec
behind it is `COLOR_AND_FORMAT.md` section 1 and `PRD.md`.

> **Rewritten 2026-09-21** from the user's own description of the workflow, after
> `docs/DOC_AUDIT_2026-09-21.md` found this page wrong in most of its rows. Everything that was
> here about an `.otio`, ProRes 4444, `Input Color Space` and per-shot `.cube` files was
> describing a delivery that does not happen.
>
> **Colour moved to the AMF on 2026-09-28** (user). Ben's session exports one ACES Metadata File
> per EDL event and the CLFs each one names, and those are the whole of the colour: the CDL in the
> EDL and the CSV's colour columns are no longer read, and there is no fallback, because there
> will be no older turnovers. Steps 5, 8, 10, 11, 13 to 16, 18, 20 and 21 and rules 3, 4 and 7 are
> rewritten for it.

## Shooters

| # | step | output |
|---|---|---|
| 1 | Shoot. **Some camera systems record RAW, some do not.** | camera media |
| 2 | **Only where RAW was recorded**, debayer to a basic file type, **baking in nothing and choosing no colours**. The encoding stays camera-native log. | a decodable mezzanine per clip. RAW itself never leaves this step |
| 3 | Bring the clips into Resolve and **set every clip to 24.000 even**. | the project conform |
| 4 | Cut a **stringout**. | offline stringout. **Superseded by Ben's** and the tool reads it never |
| 5 | **Fill in the clip metadata**: the shot code in `Shot` and what the clip is in `Shot Type` (`pl`, `cp`, or a reference type - see the table below). `Gamma Notes` and `Color Space Notes` are **no longer read** (2026-09-28): the encoding reaches the tool in Ben's AMFs. | the metadata that every deliverable's name depends on |
| 6 | **Media Management > Copy with trim, consolidating, not transcoding.** | one file per timeline clip: camera filename kept, camera timecode kept, handles both sides, nothing recompressed. Resolve also writes a `.drt` beside the media as a by-product, which **nothing downstream uses** |
| 7 | Hand the consolidated timeline **and the metadata** to Ben. | the turnover folder, plus the metadata export (see the note below) |
| 8 | Put the per-shot extras in the turnover. | HDRI, camData, BTS, lens grid folder. **None of these is a tool deliverable** (2026-09-22): they carry no `Shot Type`, so the tool ignores them and they are delivered by hand. **An HDRI that is on the timeline with `Shot Type` `HDRI`** is a frame hold on the HDRI EXR with a pan: the tool delivers the EXR byte for byte, and the stringout shows Ben's pre-render of the event, a video under the EXR's name (QC-080, QC-083, user 2026-10-07) |

> **The metadata has to reach Ben, and how is worth pinning down.** The user's position
> (2026-09-21) is that it travels with the consolidated clips or in the CSV. In `Turnover199` it
> travelled **only** in the CSV: the consolidated MP4s carry no user data but Resolve's 72-byte
> encoder tag, and the `.drt` carries none either (all 81 blobs decoded and searched). That sample
> had `Shot Type` empty and little else filled, so it may simply not be representative. Either way
> the CSV is the carrier the tool reads, and a shooter whose metadata does not reach Ben leaves
> him exporting blank identity columns, after which the tool can name nothing. There is no check
> in front of this.

## Ben

| # | step | output |
|---|---|---|
| 9 | Import the consolidated timeline, and the shooters' metadata with it. | his session |
| 10 | Take the AD meeting's decisions into a **colour managed** Resolve session, ACES 2.0, each clip's input transform set to its camera encoding (`COLOUR_SESSION_EXPORT.md`). The timeline space no longer reaches the tool: each exported CLF carries its own trip into and out of it (ACEScct in turnover097). | nothing yet, this is setup |
| 11 | **Final trims** with the AD, and grade: **primaries plus simple sky secondaries** (user, 2026-09-28), in as many corrector nodes as it takes. | the approved cut and the approved look |
| 12 | Cut the **final stringout timeline**. **Ben does not render or export a stringout** (user, 2026-09-29): the tool builds it from his EDL (step 24). | the final timeline, in his session |
| 13 | Export the **EDL** from that same stringout timeline. **This is the cut**, and because it comes off the stringout its events state the final clip durations. Any `*ASC_SOP` / `*ASC_SAT` lines in it are **not read** (2026-09-28). | `.edl`: the approved In/Out per event, and any retimes |
| 13a | Export **one AMF per EDL event** from the same timeline, with the **CLF** for each corrector node it names (user, 2026-09-28). **This is the colour.** Turnover097 used Resolve's `Dailies Request` preset (QC-078, info); whichever preset arrives is used. | `.amf` per event, named with the timeline index (event number less one), and `..._ClipGraph_CorrectorNode_<n>.clf` beside it |
| 14 | Export the **metadata CSV**. **This is identity only** since 2026-09-28. | `.csv`: `File Name`, `Shot`, `Shot Type`. Its colour columns (`Gamma Notes`, `Color Space Notes`, `Input Color Space`) are not read |
| 15 | Put the EDL, the CSV, the AMFs and their CLFs **and the ALE** in the same folder as the media and hand that one folder over (OQ-74; the ALE since 2026-09-23). | one folder holding the media, the EDL, the CSV, the AMFs and CLFs, and the ALE. The `.otio` and `.drt` Resolve may write beside them are ignored. A folder missing the EDL or the CSV does not scan at all (QC-001); the ALE is what names the EDL's events, which timecode alone cannot do for cameras without time of day |

## Tool

| # | step | output |
|---|---|---|
| 16 | Scan the turnover: **the folder, Ben's EDL, Ben's CSV and his AMFs**. Identity from `Shot` + `Shot Type`, media matched by `File Name`. | the shot list |
| 17 | Run pre-flight checks on every row. A **must-fix** blocks the run until the user drops the correction into the folder and re-scans; an **info** is shown and never blocks (2026-09-23, `REVIEW_2026-09-23.md` section 4). | QC-0xx results |
| 18 | Read the EDL for the approved In/Out per event. **An event belongs to the row whose file's timecode range contains its source range**: Ben's real EDL carries no `FROM CLIP NAME` and reels every event `AX` (2026-09-23). The plate is **the cut only**, no handles. Then **each event's AMF**, found by the timeline index in its file name (event number less one, verified on all 15 of turnover097) and required to name the row's file; its input transform, looks and output transform are resolved through the pinned OCIO config's own AMF IDs, and each CLF it names is checked against the md5 the AMF recorded. | the conform and the grade, or QC-066, QC-075 to QC-079, QC-008; QC-009 (info) for a clip Ben left ungraded |
| 19 | Let the editor make the occasional one-off trim not worth a trip back to Resolve. | QC-045 on any row that moved |
| 20 | Convert each clip into ACES2065-1 through its AMF's input transform, apply the AMF's looks in order (the Reference Gamut Compress, then each CLF), convert to ACEScg, write the plates. | 4k and HD EXR, ACEScg, DWAA 45, frames from 1001 (OQ-35) |
| 21 | Bake that chain plus **the AMF's output transform** into one LUT and encode the references through it (turnover097: Gamma 2.2 Rec.709, not sRGB). | 4k and HD H.264 mp4 |
| 22 | Deliver the single-frame reference stills, **converted but never graded**, each at **its EDL event's frame**. A still with no event is a must-fix, never a guess. | `<shot>_colorChart_01_4k_v01.exr` and the rest, keyed to the **shot code**, not to an element |
| 23 | Deliver the audio of each plate row, renamed to spec, **trimmed to the same event as the picture and retimed by 1000/1001 so it follows the 24 fps video** (2026-09-23). Its contents are not judged. | wav |
| 24 | **Build the stringout** (OQ-38, PRD FR-9): Ben's final EDL as one HD mp4, cut from the delivered EXRs (an HDRI from its pre-render), the HD reference, the source through its AMF, or black standing in, everything graded but a style frame (shown as it is), with the burn-ins of `burn-ins.png`. At the end of a Run and from Build Stringout on a turnover heading or its stringout line, which shows its progress and a green or red ball. | `turnover###_MM_DD_YYYY_<shooter>_SO_v##.mp4` in `<show>/_reports/` |
| 25 | Verify every deliverable **under its temp name**, and rename only when it passes. A failure leaves nothing that looks finished: the row is marked failed, naming the output and why, and the user fixes the cause and **resets the row** to re-run it (2026-09-23). | QC-1xx results |
| 26 | Write the spreadsheets. | `shot_tracker_<batch>_<date>.xlsx` and `qc_ingest_log_<batch>_<date>.xlsx` |

## What the tool is for

**Checking all media, running QC, and producing every turnover output.** It does not author
colour, it does not cut a stringout, and it does not decide anything creative. Everything it
writes is either a deliverable named from the spec or a report about one.

## The rules that hold it together

1. **Colour and the cut are both decided once, by Ben and the AD.** The shooters' stringout is a
   starting point, superseded by Ben's final timeline. The tool has no colour controls and no viewers, and its
   In/Out editing exists for the one-off trim not worth a new EDL.
2. **Nothing final renders before step 18.** Steps 16 and 17 work without Ben; step 20 onward do
   not.
3. **The colour is each clip's AMF and its CLFs** (user, 2026-09-28). The AMF names the input
   transform, the looks and the output transform by ACES transform ID, and the pinned OCIO config
   resolves every ID itself (`interchange: amf_transform_ids`), so the tool holds no table. Every
   look is applied in ACES2065-1, because that is where the AMF puts them: each Resolve CLF takes
   ACES2065-1 in and gives it back, carrying its own trip into ACEScct and out around a 33 point
   3D LUT. The tool therefore has no working space of its own. A look it cannot apply is ignored
   with a warning (QC-077). **A window or any other spatial operation inside a node does not
   survive into a CLF, and nothing in the AMF or the CLF says one was there**, so the tool cannot
   detect it.
4. **The grade files are the CLFs the AMF names.** 2026-09-21 removed per-shot grade files and made
   the CDL the only carrier; 2026-09-28 reverses that: the CDL is no longer read, and a CLF that is
   missing, changed since the export or unreadable is an error (QC-076).
5. **The project rate is 24 and the tool asserts it.** An EDL states no frame rate - CMX 3600 has
   no field for one, and the reader takes the rate as an argument - and the `.drt` that could have
   stated it is not read. **Every source is treated as, and rendered at, 24, frame for frame**
   (user, 2026-09-23). A file stating 24000/1001 is the shooters' normal conform and is silent;
   **any other rate, 25 or 30, is a QC-026 must-fix and the batch does not run** until it is
   fixed. The rate is a constant today, not a setting.
6. **Identity is metadata, never a filename.** Camera filenames are delivered unchanged. Nothing
   parses a filename to learn what a clip is.
6a. **`Shot Type` is the whole of the tool's scope** (user, 2026-09-22). A CSV row that carries a
   `Shot Type` gets the deliverables for that type. **A clip with no `Shot Type` is ignored**: not
   named, not rendered, not blocked, not an error. The tool never infers a type from a duration, a
   track, a filename or a Resolve VFX flag. Everything in the turnover that is not a `Shot Type`
   row - HDRI, camData, BTS, the lens grid - is delivered by hand or by Ben, and
   the tool does not touch it. The one exception is a plate's **audio**, which has no row of its
   own and rides along with its `pl` row. **A `Shot Type` the tool does not recognise is a
   must-fix warning** and gets no deliverables (user, 2026-09-23); so is the same shot code, type
   and index on two rows. `BTS` and `lensgrid` are ignored when they carry no `Shot Type`.
7. **A trim does not disturb the grade.** The AMF's looks are one static transform for the whole shot, so
   moving In or Out carries it unchanged. Extending into the handles applies the approved grade to
   frames Ben never saw, which is why step 19 is for one-offs.

## Element codes and clip types

`Shot Type` names **what the clip is**. The full vocabulary, from the shooters' resources guide
(user, 2026-09-21):

| `Shot Type` | written by the tool | what it is | tool delivers |
|---|---|---|---|
| `pl`, `pl01`, `pl02` | `pl01`, `pl02` | main plate | 4k + HD EXR, 4k + HD ref mp4, audio wav |
| `cp`, `cp01`, `cp02` | `cp01`, `cp02` | clean plate | 4k + HD EXR, 4k + HD ref mp4 |
| `el`, `el01` | `el01` | element plate | 4k + HD EXR, 4k + HD ref mp4 |
| `wit`, `wit01` | `wit01` | witness cam | 4k + HD EXR, 4k + HD ref mp4 |
| `re`, `re01` | `re01` | recon plate | 4k + HD EXR, 4k + HD ref mp4 |
| `colorChart` | `colorChart_01` | reference still | one 4k EXR, converted, never graded |
| `mirrorBall` | `mirrorBall_01` | reference still | one 4k EXR, converted, never graded |
| `greyBall` | `greyBall_01` | reference still | one 4k EXR, converted, never graded |
| `sizeRef` | `sizeRef_01` | reference still | one 4k EXR, converted, never graded |
| `BTS` | - | behind the scenes, phone stills | **nothing** (user, 2026-09-22) |
| `lensgrid` | - | lens distortion chart | **nothing. Ben delivers it** (user, 2026-09-22) |
| `HDRI` | `pl01_HDRI_01` | HDRI, on the timeline as a frame hold with a pan | **the EXR, copied byte for byte, never checked**; the stringout shows the pre-render Ben puts beside it (`xxxx_001.mp4` beside `xxxx_001.exr`, QC-083) (QC-080, user 2026-10-07) |
| *anything else, or blank* | - | - | **nothing. The clip is ignored** |

The first nine rows are the tool's entire output. `BTS` and `lensgrid` stay in the vocabulary
because a shooter may still type them and the tool has to recognise them in order to pass over
them deliberately rather than treat them as unknown.

A bare code means index `01`; `pl` is `pl01`. Parsing ignores case, because the camel case is not
kept. Each shot code has exactly one of each reference still, so a bare `colorChart` is
`colorChart_01`. Reference stills are keyed to the **shot code**, not to an element.

**`el`, `wit` and `re` were omitted from the user's list by accident** and are confirmed to stay
(user, 2026-09-21). OQ-73 is closed with them: **`lensgrid` is delivered by Ben** and `raw` stays
the deliverable qualifier rather than a clip type. What follows is the reasoning, kept:

- **`raw`** appeared in the user's list. In the deliverable spec `raw` is not a clip type but the
  token separating the EXR sequence from the reference video (`_pl01_raw_4k_` against
  `_pl01_ref_4k_`), and `ref` is not listed beside it. Treated as the deliverable qualifier until
  told otherwise.
- **`lensgrid`** appeared in the user's list, which would make it a clip on the timeline. OQ-20
  says the lens grid arrives as a folder in the turnover and never as a clip, which is why the
  planner has nothing to plan for it. OQ-20's behaviour stands until this is settled.

## Still open

- **OQ-59**, step 20: the per-turnover default input transform, for a clip that names no encoding.
  Overtaken on 2026-09-28: the input transform comes from the clip's AMF and there is no fallback.
- **Not verified**, steps 13a to 21: that the tool's render matches Resolve's own (Ben provides no
  frame to compare, and the graded EXR in the repo is Turnover121's); how Resolve names an EXR
  sequence plate in the CSV against the AMF (only single-frame HDRI sequences seen); and what the
  `VFX Request` preset does differently.
- **OQ-60**, step 20: the decode asserts no matrix, and is measurably BT.601 where it should
  almost certainly be BT.709 - 1.94% mean and 21.3% peak error in the delivered plate. Wants one
  original camera file.
- **OQ-55**, steps 10 to 14: the test export, one shot through the real chain.
- **OQ-30**, step 18: which EDL field identifies an event. Wants one real EDL.
- **OQ-35**, step 20: EXR frame numbers from 1001, or derived from source timecode.
