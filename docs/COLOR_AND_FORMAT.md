# Color and Format

## 1. Colour policy (v01)

**Colour is decided before the tool runs. A final grade session delivers one final EDL whose
events carry the ASC CDL, the tool applies that CDL in ACEScct to everything it writes, between
its own conversion in from the clip's camera encoding and out to linear ACEScg, and the plate is
delivered graded, scene linear ACEScg.**

### 2026-09-18, later the same day: the grade is the CDL in the EDL, applied in ACEScct

> **Corrected 2026-09-21/22.** Three things below are superseded and are left in place as the
> record of how the plan moved. **(1) There are no per-shot grade files**: the `.cube` from
> Generate LUT is gone and the CDL is the only grade carrier. **(2) The encoding is not in
> `Input Color Space`**: the shooters write it into the Media Pool fields `Gamma Notes` and
> `Color Space Notes`, which reach the tool through Ben's metadata CSV. `Input Color Space`
> remains correct where this document describes what **Ben** sets in his own session, because
> that is a Resolve clip property. **(3) Sources are not ProRes 4444**: they are camera native as
> Copy with trim wrote them, or, where the camera system records RAW, debayered to a basic file
> type with no colours baked in. See `docs/WORKFLOW.md`.

**Decided by the user on 2026-09-18, after the cube correction below and superseding it.** The
grade travels as the `*ASC_SOP` and `*ASC_SAT` lines on each event of the final EDL, the tool
applies it in **ACEScct**, and the clip's metadata names the input transform that gets it there.
ACEScct is the standard the colourist's session is set to. The chain for a graded plate:

```
source encoding  ->  ACEScct  ->  the CDL  ->  linear ACEScg
   (metadata)       (tool)      (session)       (tool)
```

**Why the CDL rather than a cube that contains everything.** Resolve's CDL export writes the
primary corrections of **the first node** of each clip and nothing else. That decides the shape
of the session: the colourist grades in node one of a **colour managed** session, Resolve
applies the camera input transform outside the node graph from the clip's `Input Color Space`,
and the CDL is a set of numbers that mean something only in the timeline space they were set
in. So the tool has to convert into that space itself, apply the numbers, and convert out. The
morning's setup, an unmanaged session with two Color Space Transform nodes bracketing the grade
so a cube would contain the whole conversion, is the opposite arrangement and would export an
identity CDL; the two cannot both be asked for.

What the CDL buys: one export per turnover instead of one per shot, no per-shot file naming and
no pairing by shot code for the normal case, exact arithmetic rather than a sampled grid, a
grade a human can read and diff, and the removal of the risk OQ-54 called the whole risk, which
was whether a cube contained the conversion. What it costs: **the input transform table is now
load bearing on every plate**, not only the aux still, so QC-046 and QC-047 block a plate as
they block a chart; the tool has to hold the working space, which is a constant
(`color.WORKING_SPACE`) rather than a setting because a value that disagreed with the session
would grade wrong silently; and the grade the CDL can carry is the wheels of node one, Lift
approximated, with Luma Mix at 0. **The cube survives as the per-shot exception**: Generate LUT
on a clip in that same managed session gives the clip's node graph ACEScct in and out, and
where a cube names a shot it takes the CDL's place in the same slot. It is how a curve or a
second node reaches a plate when a shot needs one.

What changed in code: `color.to_working`, `color.from_working` and `color.cdl_transform`
supply the two legs and the middle; `ShotColor.plate_transforms` builds the three-leg chain, or
one leg where there is no grade; `clf.has_grade` is the one definition of graded (a CDL on the
event or a cube) that the ingest report, QC-008, QC-009 and QC-048 share; QC-039's probe
measures the **step** between two samples at the top of ACEScct through the cube alone, because
a grade-only cube is log in and log out and the old ratio would have refused every one; the EXR
header's `proingest/cdl_note` says whether the CDL was applied and where, or was a record beside
a cube; and `.cube` is optional in the package (`tests/fixtures/color.make_session` writes none).
`docs/COLOUR_SESSION_EXPORT.md` is rewritten for the colourist and OQ-55 is the test export.

**How to read the rest of this section.** It was written across 2026-09-11 and 2026-09-12 for
a grade file that was the whole conversion, and most of it still holds: the two colour stages,
the metadata naming the source encoding, the input transform table and its three rules, the
aux still, the view branch collapsing into one LUT, the EXR header. Three passages are
**superseded and left in place as history**, each marked at its heading: the tool applying no
input transform ahead of a grade file, the chain diagram's grade-file leg, and ACEScct having
left the chain. Where the text below says "grade file" of the thing the tool applies, read
"the CDL, or the cube that stands in for it, in ACEScct".

### 2026-09-18, morning: the grade file is a cube, because Resolve writes no CLF

*Superseded the same day by the section above; kept because the fact it records is true and
the setup it asks for is not.*

Every version of this document before today said the session exports **a CLF per shot**. On
2026-09-18 the user pointed out that there is no evidence Resolve exports one, and there is
none: the Resolve manual lists CLF among the LUT formats it **reads**, and its Generate LUT
command writes 17, 33 or 65 point `.cube` files and nothing else. Resolve also writes no `.cdl`
or `.ccc`; the CDL travels as comment lines in an exported EDL, which is what this document
always said and what the tool reads.

**So the per-shot grade file is a 65 point `.cube` from Generate LUT.** Everything below that
says "grade file" used to say "CLF", and the code keeps the old name (`core/clf.py`,
`ShotRow.clf_path`, the `proingest/clf` EXR attribute) because the mechanism did not move:
OpenColorIO loads a cube through the same file transform, the file is paired to a shot by the
shot code in its name, and QC-039 probes it for where it lands exactly as before. A `.clf` is
still accepted in the same role, for a session that has a way to make one.

**What a cube contains depends on how the session is set up, and that is the whole risk.**
Generate LUT bakes the clip's node graph: Primaries, Custom Curves and the compatible
ResolveFX including Color Space Transform, and nothing outside the graph. So the contract on
the grade file below - starts at the source encoding, ends in linear ACEScg, no display
rendering - is met by putting the two Color Space Transforms **inside** the node graph and
the viewing transform **outside** it. `docs/COLOUR_SESSION_EXPORT.md` is that setup written
for the colourist, and one test export against it is OQ-54. A cube is a sampled transform
where a CLF could be an analytic one; at 65 points on a log input that is well within what a
primary grade needs, and it is why the export asks for 65 rather than 33.

This **supersedes the policy written earlier on 2026-09-11**, which itself superseded OQ-17.
Both carry the same date, which is worth noticing before trusting a file by its timestamp alone.
That morning's version had
the shooters delivering ACEScct, the CDL read out of an EDL, an ungraded plate with the CDL
carried in the header, and four colour controls in the tool for the AD's notes. The pipeline
mechanics from it survive almost intact. What changed is where colour is authored and when,
and that moves enough to be worth rewriting rather than amending.

### Two colour stages, and only the second one reaches a deliverable

**Offline.** Shooters deliver a string-out and a CDL with it. The CDL is a starting point and
a record of what the shooter intended, nothing more. **The tool never renders a deliverable
from it.**

**Final.** The AD meeting decides the look, and that decision goes into a colour session in
DaVinci Resolve, where Ben works with the AD. That session exports an **updated final EDL**
carrying the conform, the trims and the CDL, and **a grade file per shot**. The tool conforms from the
EDL and **applies the grade file**. Final colour is applied before every export, the references and the
plates alike.

The consequence to be clear about: **a batch cannot produce final deliverables until the
colour session for it exists.** Scanning, review and In/Out work all happen without it, because
they are about frames rather than pixels. Rendering waits. That is a change of shape in the
user flow and it is written up in PRD section 6.

### The colour session

These are constraints on the session, not descriptions of it. The pipeline below is only
correct if they hold.

| | |
|---|---|
| colour science | DaVinci YRGB Color Managed, **ACES 1.3** |
| timeline colour space | **ACEScct**, by standard (2026-09-18). The CDL is applied there, by Resolve and by the tool alike |
| input colour space, per clip | **the clip's camera encoding**. Ben sets each clip's `Input Color Space` in his session to it, and Resolve converts from there outside the node graph. The tool reads the same encoding from the metadata (`Gamma Notes` + `Color Space Notes`, joined in that order) and resolves it through `color.INPUT_TRANSFORMS` |
| grade | **the wheels of node one**, Luma Mix at 0, which is what Resolve's CDL export carries. **That is the whole grade**: there are no per-shot grade files (2026-09-21), so a look the wheels cannot reach is not deliverable through this pipeline |
| viewing | on the timeline node or the output, never the clip. With the cube retired there is no grade file to inspect, so QC-039 is retired with it |

**ACEScct is back in the chain as of 2026-09-18.** The 2026-09-12 version of this document took
it out, because a grade file that started at the source encoding needed no working space. A
CDL is different in kind: it is arithmetic on code values and means something only in the
space it was set in, so the tool has to know that space and convert into it. It is a constant
rather than a setting (`color.WORKING_SPACE`) because a value here that disagreed with the
session would replay the grade in the wrong space without an error.

**Primary only is a hard requirement rather than a stylistic preference.** A grade file is a static
transform of a pixel value. A window, a qualifier or a tracked secondary is a function of where
the pixel is or what is around it, and none of that survives being written to one. A session
that used one would export a grade file that silently omits it, and the tool would deliver a grade
that is not the grade that was approved.

Everything else a primary can do, the grade file carries: curves, log wheels and hue versus saturation
curves included. **That is the whole reason the grade file is the thing applied rather than the CDL.**
A CDL can say only slope, offset and power per channel plus one saturation, so a grade built
with a curve in it would arrive silently incomplete. The CDL still travels, and it has a job
(see EXR metadata below), but it is a record rather than the transform.

The practical safeguard is that the session also exports the stringout with the real look on it.
**If a reference mp4 from this tool does not match that stringout, something did not survive**,
and that is the comparison to make the first time this runs (OQ-31).

The session exports three things and the tool uses all three:

| export | what it is for |
|---|---|
| the **updated final EDL** | the conform: timecode, shot identity, and the **approved In/Out** from Ben and the AD's trims. It also carries the CDL as `*ASC_SOP` / `*ASC_SAT` comment lines. Supersedes the shooters' EDL entirely |
| a **`.cube` per shot**, 65 point, from Generate LUT | **the whole of what the tool applies**, encoding `source encoding in > grade > linear ACEScg out`, with no display rendering in it. Named with the shot code. A `.clf` is accepted in the same role |
| the **stringout** | a ProRes QT with the look and burn-ins. The tool does not build one, and it is what the tool's own references should be checked against |

**The CDL and the grade file both come from this session and they have different jobs**, which is worth
stating plainly because carrying two grade artifacts looks redundant until it is not. The grade file is
applied, because it carries everything a primary grade can contain. The CDL is recorded, in the
EDL and in the EXR header, because it is the form a human or another facility's tool can read,
compare and talk about without an OCIO install. **Where they disagree the grade file is what is in the
pixels**, and the tool never applies both.

**That EDL carries the approved cut as well as the approved colour**, because Ben and the AD
trim in the same session. It is the tool's authority on In and Out. The tool keeps its own
In/Out editing for the one-off trim that is not worth asking for a new EDL (PRD FR-5), and
reports any row that used it (QC-045).

**A trim does not disturb the grade.** A grade file is one static transform for the whole shot rather
than an animated one, so moving In or Out carries it unchanged. The one thing to know is that
extending into the handles applies the approved grade to frames nobody looked at in the session.
For a static primary that is almost always right, and it is the reason the tool's trimming is
described as a one-off rather than a re-edit facility.

### What arrives

| | |
|---|---|
| picture | **camera native**, one file per timeline clip, as Copy with trim wrote it: camera filename, camera timecode, handles both sides, nothing recompressed. Where the camera system records RAW, a **debayered basic file type with no colours baked in**. RAW itself never arrives |
| encoding | **named in the metadata, per clip**, as `Gamma Notes` + `Color Space Notes` joined in that order, reaching the tool through Ben's CSV. Camera native log is the expectation; DaVinci Wide Gamut / DaVinci Intermediate is one more value, not a separate mode. A turnover may mix them |
| grade | **the CDL on each event of Ben's EDL**, applied in ACEScct (2026-09-18). It is the only grade carrier (2026-09-21) |
| conform | Ben's EDL: timecode, shot identity and the approved In/Out. Identity itself comes from his CSV, not from the EDL or any filename |

### One mechanism: the clip's metadata names the source encoding

**Decided 2026-09-12, and simplified the same evening.** The expectation is **camera native
log**: each shooter delivers in whatever their camera shoots, and **writes that encoding into
the clip's metadata**. This reverses the 2026-09-11 decision that there is one studio standard
log encoding on every file.

**There is no mode.** A first version of this section gave Settings a switch between "camera
log" and "studio standard", which was the wrong shape: **DaVinci Wide Gamut / DaVinci
Intermediate is not a mode, it is one more input transform**, and a clip encoded in it says so
in its metadata like every other clip. A shooter working from a house template and a shooter
delivering S-Log3 are the same case with different strings. So:

**Read at scan time from Ben's metadata CSV** (corrected 2026-09-21), from **two** named
columns joined in order: `Gamma Notes` then `Color Space Notes`, giving `S-Log3 S-Gamut3.Cine`
and the like. The shooters type both by hand. The file itself carries nothing - Copy with trim
strips the camera's own metadata, verified on `Turnover199` - so there is no second carrier to
fall back to, and an empty field is no field. Matching after casefolding and stripping
punctuation is provably safe (no two colour spaces in the pinned config collide under it); a
name that still does not resolve is QC-047 and is never guessed at. What is stored on the
row is **what was written, verbatim**: the table resolves it at plan time, and QC-047 has to be
able to quote back what somebody typed.

- **One mechanism.** The clip's metadata names the source encoding, always. Nothing in Settings
  overrides it and nothing has to be switched before a turnover is scanned.
- **`DaVinci Intermediate WideGamut` is a row in the table**, alongside the camera logs, not a
  special path.
- **A turnover may mix them freely**, including one shooter on a house template and two on their
  cameras, which is a real possibility this design now costs nothing to support.

What that deletes: the Settings mode, the batch-wide encoding value it selected, and the need
to get either right before scanning. **QC-038 retires with them.** What survives is the table
below, which was always the real work.

### ~~The tool applies no input transform ahead of a grade file~~ Superseded 2026-09-18

*Superseded: the tool applies the input transform into ACEScct ahead of the CDL on every plate,
and the bill this section lists as deleted is back, which is why the input transform table is
load bearing everywhere and QC-046 and QC-047 are errors on every plate. Kept as history.*

**Answered 2026-09-12.** The colourist builds each shot's grade file starting from whatever that shot
is encoded in, camera log or DaVinci Wide Gamut alike. **So the tool converts nothing before the
grade.** It decodes the source to float and applies the grade file, and the grade file is the entire transform
from what arrived to linear ACEScg.

This is OQ-37, asked and answered, and what it buys is worth listing because an earlier version
of this section spent a page on the bill it deletes:

- **A plate does not depend on the mapping table being right.** The tool does not turn "S-Log3"
  into a colour space in order to render one, so a wrong table entry cannot reach a plate. **The
  table is still built**, because the aux still uses it and because a row with no grade file uses it.
- **The tool and Resolve cannot disagree about what a camera log is**, because only one of them
  converts. That was the invisible failure and it is gone rather than mitigated.
- **A camera nobody has mapped still delivers its plates.** A fourth camera arrives, the
  colourist grades from its log, and the tool applies the result. Its aux stills still need a
  table row, so "more may be added" is a row rather than a code change.
- **ACEScct leaves the chain entirely**, and with it the one stage that existed only to get from
  the source to where the grade began.

**On a plate the source encoding is therefore provenance, not a transform.** It goes in the EXR
header so a delivered frame says what it was made from, it is what QC-018 compares the
container's own tags against, and it is what QC-021 checks the delivery format against. A wrong
one is a header that lies, which is worth catching and is not a wrong picture.

### The input transform is a table, keyed on the metadata

**Required 2026-09-12.** The tool carries **multiple input transforms and picks one per shot
from what the clip's metadata says**, rather than one transform named in Settings. That is the
whole of OQ-34 and it is now a build requirement rather than a question: a table from the
string a shooter wrote to one OpenColorIO colour space, extensible as cameras are added, and
**refusing anything it cannot resolve to exactly one entry** rather than reaching for the
nearest.

Three rules on that table, and none of them are style:

- **It is a table, not a search.** No prefix matching, no fuzzy matching, no "contains". A name
  that is not an entry is an error (QC-047). The failure this prevents is a near miss, which
  produces a plausible looking wrong image that nothing downstream notices.
- **An entry names a curve and a gamut together**, because a curve alone does not identify a
  colour space: "S-Log3" matches four entries in the pinned config. The table's keys are
  therefore whatever the shooters are actually told to write (OQ-44), and the safest instruction
  is the Resolve input transform name verbatim.
- **Adding a camera is adding a row.** "More may be added" is the reason this is a table at all,
  and a new camera must not need a code path.

**Built 2026-09-12 as `color.INPUT_TRANSFORMS` and `color.resolve_encoding`** (M4.6.3). Two
things about the shape are worth knowing before adding to it. The config's own colour space
names, its aliases and any casing resolve **without a row**, and what comes back is the
config's own spelling, so the table carries only the names OpenColorIO does not already know:
`c-log3`, `bm film` and `davinci wide gamut` today. And **`S-Log3` has no row on purpose**,
because it names four colour spaces here; it resolves to nothing and the error names all four.
Keys are compared with their case and their spacing normalised, which is still an exact lookup:
a Resolve export and a shooter's typing differ that way far more often than they disagree about
which camera shot the clip.

### Where that transform is applied, and where it must not be

**This is the one place in the pipeline where doing the obvious thing twice produces a wrong
image**, so it is stated as a rule rather than left to a diagram.

| chain | into ACEScct | grade | out to ACEScg | why (2026-09-18) |
|---|---|---|---|---|
| plate, graded | applied, from the metadata | **the CDL, or the shot's cube in its place** | applied | the CDL means something only in ACEScct, and a cube out of the managed session is ACEScct in and out |
| reference, graded | applied | the same | applied | the same chain plus the output transform |
| **aux still** | one leg, source encoding straight to ACEScg | **never** | | delivered ungraded by design |
| any row with no grade | one leg, the same | none | | a batch with no colour session yet; QC-009 on a plate |

**Applying both is the failure to design against.** A grade file that begins at camera log, fed pixels
that have already been converted to a working space, produces an image that is wrong in a way
that looks like a grade decision. Nothing errors, every check passes, and the mistake is
invisible until a compositor tries to work against it. That is the same class of failure as
QC-039 and it deserves the same treatment.

**Whether the grade contains the input transform was OQ-46, and it is decided rather than
inferred** (2026-09-18): it does not. A CDL cannot, and a cube out of a colour managed session
does not, so the tool converts into ACEScct itself on every plate. QC-048 records the chain on
every row so a delivery can still be audited afterwards.

### The aux still is why the table is load bearing even so

**An aux still is delivered ungraded** (see below) and never gets the shot's grade file, so it is the
**one picture the tool transforms on its own authority**, whatever the grade file contains. That alone
is enough to require the table, which is why the requirement stands independently of OQ-46.

It is also the sharpest place to be wrong. The aux names are `colorChart`, `mirrorBall`,
`greyBall` and `sizeRef`, and every one of them exists so a compositor can match against a
known quantity. **A mis-converted colour chart still looks exactly like a chart**, and the
artist matching against it has no way to tell. So an unresolvable encoding blocks that
deliverable (QC-047) rather than converting it approximately.

Two consequences worth being explicit about:

- **Every plate needs its encoding resolved to render**, since 2026-09-18: the grade is applied
  in ACEScct and the encoding is what gets the clip there. So QC-046 and QC-047 are errors on
  every row the tool transforms, plate and aux still alike, and info only on a BTS frame. This
  bullet used to say the opposite, for a grade file that started at the source encoding, and
  ended "if OQ-46 comes back the other way, they become errors everywhere". It did.
- **The aux still is the one deliverable whose colour the colourist does not underwrite.**
  Everything else is the session's work and can be checked against the session's own stringout.
  Asking the session to hand the stills over already converted would delete the tool's last
  transform of its own: OQ-45, recorded and not decided.

### The three encodings expected today

The shooters named on 2026-09-12 are **S-Log3, C-Log3 and BM Film**, and **more may be added**.
Since 2026-09-18 this table matters for **every plate**, because the tool converts from the
source encoding into ACEScct ahead of the CDL. All three exist in the pinned config:

| written as | the colour space in the pinned config | the catch |
|---|---|---|
| S-Log3 | `S-Log3 S-Gamut3.Cine`, `S-Log3 S-Gamut3`, or either Venice variant | **four candidates.** The curve name alone does not choose one, so the gamut has to be written too |
| C-Log3 | `CanonLog3 CinemaGamut D55` | the only C-Log3 the config carries. A Canon shot in BT.2020 gamut rather than Cinema Gamut has no colour space here |
| BM Film | `BMDFilm WideGamut Gen5` | **Gen 5 only.** Gen 4 and the older "Blackmagic Design Film" are absent |

Each of the three was built through `color.input_transform` against the pin on 2026-09-12 and
each produced a processor, so this is checked rather than assumed. **What is not checked is
that the string a shooter types lands on the right row of that table**, and that is what is
left of OQ-34.

"more may be added" is why the mapping is a table rather than three branches, and why an
unrecognised name blocks an aux still rather than converting it approximately: a fourth camera
turning up should stop that one deliverable, not convert a colour chart through whatever the
last camera used. Since 2026-09-18 a plate on that same row **does not render either**, for the
same reason.

**The source encoding is recorded on every deliverable**, and since 2026-09-18 it names the
transform the tool applied on a plate as well as on a still. A plate that does not say what it
was made from cannot be checked against the session that made it. `proingest/source_encoding` names it and `proingest/source_encoding_origin` says which
carrier it was read from.

### The chain

One decode, one transform stack, then a branch at the point where the two deliverables stop
wanting the same thing:

```
camera native or debayered log, encoding named in the metadata (one file per clip)
        |
        |  decode to float RGB, colour tags overridden, range confirmed
        |
     source encoding -> ACEScct          (tool: color.to_working, from the metadata)
        |
     the CDL, or the shot's cube         (session: the grade, in ACEScct)
        |
     ACEScct -> linear ACEScg            (tool: color.from_working)
        |
   +----+--------------------------------------------+
   |                                                  |
 PLATE branch                                     VIEW branch
   |                                                  |
 (linear ACEScg)                                  (linear ACEScg)
   |                                                  |
 resize in numpy, unbounded                       ACES output transform -> sRGB
   |                                              ... grade file and output transform
 EXR: ACEScg, AP1, graded                             collapsed into one 3D LUT
                                                      |
                                                  ffmpeg lut3d, tetrahedral, resize bounded
                                                      |
                                                  mp4: sRGB display

the AUX STILL branch, and the only one with a transform of its own:

 aux still -> source encoding -> linear ACEScg    (never the grade file. See above)
```

**Every transform is a single OCIO `GroupTransform`, interpolated tetrahedrally.** Not a
sequence of separate applications, and not trilinear. Tetrahedral is stated here because the
default in several tools is trilinear, it is visibly worse on saturated colour, and it is a
one word difference that nobody notices being wrong.

Three properties carry over from the previous policy unchanged, because the reasoning behind
them did not depend on where the grade came from.

**The plate branch is unbounded and no scene linear pixel goes through swscale.** Scene linear
values run past 1.0 and swscale clamps float to 0..1, so `core/resize.py` exists for the HD
downscale of a source that is already scene linear, which is an EXR sequence. A log source is
bounded, so its downscale happens in the ffmpeg decode, **before** the transform rather than
after it as the diagram draws it: the property that matters survives either way, and the
difference between resampling in log and resampling in linear is OQ-43.

**The view branch stays bounded everywhere ffmpeg can see it.** Corrected twice on 2026-09-12.
It used to say everything before the output transform happens in ACEScct, which stopped being
true when the grade file became the thing applied and stopped being true a second time when ACEScct
left the chain altogether. What the property actually rests on is the LUT's own ends, which is
why it survived both corrections unharmed. ffmpeg reads the log source, bounded 0..1, applies one cube and gets display sRGB,
bounded again; the unbounded stretch in between is inside the cube, where OCIO handles it and
swscale never sees it. swscale clamps float to 0..1, and that is what would otherwise cost the
reference its single pass.

**The whole view branch collapses into one 3D LUT per shot**, generated in core by
`color.view_lut`: source log in, sRGB display out, with the grade file and the
ACES output transform inside it. **This is how an OCIO
transform gets into ffmpeg**, which has no OCIO filter and does have `lut3d`, and it is what
keeps the reference a single fast pass with no frames pulled through Python.

An earlier version of this section justified the LUT differently, as one definition shared by
the encoder and the on-screen viewers so the two could not drift. **The viewers are gone**
(PRD FR-16), so the LUT now has exactly one consumer and that argument no longer applies. It is
recorded because the argument was a good one and will be tempting again if a viewer ever
returns in v02: the cube is the thing to hand it.

A 3D LUT is accurate here because its input domain is log, which is where LUTs are meant to be
authored, and its output is display referred and therefore bounded. **The plate branch cannot
use one**, because scene linear output is unbounded; that path applies the GroupTransform to
float pixels directly.

**The grade sits between the tool's two legs and nowhere else** (2026-09-18). The CDL is
applied in ACEScct because that is the space it was set in; a cube out of the managed session
is ACEScct in and out and sits in the same slot. Applying either in a different space, or
applying both, is a plausible looking wrong image rather than an error, which is why
`ShotColor.plate_transforms` builds the whole chain and a caller cannot assemble half of one.
QC-039 probes a cube for a display rendering, through the cube alone, in ACEScct.

**The one-leg conversion from the source encoding straight to ACEScg still exists in
`core/color.py`** (`input_transform`), for the two chains with no grade in them: an aux still,
which must never have one, and a row the session left no grade for.

### The plate is graded, and what that costs

The morning's policy delivered an ungraded plate and carried the CDL in the header. The
argument for it was that a grade baked into a plate can clip highlights the comp needs, and
that work done against a graded plate stops matching the moment the grade moves in the DI.

**The second half of that argument no longer applies**, because this workflow finishes the DI
before the turnover is ingested. There is no later grade for the plate to stop matching. The
first half still applies, and it becomes a requirement on the grade file rather than a reason to
refuse:

**The grade file must end in scene linear ACEScg and must contain no display rendering.** A grade file whose
chain includes an ACES output transform, a film emulation, or any tone curve that lands in a
display range produces a file that is display referred and says it is linear. That file grades
and comps wrong, and it looks completely normal until someone tries to work on it. The tool
probes for it and raises QC-039, because the alternative is trusting a filename.

Within that constraint a grade authored in a log working space and landing in linear keeps its
float headroom. Values above 1.0 survive it.

### The one picture the grade is never applied to

**An aux still is delivered ungraded.** The aux names are `colorChart`, `mirrorBall`, `greyBall`
and `sizeRef`, and every one of them is a reference a comp matches lighting or colour against. A
creative grade applied to a colour chart destroys the only thing the chart is delivered for, and
it does it invisibly: the chart still looks like a chart. So an aux still gets the input
transform and lands in linear ACEScg like every other EXR the tool writes, and never the shot's
grade file. It is the single exception to "the tool applies the grade file to everything it writes", and it is
enforced in `planner._aux_plan` rather than left to the renderer.

### EXR metadata

The header carries provenance, because a graded plate is only auditable if the file says what
was done to it.

- `chromaticities` states **AP1** primaries. That constant is the difference between a file
  that is ACEScg and a file that lies about being ACEScg.
- `proingest/colorspace` states `ACEScg`. It is a constant rather than a setting: the tool
  transforms every plate into it, so the value is a fact about the deliverable.
- `proingest/source_encoding` names the log encoding the source was read as, and since
  2026-09-18 that is the transform the tool applied to get into ACEScct ahead of the grade, on
  a plate as on an aux still. It is what the plate was made from, so the file can be checked
  against the session that made it.
- `proingest/source_encoding_origin` says which carrier named it: `clip metadata` or
  `container tag`, the two the scan reads (OQ-44). The encoding is the fact that matters and
  the origin is how a wrong one gets traced back to whoever wrote it, because a name typed into
  the session and a name that travelled inside the file were written by different people at
  different times. It is written **only beside an encoding**, so the header never states a
  source for a name it does not carry. This paragraph read "the clip's metadata or a per row
  override" while no override existed and the second carrier did; **a per row override, if the
  tool is ever given one, is a third value rather than a second mechanism.** Nothing in
  `UI_SPEC.md` asks for one today.
- `proingest/clf` names the cube and `proingest/clf_hash` is its sha256, **only where a cube took
  the CDL's place** for the shot. The hash is what identifies that grade: a cube re-exported
  and redelivered gets a different one, so the deliverables rendered from the old version stay
  findable afterwards. Both are **absent** from a frame graded by its CDL rather than present
  and empty, so a reader cannot mistake one for the other.
- The CDL from the EDL, as machine readable numbers in `proingest/cdl_slope`,
  `proingest/cdl_offset`, `proingest/cdl_power` and `proingest/cdl_saturation`, and as the
  **original `*ASC_SOP` / `*ASC_SAT` text** in `proingest/cdl_asc_sop` and
  `proingest/cdl_asc_sat`. Since 2026-09-18 **it is the grade that was applied**, and
  `proingest/cdl_note` says so and where: `applied in ACEScct, between the source encoding and
  ACEScg`. Where a cube took its place the note reads `record only; the grade file named in
  proingest/clf is what was applied`. Writing the numbers and the verbatim lines is what makes
  a delivered plate legible to someone who has neither the session nor an OCIO install.
- The source timecode, as the standard `timeCode` attribute. **Not yet written:**
  `proingest/tool_version`, the shot ID and the frame range, from the proposal's header list.
  They are spec rather than code until something asks for them.

### OpenColorIO

Transforms come from **OpenColorIO**, not from hand written curves and matrices.
`Config.CreateFromBuiltinConfig(...)` carries the ACES transforms inside the wheel, so **no
config files ship**. The macOS arm64 wheel is 5.7 MB, which is nothing against the 300 MB
budget in PRD section 8, and a Windows wheel exists for v02. `ColorSpaceTransform` supplies
the two legs around the grade and the aux still's one, `CDLTransform` is the CDL, in
OpenColorIO's default no-clamp style (OQ-55), `FileTransform` loads a cube, and
`DisplayViewTransform` is the output transform.

The session is ACES 1.3, so the config is pinned to an ACES 1.3 built-in config rather than
tracking `studio-config-latest`. Matching the colour session matters more than being current,
and a dependency bump must not change what the references look like. OQ-29.

The pin is **`studio-config-v2.2.0_aces-v1.3_ocio-v2.4`**, and it lives in
`core/color.BUILTIN_CONFIG` where nothing else restates it. The studio config rather than the
cg one for two reasons: it carries the camera vendor log encodings, which is what OQ-39 may
yet name, and it carries the full set of view transforms the viewing LUT is baked from. What
What was still open inside OQ-29 is which sRGB output transform within 1.3, and M4.5.3 built
it to a default: **`ACES 1.0 - SDR Video` on the `sRGB - Display` display**, in `color.VIEW`.
The pinned config offers four views on that display and the other three are not candidates: two
are a D60 simulation and an un-tone-mapped debug view, and `Raw` is no transform at all.

### The EXR writer stays as it is

The proposal writes EXRs via OpenImageIO. **This keeps the `OpenEXR` Python bindings**, which
is what `core/exr.py` already uses and what CLAUDE.md's ground rules pin. Nothing in the
proposal's header list needs OIIO: the bindings write arbitrary named attributes, AP1
chromaticities, DWAA and timecode already, with 45 tests behind them. OIIO would be a second
large dependency inside a 300 MB installer budget in exchange for no capability. Compression
stays **DWAA at level 45** per section 3; PIZ is a defensible option for a graded final plate
and is recorded as OQ-36 rather than built.

## 2. Source formats accepted

The studio sets the delivery spec and the shooters work to it, so this is a specification
rather than a survey of what might turn up. **The container is fixed; the encoding is per clip
and its metadata says which** (section 1). A turnover may carry several encodings, including a
mix of camera logs and a house wide gamut, and nothing has to be told which in advance.

**Expected**, and what every QC rule is written around:

- **Whatever the camera recorded**, in the log encoding the metadata names, one file per timeline
  clip, with handles both sides, copied with trim and **not recompressed**. Where the camera
  system records RAW, a debayered basic file type with no colours baked in.
- **RAW never arrives.** ffmpeg decodes no RAW format - BRAW, REDCODE, ARRIRAW, X-OCN, Cinema RAW
  Light, ProRes RAW - so a RAW file in a turnover is refused rather than mis-rendered.
- **8 bit and 4:2:0 are must-fix** (user, 2026-09-25). They were allowed with a warning from
  2026-09-19; QC-020 is an error again and blocks the run until the row is skipped or its media
  replaced. QC-021 stays rebased on what really arrives rather than on a ProRes 4444 intermediate
  that is never made.

4:4:4 matters more on a log source than it would on a display referred one. Subsampled chroma
in a log signal is stretched when the signal is linearised, and it shows on saturated edges.

**Accepted with a warning**, because it decodes correctly and delivers usable work:

- ProRes 422 HQ or any 4:2:2 10 bit variant carrying the same encoding. QC-021, for the chroma
  reason above.
- An EXR sequence already in ACEScg or ACES2065-1. Nothing is wrong with it; it simply is not
  what the shooters are asked to deliver, so it is flagged as an unexpected delivery rather
  than a defect.

**Refused:**

- 8 bit anything, and any 4:2:0 source. QC-020, must-fix. Neither can carry a log signal
  without banding the moment it is linearised.

**The tool does not read the colour space off the container, it overrides it.** No standard
transfer tag names any camera log or wide gamut log encoding, and a container that does carry tags is as
likely to carry the wrong ones. **The authority is the clip's metadata**, and the decode is
forced to match what it names.
The distinction worth keeping is between a *colour tag*, which a container writes because it
must write something, and a *named metadata field a shooter filled in deliberately*: the tool
overrides the first and trusts the second. QC-018 fires when the file's own tags contradict the
encoding in use, which is information rather than a veto. **Range is confirmed rather than assumed**: a log signal
carried as YCbCr and decoded at the wrong range gives crushed blacks and clipped whites that
look very nearly right.

## 3. Output formats

| output | spec |
|---|---|
| raw EXR | OpenEXR 2 scanline, DWAA compression level 45, half float RGB (alpha dropped unless source has real alpha, then RGBA), data window = display window, frame numbers start 1001 (OQ-35). **ACEScg, scene linear, AP1 chromaticities, graded with the shot's grade file**, with the source encoding, the grade file name and hash, and the CDL as its readable record, carried in the header (section 1) |
| ref mp4 4k | 3840x2160, H.264 High, yuv420p, CRF 18 (x264 `-preset slow`) or `h264_videotoolbox` when hardware encoding is enabled, keyint 24, `-movflags +faststart`, AAC 192k if audio associated. **Only a plate's reference carries sound** (2026-09-23): a cp or el is delivered silent even when its own file has a track |
| ref mp4 HD | same, 1920x1080 |
| audio | PCM 16 bit, same sample rate and channel count, no resampling. Cut to the delivered range and sped up with the picture (1.001 for a 24000/1001 source, D2 of `docs/REVIEW_2026-09-23.md`), padded with silence where the range runs past the recorded sound. Only a row with no range is delivered as-is: a wav source byte for byte, audio in a container extracted whole. QC-044 if the source was not 16 bit |
| HDRI, stills, camData | byte copy with rename, checksum recorded |
| lens grid | not written in v01; moved and renamed by hand (OQ-20) |

**Two of those numbers are editable as of M5.12** and only two: the EXR compression level and
the reference's CRF, in Settings' Output section (`UI_SPEC.md` section 9). The page opens on
the values above, reads them from `core/exr.py` and `core/ffmpeg.py` rather than carrying a
second copy, and says what the spec is beside each field. They are settings because the tool
must not hardcode a delivery cost a slow line or a picky vendor can force a change to;
**they remain what this document pins**, so a turnover delivered at anything else is a
decision somebody made rather than a default that drifted. Everything else in the table -
the preset, the codec, the pixel format, the keyint, the chromaticities, half float - is not
editable and is not meant to be.

### Hardware encoding on macOS

NVENC was the Windows hardware encoder and **does not exist on macOS**. The macOS equivalent is
`h264_videotoolbox`, which the bundled build carries (PROVENANCE.md).

- **The default is software x264 at CRF 18.** It is deterministic, it is what this spec pins,
  and it is what every QC threshold was written against. Hardware encoding is opt-in in
  Settings, exactly as NVENC was.
- VideoToolbox has no CRF. On Apple Silicon it takes a constant-quality `-q:v` on a 1 to 100
  scale where higher is better, which is **not** convertible to a CRF number by any published
  formula. `-q:v 65` is the starting point, not a specification.
- **That number is uncalibrated and must not be trusted until it is measured** on the target
  Mac against x264 CRF 18 on a real plate. Until then Settings should describe it as an
  approximation. OQ-23.
- Detection is a trial encode of a few frames, not a string match on `-encoders`. A codec
  compiled into the binary can still fail to open a session on the actual hardware, and the
  reference deliverables are not the place to discover that.

## 4. Resolution rules

- 4k deliverables are exactly 3840x2160. HD deliverables are exactly 1920x1080.
- Source must be 3840x2160 for a normal plate. Anything else: QC-023 error, row blocked, unless the user enables "allow non-4k source" in Settings, in which case the tool letterboxes/pillarboxes into 3840x2160 with black. No cropping ever. The picture is resized to the largest even size of its own shape inside the target and centred on an even pixel (`resize.fit_inside`, `resize.letterbox_offset`). In an EXR the bars are added after the colour chain, so they are linear zero rather than a log code value pushed through it; in a reference they are added after the conversion to 4:2:0. Non-square pixels are not handled: `MediaInfo` does not carry the sample aspect ratio, and no source so far has one.
- HD is produced by Lanczos downscale (`scale=1920:1080:flags=lanczos`), no sharpening. It is a second decode of the source, not a second output of the 4k one. Section 7 says why.
- Aspect other than 16:9 is QC-023 as above.

## 5. Frame rate and timecode

- **Project fps is 24 and the tool asserts it** (user, 2026-09-21). An EDL states no frame rate - CMX 3600 has no field for one and otio's reader takes the rate as an argument - and the `.drt` that could have stated one is not read. So the rate is a setting defaulting to 24 rather than a fact read from a file, and QC-025 is retired with the timeline file it checked.
- Shooters set every clip to the project rate in Resolve before export, so **the timeline rate is authoritative**. It is what the media is actually played at and what all frame math and timecode conversion use.
- A clip's media may still carry a rate of its own: an EXR sequence states one in its `framesPerSecond` header, a container in its stream. After a conform that value can be stale camera metadata. It is recorded as `MediaInfo.stated_rate` and compared against the project rate for QC-026, but nothing computes with it. Computing with a stale rate would misread the source timecode and block every row.
- A frame count is a property of the file, so it is always counted at the file's own rate, never at the timeline's. A 30 fps container conformed to 24 still holds the frames it holds.
- QC-026 therefore fires when the media states a rate and that rate differs from the project rate. Media that states no rate, such as a DPX sequence, cannot disagree. No retiming is ever performed. See OQ-19 on severity.
- Timecode is non-drop only. An EDL declaring drop frame (`FCM: DROP FRAME`) is QC-027 error.
- Source TC = media start timecode from the container or EXR header plus frame offset. If the media has no timecode, source TC is displayed as frames only and QC-028 warning is raised.

## 6. Frame math

Definitions, all integers:

- `src_start`: first frame index of the media (0 for containers, first sequence number for sequences)
- `src_len`: total frames in media
- `in`, `out`: inclusive source frame indices chosen for the deliverable
- `duration = out - in + 1`
- `max_available_out = src_start + src_len - 1`

Output frame numbering: output frame `1001 + k` corresponds to source frame `in + k` for `k` in `[0, duration)`.

Editing:
- Absolute frame typed into In/Out is a source frame index.
- Timecode typed is converted with the source start TC (or record start TC when the toggle is on record).
- Relative offset `+n`/`-n` adds to the current value.
- Constraints enforced live: `src_start <= in <= out <= max_available_out`. Violations show max available and color the row (QC-031, QC-032) but the value is kept so the editor sees what they typed.

## 7. EXR writing pipeline

```
ffmpeg -i <src> -f rawvideo -pix_fmt gbrpf32le - | numpy frames
    -> OCIO GroupTransform (the grade file; or the source-to-ACEScg leg for an aux still), tetrahedral
    -> float16 -> OpenEXR (DWAA, level 45)
```

- **The colour stage is in numpy, between the decode and the write**, and it is the whole of
  what section 1 calls the plate branch. It is applied to unbounded float, before the HD
  downscale, so the resize happens on the pixels that are being delivered rather than on
  something that still has a transform waiting for it.

- One ffmpeg decode per resolution (4k pass writes 4k EXRs; HD pass adds the Lanczos scale filter). Two passes are simpler than a filtergraph split and cost one extra decode, acceptable at this scale.
- **The frame range is a frame seek, never a time seek.** A container seeks with the `trim` filter, `trim=start_frame=<in>:end_frame=<out+1>`, whose end is exclusive; it counts frames after the decoder has put them back in display order, so a long GOP source lands exactly. A sequence seeks with `-start_number <in>`, which never opens the frames before the range. `-ss` takes a float number of seconds and would land on the wrong frame at 23.976.
- `gbrpf32le` is planar and stores G, then B, then R, so RGB is planes 2, 0 and 1. It carries no alpha, which is OQ-21: the EXR source path preserves a source alpha and the container path cannot yet, because nothing records whether a container has a real one.
- EXR source sequences skip ffmpeg and are read with OpenEXR directly, then downscaled by `core/resize.py`, an antialiased Lanczos-3 in numpy. They have to: ffmpeg's `scale` accepts a float pixel format but **clamps the values to 0-1**, so routing a scene linear EXR through it would flatten every highlight above 1.0 to white without a word. The container path is unaffected because every container format section 2 accepts is integer and already bounded. That is the same filter the container path gets from `flags=lanczos`, so the two paths do not disagree: on a hard edge they are identical, and on smooth content they are within one 8 bit level. OQ-7, resolved.
- **DWAA is lossy.** At level 45 a written frame comes back about a tenth of a percent off the value that went in, proportionally, at every brightness. The plate carries a colour transform by design (section 1), so a delivered frame was never going to equal its source; DWAA means it does not even equal the float that was handed to the writer. QC therefore never compares a rendered frame to its source by equality.
- The encoder is deterministic: the same pixels and header produce the same bytes, which is what makes the QC-106 per-frame hash meaningful across a re-render.
- `framesPerSecond` is **not** written on output. The OpenEXR Python bindings cannot write a `Rational` attribute, and writing an int or a string under that name would be the wrong attribute type for any reader expecting a rate. Delivered frames carry a per-frame `timeCode` instead, which the bindings do write correctly.
- Checksum (xxhash64) of each written frame is recorded in the batch and the QC log.
- The writer does not read each frame back. QC-103 opens every frame of the finished sequence anyway, and the sequence is not renamed off its `.part` name until that passes, so a second read at write time would double the IO to learn nothing new.
