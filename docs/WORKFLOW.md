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
| 4 | Deliver an offline string-out and a CDL as a record of intent. | string-out, CDL. **The tool reads neither** |
| 5 | Deliver the per shot extras. | HDRI, camData, reference stills, BTS, lens grid folder |

## Ben

| # | step | output |
|---|---|---|
| 6 | Take the AD meeting's decisions into a Resolve session set to ACES 1.3 with an ACEScct timeline. | nothing yet, this is setup |
| 7 | Grade each shot **primary only**: no windows, no qualifiers, no tracked secondaries. | the approved look |
| 8 | Export the grade per shot as `ACEScct in > CDL + look > linear ACEScg out`, with **no display rendering in it**. | one `.clf` per shot |
| 9 | Export the conform data. | `.edl` or `.xml`: timecode and shot IDs |
| 10 | Export a reference movie with the look and burn-ins. | ProRes QT. **This is the stringout**; the tool no longer builds one |
| 11 | Hand over something that says which CLF belongs to which shot (OQ-33, not yet settled). | sidecar |

## Tool

| # | step | output |
|---|---|---|
| 12 | Scan the turnover: parse the timeline, match media, probe it, find audio and side files. | the shot list |
| 13 | Run pre-flight checks on every row and block the ones that cannot be delivered. | QC-0xx results |
| 14 | Let the editor review and trim In and Out with the AD and supervisor watching. | edited In/Out per shot |
| 15 | Ingest Ben's package and match a CLF to every row. | a grade per row, or QC-008 / QC-009 |
| 16 | Apply the input transform and the CLF, then write the graded plates. | 4k and HD EXR, ACEScg, DWAA 45, frames from 1001 (OQ-35) |
| 17 | Bake the CLF and the ACES output transform into one LUT and encode the references with it. | 4k and HD H.264 mp4, sRGB |
| 18 | Copy audio and side files, renamed to spec. | wav, HDRI, camData, stills |
| 19 | Verify every deliverable the moment it lands, and keep any that fails for inspection. | QC-1xx results |
| 20 | Write the spreadsheets. | `shot_tracker.xlsx`, `qc_ingest_log.xlsx` |

## The three rules that hold it together

1. **Colour is authored once, by Ben.** The shooters' CDL is a starting point and the tool has
   no colour controls at all.
2. **Nothing final renders before step 15.** Steps 12 to 14 work without Ben; steps 16 onward
   do not.
3. **The CLF must end in scene linear ACEScg.** A display rendering inside it produces a plate
   that comps wrong and looks perfectly normal (QC-039).

## Still open

- **OQ-39**, step 2: which log encoding is the studio standard. ACEScct means the tool applies
  no input transform at all.
- **OQ-33**, step 11: what the sidecar is and what writes it. This one blocks the build.
- **OQ-35**, step 16: EXR frame numbers from 1001, or derived from source timecode.
