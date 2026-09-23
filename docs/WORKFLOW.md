# Workflow

Who does what, in order. Three entities: **Shooters**, **Ben** (colour), **Tool**.

This page is the one-line version, for checking that everyone means the same thing. The spec
behind it is `COLOR_AND_FORMAT.md` section 1 and `PRD.md`.

> **Rewritten 2026-09-21** from the user's own description of the workflow, after
> `docs/DOC_AUDIT_2026-09-21.md` found this page wrong in most of its rows. Everything that was
> here about an `.otio`, ProRes 4444, `Input Color Space` and per-shot `.cube` files was
> describing a delivery that does not happen.

## Shooters

| # | step | output |
|---|---|---|
| 1 | Shoot. **Some camera systems record RAW, some do not.** | camera media |
| 2 | **Only where RAW was recorded**, debayer to a basic file type, **baking in nothing and choosing no colours**. The encoding stays camera-native log. | a decodable mezzanine per clip. RAW itself never leaves this step |
| 3 | Bring the clips into Resolve and **set every clip to 24.000 even**. | the project conform |
| 4 | Cut a **stringout**. | offline stringout. **Superseded by Ben's** and the tool reads it never |
| 5 | **Fill in the clip metadata**: the shot code in `Shot`, what the clip is in `Shot Type` (`pl`, `cp`, or a reference type - see the table below), the encoding in `Gamma Notes` and `Color Space Notes`. | the metadata that every deliverable's name and colour depends on |
| 6 | **Media Management > Copy with trim, consolidating, not transcoding.** | one file per timeline clip: camera filename kept, camera timecode kept, handles both sides, nothing recompressed. Resolve also writes a `.drt` beside the media as a by-product, which **nothing downstream uses** |
| 7 | Hand the consolidated timeline **and the metadata** to Ben. | the turnover folder, plus the metadata export (see the note below) |
| 8 | Put the per-shot extras in the turnover. | HDRI, camData, BTS, lens grid folder. **None of these is a tool deliverable** (2026-09-22): they carry no `Shot Type`, so the tool ignores them and they are delivered by hand |

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
| 10 | Take the AD meeting's decisions into a **colour managed** Resolve session, ACES 1.3, timeline **ACEScct**, each clip's Input Color Space set to its camera encoding (`COLOUR_SESSION_EXPORT.md`). | nothing yet, this is setup |
| 11 | **Final trims** with the AD, and grade **in node one with the wheels**, Luma Mix 0, Offset rather than Lift. No windows, no qualifiers, no tracked secondaries. | the approved cut and the approved look |
| 12 | Cut the **final stringout timeline** and render the stringout from it. **Ben produces and exports it, and the tool does nothing with it at all** (user, 2026-09-22): it is not read, not transcoded, not renamed and not checked. | the delivered stringout, delivered by Ben |
| 13 | Export the **EDL with the CDL in it** from that same stringout timeline (Timelines > Export > CDL). **This is the conform and the grade**, and because it comes off the stringout its events state the final clip durations. | `.edl`: shot identity, the approved In/Out, and `*ASC_SOP` / `*ASC_SAT` per event |
| 14 | Export the **metadata CSV**. **This is identity and encoding.** | `.csv`: `File Name`, `Shot`, `Shot Type`, `Gamma Notes`, `Color Space Notes` |
| 15 | Put the EDL and the CSV **in the same folder as the media** and hand that one folder over (OQ-74). | one folder holding the media, the EDL and the CSV. A folder missing either file does not scan at all (QC-001) |

## Tool

| # | step | output |
|---|---|---|
| 16 | Scan the turnover: **the folder, Ben's EDL and Ben's CSV**. Identity from `Shot` + `Shot Type`, encoding from `Gamma Notes` + `Color Space Notes`, media matched by `File Name`. | the shot list |
| 17 | Run pre-flight checks on every row. A **must-fix** blocks the run until the user drops the correction into the folder and re-scans; an **info** is shown and never blocks (2026-09-23, `REVIEW_2026-09-23.md` section 4). | QC-0xx results |
| 18 | Read the EDL for the approved In/Out and the CDL per event. **An event belongs to the row whose file's timecode range contains its source range**: Ben's real EDL carries no `FROM CLIP NAME` and reels every event `AX` (2026-09-23). The plate is **the cut only**, no handles. | the conform and the grade, or QC-008 / QC-009 / QC-066 |
| 19 | Let the editor make the occasional one-off trim not worth a trip back to Resolve. | QC-045 on any row that moved |
| 20 | Convert each clip into ACEScct from the encoding its metadata names, apply the CDL, convert to ACEScg, write the plates. | 4k and HD EXR, ACEScg, DWAA 45, frames from 1001 (OQ-35) |
| 21 | Bake that chain plus the ACES output transform into one LUT and encode the references through it. | 4k and HD H.264 mp4 |
| 22 | Deliver the single-frame reference stills, **converted but never graded**, each at **its EDL event's frame**. A still with no event is a must-fix, never a guess. | `<shot>_colorChart_01_4k_v01.exr` and the rest, keyed to the **shot code**, not to an element |
| 23 | Deliver the audio of each plate row, renamed to spec, **trimmed to the same event as the picture and retimed by 1000/1001 so it follows the 24 fps video** (2026-09-23). Its contents are not judged. | wav |
| 24 | *(was: transcode and name Ben's stringout. **Removed 2026-09-22** - the tool does nothing with the stringout.)* | nothing |
| 25 | Verify every deliverable **under its temp name**, and rename only when it passes. A failure leaves nothing that looks finished: the row is marked failed, naming the output and why, and the user fixes the cause and **resets the row** to re-run it (2026-09-23). | QC-1xx results |
| 26 | Write the spreadsheets. | `shot_tracker_<batch>_<date>.xlsx` and `qc_ingest_log_<batch>_<date>.xlsx` |

## What the tool is for

**Checking all media, running QC, and producing every turnover output.** It does not author
colour, it does not cut a stringout, and it does not decide anything creative. Everything it
writes is either a deliverable named from the spec or a report about one.

## The rules that hold it together

1. **Colour and the cut are both decided once, by Ben and the AD.** The shooters' stringout is a
   starting point, superseded by Ben's. The tool has no colour controls and no viewers, and its
   In/Out editing exists for the one-off trim not worth a new EDL.
2. **Nothing final renders before step 18.** Steps 16 and 17 work without Ben; step 20 onward do
   not.
3. **The grade is the CDL, applied in ACEScct.** Resolve's CDL export carries node one's primaries
   and means something only in the session's timeline space, so the tool converts each clip into
   ACEScct from the encoding its metadata names, applies the CDL, and converts out to ACEScg.
   ACEScct is the standard the session is set to; a session set to anything else grades wrong and
   nothing errors, which is why it is a constant in the tool rather than a setting.
4. **There are no per-shot grade files.** Decided 2026-09-21: the CDL is the only grade carrier,
   and the `.cube` from Generate LUT that used to be the exception is gone.
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
   row - HDRI, camData, BTS, the lens grid, Ben's stringout - is delivered by hand or by Ben, and
   the tool does not touch it. The one exception is a plate's **audio**, which has no row of its
   own and rides along with its `pl` row. **A `Shot Type` the tool does not recognise is a
   must-fix warning** and gets no deliverables (user, 2026-09-23); so is the same shot code, type
   and index on two rows. `BTS` and `lensgrid` are ignored when they carry no `Shot Type`.
7. **A trim does not disturb the grade.** The CDL is one static transform for the whole shot, so
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
  Two decisions are the user's.
- **OQ-60**, step 20: the decode asserts no matrix, and is measurably BT.601 where it should
  almost certainly be BT.709 - 1.94% mean and 21.3% peak error in the delivered plate. Wants one
  original camera file.
- **OQ-55**, steps 10 to 14: the test export, one shot through the real chain.
- **OQ-30**, step 18: which EDL field identifies an event. Wants one real EDL.
- **OQ-35**, step 20: EXR frame numbers from 1001, or derived from source timecode.
