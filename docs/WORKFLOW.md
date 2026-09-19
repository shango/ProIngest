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
| 6 | Take the AD meeting's decisions into a Resolve session: **colour managed, ACES 1.3, timeline ACEScct**, each clip's Input Color Space set to its camera encoding (`COLOUR_SESSION_EXPORT.md`). | nothing yet, this is setup |
| 7 | Trim each shot with the AD, and grade it **in node one with the wheels**, Luma Mix at 0, Offset rather than Lift. No windows, no qualifiers, no tracked secondaries. | the approved cut and the approved look |
| 8 | Export the updated final edit list with the CDL in it (Timelines > Export > CDL). **This is the grade** (2026-09-18). | **final `.edl`**: timecode, shot IDs, the approved In/Out, and the grade as `*ASC_SOP` / `*ASC_SAT` lines on each event |
| 9 | Export the grade per shot with Generate LUT, from a node graph whose first and last nodes are the Color Space Transforms **from the encoding the clip arrived in** and **to linear ACEScg** (`COLOUR_SESSION_EXPORT.md`). | **one 65 point `.cube` per shot**, named with the shot code, `source encoding in > grade > linear ACEScg out`, with **no display rendering in it**. This is the whole of what the tool applies. **Not a CLF: Resolve writes none** (2026-09-18) |
| 9a | Save the EDL, the stringout and any cubes for each turnover in a folder **named exactly as that turnover's folder**, inside `_color` beside the turnovers on the mount (OQ-53). | the tool finds it when the turnover is scanned and offers to ingest it; anywhere else, the editor points at the EDL |
| 10 | Export the stringout with the look and burn-ins. | ProRes QT. **The tool no longer builds one**, and it is what the tool's references get checked against |

## Tool

| # | step | output |
|---|---|---|
| 12 | Scan the turnover: parse the timeline, match media, probe it, find audio and side files. | the shot list |
| 13 | Run pre-flight checks on every row and block the ones that cannot be delivered. | QC-0xx results |
| 14 | Read Ben's final EDL for the conform and the grade, and pair any cube with its shot. | approved In/Out and the CDL to apply per row, a cube in its place where one was delivered, or QC-008 / QC-009 |
| 15 | Let the editor check the list and make the occasional one-off trim not worth a trip back to Resolve. | QC-045 on any row that moved |
| 16 | Convert each clip into ACEScct from the encoding its metadata names, apply the CDL (or the shot's cube), convert to ACEScg, then write the graded plates. | 4k and HD EXR, ACEScg, DWAA 45, frames from 1001 (OQ-35) |
| 17 | Bake that chain and the ACES output transform into one LUT and encode the references with it. | 4k and HD H.264 mp4, sRGB |
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
3. **The grade is the CDL, applied in ACEScct** (2026-09-18, reversing the 2026-09-12 rule that
   the tool converted nothing ahead of the grade). Resolve's CDL export carries node one's
   primaries and means something only in the session's timeline space, so the tool converts
   each clip into ACEScct from the encoding its metadata names, applies the CDL, and converts
   out to ACEScg. ACEScct is the standard the session is set to; a session set to anything else
   grades wrong and nothing errors, which is why it is a constant in the tool and a line on the
   export page rather than a setting.
4. **A cube takes the CDL's place for a shot that needed more than the wheels.** Generate LUT on
   a clip in that same managed session holds the node graph, ACEScct in and out, and where one
   names a shot the tool applies it instead of the CDL, in the same slot. The header of every
   plate says which was applied.
5. **A cube must be the grade alone.** A display rendering inside it produces a plate that comps
   wrong and looks perfectly normal (QC-039).
6. **A trim does not disturb the grade.** A grade file is one static transform for the whole shot, so
   moving In or Out carries it unchanged. Extending into the handles does apply the approved
   grade to frames Ben never saw, which is why step 15 is for one-offs.

## Still open

- **OQ-44**, steps 1 and 2: which metadata field carries the encoding and exactly what string
  goes in it. The tool reads `Input Color Space`, and "S-Log3" on its own names four colour
  spaces in the pinned config, so the instruction to the shooters has to ask for the gamut too.
  **OQ-39 dissolved on 2026-09-12**: there is no studio standard encoding and no mode.
- **OQ-55**, steps 6 to 9: the test export. One shot graded with the wheels in node one, in a
  session set up as step 6 says, handed over as the EDL, the stringout and a cube of the same
  clip. The tool renders it both ways and compares each to the stringout. It confirms the CDL
  replayed in ACEScct matches the session, and that the tool's camera conversion agrees with
  Resolve's. OQ-46 was decided on 2026-09-18 and this is what checks the decision.
- **OQ-30**, step 14: which EDL field identifies an event, so a neighbouring shot's conform is
  never used. Wants one real EDL out of the session.
- **OQ-33**, step 14: what pairs a cube with a shot, the shot code in its name. Only the
  exception needs pairing now; the CDL sits on the event the row already matched.
- **OQ-35**, step 16: EXR frame numbers from 1001, or derived from source timecode.
