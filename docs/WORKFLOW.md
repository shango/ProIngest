# Workflow

Who does what, in order. Three entities: **Shooters**, **Ben** (colour), **Tool**.

The spec behind this is `COLOR_AND_FORMAT.md` section 1 and `PRD.md`. This page is the
one-line version, for checking that everyone means the same thing.

## Shooters

| # | step | output |
|---|---|---|
| 1 | Shoot, then conform each shot in Resolve and **name the camera's encoding** in the clip's `Input Color Space` field. **Do not convert it** (2026-09-12). | nothing yet, this is setup |
| 2 | Deliver one file per shot, cut with handles, in **whatever the camera shot**: camera native log, or DaVinci Wide Gamut as one more value rather than a mode (OQ-44). | ProRes 4444 log, one per shot |
| 3 | Export the timeline. | `.otio` |
| 4 | Deliver an offline string-out and a CDL as a record of intent. | string-out, CDL. **Both are superseded by Ben's final versions and the tool reads neither** |
| 5 | Deliver the per shot extras. | HDRI, camData, reference stills, BTS, lens grid folder |

## Ben

| # | step | output |
|---|---|---|
| 6 | Take the AD meeting's decisions into a Resolve session set to ACES 1.3. | nothing yet, this is setup |
| 7 | Trim each shot with the AD, and grade it **primary only**: no windows, no qualifiers, no tracked secondaries. Curves and log wheels are fine, and rule 4 says why. | the approved cut and the approved look |
| 8 | Export the updated final edit list. | **final `.edl`**: timecode, shot IDs, the approved In/Out, and the CDL as `*ASC_SOP` / `*ASC_SAT` lines |
| 9 | Export the grade per shot as a transform, **starting from the encoding the clip arrived in**. | **one `.clf` per shot**, `source encoding in > grade > linear ACEScg out`, with **no display rendering in it**. This is the whole of what the tool applies |
| 9a | Save the EDL and the CLFs for each turnover in a folder **named exactly as that turnover's folder**, inside `_color` beside the turnovers on the mount (OQ-53). | the tool finds it when the turnover is scanned and offers to ingest it; anywhere else, the editor points at the EDL |
| 10 | Export the stringout with the look and burn-ins. | ProRes QT. **The tool no longer builds one**, and it is what the tool's references get checked against |

## Tool

| # | step | output |
|---|---|---|
| 12 | Scan the turnover: parse the timeline, match media, probe it, find audio and side files. | the shot list |
| 13 | Run pre-flight checks on every row and block the ones that cannot be delivered. | QC-0xx results |
| 14 | Read Ben's final EDL for the conform, and pair each row with its CLF. | approved In/Out, a CDL on record and a CLF to apply, or QC-008 / QC-009 |
| 15 | Let the editor check the list and make the occasional one-off trim not worth a trip back to Resolve. | QC-045 on any row that moved |
| 16 | Apply the CLF and nothing before it, then write the graded plates. | 4k and HD EXR, ACEScg, DWAA 45, frames from 1001 (OQ-35) |
| 17 | Bake the CLF and the ACES output transform into one LUT and encode the references with it. | 4k and HD H.264 mp4, sRGB |
| 18 | Copy audio and side files, renamed to spec. | wav, HDRI, camData, stills |
| 19 | Verify every deliverable the moment it lands, and keep any that fails for inspection. | QC-1xx results |
| 20 | Write the spreadsheets. | `shot_tracker_<batch>_<date>.xlsx` and `qc_ingest_log_<batch>_<date>.xlsx`, under `<delivery root>/<show>/_reports/` |

## What the tool is for

**Checking all media, running QC, and producing every turnover output.** It does not author
colour, it does not cut a stringout, and it does not decide anything creative. Everything it
writes is either a deliverable named from the spec or a report about one.

## The rules that hold it together

1. **Colour and the cut are both decided once, by Ben and the AD.** The shooters' CDL is a
   starting point, superseded by the final one. The tool has no colour controls and no viewers,
   and its In/Out editing exists for the one-off trim that is not worth a new EDL for.
2. **Nothing final renders before step 14.** Steps 12 and 13 work without Ben; steps 16 onward
   do not.
3. **The tool applies no input transform ahead of a CLF** (2026-09-12). The CLF starts at the
   source encoding, so it is the whole conversion and doing one first converts twice - which
   looks like a grade decision and passes every check. The tool's own input transform table is
   used on the one deliverable that never gets a CLF, the ungraded reference still, and on any
   row the session did not grade.
4. **The CLF is applied, the CDL is recorded.** Both come from Ben's session and they are not
   duplicates: the CLF carries everything a primary grade can contain including curves and
   wheels, and the CDL is the readable version for anyone without an OCIO install. Where they
   differ, the CLF is what is in the pixels.
5. **The CLF must end in scene linear ACEScg.** A display rendering inside it produces a plate
   that comps wrong and looks perfectly normal (QC-039).
6. **A trim does not disturb the grade.** A CLF is one static transform for the whole shot, so
   moving In or Out carries it unchanged. Extending into the handles does apply the approved
   grade to frames Ben never saw, which is why step 15 is for one-offs.

## Still open

- **OQ-44**, steps 1 and 2: which metadata field carries the encoding and exactly what string
  goes in it. The tool reads `Input Color Space`, and "S-Log3" on its own names four colour
  spaces in the pinned config, so the instruction to the shooters has to ask for the gamut too.
  **OQ-39 dissolved on 2026-09-12**: there is no studio standard encoding and no mode.
- **OQ-46**, step 9: whether a real session's CLF really does start at the source encoding. If
  it does not and the tool converts as well, it converts twice, nothing fails, and both images
  look plausible. One real export settles it.
- **OQ-30**, step 14: which EDL field identifies an event, so a neighbouring shot's conform is
  never used. Wants one real EDL out of the session.
- **OQ-33**, step 14: what pairs a CLF with a shot, a filename convention or a sidecar. Same
  failure mode as OQ-30 and it wants the same one real export to answer it.
- **OQ-35**, step 16: EXR frame numbers from 1001, or derived from source timecode.
