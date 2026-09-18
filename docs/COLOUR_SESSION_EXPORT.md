# What the colour session exports, per turnover

The page to hand the colourist. Three files per turnover, into one folder, and the Resolve
setup that makes the second of them correct. `COLOR_AND_FORMAT.md` section 1 is the reasoning;
this is the instruction. Written 2026-09-18, when it was established that Resolve exports no
CLF and the per-shot grade file became a `.cube` (OQ-54).

## Where

One folder per turnover, **named exactly as the turnover's folder is named**, inside a `_color`
folder beside the turnovers on the shared mount:

```
<shared mount>/
  turnover001_02_23_2026_danielluckett/      the shooters' delivery
  turnover002_.../
  _color/
    turnover001_02_23_2026_danielluckett/    this page's three files, for that turnover
      turnover001_02_23_2026_danielluckett_final_v01.edl
      MELT0001_grade_v01.cube
      MELT0002_grade_v01.cube
      ...
      turnover001_02_23_2026_danielluckett_stringout_v01.mov
```

The tool looks there when the turnover is scanned and offers to ingest what it finds. Anywhere
else works too, through the Ingest Colour Session button, but then somebody has to know to
press it. If `_color` beside the turnovers is not writable, the folder named in Settings under
"Ingest opens at" is looked in first, with the same per-turnover folder name under it.

## One timeline per turnover

Import each shooter's turnover into the session as **its own timeline**, built from the
delivered clips themselves, unrenamed. The tool matches the EDL's events to shots by the clip
name Resolve writes into the `FROM CLIP NAME` comment, and a renamed or re-consolidated clip
matches nothing. Trim each shot with the AD on that timeline; the trimmed In and Out are the
approved cut and they leave in the EDL.

## The three files

### 1. The final EDL, with the CDL in it

Edit page, right-click the timeline in the Media Pool, **Timelines > Export > CDL**. That
writes an EDL whose events carry the approved In and Out, and the grade's `*ASC_SOP` and
`*ASC_SAT` lines. The manual's conditions for that export: one video track, no transitions, no
compound or nested clips. If the export refuses, one of those is the reason.

**There is no separate CDL file.** Resolve writes no `.cdl` or `.ccc`; the CDL is the comment
lines inside this EDL, so naming the CDL means naming the EDL. Name it after the turnover folder
with a version: `<turnover folder name>_final_v01.edl`. The tool does not read the name, but it
wants **exactly one `.edl` in the folder**: a re-export replaces the old file rather than
sitting beside it, because two EDLs in the folder is two cuts and the tool will not choose.

The tool reads the cut from this file and records the CDL as the readable form of the grade.
**It does not apply the CDL**; the cube is what it applies, and where the two differ the cube is
what is in the pixels.

### 2. One 65 point cube per shot

Color page, right-click the clip's thumbnail, **Generate LUT > 65 Point Cube**. Name the file
with the **shot code** and a version, for example `MELT0001_grade_v01.cube`. The tool pairs a
file to its shot by the shot code in the name and refuses to guess: no cube naming the shot
means that shot is not delivered (QC-009), and two cubes naming it means neither is used until
one is removed.

65 rather than 33 because the tool applies this to plates, not to a monitor.

### 3. The stringout

The ProRes QuickTime of the whole turnover with the look and burn-ins, as it is exported today.
The tool does not read it. It is what the tool's own reference mp4s are compared against the
first time a turnover goes through, and whenever something looks wrong.

## The setup that makes the cube correct

**Generate LUT bakes the clip's node graph and nothing outside it.** The tool needs the cube to
be the whole conversion, from the pixels as the shooter delivered them to the scene linear
ACEScg the plates are written in, with no viewing transform in it. So:

| | |
|---|---|
| Project colour management | **DaVinci YRGB**, not colour managed. Nothing is applied outside the node graph, so nothing is missing from the cube |
| First node of every clip | **Color Space Transform** from the clip's camera encoding, the same value the shooter wrote into the clip's `Input Color Space`, to **ACEScct**. Grade in the nodes after this one |
| Last node of every clip | **Color Space Transform** from ACEScct to **ACES AP1, Linear**, which is ACEScg |
| Viewing | The transform to the monitor, ACEScg to Rec.709 or sRGB, goes on the **timeline** node graph or as the project's **output LUT**. **Never on the clip.** A clip graph with it in bakes the display rendering into the plate, which looks right on every monitor and comps wrong; the tool checks for exactly this (QC-039) and refuses the shot |
| Grade | **Primary only.** Primaries, log wheels, custom curves, hue curves. No windows, no qualifiers, no tracking: Generate LUT drops them silently and the delivered grade would not be the approved one |

If the session is run colour managed in ACES instead, the cube comes out as the grade alone,
ACEScct in and ACEScct out, and the tool cannot tell that from a cube that contains the
conversion. Say so if that is the setup, because the tool then has to convert around it.

## The first time

Before the first real turnover: one shot graded in this setup, its cube and its EDL, handed
over. That single export confirms the cube starts and ends where this page says, that the EDL
carries the clip names and the CDL lines, and that the tool's reference matches the stringout.
It answers OQ-54, OQ-31, OQ-33 and OQ-46 together.
