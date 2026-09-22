# What the colour session exports, per turnover

The page to hand the colourist. Three files per turnover, and the Resolve setup that makes the
first of them mean what the tool takes it to mean. `COLOR_AND_FORMAT.md` section 1 is the
reasoning; this is the instruction. Rewritten 2026-09-18, the day the grade became **the CDL in
the final EDL, applied in ACEScct** (OQ-46), and corrected 2026-09-22 for the single-folder
handover.

## Where

**Put the EDL and the CSV in the same folder as the media, and hand that one folder over.** There
is no separate colour folder and no `_color` convention: the handover is one folder holding the
consolidated media, the EDL and the CSV together (OQ-74, user 2026-09-21).

```
<shared mount>/
  turnover001_02_23_2026_danielluckett/      the one folder the tool is pointed at
    C0145.MP4  C0148.MP4  ...                the consolidated media, unrenamed
    turnover001_02_23_2026_danielluckett_final_v01.edl
    turnover001_02_23_2026_danielluckett.csv
```

The tool scans that folder. **A folder missing either file cannot be scanned at all** and says so
(QC-001): there is nothing to do until both are in it. An earlier version of this page asked for
a `_color/<turnover folder name>/` tree beside the turnovers, which the tool discovered and
offered on scan; that is retired with the two-phase flow it belonged to.

## The session

| | |
|---|---|
| Colour management | **DaVinci YRGB Color Managed, ACES 1.3** |
| Timeline colour space | **ACEScct.** This is the standard, not a preference. The tool replays each shot's CDL in ACEScct; a session set to ACEScc grades the shadows differently and nothing anywhere errors |
| Input colour space, per clip | **the clip's camera encoding**, the same value the shooter wrote into `Gamma Notes` and `Color Space Notes`, which you set as the clip's `Input Color Space` in this session. Resolve converts into ACEScct from it outside the node graph, and the tool does the same from the same name |
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
- **a look the wheels cannot reach is not deliverable through this pipeline.** There are no
  per-shot grade files: no `.cube`, no `.clf`, nothing beside the EDL (user, 2026-09-21, restated
  2026-09-22). The CDL is the only grade carrier there is.

**There is no separate CDL file.** Resolve writes no `.cdl` or `.ccc`; the CDL is the comment
lines inside this EDL, so naming the CDL means naming the EDL. Name it after the turnover folder
with a version: `<turnover folder name>_final_v01.edl`. The tool does not read the name, but it
wants **exactly one `.edl` in the folder**: a re-export replaces the old file rather than
sitting beside it, because two EDLs in the folder is two cuts and the tool will not choose.

The tool applies this CDL **in ACEScct**, between its own conversion into ACEScct from the
clip's encoding and its conversion out to linear ACEScg. The CDL also goes into every delivered
EXR's header, as numbers and as the lines above, so a plate says what was done to it.

### 2. The stringout. You produce and export it.

The QuickTime of the whole turnover with the look and burn-ins, cut on the timeline the EDL above
is exported from. **That ordering is the point**: because the EDL comes off the stringout
timeline, the EDL's events state the final clip durations and the two cannot disagree (user,
2026-09-22). The tool never builds a stringout of its own. It is also what the tool's reference
mp4s are compared against the first time a turnover goes through, and whenever something looks
wrong.

### 3. The metadata CSV. This is identity and encoding.

Media Pool metadata export for the timeline. It carries one row per consolidated clip, and the
tool cannot build a shot list without it:

- `File Name`, which is how a row is matched to its media
- `Shot`, the shot code
- `Shot Type`, what the clip is: `pl`, `cp`, `el`, `wit`, `re`, or a reference type
- `Gamma Notes` and `Color Space Notes`, the camera encoding, typed by the shooter and joined in
  that order by the tool (`S-Log3` + `S-Gamut3.Cine` reads as `S-Log3 S-Gamut3.Cine`)

The shooters fill those fields in their own project; they have to reach yours, and the export has
to carry them. A blank `Shot` or `Shot Type` is QC-010 and that deliverable cannot be named.

> **Retired 2026-09-21: there are no per-shot cube files.** A section here used to ask for a
> 65-point cube from Generate LUT for a shot the wheels could not do. The user removed it: the CDL
> is the only grade carrier. A look the wheels cannot reach is not deliverable through this
> pipeline, and QC-019 and QC-039, which existed to inspect those files, are retired with them.

## The first time

Before the first real turnover: one shot graded with the wheels in node one, in a session set up
as above. Hand over the one folder, with the media, the EDL, the CSV and the stringout in it. The
tool renders the shot and compares its reference mp4 to the stringout. That single export confirms
that the EDL carries the clip names and the CDL lines, that the CSV carries `Shot`, `Shot Type`
and the two encoding fields, that the tool's conversion from the camera encoding agrees with
Resolve's, and that the CDL replayed in ACEScct matches what you saw. It answers OQ-46, OQ-31,
OQ-33 and OQ-55 together.
