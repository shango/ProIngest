# What the colour session exports, per turnover

The page to hand the colourist. What each turnover's export is, and the Resolve setup behind it.
`COLOR_AND_FORMAT.md` section 1 is the reasoning; this is the instruction. Rewritten 2026-09-18,
the day the grade became the CDL in the final EDL (OQ-46), corrected 2026-09-22 for the
single-folder handover, and **rewritten again 2026-09-28** (user), when the colour moved to **one
AMF per EDL event and the CLFs it names**. The CDL is no longer read and nothing falls back to it:
there will be no older turnovers.

## Where

**Put the EDL, the CSV, the AMFs and their CLFs in the same folder as the media, and hand that one
folder over.** There is no separate colour folder and no `_color` convention: the handover is one
folder holding all of it together (OQ-74, user 2026-09-21; the AMFs since 2026-09-28). The tool
reads the AMFs and the CLFs **directly in that folder**, not in a subfolder, and ignores the
`.otio` and `.drt` Resolve may write beside them.

```
<shared mount>/
  turnover001_02_23_2026_danielluckett/      the one folder the tool is pointed at
    C0145.MP4  C0148.MP4  ...                the consolidated media, unrenamed
    turnover001_02_23_2026_danielluckett_final_v01.edl
    turnover001_02_23_2026_danielluckett.csv
    <project>_<timeline>_<preset>_C0145_0_<date>_<time>Z.amf      one per EDL event
    C0145_0_ClipGraph_CorrectorNode_1.clf                          one per corrector node
```

The AMF and CLF names above are the shape turnover097 arrived in
(`Tool_Test2_turnover097_DailiesRequest_C4261_1_2026-09-28_180306Z.amf`,
`C4261_1_ClipGraph_CorrectorNode_1.clf`). The tool reads one thing from an AMF's name: the number
before the timestamp, which is Resolve's timeline index and is **the EDL event number less one**
(verified on all 15 of turnover097). Rename an AMF and its event cannot be found (QC-075).

The tool scans that folder. **A folder missing the EDL or the CSV cannot be scanned at all** and
says so (QC-001): there is nothing to do until both are in it. A folder with no AMF scans, and
nothing in it can render (QC-008). An earlier version of this page asked for
a `_color/<turnover folder name>/` tree beside the turnovers, which the tool discovered and
offered on scan; that is retired with the two-phase flow it belonged to.

## The session

| | |
|---|---|
| Colour management | **ACES 2.0**. Every ID the AMF writes is resolved through the tool's pinned config, `studio-config-v4.0.0_aces-v2.0_ocio-v2.5`, so an ACES 1.3 ID it lacks does not resolve |
| Input transform, per clip | **the clip's camera encoding.** It leaves in the clip's AMF as a transform ID (turnover097: `CSC.Sony.SLog3_SGamut3Cine_to_ACES.a2.v1`, which the config names `S-Log3 S-Gamut3.Cine`), and that is the only place the tool reads it. A clip whose AMF names none is QC-046, one the config lacks QC-047 |
| Timeline colour space | **no longer the tool's concern** (2026-09-28). The 2026-09-18 version of this page made ACEScct a standard because the tool replayed the CDL in it. Each CLF now carries its own trip into the working space and back (ACEScct in turnover097), so the tool needs no working space of its own |
| Reference Gamut Compress | turnover097's AMFs list it as their first look (`Look.Academy.ReferenceGamutCompress.a2.v1`, the config's `ACES 1.3 Reference Gamut Compression`), and the tool applies it where the AMF puts it |
| Output transform | **what the references are viewed through** (2026-09-28): the tool follows the AMF rather than a fixed sRGB. turnover097: `Output.Academy.Rec709-D65_100nit_in_Rec709-D65_Gamma2pt2.a2.v1`, the config's `ACES 2.0 - SDR 100 nits (Rec.709)` on `Gamma 2.2 Rec.709 - Display`. One the config lacks is QC-079. The plates never see it |

## One timeline per turnover

Import each shooter's turnover into the session as **its own timeline**, built from the
delivered clips themselves, unrenamed. The tool matches the EDL's events to shots by the clip
name Resolve writes into the `FROM CLIP NAME` comment, and a renamed or re-consolidated clip
matches nothing. Trim each shot with the AD on that timeline; the trimmed In and Out are the
approved cut and they leave in the EDL.

## The files

### 1. The final EDL. This is the cut.

The EDL of the stringout timeline, carrying the approved In and Out of every event and any
retimes. Name it after the turnover folder with a version: `<turnover folder name>_final_v01.edl`.
The tool does not read the name, but it wants **exactly one `.edl` in the folder**: a re-export
replaces the old file rather than sitting beside it, because two EDLs in the folder is two cuts
and the tool will not choose.

**Its CDL is no longer read** (user, 2026-09-28). An EDL exported through Timelines > Export > CDL
still works as the cut, and its `*ASC_SOP` / `*ASC_SAT` lines are passed over. The 2026-09-18
instruction on this page, to grade in node one with the wheels because only node one's primaries
survive a CDL export, is retired with it.

### 1a. One AMF per EDL event, and the CLFs it names. This is the colour.

Export an ACES Metadata File for every clip on the stringout timeline. Turnover097 was exported
with Resolve's **`Dailies Request`** preset, and the tool notes that on each row (QC-078, info);
**whichever preset arrives is used**. What the `VFX Request` preset writes differently is not yet
verified. The Resolve menu path for the export is not recorded here yet.

Each AMF names, in pipeline order:

- **the clip** it is for, as `<aces:file>` (`C4261.MP4`), or as an `<aces:sequence>` pattern and
  frame range for an EXR sequence. The tool refuses an AMF that names a different file from the
  row its event belongs to (QC-075). How Resolve names an EXR sequence plate in the CSV against
  the AMF is **not verified**: only single-frame HDRI sequences have been seen;
- **the input transform**, the camera encoding;
- **the looks**: the Reference Gamut Compress by ID, then **one CLF per corrector node**, each by
  file name with its md5. Each of Resolve's CLFs takes ACES2065-1 in and gives it back, with the
  node's grade as a 33 point 3D LUT inside a trip into ACEScct and out. The tool applies them all,
  in order, in ACES2065-1. A look already marked `applied="true"` is not applied again;
- **the output transform**, the display the session was viewed on.

**Grade with primaries plus simple sky secondaries** (user, 2026-09-28), in as many corrector
nodes as the shot needs. What does not survive:

- **A window, a blur or any other spatial operation.** A CLF is a per pixel transform, so a
  node's window cannot be written into one, and **nothing in the AMF or the CLF says one was
  there**. The tool cannot detect it; a reference mp4 played beside your own playback of the clip is the only check.
- **A look the AMF carries as anything but a config ID or a CLF**, such as an embedded CDL, or an
  ID the pinned config lacks. The tool ignores it and says so (QC-077, warning).

**A CLF must stay as exported.** One missing from the folder, one whose md5 no longer matches
the AMF's, or one OCIO cannot read is an error on its row (QC-076): the grade is yours, so the
tool never drops a node quietly. A clip you left ungraded has an AMF with no CLF, and that is
noted (QC-009, info) and rendered through its input transform and the Reference Gamut Compress
alone.

### 2. No stringout. The tool builds it.

**Do not render or export a stringout** (user, 2026-09-29). The tool builds it from your final EDL
after a Run: one HD mp4 cut from its delivered HD references, with the burn-ins of your frame
(`burn-ins.png`), named `turnover###_MM_DD_YYYY_<shooter>_SO_v##.mp4` (PRD FR-9). What you do is
cut the final timeline the EDL comes off, which is what makes the EDL's events the final clip
durations.

### 3. The metadata CSV. This is identity.

Media Pool metadata export for the timeline. It carries one row per consolidated clip, and the
tool cannot build a shot list without it:

- `File Name`, which is how a row is matched to its media
- `Shot`, the shot code
- `Shot Type`, what the clip is: `pl`, `cp`, `el`, `wit`, `re`, or a reference type. `HDRI` is
  the shooters' to deliver: the tool skips the row and shows its clip in the stringout only
  (QC-080)

**Its colour columns are no longer read** (user, 2026-09-28): `Gamma Notes`, `Color Space Notes`
and `Input Color Space` may be in the export and change nothing. The encoding comes from the AMF.

The shooters fill those fields in their own project; they have to reach yours, and the export has
to carry them. A blank `Shot` or `Shot Type` is QC-010 and that deliverable cannot be named.

> **Retired 2026-09-21: there are no per-shot cube files.** A section here used to ask for a
> 65-point cube from Generate LUT for a shot the wheels could not do. The user removed it: the CDL
> is the only grade carrier. A look the wheels cannot reach is not deliverable through this
> pipeline, and QC-019 and QC-039, which existed to inspect those files, are retired with them.
> **2026-09-28:** per-node grade files are back, as the CLFs each AMF names (section 1a). They are
> Resolve's own export, not a cube from Generate LUT, and QC-019 and QC-039 stay retired: QC-076
> checks a CLF and QC-077 reports what the tool ignores.

## The first time

Before the first real turnover: one shot graded in a session set up as above. Hand over the one
folder, with the media, the EDL, the CSV, the AMFs and CLFs in it. The tool
renders the shot and its reference mp4 is compared to your own Resolve playback of it. **That comparison has not
been made yet** (2026-09-28): turnover097 came with no frame rendered by Resolve to compare
against, and the graded EXR in the repo is Turnover121's and not comparable. Until it is made,
that the tool's render of an AMF matches Resolve's is unverified.

> **Superseded 2026-09-28.** This section asked for one shot graded with the wheels in node one,
> to confirm that the EDL carried the CDL lines, that the CSV carried the two encoding fields, and
> that the CDL replayed in ACEScct matched. None of those is read any more.
