# What the colour session exports, per turnover

The page to hand the colourist. Two files per turnover into one folder, a third only when a
shot needs it, and the Resolve setup that makes the first of them mean what the tool takes it
to mean. `COLOR_AND_FORMAT.md` section 1 is the reasoning; this is the instruction. Rewritten
2026-09-18, the day the grade became **the CDL in the final EDL, applied in ACEScct** (OQ-46).
A version from the same morning asked for a cube per shot out of an unmanaged session; this
replaces it.

## Where

One folder per turnover, **named exactly as the turnover's folder is named**, inside a `_color`
folder beside the turnovers on the shared mount:

```
<shared mount>/
  turnover001_02_23_2026_danielluckett/      the shooters' delivery
  turnover002_.../
  _color/
    turnover001_02_23_2026_danielluckett/    this page's files, for that turnover
      turnover001_02_23_2026_danielluckett_final_v01.edl
      turnover001_02_23_2026_danielluckett_stringout_v01.mov
      MELT0007_grade_v01.cube                 only for a shot the wheels could not do
```

The tool looks there when the turnover is scanned and offers to ingest what it finds. Anywhere
else works too, through the Ingest Colour Session button, but then somebody has to know to
press it. If `_color` beside the turnovers is not writable, the folder named in Settings under
"Ingest opens at" is looked in first, with the same per-turnover folder name under it.

## The session

| | |
|---|---|
| Colour management | **DaVinci YRGB Color Managed, ACES 1.3** |
| Timeline colour space | **ACEScct.** This is the standard, not a preference. The tool replays each shot's CDL in ACEScct; a session set to ACEScc grades the shadows differently and nothing anywhere errors |
| Input colour space, per clip | **the clip's camera encoding**, the same value the shooter wrote into the clip's `Input Color Space`. Resolve converts into ACEScct from it outside the node graph, and the tool does the same from the same name |
| Output colour space, viewing | whatever the monitor wants. It is outside the node graph and never reaches the tool |

## One timeline per turnover

Import each shooter's turnover into the session as **its own timeline**, built from the
delivered clips themselves, unrenamed. The tool matches the EDL's events to shots by the clip
name Resolve writes into the `FROM CLIP NAME` comment, and a renamed or re-consolidated clip
matches nothing. Trim each shot with the AD on that timeline; the trimmed In and Out are the
approved cut and they leave in the EDL.

## The files

### 1. The final EDL, with the CDL in it. This is the grade.

Edit page, right-click the timeline in the Media Pool, **Timelines > Export > CDL**. That
writes an EDL whose events carry the approved In and Out, and the grade as `*ASC_SOP` and
`*ASC_SAT` lines. The manual's conditions for that export: one video track, no transitions, no
compound or nested clips. If the export refuses, one of those is the reason.

**What Resolve puts in those lines, and what it leaves out.** The CDL export takes the primary
corrections of **the first node** of each clip and nothing else: Lift, Gamma, Gain, Offset and
Saturation, with **Luma Mix at 0**. Gain becomes slope, Gamma becomes power and Offset becomes
offset. Lift has no CDL equivalent and Resolve approximates it, so **reach for Offset rather
than Lift**. Curves, log wheels, hue curves and anything in a second node do not travel. So:

- grade each shot **in node one, with the wheels**, Luma Mix at 0;
- a shot that needs more than that gets a cube as well (file 3), and the cube is what the tool
  uses for that shot.

**There is no separate CDL file.** Resolve writes no `.cdl` or `.ccc`; the CDL is the comment
lines inside this EDL, so naming the CDL means naming the EDL. Name it after the turnover folder
with a version: `<turnover folder name>_final_v01.edl`. The tool does not read the name, but it
wants **exactly one `.edl` in the folder**: a re-export replaces the old file rather than
sitting beside it, because two EDLs in the folder is two cuts and the tool will not choose.

The tool applies this CDL **in ACEScct**, between its own conversion into ACEScct from the
clip's encoding and its conversion out to linear ACEScg. The CDL also goes into every delivered
EXR's header, as numbers and as the lines above, so a plate says what was done to it.

### 2. The stringout

The ProRes QuickTime of the whole turnover with the look and burn-ins, as it is exported today.
The tool does not read it. It is what the tool's own reference mp4s are compared against the
first time a turnover goes through, and whenever something looks wrong.

### 3. A cube, only for a shot the wheels could not do

Color page, right-click the clip's thumbnail, **Generate LUT > 65 Point Cube**. Name the file
with the **shot code** and a version, for example `MELT0007_grade_v01.cube`. Out of the session
above the cube holds the clip's whole node graph, **ACEScct in and ACEScct out**, and the tool
uses it **in place of the CDL** for that shot: everything else in the chain is the same.

Still **primary only**: primaries, log wheels, custom curves, hue curves. No windows, no
qualifiers, no tracking. Generate LUT drops them silently and the delivered grade would not be
the approved one. The viewing transform stays on the timeline node or the output, never on the
clip: a clip graph with it in bakes the display rendering into the plate, and the tool refuses
the shot (QC-039). Two cubes naming one shot means neither is used until one is removed.

## The first time

Before the first real turnover: one shot graded with the wheels in node one, in a session set
up as above. Hand over the EDL, the stringout, **and a cube of that same clip**. The tool renders
the shot both ways and compares each to the stringout. That single export confirms that the
EDL carries the clip names and the CDL lines, that the CDL replayed in ACEScct matches what the
session showed, that the tool's conversion from the camera encoding agrees with Resolve's, and
that the cube out of a managed session is the grade alone. It answers OQ-46, OQ-54, OQ-31,
OQ-33 and OQ-55 together.
