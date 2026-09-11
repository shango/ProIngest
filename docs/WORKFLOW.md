# Workflow

Who does what, in order. Three entities: **Shooters**, **Ben** (colour), **Tool**.

The spec behind this is `COLOR_AND_FORMAT.md` section 1 and `PRD.md`. This page is the
one-line version, for checking that everyone means the same thing.

## Shooters

| # | step | output |
|---|---|---|
| 1 | Shoot, then conform each shot in Resolve and apply the camera's own input transform there. | nothing yet, this is setup |
| 2 | Deliver one file per shot, cut with handles, in the **studio standard log encoding** (OQ-39). | ProRes 4444 log, one per shot |
| 3 | Export the timeline. | `.otio` |
| 4 | Deliver an offline string-out and a CDL as a record of intent. | string-out, CDL. **Both are superseded by Ben's final versions and the tool reads neither** |
| 5 | Deliver the per shot extras. | HDRI, camData, reference stills, BTS, lens grid folder |

## Ben

| # | step | output |
|---|---|---|
| 6 | Take the AD meeting's decisions into a Resolve session set to ACES 1.3 with an ACEScct timeline. | nothing yet, this is setup |
| 7 | Grade each shot **primary only**: no windows, no qualifiers, no tracked secondaries. | the approved look |
| 8 | Export the updated final edit list, with the approved grade carried in it. | **final `.edl` carrying one CDL per shot** as `*ASC_SOP` / `*ASC_SAT` lines: timecode, shot IDs and grade in one file |
| 9 | Export the stringout with the look and burn-ins. | ProRes QT. **The tool no longer builds one** |

## Tool

| # | step | output |
|---|---|---|
| 12 | Scan the turnover: parse the timeline, match media, probe it, find audio and side files. | the shot list |
| 13 | Run pre-flight checks on every row and block the ones that cannot be delivered. | QC-0xx results |
| 14 | Let the editor review and trim In and Out with the AD and supervisor watching. | edited In/Out per shot |
| 15 | Read the final EDL and match its CDL to every row. | a CDL per row, or QC-008 / QC-009 |
| 16 | Apply the input transform and the CDL, then write the graded plates. | 4k and HD EXR, ACEScg, DWAA 45, frames from 1001 (OQ-35) |
| 17 | Bake the CDL and the ACES output transform into one LUT and encode the references with it. | 4k and HD H.264 mp4, sRGB |
| 18 | Copy audio and side files, renamed to spec. | wav, HDRI, camData, stills |
| 19 | Verify every deliverable the moment it lands, and keep any that fails for inspection. | QC-1xx results |
| 20 | Write the spreadsheets. | `shot_tracker.xlsx`, `qc_ingest_log.xlsx` |

## What the tool is for

**Checking all media, running QC, and producing every turnover output.** It does not author
colour, it does not cut a stringout, and it does not decide anything creative. Everything it
writes is either a deliverable named from the spec or a report about one.

## The three rules that hold it together

1. **Colour is authored once, by Ben.** The shooters' CDL is a starting point, superseded by
   the final one, and the tool has no colour controls at all.
2. **Nothing final renders before step 15.** Steps 12 to 14 work without Ben; steps 16 onward
   do not.
3. **A CDL says four things and no more**: slope, offset and power per channel, plus saturation.
   A curve or a hue wheel in the session does not reach the tool at all. Compare a reference
   against Ben's stringout the first time this runs (OQ-31).

## Still open

- **OQ-39**, step 2: which log encoding is the studio standard. ACEScct means the tool applies
  no input transform at all.
- **OQ-30**, step 15: which EDL field identifies an event, so a neighbouring shot's grade is
  never applied. Wants one real EDL out of the session.
- **OQ-35**, step 16: EXR frame numbers from 1001, or derived from source timecode.
