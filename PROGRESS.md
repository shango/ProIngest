# Implementation progress

Durable handoff record. It is written to be picked up cold: everything a new session
needs that is not already in the code or the docs lives here. Update it at every
commit.

---

## 1. Resume here

**State at 2026-09-13. Every feature milestone is built, and so is packaging.** M1 to M4
complete, M4.5 all four chunks, M4.6 all five, **M5 all eleven**, and **M7 as of this
afternoon**. `ruff`, `ruff format` and `mypy --strict` clean, the last two now over `build/`
as well. What is left is **M8 polish** (needs a real turnover and a real colour session) and
**M9 the user guide**.

**M7 did not need a Mac and this file said it did.** Everything but the `.app`'s behaviour
once double-clicked is exercised by CI on every push: `package-macos` builds the bundle and
the dmg on an arm64 runner and uploads the image, `package-linux` builds the same spec for
free and smoke tests it, and `build/smoke_test.py` drives the packaged binary through a whole
turnover in both. The spec was also built and smoke tested on this Linux machine before it
was ever pushed, which is what turned M7 from written-blind into verified-except-the-wrapper.
Detail is in section 5 under M7.

**A code quality review went in on 2026-09-13, on the branch `review/quality-fixes`.**
`REVIEW.md` at the repo root is the record: 27 bugs fixed with a test each, five structural
findings and the stale docs with them, `uv.lock` committed and installed in CI, and
`ruff format` enforced. The two that changed behaviour a person would notice: closing the
window mid-run now waits for the run's results instead of dropping them, and OTIO clip times
are rescaled to the timeline rate (OQ-51). What the review deferred, and why, is in
`REVIEW.md`'s last section; the largest is the `MainWindow` split. Pushed as PR #1, and run
34783167555 is green on both runners: Linux in 2m32s, macOS arm64 in 1m52s, the first run
with the lock install and the format check.

**What the tool does today, end to end.** A batch is made, opened, saved and filled with
turnover folders; the scan runs off the UI thread; the list shows it grouped by turnover and
can be typed into, with every edit re-checking that row and autosaving. A colour session is
ingested from the window, one turnover at a time, which writes the approved cut, the CDL and
each shot's CLF onto the rows. Run plans the batch and drives the worker pool, the rows fill
in as they go, a strip above the list narrates the step, Stop reaches a job mid flight, and a
finished run writes both spreadsheets and says where they went. Everything known about a
selected row reads in the pane beside the list; every QC result reads in the Issues dock and
clicks back to its shot; everything the tool did reads in the Log tab and in a rotating file.
Settings carries five of its six sections. Every toolbar button says what it does and, when it
is greyed, why.

**What the colour chain delivers.** A plate is written graded, in linear ACEScg with AP1
primaries and a header stating what was applied to it; a reference mp4 is encoded through the
shot's grade and the ACES output transform baked into one cube. **The chain converts nothing
ahead of the CLF**, which was the one thing in the code that would have delivered a wrong plate
against a real session. The source encoding is camera native log as of 2026-09-12, read per
shot, resolved through a table, recorded in the QC log and stated with its origin in the
delivered header.

**Nothing in the plan is next that can be built on this machine alone.** M7 wants a Mac, M8
wants a real turnover and a real colour session, and M9 wants both plus the screenshots. Two
questions are open and both are about correctness rather than scope: OQ-46, and **OQ-47, which
was found by building M4.6.2**. Every chunk has its own note further down saying what it
settled.

**One of the three things added to the plan on 2026-09-12 is still unbuilt**: the user guide
with screenshots (PRD FR-17, the new M9). The other two are done - the run's strip, built
first because it finishes what the user had just watched being built, and the toolbar
tooltips (M5.11). The note below says what the guide is and what decides its shape.

**M4 is done.** `core/exports.py` writes both spreadsheets, `proingest qc <batch>` writes them
headless, and QC-053 parses camData through the new `core/camdata.py`. Proved end to end on a two
shot turnover: 14 deliverables, five sheets, and a tracker of two rows filling nine columns and
touching none of the other thirty.

M4.5.1 put OpenColorIO in and rebuilt `core/color.py` as the two ends of the chain: the input
transform from the studio standard log to ACEScct, the plate transform from ACEScct to linear
ACEScg, and the machinery to compose them into one `GroupTransform` and apply it to a decoded
frame in place. **Both ends of that sentence were overtaken on 2026-09-12**: ACEScct is gone
from the chain and the input transform no longer runs ahead of a CLF, **which M4.6.2 built on
2026-09-12**. The composition machinery is untouched and is what the whole thing still rests on. **The display referred block it kept under a fence
is gone**, deleted with its tests in M4.5.4 as planned.

### First five minutes

```
.venv/bin/python -m pytest tests/ -q
.venv/bin/python -m ruff check . && .venv/bin/python -m ruff format --check . && .venv/bin/python -m mypy proingest tests build
```

Then read `docs/COLOR_AND_FORMAT.md` section 1 before anything else. It was rewritten twice on
2026-09-11 and again on 2026-09-12, and it invalidates things a commit message or a memory of
this project may still say. The table below dates each version.

### Read this before trusting anything about colour

**The colour spec has now been wrong twice and rewritten twice.** Take nothing about colour
from memory or from a commit message, and check the time on anything dated 2026-09-11 before
trusting it: two of the three versions below share that date.

| dated | what it claimed | status |
|---|---|---|
| 2026-09-10 | sources display referred, sRGB baked in, references apply no transfer | wrong |
| 2026-09-11 am | sources ACEScct, plate **ungraded**, CDL read from the shooters' EDL, four colour controls in the tool | superseded |
| 2026-09-11 pm | colour finished before ingest, **CLF per shot applied**, plate **graded**, no controls, no viewers, no stringout | current, except the source |
| 2026-09-12 | the source goes back to **camera native log**, named in the clip's metadata. Settled that evening: **no mode**, DaVinci Wide Gamut is one more entry in an input transform table, **the CLF starts at the source encoding** so the tool applies no input transform ahead of it, and **ACEScct leaves the chain** | current |

The mechanics survived all three rewrites almost intact: ACEScg working space, OCIO for every
transform, the plate branch unbounded in numpy, the view branch bounded and collapsed into one
3D LUT. What kept changing is **where colour is authored and by whom**, and on 2026-09-12,
**what the source is encoded in**. That last one has now been answered three different ways in
two days - camera original, one studio standard, camera native again - so take nothing about
the source encoding from memory either.

### What the tool is for

**Checking all media, running QC, and producing every turnover output.** The user said it in
those words on 2026-09-11. It does not author colour, it does not cut a stringout, and it
decides nothing creative. Everything it writes is either a deliverable named from the spec or
a report about one.

### What the workflow is now

The user described it on 2026-09-11 and it is written up in `docs/COLOR_AND_FORMAT.md`
section 1. In one paragraph: the shooters deliver **ProRes 4444 in their camera's native log**,
each clip's metadata naming which (2026-09-12; S-Log3, C-Log3 and BM Film today, more later, and
DaVinci Wide Gamut is one more value rather than a mode). Their CDL and their string-out
are offline reference and **the tool reads neither**. After the AD meeting, a **colour session
in Resolve**, where Ben works with the AD (ACES 1.3, primary grades only, the CLF starting at
whatever the clip is encoded in),
exports an **updated final EDL** (conform, the approved trims, and the CDL as `*ASC_SOP` /
`*ASC_SAT` lines), **a `.clf` per shot**, and the stringout. The tool conforms from the EDL and
**applies the CLF** to everything it writes, plates included, so the plate is delivered graded.

### What changed on 2026-09-11, and where it lives

| decision | where it lives |
|---|---|
| Colour is finished before ingest; the tool applies, never authors | COLOR_AND_FORMAT section 1, PRD section 3 |
| The colour session's grade is what ships; the shooters' is superseded | COLOR_AND_FORMAT section 1, PRD FR-15 |
| The **CLF is applied**; the CDL travels beside it as the readable record | OQ-40, closed |
| The session's **updated final EDL** is the conform the run uses | COLOR_AND_FORMAT section 1, PRD section 4 |
| **The plate is graded**, reversing the morning's spec | COLOR_AND_FORMAT section 1, PRD section 5 |
| Sources are one **studio standard log**, camera agnostic | COLOR_AND_FORMAT sections 1 and 2, OQ-39 |
| **The four colour controls are removed**, then **the three viewers too** | PRD section 3 and FR-16, UI_SPEC section 14 |
| Ben trims with the AD; his final EDL is the **approved cut** as well as the colour | COLOR_AND_FORMAT section 1, PRD FR-5 and FR-15 |
| The tool keeps In/Out editing for the **one-off trim**, reported by QC-045 | PRD FR-5, QC-045 |
| **The stringout is dropped**, M6 with it | PRD FR-9, UI_SPEC section 8, OQ-38 |
| A batch cannot render until its colour session exists | PRD section 6, QC-008 |
| OCIO `GroupTransform`, tetrahedral, pinned ACES 1.3 | COLOR_AND_FORMAT section 1, OQ-29 |

QC rules: QC-006, QC-007, QC-017 and QC-037 are **retired**, and QC-140 and QC-141 went with
the stringout. QC-008, QC-009, QC-019, QC-038, QC-039 and QC-045 are new. Retired IDs stay in
the table and are never reused, so an old log line still resolves. **QC-009, QC-019 and QC-039
were written, reworded and written back inside the one day**, as the grade carrier went CLF,
CDL, CLF; that is safe only because nothing had ever referred to them, and `QC_RULES.md` says
so and says it is not a precedent.

### Three things behind those that should not be re-derived

- **The graded plate is not a reversal of the argument, it is the argument running out.**
  The morning's spec refused a graded plate because a baked grade stops matching when it moves
  in the DI. This workflow does the DI **first**, so there is no later grade to stop matching.
  The objection's other half, that a baked grade can clip the highlights a comp needs, survives
  as a hard requirement on the CLF rather than as a reason to refuse: it must end in scene
  linear ACEScg and contain **no display rendering**, or the delivered EXR is display referred
  and claims to be linear. That is QC-039, it is an error, and the tool probes for it rather
  than trusting a filename, because the failure is invisible on a monitor and expensive in a
  comp.
- **"Studio standard log" was called the single most valuable line in the spec on 2026-09-11,
  and on 2026-09-12 the user took it back.** It is left here rather than deleted because the
  reasoning was correct and only the premise moved, and because the same instinct will be
  tempting again. What it said: one encoding on every file means **one input transform
  forever**, no per shot IDT, and no mapping of Resolve's transform names onto OpenColorIO's,
  which do not agree; a session that finds itself building an IDT table has taken a wrong turn.
  **The tool is now expected to build exactly that table** (OQ-34, reopened), because the
  shooters deliver camera native log and name it in the clip metadata. That is not a wrong
  turn any more, it is the price of the workflow the user wants. **OQ-37 came back the same
  day and paid most of the bill**: the colourist starts the CLF from the source encoding, so a
  graded plate never goes through the tool's own conversion and a wrong table entry cannot
  reach one. The table is still built, because the user asked for multiple input transforms
  selected by the metadata and because the **aux still** needs one whatever the CLF contains.
  What is left of the original hazard is OQ-46: applying the table *and* a CLF that already
  contains it converts twice, and that is invisible.
- **The tool's stringout would have been the only one cut to the edited In/Out.** The colour
  session's QT and the shooters' offline are both cut to the turnover as delivered. That is
  what dropping M6 gives up, and it is recorded in PRD FR-9 so it reads as a decision rather
  than an oversight.

### What changed on 2026-09-12: the source encoding, and only the source encoding

The user's words: there will likely **not** be one studio standard log for the sources; each
camera's native LOG is used and **the shooters write the correct LOG for their camera into the
clip's metadata**. The cameras today are **S-Log3, C-Log3 and BM Film**, and more may be added.

**The shape of it changed twice inside the same evening and the final shape is the simplest
one.** It was first written as a Settings **mode**, Camera log or Studio standard, with DaVinci
Wide Gamut / DaVinci Intermediate as the studio standard. The user then removed the mode:
**DaVinci Wide Gamut is not a mode, it is one more input transform, and a clip encoded in it
says so in its metadata like any other clip.** So there is one mechanism, the metadata names the
encoding per clip, a turnover may mix encodings freely, and nothing has to be switched before a
scan. If a future session finds itself adding a batch-wide source encoding setting, this is the
paragraph that says it was tried and removed within the hour.

| decision | where it lives |
|---|---|
| Source encoding is named **per clip in its own metadata** | COLOR_AND_FORMAT section 1, PRD section 4 and FR-15 |
| **There is no mode.** `DaVinci Intermediate WideGamut` is one entry in the table | OQ-39, answered then dissolved; QC-038 retired |
| A turnover may **mix encodings** freely | COLOR_AND_FORMAT section 1 |
| Resolve's IDT names still do not match OCIO's, and the table is needed again | OQ-34, **reopened, then required** |
| **The CLF starts at the source encoding**, so the tool applies no input transform on a graded plate | OQ-37, **answered yes** |
| **ACEScct leaves the chain entirely** | COLOR_AND_FORMAT section 1 |
| The tool still carries **multiple input transforms, picked per shot from the metadata** | PRD FR-15, OQ-34 |
| Applied on the **aux still** and on rows with no CLF, never alongside a CLF | COLOR_AND_FORMAT section 1, QC-048 |
| What field the metadata is in, and what string goes in it | OQ-44, **new** |
| An unnamed or unresolvable encoding blocks the aux still | QC-046, QC-047, **new** |
| Whether a session's CLF really contains the conversion | OQ-46, **new, and the one open risk** |
| Whether the session should hand aux stills over already converted | OQ-45, **new** |

**Three things checked rather than assumed on 2026-09-12.** All three of today's cameras exist
in the pinned config, as `S-Log3 S-Gamut3.Cine` and three siblings, `CanonLog3 CinemaGamut D55`
and `BMDFilm WideGamut Gen5`, and each built a processor through `color.input_transform`. So
did `DaVinci Intermediate WideGamut`. **The transforms are not the problem; the names are.**

**Two traps, both silent, both written up in COLOR_AND_FORMAT section 1.** A curve name does
not choose a gamut - "S-Log3" names four colour spaces - so the shooters must be asked to write
the curve *and* the gamut, ideally the Resolve input transform name verbatim. And the config
carries one variant where the camera offers several: LogC3 at EI800 only, BMD Film Gen 5 only,
Canon at Cinema Gamut only. Neither failure looks wrong on a monitor.

**What did not change**: everything downstream of the input transform. The CLF, both branches,
the LUT bake, the EXR header and every QC rule take the source encoding as a string, and
`clf.ShotColor` has carried it **per shot since M4.5.1**. That is why this is a switch and not a
fork, and why M4.6 is a small milestone rather than a rewrite of M4.5.

### The studio tracker arrived, and M4.3 was built against it

**On 2026-09-11 the user supplied the real shot tracker**, `docs/Pre Pro Shot Tracker - W1.csv`:
790 rows across 55 turnovers of a live production. **OQ-2 is answered** and the full column
mapping is in `QC_RULES.md` under the QC log structure. Three things came out of one file.

- **The tracker has 39 columns and the tool owns nine of them.** The rest is production state
  the vendor's team fills in for weeks after delivery: statuses, owners, difficulty grades,
  callout movies, requesters. So `shot_tracker.xlsx` is **additive rows in the tracker's own
  column order**, never a sheet of our own design, and never anything that could overwrite a
  column someone else maintains. PRD section 6 already said "for paste into the studio tracker";
  the sheet turns that from an intention into a specification.
- **The guessed default template was wrong in ten of its eleven columns.** Only Shot Code
  survived. Four of the columns it invented - duration, source TC in and out, version, delivery
  path - have no home in the real tracker at all, and stay in the QC log where they already are.
  Worth remembering the next time a default is written to stand in for a studio's real document.
- **Two settled things came unsettled.** OQ-19 is reopened, because the FPS column says 24 is no
  longer the only rate on current turnovers, and QC-026 is an error. OQ-41 is new: the stringout
  filename checker accepts **none** of the 55 real names, so it must not ship as a checker.

What the sheet confirmed is worth as much as what it broke. **628 of its 782 reference filenames
parse under the existing output grammar**, to the right kind, and the misses are rows that
predate the convention rather than disagreements with it. The shot code is four letters and four
digits, which is what `naming.py` already reads, whatever the column header's `ABCD123` says.

**M4.3 was then built against it the same evening**, which is the whole of what M4 had left.
Three things in it are worth not re-deriving:

- **`core/exports.py` reads no template file.** The tracker's columns were to be loaded from a
  studio template configured in Settings, which was the right shape while OQ-2 was open and
  nobody knew them. They are known now, and a template loader would be a configuration point
  standing where a fact belongs. PRD section 7's Exports settings group loses its only entry.
- **`qc.DELIVERABLE_RULES` and `DELIVERABLE_RULES_BY_KIND` exist so NA means something.** The
  Deliverables sheet is one column per QC-1xx rule, so the list has to exist whole rather than
  being inferred from whichever rules fired, and the per kind map is what stops an mp4 reading
  PASS on a rule about EXR compression it was never asked. Two tests read `qc.py`'s own source
  back, so a new rule cannot be added without a column appearing.
- **QC-053 went into `preflight`, not into the model rules**, and the existing tests are what
  caught it: it opens a file, exactly like QC-052 next to it. The first placement made the
  fixture row, the one documented as passing every default rule, emit a warning.

### M4.5.2 is built, and OQ-30 and OQ-33 are built to their defaults

`core/clf.py` reads the colour session package: the final EDL as the conform, the approved
In/Out and the CDL per event, and the CLF for a row, loaded, hashed and probed. 42 tests.
Five things in it should not be re-derived.

- **The final EDL is parsed here rather than through `core/timeline.py`.** The plan said to
  reuse the otio walk and half of it does exist, but otio's CMX3600 adapter hands back the CDL
  as numbers and **drops the event id and the verbatim `*ASC_SOP` / `*ASC_SAT` lines**, which a
  delivered EXR is specified to carry. Reading a fixed format event line directly costs less
  than reconstructing what the adapter threw away. Timecode still goes through
  `frames.timecode_to_frames`, so drop-frame is refused rather than misread, and the module
  docstring says all of this so the next session does not undo it.
- **OQ-30's answer is one constant, `clf.MATCH_FIELD`.** A row matches an event on
  `FROM CLIP NAME`, compared without the extension and without case, because a case difference
  between a Resolve export and a macOS filesystem is not a disagreement about which shot this
  is. The fallback wants the reel **and** a source range inside the media's own timecode, since
  reels repeat across a turnover and timecode repeats across anything not jam synced. Nothing
  returns a nearest candidate: unmatched is None, and QC-009 is what fires.
- **OQ-33's answer is the shot code in the CLF filename**, and two CLFs naming one shot raises
  rather than choosing, because picking either is picking a grade. A CLF naming no shot at all
  is nobody's rather than an error.
- **An EDL's out timecode is the first frame after the cut and is converted on the way in.**
  `ConformEvent` ranges are inclusive like every other range in the codebase, so nothing
  downstream has to remember which convention the file used.
- **QC-039 is a probe of what the CLF does to white, not of what it is called.** ACEScct 1.0 is
  222 in scene linear; a display rendering tone maps it to about 1.0, four stops down still
  answers 13.9, so `SCENE_LINEAR_FLOOR` is 2.0 and sits clear of both. The test fixture bakes a
  real ACES output transform into a 3D LUT to make the failing case, which is also the only way
  such a CLF can exist: the output transform uses ops CLF cannot express, so a session that
  shipped one would have had to bake it exactly the same way.

**What is still not checkable is which fields Ben's export actually populates.** Both defaults
are built and both are pinned by tests, so one real EDL and one real CLF confirm or move one
constant each.

**The rules are still not wired.** QC-008, QC-009, QC-019, QC-039 and QC-045 all read this
module and none of them can fire until a batch knows where its colour session package is. That
is a Settings value (PRD section 7, Colour group) and the wiring is **M5**. What M4.5.4 added is
a caller: the planner asks a `ColorSession` for each row's `ShotColor`, and
`proingest run --color-session` supplies the session headlessly. The rules themselves report
nothing yet.

### M4.5.3 is built: the view branch bakes to a cube

`color.output_transform` and `color.view_lut` finish the view branch, 11 tests. Four things in
it should not be re-derived.

- **OQ-29's open half has a default: `color.VIEW` is `ACES 1.0 - SDR Video` on `sRGB - Display`.**
  The pinned config offers four views on that display and the other three are not candidates:
  two are a D60 simulation and an un-tone-mapped debug view, and `Raw` is no transform at all.
  A test asserts the name is in the config, so a rename in a later ACES version fails at the
  first bake rather than in a delivered mp4.
- **The cube is sampled from the processor, not baked with `ocio.Baker`.** Baker only bakes
  between colour spaces a config names, so a chain with a `FileTransform` in it means a deep
  copy of the config, a synthetic colour space and a round trip through ACES2065-1 to define
  it. Sampling the processor on the cube's own grid is the chain exactly as composed, and the
  file is 35937 lines of text that OCIO cannot write anyway: `GroupTransform.write` supports
  CLF and CTF only, and answers "format resolve_cube does not support writing".
- **Red varies fastest, and that is pinned from both ends.** It is the `.cube` format's
  ordering, getting it wrong swaps channels in a way that looks like a grade, and two tests
  hold it: OCIO reads the file back as the transform it was baked from, and **ffmpeg's `lut3d`
  applies it to a 16 bit ramp and lands within 0.005 of what OCIO's own processor gives.**
  That second test is the one that matters, because ffmpeg is what will actually apply it.
- **Tetrahedral is not ffmpeg's problem, it is OCIO's.** ffmpeg's `lut3d` already defaults to
  tetrahedral. `ocio.FileTransform` defaults to linear, and reading the same cube that way
  moves mid grey twice as far off; a test pins the difference, which is what `INTERPOLATION`
  exists for.
- **COLOR_AND_FORMAT section 1 was corrected, not the code.** Its chain diagram had the view
  branch "stays in ACEScct" after the CLF, which was true in the morning version where the
  grade was a CDL and the plate branch did the conversion. The CLF lands in linear ACEScg, so
  the output transform starts there, and `color.output_transform` takes `PLATE_SPACE`. The
  bounded view branch property survives the correction and now rests on the LUT's own ends:
  ffmpeg sees log in and display out, and the unbounded stretch is inside the cube where
  swscale never sees it.

### M4.5.4 is built: render and exr are on the new chain

The last colour chunk, and the one that makes the other three visible in a file. 34 tests.
`render.py` now splits the way COLOR_AND_FORMAT section 1 does: `_plate_branch` builds one OCIO
processor per job and applies it to every frame on the way to an EXR, and `_view_lut` bakes the
same chain plus the ACES output transform into a `.cube` that ffmpeg applies with `lut3d`.
`exr.py` writes AP1 chromaticities, states `ACEScg`, and carries the CLF's name and sha256, the
source encoding and the CDL both ways. The fenced display referred block and
`TestSupersededDisplayEncode` are deleted. **M3's wrong reference encode is fixed**, which was
the oldest item on the open list.

Seven things in it should not be re-derived.

- **What a worker needs to know about colour rides on the job, as `clf.ShotColor`.** A path, a
  colour space name and the CDL: three picklable things, because a job crosses a spawn boundary
  and no `ocio` object survives one. The worker calls `ShotColor.load()` once per job to turn the
  path back into a transform, which also means **the digest in the header is taken at render
  time** and describes the file that was actually applied.
- **`plate_transform` is applied only when there is no CLF**, and `ShotColor.plate_transforms`
  is the one place that decides. Applying both converts ACEScct to ACEScg twice and delivers a
  plate about seventeen times too dark, with no error anywhere. A test holds it by writing a CLF
  that only converts and asserting mid grey still lands on 0.18.
- **An aux still is never graded, and that is a decision rather than an oversight.** The aux
  names are `colorChart`, `mirrorBall`, `greyBall` and `sizeRef`. A creative grade applied to a
  colour chart destroys the only thing the chart is delivered for, and it does it invisibly. It
  still gets the input transform, so it lands in ACEScg like every other EXR. Enforced in
  `planner._aux_plan`, tested there, and now written into COLOR_AND_FORMAT section 1.
- **The cube goes in a system temp directory, not under `job.temp`.** The handoff proposed the
  job's temp area and the delivery folder is the wrong volume for it: that folder is a Google
  Drive mount (OQ-25), and a megabyte of LUT written there is a megabyte synced up and back for
  a file whose life is one encode. It is named after the deliverable so the ffmpeg command,
  which is logged verbatim, still says which shot the cube belonged to.
- **Both reference jobs of a shot bake their own cube.** Sharing one would mean a cache keyed by
  shot across worker processes; baking is 35937 samples through a processor and costs
  milliseconds.
- **`format=gbrpf32le` precedes `lut3d` in the filtergraph.** Without it ffmpeg negotiates a
  format between the decoder and `lut3d`, which is a high bit depth one today and is not
  something the delivered look should rest on.
- **An EXR header read back from the bindings empties when the file closes.** `handle.header()`
  hands back a live mapping, so an assertion on it outside its `with` block passes on nothing
  and a test that should have failed does not. Copy it with `dict(...)`. This cost twenty
  minutes and the tests that read a header now all copy.

**CI caught the one thing the dev machine could not.** Putting a `lut3d` in the encode's
filtergraph made `-shortest` stop bounding the audio: on the bundled ffmpeg 9.0.1 a
reference delivered 0.98 seconds of sound against a third of a second of picture, where
6.1.1 on this machine was still correct. The audio's length is now stated outright,
`apad,atrim=duration=<seconds>` from integer frames and the exact rational rate, so it
depends on no ffmpeg heuristic at all. **The lesson generalises**: a filter added to the
video chain changes the timing of the audio chain, and only the runner with the shipped
binary will say so.

**Two assumptions came out of it and both are recorded.** OQ-42: an EXR source is transformed as
though it were the studio standard log, which is a wrong image rather than an error for a
sequence already in ACEScg, and reading the source's own header is the way out. OQ-43: the
resize happens before the colour transform rather than after it as the chain diagram draws it.
Both orders are bounded so nothing clips and the property the diagram protects holds, but log
and linear resampling ring differently on a high contrast edge. COLOR_AND_FORMAT section 1 was
corrected to say where the resize actually is.

**`proingest run --color-session <final.edl>` is how the package gets in** until Settings holds
it (PRD section 7). Without it the run produces every deliverable in ACEScg, ungraded; the CLF
is the only difference. The EDL's rate comes from the first row that has media, and a batch
carrying more than one rate prints which was used rather than choosing silently (OQ-19).

### M4.6.2 is built: the tool converts nothing ahead of a CLF

The correctness half of M4.6, built 2026-09-12 and the only chunk that changes a delivered
plate. `ShotColor.plate_transforms` returns **the CLF alone** where there is one, and where
there is none it returns one leg, source encoding to linear ACEScg. 876 tests. Four things in
it should not be re-derived.

- **The chain lost a space, not just a call.** `color.WORKING_SPACE` and
  `color.plate_transform` are gone, and `color.input_transform` now goes straight from the
  source encoding to ACEScg. They were two legs because the first landed where the grade began,
  in ACEScct; the grade begins at the source now, so there is no intermediate space to arrive
  in and no way to apply half a chain. ACEScct survived in exactly one place, as the
  placeholder value of `DEFAULT_SOURCE_ENCODING`, and M4.6.1 deleted that the same day.
- **The tests pin which transforms a chain contains, not only what it does to a pixel.** That
  is the point: before this, `plate_transforms` returned `[input_transform, clf]` and every
  numeric test still passed, because the default source encoding made the extra leg identity.
  A test that only checks pixels cannot see this bug at all. `test_the_tool_converts_nothing_ahead_of_a_clf`
  is the numeric one that can, and it works by setting the source encoding to something the
  CLF does **not** start at, which is exactly the real case.
- **The CLF fixtures still start at ACEScct and that is now arbitrary rather than wrong.** A
  real session's CLF starts at whatever its clip is encoded in, the tool applies it whole, and
  so the fixture's choice of starting space no longer means anything to the tool. It is named
  `CLF_SOURCE` in the fixtures rather than borrowed from `core/color.py`, so nothing reads a
  constant of the tool's as though it were a fact about the session.
- **QC-039's probe came out of this looking weaker than it went in, and that is OQ-47.** The
  probe feeds log white through the CLF and wants the answer above 2.0. That floor was set
  when white meant 222, which is what ACEScct white is worth; out of C-Log3 white is worth
  **14.7**, so four stops of grade answers 0.92 and the probe cannot tell it from a display
  rendering's 1.0. Measured, not estimated, and a ratio probe separates every case cleanly
  (1.88 to 3.37 against 1.010 to 1.015, and invariant to how dark the grade is). **Not changed
  here**, because it is QC-039's definition rather than this chunk's chain, and because the
  failure is a valid grade refused rather than a bad one delivered.

### M4.6.1 is built: the source encoding is a per row fact

Built 2026-09-12, straight after M4.6.2. `ShotRow.source_encoding` holds what the clip's own
metadata names, verbatim, and it is what reaches every job. **`color.DEFAULT_SOURCE_ENCODING`
is deleted**, and so is every parameter that carried a batch-wide value down to a row:
`plan_batch`, `ColorSession.shot_color` and `proingest run --source-encoding` all lost one.
882 tests. Four things in it should not be re-derived.

- **The constant was deleted rather than given a better value.** OQ-39 named a studio standard
  on 2026-09-12 and the same evening dissolved the question: there is no batch-wide encoding to
  name. A default would have been wrong for every clip it was not guessed for, and wrong
  silently, since a plate converted from the wrong log looks like a grade decision.
- **A chain with no CLF and no encoding is refused, not passed through.** That is the one
  combination that cannot be built: nothing turns those pixels into ACEScg, and writing them
  unconverted would deliver a log frame under a header claiming ACEScg. `plate_transforms`
  raises, which is a backstop rather than the report: QC-046 and QC-047 are what stop the row,
  and they are M4.6.4.
- **A graded row does not need the string at all**, which is why the severity in QC-046 is
  scoped the way it is. The CLF is the whole chain there, so a clip that named no encoding
  still renders correctly and what it loses is one line of EXR header provenance. The header
  leaves the attribute **out** rather than writing an empty one, exactly like `proingest/clf`.
- **Nothing fills the row in yet.** The scan reads no metadata until M4.6.4, so every scanned
  row names no encoding, and `tests/test_cli.py` stamps one onto a saved batch before it runs
  it. That helper is scaffolding with a date on it: M4.6.4 deletes it.

### M4.6.3 is built: the input transform table

Built 2026-09-12. `color.INPUT_TRANSFORMS` maps what a shooter writes onto one colour space in
the pinned config and `color.resolve_encoding` is the only way in. 897 tests. Four things in it
should not be re-derived.

- **The table only carries names the config does not already know.** OCIO's own lookup takes
  aliases and any casing, so `S-Log3 S-Gamut3.Cine`, `acescg` and `DaVinci Intermediate
  WideGamut` all resolve with no row at all, and what comes back is the config's own spelling
  so two clips that named one space two ways record the same provenance. Three rows exist:
  `c-log3`, `bm film` and `davinci wide gamut`, which are the names the shooters were given.
- **`S-Log3` has no row on purpose.** It names four colour spaces in this config, a curve does
  not choose a gamut, and a row picking one would be picking a gamut on the shooter's behalf.
  It resolves to nothing and the error names all four.
- **The candidate list in the message is built by a substring search, and that search never
  matches.** It exists so QC-047 can say "S-Log3 names 4 colour spaces here" rather than "not
  found". Resolving to any of them would be the nearest miss the table exists to refuse.
- **An unresolvable name is not an exception on the way to a job.** `clf.resolved_encoding`
  catches it and carries None, because a graded row renders correctly without it and both
  paths that build a `ShotColor`, with a session and without, need the same answer. QC-047 is
  where it is reported, and that is M4.6.4.

### New scope, 2026-09-12 (late): three things the user asked for, two now built

Asked for immediately after M5.5 landed, as a heads up rather than a change of direction.
All three are in section 5's tables and in the specs that own them.

- **The run should narrate itself above the list.** **Built the same day as M5.10**; the note
  further down says how. `docs/UI_SPEC.md` section 7.1 is the spec.
- **Every toolbar button should say what it does on hover**, concisely. **Built 2026-09-13 as
  M5.11**; the note further down says how. `docs/UI_SPEC.md` section 1 is the spec. The half
  worth building carefully was the **disabled** button, and that is what it got - plus one note
  on a button that is *enabled*, Run over a batch with no colour session, which is the case that
  actually reads as broken.
- **A user guide**, and it is a milestone rather than a task: install, quickstart, then a
  section per surface of the window, with screenshots, delivered as a PDF or something that
  pastes into Google Docs. **PRD FR-17** and **M9**, five chunks in section 5. The user said
  "later", so it is scheduled after the interface it documents rather than alongside it.
  **OQ-49** is the one question in it: which of those two forms, and whether anybody but the
  editor edits the result.

**The one left is the guide, and it is partly blocked.** M9.1 waits on M7 and M9.4's shipped
images wait on the Mac session; M9.2 and the screenshot harness could be drafted today. Its
button reference should **read `ui/toolbar_help.py`** rather than restate it, which is the whole
reason that module is apart from the window.

### M5.6 is built: the pane beside the list

Built 2026-09-12. `ui/metadata.py` and `ui/metadata_pane.py` are new, `ui/shot_list.py` gains
`selected_turnover`, `ui/issues.py` gains `select_result`, and `core/settings.py` remembers
which sections are shut. 78 tests, 1344 in total. **Driven on a real three shot turnover**
with a hand written camData file: nine sections, the lens and filter reading out of the side
file, and a three row selection reporting `mixed` on the clip name and `3840x2160` on the
resolution they agree about.

- **The field list is a value, not a layout, and that is the point of the split.**
  `describe(rows, batch)` returns `Section`s of frozen `Field`s with no Qt in it. Two things
  fall out. **OQ-26 wants a review session with the AD** about which fields earn their place,
  and arguing with a list is easier than arguing with a widget. And **the pane redraws only
  when the answer moved**, because two answers can be compared exactly, which is what lets it
  be wired to every signal that might change a value without counting how often they fire.
- **Where the pane gets its updates from was the thing to decide first, and it is three
  signals.** The selection is the obvious one. A cell commit (`row_edited`) changes a value
  while the selection has not moved. And `_show_results` is now the single method that
  refreshes the Issues dock and the pane together, called from all five places that rewrite
  QC wholesale - opening a batch, a scan landing, pre-flight, and a run finishing. **The run
  timer is deliberately not one of them**: it fires five times a second and a run does not
  change what the pane says until `apply_results` has run, which `_show_results` covers.
- **A right `QDockWidget` rather than a splitter pane**, which is three of section 12's asks
  for free: it collapses to nothing, `saveState` remembers its width and whether it is
  showing, and `toggleViewAction` is the Ctrl+I the spec names. Closable but **not movable or
  floatable**: section 1 calls it a fixed width reading surface, not a second workspace.
  Which sections are shut is the one thing Qt's blob cannot hold, so it is a settings field
  storing **the titles of the shut ones** - a section a later chunk adds then arrives open.
- **Every value is one elided line, and that is structural rather than cosmetic.** A wrapping
  `QLabel` reports a one line minimum height whatever it will actually need, so a column of
  them in a scroll area gives the scroll area a minimum far too small: the sections are
  squashed to fit the viewport instead of scrolling, and one overlaps the next. That is what
  it did, and the screenshot is how it was found. One line per field makes every height
  exact, and it also stops one unbreakable 40 character value setting the pane's minimum
  width. What is given up is reading a long message here, which is why a rule ID in the pane
  clicks through to the Issues dock and why the dock carries the full text.
- **The pane never reads a file.** camData is the one field that lives on disk, so it arrives
  through a lookup the window supplies and caches per batch. The pane redraws on every arrow
  key; an uncached read would be a round trip to a Drive mount per keystroke.
- **There is a Colour section and section 12.2's table did not have one.** M4.6 put the
  source encoding, its origin and the CLF path on the row after that table was written, and
  all three are exactly what the pane is for: facts about a shot with no column in the list.
  UI_SPEC 12.2 now carries the row and says when it was added.
- **A turnover header shows the Turnover section alone**, and the turnover's own results are
  fields inside it rather than a QC section beside it, so section 12.3's sentence stays
  literally true. The rows' results are not rolled up: the group header in the list already
  counts them and the Issues dock lists every one.
- **The QC section is built across the selection rather than merged field by field**, unlike
  every other section. Two rows with different problems agree on nothing, so the merge would
  reduce it to `mixed`, which is the one answer that helps nobody.
- **QC-012 now names the path the timeline claimed.** Section 12.3 says an unresolved row is
  exactly when somebody wants to see it, and **nothing stores it** once the row has no media,
  so the rule's message is the only record. Three lines in `core/scan.py`; the alternative
  was a new `ShotRow` field, which is a schema change for a string that is already written
  down somewhere.

**What M5.6 does not do.** The pane shows no deliverable: section 12.4 keeps that boundary
and the Deliverables tab in the bottom dock is where an output file belongs. Nothing about
a Drive placeholder that has not downloaded yet, which section 12.3 asks for and which
depends on a scan behaviour nothing has needed yet. And **the field list is a default, not an
answer**: OQ-26 is still open and wants the review session `docs/MAC_SESSION.md` now has a
line for.

### M5.10 is built: the run says what it is doing

Built 2026-09-12, out of order and ahead of M5.6, because it finishes the thing the user
had just watched being built. `ui/run_strip.py` is new, `RunProgress` gains `activity`,
and the window narrates the steps either side of the pool. 17 tests, 1266 in total.
**Driven end to end on a real two shot turnover through the real pool**: 14 deliverables,
the line naming each step in order, and the banner taking the strip when it finished.

- **The strip is one band with three states and the empty one is the widget hidden.**
  A `QStackedWidget` would have been the obvious way and it is the wrong one: it takes the
  tallest page's height whichever page is showing, so a window that has never run a batch
  would carry an empty band above the list forever. Toggling two children and the widget
  itself gives the height back, and `RunStrip.state` is the one place the "only ever one
  of them" invariant is asserted.
- **The line names the longest running job, not the newest message.** `_states` is in the
  order jobs first reported, so the first one still running is the oldest one still
  running, and it holds still until it finishes. Following the newest message instead is a
  line that changes several times a second with four workers, which is a flicker rather
  than a sentence. This is the one decision in the chunk that is not obvious from the
  spec.
- **Four steps come from the window rather than from a worker**, because they happen on
  the UI thread with nothing else running: checking the batch, planning it, applying what
  came back, and writing the two spreadsheets. Those are exactly the moments the window
  looks frozen, so they are the ones most worth naming.
- **`RunStrip.say` repaints immediately**, which is not decoration. Two of those four
  steps block the UI thread for as long as they take, so a label that waited for the next
  trip round the event loop would appear **after** the step it announces had finished. The
  repaint is guarded on the text having changed, so the five draws a second a run does
  cost nothing.
- **All four surfaces read one `RunProgress` and are drawn by the one 200 ms timer.**
  That was the thing section 7.1 said would decide the shape and it turned out to cost
  nothing, because M5.5 had already put the arithmetic in one Qt-free object.
- **There is no "Verifying" step and the spec now says why.** Post-render QC runs inside
  the worker between the rename and the record coming back and the pool publishes nothing
  for it, so the line says "Rendering" through it. Saying otherwise means a new
  `render.ProgressState` and a publish inside `render_job`, which is a core change for a
  wait nobody has measured. UI_SPEC 7.1 carries the note.
- **The banner's link was unreadable and this chunk fixed it.** It rendered in Qt's own
  `#0000ff` on the `#1b1e23` band. A stylesheet cannot select an anchor inside a `QLabel`,
  and the palette's `Link` role that could is overridden by the application stylesheet
  this window sets, so the colour is written into the anchor by `banner_text` from
  `run_strip.LINK_COLOR`. A test pins it. It is M5.5's bug, fixed here because it is in
  the widget this chunk took ownership of.

**What M5.10 does not do.** The bar reports the same frame-counted percentage the status
bar does, so a run made only of copies falls back to counting jobs exactly as section 7's
numbers do. The line says nothing between the last job finishing and `_run_finished`
running, which is a gap of milliseconds. And a run started from the CLI narrates nothing,
because this is a window and `proingest run` has its own reporter.

### M5.5 is built: the run reaches the window

Built 2026-09-12. `ui/runner.py` is new, the window gains Run, Stop, the status bar line, the
exports and the banner, and the Progress column finally has a bar in it. 50 tests, 1249 in
total. **Driven end to end on a real two shot turnover before it was committed**: ten
deliverables, both spreadsheets, the banner naming `_reports`, and every row at 5/5.

- **The pool goes on a `QThread` and nothing else changed about it.** `render.execute`
  already takes an `on_progress` callable and a `multiprocessing.Event`, and it already
  calls back in the calling process rather than in a worker, so this chunk is wiring and
  not a mechanism. The shape is `ui/scanner.py`'s, deliberately: a worker `QObject` moved
  onto a thread that lives only as long as the work. **The jobs cross and the batch does
  not**, which is the same rule the scan obeys and is easy here because a `DeliverableJob`
  is self contained already: it crosses a process boundary every run.
- **Progress arrives on a third thread and that is fine.** `execute` drains its queue on a
  plain Python thread, so `on_progress` runs there; the receiver lives on the UI thread, so
  Qt queues the signal and the message arrives where it can be drawn. Nothing shares state
  across the boundary: `Progress` is frozen, and it is the only thing that crosses.
- **Nothing repaints per message.** A hundred shot run emits a message per frame per worker,
  and Qt coalesces none of it. The messages are folded into `RunProgress` and a 200 ms timer
  draws the status bar and the rows, which is one mechanism for both and is why the message
  rate cannot become a frame rate problem. `RunProgress` has no Qt in it, so the percentage,
  the throughput and the ETA are testable against a fake clock.
- **The percentage is counted in frames and the row bars in deliverables.** Jobs are wildly
  uneven - a 240 frame plate and a camData copy are one job each - so a job counter jumps.
  A run made only of copies has no frames at all and falls back to counting jobs. Within one
  row the four deliverables count equally, because that bar is 90 pixels wide and answers
  "is this row moving" rather than how many frames a reference has beside a plate.
- **Rendering is a state only a live run can report.** `row_state` reads the deliverables'
  statuses and `render.apply_results` does not write those back until the run ends, so a row
  in flight would otherwise look untouched for the whole run. `ShotListModel.state_for` is
  `row_state` plus what the run knows, and **skipped still wins**: it is the one state the
  editor chose rather than the tool.
- **A live run outranks the recorded status in the Progress cell too**, for the same reason,
  and a deliverable this run never planned keeps whatever a previous run wrote on it.
- **The run writes the two spreadsheets and the banner says where.** UI_SPEC section 7's
  banner names them, PRD section 7 puts them at the end of a delivery, and doing it here is
  what makes the sentence true. A batch whose rows have no shot code has no show to file them
  under, which `exports.report_paths` refuses; the banner then says nothing was written
  rather than naming a folder that does not exist.
- **A stopped run says "Run stopped" rather than calling itself complete.** The spec gives
  the wording for a finished batch only, and the counts alone would read as a batch that
  finished with most of it skipped.
- **`Runner.shutdown` quits the thread before it waits, and that was a real bug.**
  The thread normally ends when `_collect` runs - on the UI thread, which is the thread
  `shutdown` is about to block. Waiting without quitting first was a deadlock that lasted
  until the 120 second timeout, which a test caught by taking exactly that long.

**What M5.5 does not do, and where each lands.** The run carried **no colour session**, so
every row planned ungraded exactly as the CLI did without `--color-session`. **M5.7.1 changed
that**: the session is ingested onto the rows and a turnover with none is held back by QC-008,
so a run is graded or it does not happen. The concurrency is `render.DEFAULT_WORKERS` until Settings can set it (FR-12).
The rendering dot is the accent colour but **is not animated**, which section 3 asks for and
which wants a repaint timer of its own. Pre-flight and planning run on the UI thread, which
is the one thing in this chunk worth measuring on a real turnover (section 9). And the
toolbar's **Export button is still disabled**: the run writes both spreadsheets, so what that
button is for is writing them again without rendering, which no chunk in section 5 owns. It
is a handful of lines against `_write_reports`, and it wants asking for before it is built.

### M5.3 is built: the list can be typed into

Built 2026-09-12. `ui/shot_model.py` gains `flags`, `setData`, `parse_frame` and
`set_skipped`, `ui/shot_list.py` the cell editor, Tab and the skip prompt, and
`ui/autosave.py` is new. 64 tests, 1125 in total. Section 5's grammar, section 4's Tab and
Ctrl+K, and the save that follows a commit. Six things in it should not be re-derived.

- **A commit re-runs the row's rules and nothing else, and that was the question to
  settle first.** `qc.apply_row_rules` is per row and cheap, which is what UI_SPEC
  section 5 asks for. The only batch level input the row rules take is the clip name
  counts QC-011 needs, and **no editable cell can change them**: `clip_name` is the name
  the turnover arrived with, and the four editable cells are Shot, In, Out and Notes. So
  a batch wide re-run on every keystroke would recompute the same answers. The rule
  settings and the counts are cached at `set_batch` rather than rebuilt per commit.
- **A range the media cannot satisfy is stored and then reported, never refused.**
  QC-031 and QC-032 already say it, they say it about the row, and an editor typing Out
  before In on the way to a valid range would otherwise be stopped halfway. The cell
  refuses only what it cannot parse at all, and that refusal leaves no trace: a QC result
  about a value that was never committed would outlive the typing that caused it.
- **The editor opens on the shot code, never on the clip name the cell falls back to.**
  A row with no identity shows its clip name in the Shot column, and an editor prefilled
  with it commits the clip name as an override the moment somebody presses Enter. Every
  other editable cell opens on exactly what it displays, In and Out included, so what is
  typed is read against what was shown.
- **`QTreeView` ships with tab key navigation off and `QTableView` ships with it on.**
  With it off, Tab moved focus out of the list entirely unless a cell editor happened to
  be open, and `moveCursor` - where the walk across the four editable columns lives - was
  never asked. **Found by driving a real window, not by a test**, which is the second
  time that has paid for itself in two chunks. One line turns it on and one test pins it.
- **Qt commits an editor on a queued connection, not when the key is pressed.**
  `QAbstractItemDelegate` posts `_q_commitDataAndCloseEditor` so the editor can validate
  first, so the row still holds its old value for the rest of that event loop turn.
  Nothing in the suite is affected, because the tests commit through `setData` the way
  the delegate does; it is written down because a test that sends Return and asserts
  immediately would fail for a reason that has nothing to do with the code.
- **Autosave is debounced, and a batch with no file keeps its edits pending.** Tabbing
  along a row is four commits in a second and a batch file is the whole batch serialized,
  so the write happens 1.5 seconds after the last one. New, Open and Save are M5.4, so
  until one of them names a file there is nowhere to write: the pending state is kept
  rather than dropped, the first `watch` with a path writes it, and closing the window
  flushes. A write that fails is logged and stays pending, because the batch can be on the
  same network mount as everything else and a mount that blinked is not a reason to lose
  an edit.

**The prompt is the view's and the facts are the model's.** Ctrl+K asks for a reason
through `QInputDialog` in `ui/shot_list.py`, because a dialog cannot live in a model, and
`ask_skip_reason` is its own method so a test can answer it: an offscreen modal is a hung
suite rather than a failed assertion. Un-skipping keeps the reason, so a row toggled off
and on is not a second interrogation about a decision already explained.

### M5.2 is built: the list shows a batch

Built 2026-09-12. `ui/shot_model.py`, `ui/shot_list.py` and `ui/batch_bar.py`, 86 tests.
UI_SPEC section 2's columns over a two level tree, section 3's dot and tints, the three state
In/Out display and the search box. **Read only**: editing is M5.3, so nothing here writes to a
row and nothing here can disagree with the rules about what a row now says. Seven things in it
should not be re-derived.

- **Record timecode needed a fact the batch was not keeping.** `ShotRow.record_in` is measured
  from the timeline's own zero, and an edit that starts at `01:00:00:00` is the normal case, so
  a row shown without the timeline's start reads an hour early. `Turnover.timeline_start` is
  new, additive, and filled by the scan from `Timeline.global_start`, which was already parsed
  and then thrown away. A batch saved before it reads back zero, which is what a timeline
  starting at zero would say anyway.
- **`ShotRow.edit_context` is core's, and there is one of it.** The list renders a frame as
  timecode through it and M5.3's typed edit will read a timecode back through the same object.
  Two of them is how a display and its editor come to disagree about which frame an hour is.
  Its **record anchor is the clip's record start paired with the snapshot's In**, which does
  not move when the editor trims: that is what keeps the mapping linear instead of sliding
  with every edit.
- **What a cell says and what colour it is are both the model's answers.** A delegate that had
  to work either out would be reading the model twice, and a stylesheet cannot see a model at
  all, which is why the dot and the tints are painted from `shot_model.py` against the palette
  `theme.qss` states at its top.
- **`RowState` is an ordered enum and the order is the precedence.** A row is often several
  states at once: skipped beats everything because the editor chose it, a render that is still
  happening beats one that failed, and a failure beats the rules that were checked before it.
  `turnover_state` is the same order applied to a group, including the turnover's own rules,
  since QC-001 and QC-002 leave it with no rows to carry the colour.
- **The two line cell is one delegate on every column, not on In and Out alone.** The row has
  to be tall enough for two lines whatever the cell holds, and a delegate that only some
  columns used would leave the rest centred against a different height.
- **The status dot is drawn once per state and cached.** Fifteen columns of a hundred shot list
  repaint often; a pixmap per cell is a pixmap per repaint. A test compares `cacheKey`, because
  Qt hands back a new Python wrapper each time and identity would pass for the wrong reason.
- **The frozen left columns are deliberately not here. They are M5.9**, built last for the
  reason section 5 gave: QTreeView has no such feature, and the overlaid second view has to
  keep working through editing, filtering and selection, which were the next two chunks.

**One thing is a stand-in.** Section 2 wants icons in the Audio and Side files columns and the
tool ships no icon set at all, toolbar included. The columns carry the count and the names
instead, which is honest and searchable, and the icons can replace them whenever there are any.

### M5.1 is built: the window, and the harness that lets a window be tested at all

Built 2026-09-12, the first chunk of M5. `ui/app.py`, `ui/main_window.py`, `ui/theme.qss`,
`ui/paths.py` and `core/settings.py`, 41 tests. There is no model in it: what it builds is
UI_SPEC section 1's frame, the menu bar with its three macOS roles, the toolbar in its three
groups, the bottom dock's three tabs, the status bar and section 10's empty state. Six things
in it should not be re-derived.

- **Qt tests run on the `offscreen` platform, and that is what makes the UI testable in CI
  at all.** `tests/conftest.py` has one session scoped `qt_app` fixture, because Qt allows one
  `QApplication` per process. Neither runner has a display, so the alternative was a suite that
  only runs on a developer's desktop. The Linux job gained `libegl1`, `libxkbcommon0` and
  `libdbus-1-3`: the offscreen **plugin** still has to load even though it draws nothing, and
  those are what the PySide6 wheel links against. glib is deliberately not named, because its
  package was renamed in the 64 bit `time_t` transition and either spelling breaks on the
  other Ubuntu.
- **`main([])` used to print help and now launches the app, which hung the suite rather than
  failing it.** `tests/test_cli.py` called it, the call entered Qt's event loop, and the run
  never came back. The test now stubs `ui.app.run` and asserts the launch; `--help` keeps its
  own test. **Nothing in the suite may ever call the real one.**
- **Where the settings file lives is `ui/paths.py`'s answer, never core's.** UI_SPEC section 11
  says to ask `QStandardPaths`; core imports no Qt, so a core copy would be a second
  implementation of one path that could not check Qt's. So `core/settings.py` takes a path in
  every function and guesses nothing, and a test points a window at a temporary file.
- **A settings file is disposable in a way a batch file is not.** Unreadable is logged and
  replaced with defaults rather than raised, because refusing to launch over a preferences file
  is a worse failure than losing a window position. Keys a newer version wrote are kept on save,
  so a downgrade is not destructive. Written atomically, the same rule as a deliverable.
- **Every action exists from the first chunk and the ones with nothing behind them are
  disabled.** A toolbar that grows buttons chunk by chunk hides the shape of the tool from
  whoever is reviewing it, and a disabled button cannot be mistaken for a feature that does
  nothing. Each is enabled by the chunk in section 5's table that wires it.
- **Qt is imported inside `_launch_ui`, not at the top of `__main__.py`.** Every subcommand
  runs headless and importing PySide6 to print a scan table would cost the import for nothing.
- **The organisation name is left unset, and that is a fix rather than an omission.** Qt
  appends the organisation **and** the application to `AppDataLocation`, so setting both put
  the settings file in `Application Support/ProIngest/ProIngest`, one level deeper than
  PACKAGING.md specifies. Found by launching the thing with a real event loop rather than by a
  test, which is the argument for doing that once per UI chunk: nothing would have noticed
  until somebody went looking for the file on a Mac. Two tests now pin the depth.

### M4.6.5 is built: the encoding is recorded where it can be read back

Built 2026-09-12, the last chunk of M4.6 and the only one that touches no pixel. 934 tests.
`ShotRow.source_encoding_origin` is set wherever the encoding is, rides to the worker on
`clf.ShotColor`, and comes out as `proingest/source_encoding_origin` in the EXR header; the QC
log's Shots sheet gains a Source encoding column beside the CLF one. Three things in it should
not be re-derived.

- **The two places record two different strings, on purpose.** The header names the **resolved
  colour space**, because that is what the pixels went through. The QC log names **what the
  clip's metadata said, verbatim**, because that column is read when QC-046 or QC-047 fires and
  what has to be corrected is the string somebody typed. Neither is derivable from the other:
  four names resolve to `S-Log3 S-Gamut3.Cine` and one resolves to nothing.
- **The origin's values are the two carriers the scan reads**, `clip metadata` and
  `container tag`, as `models.SourceEncodingOrigin`. COLOR_AND_FORMAT specified the pair as
  "the clip's metadata or a per row override" while no override existed and the second carrier
  did; **the doc was corrected rather than the code**. An override, if the tool is ever given
  one, is a third value rather than a second mechanism, and `UI_SPEC.md` asks for none.
- **An origin is written only beside an encoding.** A row whose name resolved to nothing still
  carries its origin through the planner, since that is exactly the case someone has to trace,
  but the header states no source for a name it does not state. The QC log carries the
  unresolvable name itself, which is the whole of what QC-047 needs.

### M4.6.4 is built: the encoding is read off the clip

Built 2026-09-12. The scan reads one named metadata field into `ShotRow.source_encoding`, and
QC-046, QC-047 and QC-048 report what it found. 924 tests. Five things in it should not be
re-derived.

- **OQ-44's field is built to a default and the default is a guess with a reason.**
  `scan.SOURCE_ENCODING_KEY` is `Input Color Space`, which is Resolve's own Media Pool column
  for the input transform, so it is the field most likely to be filled in already rather than a
  new one somebody has to remember. It is a `ScanSettings` value, so the answer to OQ-44 is one
  string and no code.
- **The clip's metadata first, the container's tags second.** The timeline is where a person
  filled the field in; a tag is the same string travelling inside the file, and it comes second
  because a consolidated media file can outlive the session that wrote it. This is not the
  colour tag COLOR_AND_FORMAT section 2 says to override: that is what a container writes
  because it must write something, and this is a named field somebody typed.
- **The metadata walk is by field name, not by path.** Resolve nests what it exports under a
  vendor key or two and which one is not knowable here, so `timeline.flatten_metadata` collects
  every string leaf keyed by its own name, outermost spelling winning. The fixture nests the
  field to keep that honest.
- **The row stores what was written, not what it resolves to.** QC-047's whole job is to quote
  a shooter's typing back at whoever briefs them, and the resolution happens at plan time where
  a failure is catchable. The EXR header still names the resolved colour space, because that is
  what the pixels went through.
- **QC-048 is in the pre-flight and QC-046 and QC-047 are in the row rules.** A row's chain
  depends on the CLF the planner resolved, so it is a fact about the run about to happen; a
  missing encoding is a fact about the batch as scanned and wants to appear the moment an
  editor looks at the list.

**One seam is left open on purpose.** QC-046 and QC-047 are errors on an **aux still** and
lesser elsewhere, which is what `QC_RULES.md` specifies. A row with no CLF *and* no encoding
also has nothing to render through, and it is not an error here, because at scan time no row
has a CLF yet and the rule would fire on every row of every batch. What catches it instead is
`ShotColor.plate_transforms` refusing the chain, which comes back as QC-100 with the reason and
nothing written. **When M5 wires the colour session into Settings**, the rules will be able to
tell "no session yet" from "this session had no grade for this row", and that is the moment to
decide whether QC-046's error widens.

### M5.7.1 is built: the colour session reaches the model

**This is the chunk that makes a run from the window a real delivery**, and it changed
what a run does rather than adding a page. Before it, Run planned every row ungraded and
wrote it. Now a turnover with no colour session is **held back**, and what the session
said lives on the rows rather than in a `ColorSession` a run has to be handed.

**Five things settled here that should not be re-derived.**

- **The session is ingested, not carried.** `clf.ingest(turnover, rows, session)` writes
  the approved In/Out, the CDL and the CLF path onto the rows and the EDL's location onto
  the turnover, and **nothing reads the package again**. `plan_batch` lost its `session`
  parameter and `ColorSession.shot_color` is gone; `clf.shot_color(row)` is the one place
  a row becomes a chain. The payoff is that a batch reopened after the package has been
  archived plans the same grade, and that the CLI and the window take the same path:
  `--color-session` ingests into every turnover and then plans.
- **The session is recorded per turnover, on the batch** (`Turnover.color_session_edl`),
  which is **OQ-50** and the one place three documents disagreed. PRD FR-12 put the
  location in Settings, PRD section 6 step 4 makes ingest a step in the user flow, and
  QC-008 is turnover scope and says one turnover can wait on colour while another
  renders, which a per-user Settings path cannot express. Built to the superset: with one
  turnover it behaves exactly like a batch wide value. The PRD now says so.
- **The approved cut overwrites a trim already made, and the ingest says which rows lost
  one** (`IngestReport.overwritten`, PRD section 6 step 4). QC-045 then fires on the
  one-off trim made *after* an ingest, which is the supported thing FR-5 keeps In/Out
  editing for. That is why `ShotRow.approved` is a third range beside `snapshot` and
  `current` rather than a flag: the three answer what the turnover delivered, what will be
  rendered, and what the AD signed off.
- **QC-008 holds back a turnover rather than stopping the batch.** FR-6's rule is that a
  batch scope error stops a run and a row scope one does not, and turnover scope sat
  between the two with nothing implementing it. `qc.blocked_turnovers` is that, read after
  pre-flight and passed to `plan_batch` as `skip_turnovers`, so planning has one authority
  rather than reading a QC list it cannot see being set. **The CLI now pre-flights before
  it plans**, which the window already did; nothing in pre-flight reads the plan.
- **QC-008 does not check the package's own files and QC-009 does.** An archived EDL costs
  a re-ingest, not a render, because what it said is on the rows. The one file a render
  still needs is the CLF, and that is per row, which is where QC-009 already lives.

**The cost worth knowing about**: a run with no colour session now writes **nothing**.
That is COLOR_AND_FORMAT section 1 as specified ("Rendering waits"), and it invalidated
six CLI tests that had been asserting the ungraded run. They now assert the refusal, and
`tests/fixtures/color.make_session` and `batches.ingested` are how a test that is about
something else gets past it.

`CDL` moved from `core/clf.py` to `core/models.py`, because a row carries one now and it
has to survive a save.

### M5.7.2 is built: the Settings page

Four of the six sections were live at this chunk and two were listed and disabled, which is
M5.1's rule for the toolbar applied to a page. **Advanced went live in M5.8.3**, leaving
Output as the only one still waiting. **Five things settled here.**

- **The page is a value and a drawing of it**, `ui/settings_form.py` and
  `ui/settings_dialog.py`, the same split `ui/metadata.py` and its pane use and for the
  same reason: which settings a tool should have is argued about, and an argument is
  easier against a list than against a layout. It also makes the page's contents
  assertable without a window.
- **The thresholds live in two places on purpose.** `AppSettings.rules` is the defaults a
  **new** batch starts from, and the batch takes its own copy at creation, which is
  UI_SPEC section 13's argument for the two roots: what a delivery was checked against is
  a record of that work. Apply writes both when a batch is open, and re-runs the rules.
- **Settings opens with no batch**, and it is the only toolbar action that does not wait
  for one, because it is where a new batch's defaults come from.
- **A field is on the page only if something reads it**, with one stated exception in the
  module docstring. That is what disabled Output and Advanced: reference quality and the
  EXR compression level are applied **inside a worker**, so a setting has to travel on the
  `DeliverableJob` rather than be read from the page, and that is a chunk rather than a
  field. The ffmpeg path override and the log level landed with M5.8.3, which is what gave
  logging somewhere to be configured from; **Advanced is live and Output is not**.
- **The Colour section is mostly read only**, and the three read-only lines are read from
  `core/color.py` rather than copied, so a config bump cannot leave the page describing a
  library that has moved. The input transform **overrides** FR-12 asks for are not built:
  an override has to reach a spawned worker, so it travels on a job like everything else,
  and half-building that on a correctness critical path is worse than not building it.

**Two wrong rule IDs were in the help text and no test could have caught them.** They
named QC-032 for a short shot and QC-033 for a long one, where the rules are QC-033 and
QC-034. Found by grabbing the page offscreen and reading it. A test now pins that every ID
a help line names is a live rule rather than a retired one, which catches a typo and a
retirement and **cannot** catch this: naming the wrong live rule is prose being wrong, and
asserting it would mean writing the mapping out twice.

### M5.7.3 is built: the window ingests a session

**The chunk that closed the gap M5.7.1 opened.** The checks refused to render a turnover
with no colour session and the window had no way to tell them there was one: a batch
ingested from the CLI and reopened in the window ran correctly, but a person working only
in the window could not deliver. `Ingest Colour Session` is a toolbar action beside Scan,
the editor points at the final EDL, and `clf.load_session` then `clf.ingest` do the work
the CLI already did. 19 tests.

**Five things settled here.**

- **One turnover at a time, and the selection is asked before the editor is.** A batch of
  one turnover never asks, a selected group header says which, and so does a selection of
  rows that are all in the same one; a selection spanning two says nothing and a list
  dialog asks. Turnovers with no rows are not offered, because an ingest writes onto rows.
- **The rate is checked before the chooser opens, not after it.** The EDL's timecode is
  read at one rate and a turnover can carry more than one (OQ-19), so the first row with
  media decides and the report says so when there was a choice. A turnover whose rows have
  no media has no rate at all, and being told that after picking a file is being told it
  one dialog too late.
- **The wording lives on `IngestReport`.** `counts` and `notices()` are the phrase and the
  three labelled lists, and both the CLI's print and the window's report read them, so the
  editor comparing a headless run against the window is comparing the same sentences. That
  is the whole of what `core/clf.py` gained; nothing else moved.
- **The report is a modal, and UI_SPEC section 1's rule was amended rather than bent.**
  Section 1 keeps modals out of review; this is the answer to a file dialog the editor just
  opened, and every list in it is something to act on now. `docs/MAC_SESSION.md` asks
  whether a long list of unmatched rows wants somewhere it can be read twice.
- **The rules re-run afterwards because the ingest moves In and Out.** A fixture row
  arriving trimmed 8-231 and conformed to a four frame event fires QC-033 on the spot,
  which is the check reading the cut that is now in force. QC-008 and QC-009 are pre-flight
  and clear at the next Run, which is where they are meant to be read.

**The chooser opens at `AppSettings.color_session_folder` and writes it back.** Where a
turnover was graded from is on the turnover (OQ-50); this is only where the dialog starts,
which is why it is a per user setting and not part of the batch.

**One thing to look at on a Mac and it is cosmetic.** `Ingest Colour Session` is two and a
half times the width of every other toolbar button, so a once-per-turnover action sits wider
than Run. The alternative is `Ingest` with the full name in the tooltip M5.11 will add, and
the argument against it is that this is a tool called ProIngest whose log is
`qc_ingest_log.xlsx`: `Ingest` alone can be read as the whole job. Judged in front of the
real window, not from a screenshot.

### M5.8.1 is built: every ffmpeg command line is now actually logged

**The requirement was false, not merely unconfigured.** FR-13 asks for every ffmpeg command
line in the log, and `core/ffmpeg.py` has logged each one at INFO since M1. But a render runs
in a process started by the spawn context, which is a fresh interpreter whose root logger has
**no handlers at all**: `logging.lastResort` prints WARNING and above to stderr and silently
drops everything below it. So every command line a *render* ran - which is all of the ones
worth reproducing - went nowhere. `core/logsetup.py` is the fix and it is where the three
decisions live.

- **The worker sends records; the parent handles them.** A `QueueHandler` in the worker, a
  `QueueListener` in the parent, which is the logging cookbook's own answer and the only one
  that keeps **one process** writing the file: a `TimedRotatingFileHandler` renames the file it
  is holding open, so two processes rotating one path is how a day's log is lost. The queue and
  its listener belong to `execute`, not to the process, because nothing outside a render has a
  worker to hear from, and that means the **CLI got the same fix for free**: `proingest run -v`
  now prints the commands its workers ran, which is what `-v`'s help has always claimed.
- **The parent's level travels to the worker** at process creation, so a quiet parent is not
  sent a record per frame to throw away. The consequence is that a level changed mid-run does
  not reach the pool; that is the right trade and it is why `set_level` exists for the window's
  own logging rather than for a run's.
- **The shot is stamped on the handler, not on the logger.** `record.shot` is what M5.8.2's
  "filter by row" will read, and a record does not know: `ffmpeg.run` holds a command line and
  nothing else. A **logger**'s filters run only for records logged through that logger, and
  every record worth stamping is made by `proingest.core.ffmpeg` and merely propagates to the
  root - so a filter on the root logger would have stamped nothing. On the handler it runs for
  everything the handler is given.

**Two smaller things that would otherwise be rediscovered.**

- **`configure` removes only its own handlers.** A test runner's handler is somebody else's,
  and closing it is how a suite loses its captured output halfway through. It stands in for
  `logging.basicConfig`, which does nothing at all when handlers already exist and is therefore
  the reason a log level cannot be applied twice.
- **The rotated file's name and the pruning are one decision.** PACKAGING.md names
  `proingest-YYYYMMDD.log`, which needs a `namer`; `getFilesToDelete` finds old files by
  searching their names for the handler's own date pattern, which is `%Y-%m-%d` and matches
  nothing in a name with no dashes. That fails **silently** - rotation keeps working and the
  folder grows forever - so `suffix` and `extMatch` are set together and a test drops twenty
  dated files in a folder and asserts the oldest six are found. PACKAGING.md was corrected to
  say that the live file is `proingest.log` and only a rotated one is dated.

**Where the folder is, and the one platform branch.** macOS keeps logs in
`~/Library/Logs/ProIngest` and `QStandardPaths` models no log location to ask for, so
`ui/paths.log_dir()` derives it from the generic data location's parent rather than writing a
`~` into the source, and answers `logs` beside `settings.json` everywhere else. Both halves are
tested, because neither runner exercises both.

### M5.8.2 is built: the Log tab

The second of the bottom dock's three tabs, present and empty since M5.1, now a table of
time, level, shot and message over a filter bar. UI_SPEC section 6.1 is the spec, written
with it. **Four things settled.**

- **A `logging.Handler` cannot touch a widget**, so the module is two halves: `LogBuffer` is a
  plain locked ring buffer that any thread may append to, and the view drains it on a 250 ms
  timer. Records genuinely arrive on three threads - a run's command lines on
  `logsetup`'s listener thread, the scan's on its own `QThread`, everything else on the UI
  thread. A queued signal per record would also have worked and is what was rejected: a run
  emits a record per ffmpeg call, and `ui/runner.py` already folds progress for exactly that
  reason.
- **A record is turned into a `Line` the moment it arrives**, on whichever thread made it. A
  `LogRecord` holds `args` and an `exc_info` that can be any live object, and five thousand of
  them is a panel keeping a whole run's memory alive.
- **The bound is the table, not the filter.** A hidden line still ages out, so no filter can be
  the thing that makes the window grow. The complete record is the file; the panel is its tail.
- **"Selected row only" unticks itself when the selection goes.** The alternative is a box that
  is ticked while filtering nothing, which is a control saying something untrue about the table.
  It is unavailable for a selection spanning two shots for the same reason.

**One Qt trap that cost a test run and would have shipped silently**: `setHidden` on a
`QTreeWidgetItem` that has not been added to a tree yet does nothing. Filtering was applied
before `addTopLevelItem`, so every line arriving while a filter was on came in visible. It
looks like a filter that ignores new lines and nothing about it raises.

### M5.8.3 is built: the Advanced section, and M5.8 is done

The section M5.7.2 listed and disabled because logging had nowhere to be configured from.
**Output is now the only disabled section left**, and it is disabled for the reason it always
was: reference quality and the EXR compression level are read inside a worker, so they have to
travel on a `DeliverableJob`.

- **`apply_to_process` is apart from `apply_values` on purpose.** One writes the settings
  objects, the other changes what the interpreter does. Merging them would mean a test of the
  form had side effects on the process running it, and there are now such tests.
- **The ffmpeg override is a module global in `core/ffmpeg.py`, not an argument.**
  `resolve_tool` already takes one and **seven call sites pass none**; threading a value
  through seven signatures that only forward it is worse than one `set_override`. It crosses
  the spawn boundary on the channel M5.8.1 built - `_worker_init`'s initargs - and `execute`
  reads it off the module rather than taking it as an argument, for the same reason it reads
  the log level: a setting a caller has to remember to forward is a setting that half works.
- **An override that is not there raises rather than falling back.** That was already
  `resolve_tool`'s behaviour and it is now the documented one: an override quietly ignored is a
  render done with the wrong build of ffmpeg and nothing said about it.
- **`set_override` clears `available_encoders`' cache**, which is keyed on the binary it asked.
  A different build of ffmpeg is exactly the thing that changes the answer.
- **The level is stored by name**, `"Debug"` rather than `10`, because a settings file is read
  by a person now and then. An unknown name reads back as the default, which is
  `core/settings.py`'s rule for every field and is what lets a file written by a later version
  be opened by this one.
- **A level changed mid-run applies from the next run**, by design: the parent's level travels
  to a worker at process creation (M5.8.1). The help text on the page says so.

### M5.11 is built: the toolbar says what it does, and why it cannot

UI_SPEC section 1, and the section was written up with it. **Five things settled.**

- **The wording is a value**, `ui/toolbar_help.py`, the same split `ui/metadata.py` and
  `ui/settings_form.py` use and for two of the same reasons: the wording is the part that gets
  argued about, and it is assertable without a window. The third reason is this one's own:
  section 1 says the tooltips must share their wording with the user guide's button reference
  (FR-17, M9) **so the two cannot drift**, and a sentence inside a widget constructor cannot be
  shared. M9 reads the module.
- **Nothing in it decides whether a button is enabled.** `_update_state` is the one authority
  on that and stays so; `toolbar_help` is handed the answer. Two copies of that rule would
  disagree the first time one grew a condition, and the wrong copy is on the button nobody
  presses.
- **One note lands on a button that is enabled**, and it is the case that made this worth
  building. A batch with shots and no ingested session runs, is refused by QC-008 and writes
  nothing: correct, and it reads as a dead button (docs/MAC_SESSION.md). Run now says so
  *before* it is pressed. What it asks is the plain question - **has anything been ingested** -
  read off `Turnover.color_session_edl`, rather than a second implementation of QC-008, which
  needs pre-flight and a look at the disk and so cannot run on every state change.
- **The reason is a second line and there is only ever one**, ordered most fundamental first:
  "No batch is open" is a truer answer than "A scan is going".
- **A tooltip line may not exceed `MAX_LINE`, and a test holds every line in every state under
  it.** Qt word-wraps a tooltip **only** when the text looks like rich text, so plain text is
  drawn on one line however long it is. The first draft had a sentence at 104 characters, which
  renders as a strip most of the way across the screen, and **nothing about that fails**. It was
  found by printing the real window's tooltips rather than by any test, which is the fifth time
  that has caught something - so the test now pins the width rather than the sentence.

**The arm64 runner caught two tests that had spelled a shortcut out.** `QKeySequence.toString()`
gives the portable `Ctrl+R` everywhere, but the tooltip asks for **native** text on purpose, so
macOS draws `⌘R` and Linux draws `Ctrl+R`. Both tests passed here and failed there. The code was
right and the tests were Linux-shaped; they now read the shortcut off the action the same way the
tooltip does. This is the second time CI has caught a difference the dev machine cannot see, and
it is the cheap kind: `Ctrl+R` is the longer of the two, so the width limit is still measured
against the worst case.

**`Ingest Colour Session` now has the tooltip that would let it read `Ingest`**, which is the
argument docs/MAC_SESSION.md asks to settle in front of the real window. The label is
deliberately **not** changed here: that judgement is about width on a real toolbar.

### M5.9 is built: the frozen left columns, and M5 with them

UI_SPEC section 2, `FrozenColumns` in `ui/shot_list.py`, 27 tests and 1536 in the suite. The
overlay is a second `QTreeView` sitting on the list, showing the same rows through the same
proxy, sharing the owner's selection model outright, and hiding every column past
`FROZEN_COLUMNS`. The list keeps all fifteen columns and lets its first three scroll away
underneath, where the overlay covers them. **Seven things in it should not be re-derived.**

- **One model and one selection between the two views is the whole trick.** Everything that
  went wrong in the building was one of the things Qt keeps *per view* - scroll position, which
  turnovers are open, the spans on the group header rows, the three column widths - and all
  four are wired both ways in `_wire_frozen`, because either view can be the one the mouse is
  over. None of those loops runs away: Qt emits none of those signals when the value it is
  being set to is the one it already has.
- **The edit is routed, not the focus followed, and the focus follower was built first and
  deleted.** It moved the focus across the seam when the cursor did, and it was wrong twice
  over: it only fires when the current index actually *changes*, so a cursor already sitting on
  Shot got nothing, and the guarantee is needed whichever view the keystroke reached anyway.
  `ShotListView.edit` and `FrozenColumns.edit` hand a cell to whichever of the two can show it,
  so an editor can no longer open underneath the overlay however the edit was started. A test
  drives the whole seam with a real Tab key event: the overlay commits the shot code and the
  list opens the In editor.
- **Each view gets its own delegate instance.** One `TwoLineDelegate` set on both reports every
  commit to both views, one of which does not own the editor and says so on the console:
  `QAbstractItemView::commitData called with an editor that does not belong to this view`. The
  delegate is stateless, so a second instance costs nothing and the two draw identically.
- **The turnover line is drawn twice and has to land in the same place.** The group header row
  is spanned, so Qt hands the list a rectangle starting wherever column 0 has scrolled to while
  the overlay's copy never moves. `TwoLineDelegate._paint_group_header` puts the rectangle back
  where an unscrolled view would have it, reading the offset off `option.widget`, and turns
  eliding off. Without the first, the sentence reads as garbage from the seam rightwards the
  moment the list is scrolled; without the second, the overlay stamps an ellipsis 250 pixels in,
  in the middle of a sentence the list is still drawing the rest of - `dani...ckett - 13 shots`.
  **Both were found by looking at a grab of the real window rather than by any test**, and both
  now have one that fails without the fix.
- **`scrollTo` keeps the horizontal position for a frozen column.** Qt's answer to "make this
  Shot cell visible" is to scroll the list back to the left edge, throwing away where the editor
  was reading in order to reveal a cell the overlay was showing all along. It still scrolls
  vertically, because `select_row` from the Issues dock arrives with a column 0 index and has to
  reach the row.
- **The two views only agree about row height once they have been shown.** The stylesheet's
  `font-size: 13px` reaches a widget when it is polished, and the overlay is polished as a child
  before its owner is: unshown, the rows are 33 pixels against 31. Nothing is wrong and nothing
  needs fixing - the window shows both - but a test that asserts the heights match has to use a
  shown view, which is what the `tall` fixture is for.
- **`FrozenColumns.moveCursor` returns whatever the owner's returns**, including for the columns
  it cannot show. Tab out of Shot lands on In, and `ShotListView.moveCursor` is the only thing
  that knows that. Two implementations of section 4's Tab order would have drifted the first
  time one of them grew a column.

### Next task

**M7 is done, and it was the thing standing in front of the Mac day.** `docs/MAC_SESSION.md`'s
own gate said not to rent until the packaging job produced a downloadable artifact whose
headless smoke test passed; all three of its preconditions are now ticked, so the rented day
is bookable.

What is left that this machine can still finish on its own, in the order it is worth doing:

- **OQ-47, QC-039's scene linear probe.** Pure core, and the one open item that is a
  correctness bug rather than a judgement: the probe is calibrated on ACEScct, the CLF no
  longer starts there, and for C-Log3 - one of the three cameras named for this show - it
  cannot separate a valid grade from a display rendering at all. The replacement ratio probe
  is already measured and written out in the question. It is a rule definition, so
  `QC_RULES.md` moves with it.
- **The Settings page's sixth section.** Output is listed and disabled because reference CRF
  and the EXR compression level are applied inside a worker and would have to travel on the
  render job. M5.8.3 already built that channel for the ffmpeg override and the log level, so
  this is following a path that exists.
- **M9.2, the quickstart, and M9.4's harness**, which builds a demo batch and grabs the
  window: the images it takes on Linux are fine for laying the document out and the shipped
  set is taken on the Mac. M9's button reference should read `ui/toolbar_help.py` rather than
  restate it. **M9.1's install section is no longer blocked**, since M7 exists to describe.
- **What `REVIEW.md` deferred**, of which the largest is the `MainWindow` split. No behaviour
  changes there; it is a session of its own if it is wanted.

**M8 still needs the real thing** and nothing here substitutes for it.

**The pane is where an ingest is seen without running anything**: its Colour section reads
`source_encoding`, `source_encoding_origin` and `clf_path` off the row, so selecting a row
is how a person checks that the right CLF was matched.

**Two things worth asking and neither is a build task.** Ask **whoever briefs the
shooters** which metadata field carries the log name and exactly what string goes in it
(OQ-44), remembering that "S-Log3" names four colour spaces in the pinned config. And
confirm **OQ-46** against one real export, because the difference between a CLF that
contains the conversion and one that does not is two plausible looking images and no error.

### Two M3 decisions to revisit rather than rediscover

- **A reference encode reports no progress and cannot be cancelled mid-encode.** It is one
  ffmpeg process, so a job goes from started to done with nothing in between and a cancelled
  run finishes the encodes in flight. The plan for M3.5 said to parse `-progress` and kill the
  child; neither was built, deliberately. Sections 6 and 9.
- **x264 CRF 18 `-preset slow` is what shipped and hardware encoding stayed out.**
  `h264_videotoolbox` has no CRF and an uncalibrated `-q:v` (OQ-23). `ffmpeg.has_nvenc()` is
  dead code nothing calls. Hardware encode is an M5 Settings toggle at the earliest and needs
  a real Mac to calibrate.

### Context a cold reader needs before touching anything

- **v01 is macOS on Apple Silicon, decided 2026-09-10.** Not Windows, and not Intel (OQ-24).
  Windows 11 is a v02 intention. Read the section 6 entry before touching packaging, settings
  paths or the reference encodes.
- **The suite runs on the target platform.** CI runs lint, types and the full suite on a
  `macos-latest` arm64 runner on every push, against the bundled ffmpeg 9.0.1 rather than this
  machine's Ubuntu 6.1.1. `h264_videotoolbox` was confirmed to open and encode there, which
  answered half of OQ-23.
- **41 open questions, 19 of them still open.** Closed on 2026-09-11: OQ-2, OQ-12, OQ-15, OQ-32,
  OQ-34, OQ-37, OQ-38 and OQ-40. **OQ-30 and OQ-33 each closed and reopened within the same
  day**, as the grade carrier went CLF, then CDL, then CLF again, and **OQ-19 was reopened after
  a day** by the real tracker's FPS column. New: OQ-35, OQ-36, OQ-39, OQ-41. OQ-29 is mostly
  answered, since the colour session pins ACES 1.3, and its config half is now built.
- **Everything through M5.9 is pushed**, at the user's instruction on 2026-09-13: 3 commits on
  top of M5.11's six - the chunk, the build track brought forward from the live board, and this
  session's note in `HANDOFF.md`. **Run 34768468796 is green on both runners**, macOS arm64 in
  1m31s and Linux in 2m02s, so **all 1536 tests pass on Apple Silicon against the bundled ffmpeg
  9.0.1** rather than only against this machine's 6.1.1, and this one went green first time.
  Check CI rather than assuming, and **pushing is still the user's call** rather than an
  automatic step: this line has twice claimed a push that had not happened, which is why it
  names the commit count and the run.
- **The push before it went red first, and that is worth expecting.** Run 34767259404 failed on
  the arm64 runner alone, on two M5.11 tests that had written `Ctrl+R` into their expected text
  where macOS draws one glyph. Nothing was wrong with the code. **Two of the last two CI-only
  failures have been the Mac disagreeing about something the Linux machine cannot observe** - the
  other was `-shortest` and the audio length on ffmpeg 9.0.1 - so a first push that goes red is
  the runner doing its job rather than a regression.

---

## 2. What this is, and what to read

A single-user macOS desktop app (PySide6, Python 3.11+) that ingests VFX shot
turnovers. It reads an OpenTimelineIO file exported from DaVinci Resolve, matches
timeline clips to media in a turnover folder on a Google Drive mount, lets the
VFX editor adjust In/Out per shot, then transcodes and names all deliverables per the
studio spec, runs automated QC, and exports spreadsheets.

Read in this order: `CLAUDE.md` (ground rules, non-negotiable), `PRD.md`, then the doc
for the area being worked on. **The docs are the spec. When code and docs disagree,
fix one and say which.**

| doc | what it settles |
|---|---|
| `docs/WORKFLOW.md` | who does what, in twenty lines. Read it first, it is the shortest thing here |
| `docs/NAMING_SPEC.md` | every input and output name, the type table, versioning, delivery layout |
| `docs/COLOR_AND_FORMAT.md` | colour policy, accepted sources, output formats, frame math, EXR pipeline |
| `docs/QC_RULES.md` | every rule ID, severity and scope. IDs never change meaning |
| `docs/ARCHITECTURE.md` | package layout, data flow, concurrency, batch file |
| `docs/UI_SPEC.md` | the M5 interface, keyboard model, burn-ins |
| `docs/OPEN_QUESTIONS.md` | OQ-1 to OQ-41, with defaults for the unanswered ones |
| `docs/PACKAGING.md` | M7, the `.app` and dmg, ffmpeg bundling, Gatekeeper |
| `docs/MAC_SESSION.md` | the only work that needs a real Mac, and what to do on the day |

Two of the studio's own documents sit in `docs/` as source material. The shooters' spec sheet is
there in two forms, the PDF and a CSV export of the same document, and **the shot tracker** is
there as `Pre Pro Shot Tracker - W1.csv`, a live production sheet carrying real people's names,
which is one more reason the repo is private. They are source material, not spec: what the app does with them is settled
in `NAMING_SPEC.md`, which is where the known defects in their type table are recorded.
Read the CSV when the question is what a row of that table actually says, since it needs no
PDF viewer.

---

## 3. Environment

- venv at `.venv` (Python 3.12), created and kept current with `uv sync --extra dev`, which
  installs exactly what `uv.lock` pins. Dependencies change by editing `pyproject.toml`, running
  `uv lock`, and committing both. There is no `pip` inside the venv: use
  `uv pip install --python .venv/bin/python` for a one-off.
- otio 0.18.1, OpenEXR 3.4.15 (numpy File API present), numpy 2.5.3, OpenColorIO 2.5.2.
- **OpenColorIO ships no config files.** `opencolorio>=2.4` is a runtime dependency and the ACES
  transforms travel inside the wheel: `Config.CreateFromBuiltinConfig` reads them from there.
  2.4 is the floor because the pinned config (`core/color.BUILTIN_CONFIG`) is a v2.4 built-in.
  There is nothing for an installer to place and nothing for a user to point at.
- Dev machine is Linux/WSL; the target is **macOS on Apple Silicon**, and there is no Mac
  available (OQ-22). Everything in core is verifiable headless on Linux, which is why the
  platform switch was cheap.
- **CI runs the suite on the target platform.** `.github/workflows/ci.yml` has two jobs: Linux
  for a fast contrast signal, and `macos-latest` (macOS 26, arm64, a standard runner on
  included minutes) for the real thing. The macOS job fetches the pinned ffmpeg and **puts it
  on PATH before pytest**, which matters twice over: `tests/fixtures/media.py` shells out to a
  bare `ffmpeg`, and `ffmpeg_available()` uses `shutil.which`, so without it `conftest` would
  skip the entire suite and the job would report green having run nothing. It also means CI
  exercises the shipping ffmpeg 9.0.1 rather than the Ubuntu 6.1.1 this machine has.
- **The repo is private** (github.com/shango/ProIngest). It carries the shooters' spec PDF and
  the client's naming conventions, so public was declined deliberately: private to public is
  one click, public to private does not un-publish. Revisit only if macOS minutes bite.
- **`core/ffmpeg.py` skips the bundled binary unless `sys.platform == "darwin"`.** This
  guard is load bearing, not tidiness. The Windows bundle was `ffmpeg.exe`, so a Linux
  lookup for `ffmpeg` missed it and fell through to PATH by accident. The macOS binary is
  named `ffmpeg`, exactly what Linux looks for, so without the guard `resolve_tool`
  returns an arm64 Mach-O and all 547 tests die with "Exec format error". Found by
  running it, immediately after the first successful fetch.
- ffmpeg binaries are not in git: `python build/fetch_ffmpeg.py` populates them. They are
  now the martin-riedl.de macOS arm64 GPL build of ffmpeg 9.0.1, 132 MB for the pair
  rather than the Windows 446 MB. Two macOS traps are handled in that script and will bite
  anyone who rewrites it: Python's `zipfile` drops the exec bit, and the host answers the
  default `Python-urllib` User-Agent with HTTP 403.
- `mypy python_version` is 3.12, not 3.11: numpy's stubs use `type` statement syntax
  that mypy rejects under 3.11, and pytest imports numpy transitively. The runtime
  floor in `requires-python` stays 3.11, which numpy genuinely supports.
- Tests generate their own media with ffmpeg into `tmp_path`. Nothing is committed.
  `tests/conftest.py` skips the suite outright if ffmpeg is missing.

---

## 4. Modules

| module | what it owns | lines |
|---|---|---|
| `core/naming.py` | every output name, both directions; `next_version`; clip and shot code parsing | 324 |
| `core/frames.py` | integer frame math, timecode, In/Out input grammar | 179 |
| `core/models.py` | Batch, Turnover, ShotRow, Deliverable, MediaInfo, AudioInfo, FrameRate, QCResult, and a row's frame math context | 686 |
| `core/ffmpeg.py` | the only place anything shells out; tool lookup, ffprobe, decode, audio extract, reference encode through the viewing LUT | 608 |
| `core/media.py` | DirectoryIndex, sequence detection, path remap, probe cache | 465 |
| `core/exr.py` | EXR header and pixel reading, delivery frame writing, and the provenance a graded plate carries | 299 |
| `core/resize.py` | antialiased Lanczos downscale for the EXR path | 96 |
| `core/color.py` | the pinned OCIO config, every leg of the chain but the CLF, composing and applying them, and the view branch baked to a `.cube` | 209 |
| `core/timeline.py` | OTIO and EDL loading, audio association | 233 |
| `core/clf.py` | the colour session package: the final EDL as the conform, the CDL, the CLF matched per row, loaded, hashed and probed, and `ShotColor`, which is what rides on a job | 606 |
| `core/scan.py` | turnover folder -> Turnover + ShotRows | 459 |
| `core/planner.py` | type table, deliverable jobs, version resolution, the shot's colour attached to each job | 485 |
| `core/batchfile.py` | `.pibatch` save/load, backup, filesystem reconciliation | 86 |
| `core/camdata.py` | key/value pairs out of a camData `.txt` or `.rtf`, RTF stripped pragmatically | 62 |
| `core/exports.py` | the QC log's five sheets and the studio tracker's rows to paste | 378 |
| `core/render.py` | executing a job and a batch of them: atomic writes, the plate and view branches, pool, progress, cancel | 631 |
| `core/qc.py` | rule registry: phase A, `RuleSettings`, `preflight`, phase B | 1416 |
| `core/settings.py` | what the app remembers between launches, as JSON. Takes the path; never works out where it is | 111 |
| `ui/app.py` | the QApplication, its names, the theme, and `run()` | 49 |
| `ui/main_window.py` | UI_SPEC section 1's frame: menus and their macOS roles, toolbar, bottom dock, status bar, the three empty states and the batch page, window state, the autosaver, the batch lifecycle (New, Open, Save, the two roots, Add Turnover and Scan), the colour session ingest (which turnover, which EDL, and what it reports), and the run (pre-flight, planning, Stop, the exports, the steps it narrates and section 7's banner text), and the metadata dock with the three signals that refresh it | 1275 |
| `ui/shot_model.py` | the batch as a two level tree: section 2's columns, section 3's dot and tints, the In/Out display mode, what the four editable cells commit, where a given row sits, and how far a live run has got with it | 760 |
| `ui/shot_list.py` | the view, the two line cell, the Progress column's slim bar, the search filter, the cell editor, Tab across the editable columns, the skip prompt, what is selected, and selecting a row somebody pointed at from the Issues dock | 410 |
| `ui/batch_bar.py` | the batch name, the delivery root button, the three state In/Out toggle and the search box | 104 |
| `ui/paths.py` | the one place that asks `QStandardPaths` where the app's own files live | 33 |
| `ui/autosave.py` | the debounced write of an edited batch, and what it does with one that has no file yet | 97 |
| `ui/scanner.py` | `core/scan.py` on a `QThread`: one result per folder, a copied probe cache, cancel between folders, and a shutdown that waits | 184 |
| `ui/runner.py` | `core/render.py`'s pool on a `QThread`: the jobs over, the records back, progress forwarded onto the UI thread, a `RunProgress` that turns it into a percentage, a throughput and an ETA, the words for the job in flight, and a shutdown that waits | 383 |
| `ui/run_strip.py` | UI_SPEC section 7.1's band above the list: the batch's thin bar, the line saying what step the run is on, and section 7's completion banner. Three states and only ever one of them | 128 |
| `ui/metadata.py` | UI_SPEC section 12's field list as a value: a selection into `Section`s of `Field`s, what a multiple selection agrees on, and the `key: value` text Copy all puts on the clipboard. No Qt and no I/O | 561 |
| `ui/metadata_pane.py` | the pane that draws it: one elided line per field, collapsible sections that remember what was shut, a copy button per path, and a rule ID that clicks through to the Issues dock | 343 |
| `ui/issues.py` | UI_SPEC section 6: every QC result in the batch as a table, with the rule ID in its own column, a double-click that selects the shot, and `select_result` for the pane's links | 184 |
| `__main__.py` | `proingest scan`, `run` and `qc` CLI, `--rules` overrides, and the UI when there is no subcommand | 440 |

Not built yet: the rest of `proingest/ui/`, which is M5.6 onward. **`core/stringout.py` will not be built**: M6 is dropped
(PRD FR-9). `naming.stringout_mp4` and `naming.normalize_shooter` are therefore reachable
from tests only; they are kept deliberately, because the stringout name is now something a
human types and the tool can still check it, exactly as with the lens grid.

Entry points worth knowing:

- `scan.scan_batch(folders) -> Batch` is the whole ingest side.
- `planner.plan_batch(batch, delivery_root) -> list[DeliverableJob]` resolves versions
  and records the plan on each row. A job carries source, destination, `.part` temp
  path, frame range, target size and audio source: enough for a worker process, by
  design.
- `exr.write_frame(path, pixels, timecode_frames, fps, colorspace)` is the only way a
  delivery frame is written.
- `render.render_job(job, colorspace=..., on_frame=..., cancelled=...) -> Deliverable`
  produces one deliverable. It either lands complete or leaves nothing: no `.part`, no
  destination. The two hooks are plain callables, so they test synchronously. It runs
  `qc.run_phase_b` after the rename, so a returned Deliverable is already verified.
- `qc.run_phase_b(job, deliverable) -> list[QCResult]` verifies one written deliverable
  against the job that planned it. The job is the expectation, the file is the claim, and
  nothing in it raises: an unreadable deliverable is reported, not thrown.
- `render.execute(jobs, ...) -> list[Deliverable]` runs them in a process pool and
  returns one record per job in job order, whatever happened to it. `apply_results`
  writes those records back onto the rows that planned them.
- `ffmpeg.decode_frames(source, source_size, in_frame, out_frame, ...)` is a generator of
  `(h, w, 3)` float32 RGB frames. `source` is whatever goes after `-i`, so a sequence passes
  `media.printf_pattern_for(first_frame)`. `ffmpeg.decode_command(...)` builds the same
  command without running it, which is what the tests assert against.

---

## 5. Milestones

| id | milestone | state |
|---|---|---|
| M1 | Core: parse, resolve, probe, model, batch file, scan CLI | complete, 348 tests |
| M2 | Naming and planning: type table, versioning, layout | complete, 66 tests |
| M3 | Render | complete, 172 tests |
| M4 | QC: all rules both phases, xlsx exports, `qc` CLI | complete, 175 tests |
| M4.5 | Colour pipeline, core only. Source log in, CLF applied, ACEScg out, the viewing LUT | complete, 111 tests |
| M4.6 | Per shot source encoding: read from the clip metadata, the input transform table, the input transform out of the graded chains, QC-046 to QC-048 | complete, all five chunks (OQ-37 answered; OQ-46 wants confirming) |
| M5 | UI: the list, the FR-14 metadata pane, settings, log. **No viewers** | **complete, all eleven chunks** |
| M6 | ~~Stringout with burn-ins~~ | **dropped 2026-09-11**, the colour session exports it |
| M7 | Packaging: PyInstaller app, dmg, the frozen smoke test, both CI jobs | **complete 2026-09-13, 19 tests.** Built and smoke tested on Linux before pushing; Gatekeeper is OQ-9 and still unanswered |
| M8 | Polish, performance on a real turnover, docs | not started |
| M9 | The user guide: install, quickstart, a section per surface, screenshots (PRD FR-17) | **new 2026-09-12**, not started, specified in section 5 |

M4 detail. The milestone had no chunk table until M4.1; this is it:

| chunk | scope | state |
|---|---|---|
| M4.1 | phase A registry, `RuleSettings`, `preflight`, `--rules` | done, 91 tests |
| M4.2 | phase B verification, QC-1xx, wired into `render_job` | done, 47 tests |
| M4.3 | `core/exports.py`, the xlsx sheets, `proingest qc <batch>`, QC-053 | done, 37 tests |

M4.5 detail, respecified 2026-09-11, M4.5.1 built the same evening. It is **smaller than that
morning's version**: the AD notes model is gone entirely, the viewers and their frame fetch went
with it, and what M4.5.2 reads is the colour session's package rather than the shooters'.

| chunk | scope | state |
|---|---|---|
| M4.5.1 | OCIO in, `core/color.py` rebuilt as a pipeline, studio log to ACEScct to ACEScg | done, 24 tests |
| M4.5.2 | `core/clf.py`: the final EDL read for conform, In/Out and CDL; the CLF matched per row, loaded and hashed | done, 42 tests. OQ-30 and OQ-33 built to their defaults |
| M4.5.3 | The viewing LUT: CLF plus ACES output transform baked to one `.cube` per shot | done, 11 tests. OQ-29's open half built to its default |
| M4.5.4 | `render` plate/view split, `lut3d` encode, `exr.py` AP1 constants and the new header attributes | done, 34 tests. OQ-42 and OQ-43 recorded |
| ~~M4.5.5~~ | ~~`core/preview.py`, single frame fetch with cache~~ **dropped 2026-09-11 with the viewers** | n/a |

Two constants in `exr.py` changed in M4.5.4 and they matter: `CHROMATICITIES` went from sRGB to
AP1, and `COLORSPACE_ATTRIBUTE`'s value from `scene_linear_sRGB` to `ACEScg`, which is now a
constant rather than a parameter. A test asserts red sits at 0.713, 0.293 rather than reading
the constant back, because a regression to Rec.709's 0.64 is exactly what a test that reads the
constant cannot see.

M4.6 detail, specified and built 2026-09-12. It is small because M4.5 already
threads the source encoding per shot; what is missing is where the string comes from and what
happens when it cannot be resolved.

| chunk | scope | state |
|---|---|---|
| M4.6.1 | `ShotRow.source_encoding` (additive, like `clf_path`), read per row rather than from one Settings value. **No mode**: `DEFAULT_SOURCE_ENCODING` stops being a batch-wide authority | **done, 882 tests.** The constant is deleted rather than redefined |
| M4.6.2 | **Take the input transform out of the graded chains.** `ShotColor.plate_transforms` drops `input_transform` when a CLF is present, `WORKING_SPACE` and `plate_transform` collapse into one source-to-ACEScg leg, and `view_lut` bakes the CLF and the output transform only | **done, 876 tests.** OQ-47 found on the way |
| M4.6.3 | The mapping table in `core/color.py`: what a shooter writes to one OCIO colour space, extensible by a row, refusing the unrecognised and the ambiguous | **done, 897 tests.** `INPUT_TRANSFORMS` and `resolve_encoding` |
| M4.6.4 | Read the encoding at scan time from the carrier OQ-44 names, and QC-046, QC-047 and QC-048 | **done, 924 tests.** OQ-44 built to its default: `Input Color Space`, clip metadata first, container tags second |
| M4.6.5 | `proingest/source_encoding_origin` in the EXR header, and the source encoding column in the QC log beside the CLF one | **done, 934 tests.** `models.SourceEncodingOrigin`, and the header's name and the log's name are deliberately different strings |

**M4.6.2 was the chunk to get right and it was the only one that changes a delivered plate.**
It returned `[input_transform, clf]`, which under the answered OQ-37 converts twice: the CLF
already starts at the source encoding. That is a wrong image that passes every check, so it
landed with tests that pin **which** transforms a chain contains rather than only what it
produces. See the M4.6.2 note in section 1.

**One question is still open and it is the one that decides M4.6.2's direction: OQ-46**, whether
a given session's CLF really does contain the conversion. The user's answer to OQ-37 says it
does. Confirm it against one real export before a delivery depends on it, which is the same
exercise as OQ-31. QC-048 exists so that a run records which chain it used rather than leaving
it to be re-derived later.

**M4.6.3 is required whatever OQ-46 says**, because the user asked for multiple input transforms
selected by the file metadata and because the aux still needs one regardless: a colour chart is
delivered ungraded, never gets the CLF, and still has to reach ACEScg.

**M5 is not blocked by any of this, and it got smaller on 2026-09-12.** An earlier version of
this note told M5 to carry a source encoding mode control from the start. **There is no mode**,
so there is no control: the Settings Colour group carries the colour session location, the input
transform table and its overrides, the ACES config version and the output transform, and nothing
about which encoding a batch is in.

M5 detail, specified 2026-09-12 against `docs/UI_SPEC.md`, which is the spec for every
row of it. The order is "the window, then the list, then what the list can do, then what a
batch can do", so each chunk has something a person can look at:

| chunk | scope | state |
|---|---|---|
| M5.1 | The shell: `ui/app.py`, `ui/main_window.py`, `ui/theme.qss`, `ui/paths.py`, `core/settings.py`, and the offscreen Qt test harness | **done, 975 tests** |
| M5.2 | The shot list: a model over a `Batch`, section 2's columns, turnover group headers, the three state In/Out display, the status dot and row tints, the search box | **done, 1061 tests.** Read only until M5.3, and **without the frozen columns**, which are M5.9 |
| M5.3 | Editing: shot code, In, Out and Notes in their cells, section 5's input parsing, Ctrl+K skip, per row revalidation, autosave | **done, 1125 tests.** A commit re-runs the row's rules only, and `ui/autosave.py` holds the edits of a batch that has no file yet |
| M5.4 | Batch lifecycle: New, Open, Save, Add Turnover against the source root, the scan off the UI thread, the Issues dock | **done, 1199 tests.** The scan is a `QThread` with a copied probe cache; `Scan` re-tries only the turnovers with no rows (OQ-48) |
| M5.5 | Run and progress: the worker pool driven from the window, the Progress column, the status bar, Stop, the completion banner | **done, 1249 tests.** `ui/runner.py` is a `QThread` over `render.execute`; one 200 ms timer draws everything a run shows; the run writes both spreadsheets |
| M5.6 | The metadata pane, FR-14 and UI_SPEC section 12 | **done, 1344 tests.** `ui/metadata.py` is the field list as a value and `ui/metadata_pane.py` draws it; a right dock, three update signals, and a **Colour** section section 12.2 did not have |
| M5.7.1 | The colour session reaches the model: `clf.ingest`, `Turnover.color_session_edl`, `ShotRow.approved` and `ShotRow.cdl`, and QC-008, QC-009, QC-019, QC-039 and QC-045 | **done, 1377 tests** |
| M5.7.2 | The Settings page, PRD FR-12, **including the Colour group** | **done, 1408 tests.** `ui/settings_form.py` is the field list as a value and `ui/settings_dialog.py` draws it; Output and Advanced are listed and disabled |
| M5.7.3 | `Ingest Colour Session` in the window, and what it reports | **done, 1427 tests.** One turnover at a time, the chooser opening where FR-12 remembers, and the report the CLI prints |
| M5.8 | The Log tab and the rotating log file, FR-13 | **done, all three chunks** |
| M5.9 | The frozen left columns: the overlaid second view sharing the model and the selection | **done, 1536 tests.** `FrozenColumns` in `ui/shot_list.py`; one model and one selection between the two views, and the edit is routed rather than the focus followed |
| M5.10 | The run's strip above the list: the thin batch progress bar and the line of text naming the step being done (UI_SPEC 7.1) | **done, 1266 tests.** `ui/run_strip.py` is three states in one band, and the line names the longest running job rather than the newest message |
| M5.11 | A hover tooltip on every toolbar button, saying what it does and, when it is disabled, why (UI_SPEC section 1) | **done, 1509 tests.** `ui/toolbar_help.py` is the wording as a value; one note lands on an **enabled** button, which is Run with no session ingested |

M5.8 detail, specified 2026-09-13 against FR-13. It is three chunks because the
requirement is three things and the first one is not a UI task at all:

| chunk | scope | state |
|---|---|---|
| M5.8.1 | `core/logsetup.py`, the rotating file, and the bridge that gets a **worker process**'s ffmpeg command lines into it | **done, 1443 tests.** `ui/paths.log_dir()`, and `execute` owns a log queue per run |
| M5.8.2 | The Log tab itself: the second tab of the bottom dock, filtered by level, by text and by the selected row | **done, 1467 tests.** `ui/log_view.py`, a locked ring buffer between the handler and the widget, drained on a timer |
| M5.8.3 | The Settings page's **Advanced** section: the log level, and the ffmpeg path override travelling to a worker on the same init channel | **done, 1483 tests.** `settings_form.apply_to_process`, and `ffmpeg.set_override` |

**M5.4 settled four things that should not be re-derived.**

- **Where the scan runs: a `QThread` owned by the window, with a worker `QObject` moved
  onto it** (`ui/scanner.py`). Core stays Qt-free, which is the rule the render pool
  already obeys. Three things cross the boundary and each is handed over rather than
  shared: the worker gets a **copy** of the probe cache and emits a copy back per folder,
  the `Turnover` and its rows are built there and never touched again, and the batch
  itself never goes near the worker. Cancellation is checked between folders only,
  because `scan_turnover` is one call into core that cannot be interrupted part way and
  threading a flag through five core functions to change that would be a worse trade.
- **`Add Turnover` scans the folder it is given straight away; `Scan` re-tries only the
  turnovers that came back with no rows.** A folder that is added and shows nothing until
  a second button is pressed is a dead click, and a turnover that has rows is never
  re-scanned because a scan rebuilds rows and the rows carry the editor's In, Out, shot
  code, notes and skip reasons. The useful version of a re-scan is a merge that keeps the
  overrides, and that is **OQ-48**, new and unasked for.
- **The file a batch is first saved as is what names it.** Found by driving the window
  rather than by a test: a batch made by New is called `untitled`, and the batch name is
  what `exports.report_names` builds the QC log and tracker filenames from. A name
  somebody has already given is never overwritten.
- **A new batch has no file, and closing with edits in hand asks.** Save writes the batch
  itself rather than routing through the autosaver, because Save is the one write the
  editor is waiting on and a failure has to be reported rather than logged and left
  pending. `AutoSaver.adopt` is how the autosaver learns where the file went.
- **`Batch.source_root` is on the batch, not in the settings** (UI_SPEC section 13), like
  `delivery_root` already was, so a second batch on another drive does not move the
  first one's starting point. `AppSettings.last_folder` is the fallback for a chooser
  with no batch to ask, and **nothing anywhere guesses at a Drive mount**.

**The tests grew a `DrivenWindow`**, a `MainWindow` subclass whose every dialog is
overridden to an answer that changes nothing. It is not tidiness: an offscreen modal is a
hung suite rather than a failed assertion, so a test that forgot to stub one would not
fail, it would stop - which is exactly what happened the first time a test opened a batch
whose delivery root did not exist.

**M5.5 settled four more, and they are about where a run's state lives.**

- **The pool is driven from a `QThread` and the jobs are what cross it.** Same shape as
  the scan, same rule: core stays Qt-free and the batch never goes near the worker.
  Pre-flight, planning and `apply_results` all write to the batch, so all three stay on
  the UI thread; `execute` gets a list of `DeliverableJob` and hands back a list of
  `Deliverable`.
- **One 200 ms timer draws everything a run shows.** Progress messages only update a
  `RunProgress`; the status bar, the row bars and the status dots are repainted on the
  timer. A repaint per message is a message per frame per worker.
- **Rendering is a state only a live run can report**, because the statuses on a row are
  not written back until the run ends. `ShotListModel.state_for` is where the run's
  answer and the row's meet, and a live run outranks the recorded status in the Progress
  cell for the same reason.
- **The run writes the two spreadsheets.** Section 7's banner says where they went, so
  the run is what has to put them there. No show to file them under is a refusal, not a
  guess: the banner says nothing was written.

**M5.9 was last on purpose and the reason held.** UI_SPEC section 2 freezes Status, Shot and
Elem while the rest scrolls, and QTreeView has no such thing: it takes a second view overlaid
on the first, sharing the model, the selection and the scroll. Editing, filtering and
selection were all built before it, which is what let it be built once instead of twice - the
two things it had to be fitted around, `ShotListView.moveCursor` and the cell editor, were
both already there to be handed the work rather than reimplemented. The chunk note in section
1 says what it cost and what it settled.

**M5.7.1 is where the colour work finished.** The five rules that read `core/clf.py` are
wired, and what a batch knows about its colour session is `Turnover.color_session_edl`
rather than a Settings value (OQ-50). Nothing in core had to change for M5.7.2 or M5.7.3
beyond `IngestReport.counts` and `notices()`, which are the words both surfaces report an
ingest in, kept in one place so the CLI and the window cannot drift.

M7 detail, built 2026-09-13. Five files in `build/` and two CI jobs.

| chunk | scope | state |
|---|---|---|
| M7.1 | `build/entry.py`: the frozen entry point and its `freeze_support()` call | done |
| M7.2 | `build/bundle.py` and `build/proingest.spec`: what goes in the bundle, and a shim | done, 19 tests |
| M7.3 | `build/build.py`: PyInstaller, the dmg, the size report | done |
| M7.4 | `build/smoke_test.py`: drive a frozen build through a whole turnover | done |
| M7.5 | `package-linux` and `package-macos` CI jobs, dmg uploaded as an artifact | done |

**Eight things in it that should not be re-derived.**

- **`multiprocessing.freeze_support()` is a no-op on macOS, and the line is still load
  bearing.** CPython's `BaseContext.freeze_support` has a body gated on
  `sys.platform == "win32"`; anyone who checks `build/entry.py` against the standard library
  will conclude the call does nothing and delete it. PyInstaller's `pyi_rth_multiprocessing`
  runtime hook **rebinds the name** to its own implementation, gated on nothing, and that hook
  runs before the entry script. Both halves were proved rather than assumed: the frozen binary
  handed `--multiprocessing-fork` by hand reaches `spawn_main` and dies on the bogus file
  descriptor, and the same argument from source is rejected by argparse with a usage line.
  Two things now hold it, a unit test on the call's position and a smoke test step that fails
  if that usage line comes back.
- **OpenTimelineIO was the one dependency freezing actually breaks, and it needs all three
  kinds of help.** Adapters are found through `importlib.metadata` entry points and JSON plugin
  manifests, so the bundle carries otio's and the CMX3600 adapter's `.dist-info`, their
  manifests, **and their `.py` sources**. The sources are not caution: otio's loader tries
  `importlib.import_module("opentimelineio.adapters.<name>")` and falls back to reading the
  path in the manifest off disk, and the EDL adapter is named `cmx_3600` while living in
  `otio_cmx3600_adapter`, so **for that adapter only the fallback ever works**. Everything
  else - PySide6, numpy, OpenEXR, xxhash, OpenColorIO - needed nothing at all, and OCIO needed
  no data files because the ACES config is compiled into the wheel.
- **The spec file is a shim and that is the point.** A `.spec` is executed rather than
  imported, so `ruff`, `mypy` and the suite never see one, which makes it the worst possible
  home for a decision: a mistake in it does not fail a build, it ships an app with a file
  missing. Everything with a judgement in it is in `build/bundle.py`, which all three do see,
  and `mypy` now runs over `build/` as well as `proingest` and `tests`.
- **`build/` needed an `__init__.py`.** Without one the folder is a namespace package,
  `bundle` is reachable as both `bundle` and `build.bundle` depending on who imports it, and
  `mypy` refuses to check a file it can reach under two names. Every script and the spec now
  import it the same way, `from build import bundle`, with the repo root on the path.
- **The Linux build is not a product, it is a test of the spec.** Nothing ships from it. It
  exists because a lost hidden import or an uncollected manifest fails a Linux build exactly
  as it fails a macOS one, and `MAC_SESSION.md` names discovering that on a rented Mac as the
  expensive way to learn it. The whole thing was built and smoke tested here before the CI
  jobs were written, which is why M7 landed green rather than being pushed hopefully.
- **The dmg is `hdiutil`, not `create-dmg`, and PACKAGING.md used to say otherwise.** The only
  part of create-dmg the tool wanted was drag-to-install, and that is one `/Applications`
  symlink in a staging folder. Doing it this way means the runner installs nothing through
  Homebrew to package a build, and there was never a background image in this repo for
  create-dmg to place.
- **The ffmpeg pair is collected as `binaries`, not as `datas`.** PyInstaller lays binaries out
  the way the `.app` needs and re-signs them ad-hoc after rewriting their load commands, which
  the arm64 kernel requires of anything it executes. That replaces their Developer ID
  signatures, which costs nothing while the app itself is unsigned (OQ-9). They are collected
  on macOS only: they are arm64 Mach-O and `core/ffmpeg.py` skips them elsewhere, so a Linux
  build would be carrying 132 MB it could never run. `build/build.py` refuses a macOS build
  when they are absent, because PyInstaller would only warn and the app would install, start,
  and fail on its first probe.
- **Size: 236 MB installed on Linux**, and the macOS number comes from CI, which prints both it
  and the dmg into the run summary. PRD section 8 budgets under 300 MB for the *installer*, so
  the dmg is what it is read against. The build prints the verdict and does not fail on it:
  what to drop when PySide6 gains a megabyte is a person's decision, not a red `main`.

**Two things M7 left open.** There is **no application icon**, so the bundle carries
PyInstaller's default; and **OQ-52**, the bundle identifier, is a placeholder
(`com.proingest.ProIngest`) because no studio name exists anywhere in this repository. The
identifier is worth settling before the first build reaches the editor, since macOS keys
per-app state off it.

M9 detail, asked for 2026-09-12 and specified against PRD FR-17. It is the first milestone
whose deliverable is not code, and it is deliberately separate from M8.4: M8.4 is what the
studio keeps about the **build**, and M9 is what somebody reads to **use the tool**.

| chunk | scope | state |
|---|---|---|
| M9.1 | Install guide: the dmg, the quarantine bit and Gatekeeper (OQ-9), first run, where settings and logs live | needs M7 |
| M9.2 | Quickstart: one turnover from Add Turnover to the exports, about a page | can be drafted now |
| M9.3 | The reference guide, one section per surface: the list and its columns, editing, the Issues dock, the run, Settings, the log, the metadata pane | follows the surfaces it documents |
| M9.4 | The screenshot harness: builds a demo batch, grabs the window, writes the files the guide references. Drafted on Linux, **shipped set taken on the Mac** | harness now, images on the Mac |
| M9.5 | The document itself: one source, printed to PDF and pasteable into Google Docs whole (OQ-49) | last |

**Three things about M9 that are decisions rather than tasks.**

- **The screenshots come from a harness, not from a person with a screenshot key.** A guide
  illustrated by hand is a guide that goes stale silently the first time a column moves. A
  script that builds a demo batch and calls `QWidget.grab()` makes a changed interface a
  re-run. It also fixes the data problem: the demo batch is the synthetic `MELT` show the
  fixtures already build, so no production shot code, shooter name or Drive path is in a
  document that gets emailed around.
- **The shipped images have to come from the Mac** even though the harness runs headless on
  Linux, because a guide showing a Linux font stack and Linux window furniture is a guide to a
  tool the editor does not have. Linux images are fine for drafting the layout. `MAC_SESSION.md`
  carries the line.
- **One source, not two exports.** OQ-49 asks the user which form they want and the default is
  one HTML file in the repo with the images embedded: it prints to PDF and pastes into Google
  Docs whole, images included, which is the only shape that satisfies "a pdf **or** a file that
  can be pasted into google docs" without maintaining two.

M3 detail:

| chunk | scope | state |
|---|---|---|
| M3.1 | `exr.write_frame`, `exr.read_pixels`, `core/resize.py` | done, 45 tests |
| M3.2 | container decode to numpy frames in `core/ffmpeg.py` | done, 25 tests |
| M3.3 | `core/render.py`: execution, atomic writes, checksums, copies | done, 35 tests |
| M3.4 | pool, progress, cancellation, `proingest run` CLI | done, 30 tests |
| M3.5 | ref mp4 encode, audio muxed, frame count verified | done, 23 tests |

The stringout moved off this table: it is M6 and always was. The M3.5 row said "ref
mp4 and stringout" and that was a mistake in the row, not a change of plan.

Tests by file: qc 195, ui_shell 130, naming 115, shot_model 92, render 75, clf 73,
planner 66, metadata 57, frames 55, media 46, models 45, shot_list 43, ffmpeg 43,
color 40, timeline 37, exr 37, scan 36, cli 32, runner 29, settings_page 28, exports 28, bundle 19,
issues 22, batchfile 18, resize 16, settings 16, camdata 12, scanner 11, autosave 11.
1408 in total, counted rather than carried forward.

---

## 6. Decisions taken

**The colour pipeline (respecified 2026-09-11, nothing built).**

`docs/COLOR_AND_FORMAT.md` section 1 is the spec and is not repeated here. What belongs here is
why each choice was made, so it is not relitigated by someone reading only the code.

**This spec has been rewritten twice in one day and both rewrites were the user correcting a
premise, not a design changing its mind.** Section 1 of this file has the table. The mechanics
were right both times; what was wrong was who authors colour and when.

- **Colour is authored in a Resolve session, not in this tool, and that deletes a feature
  rather than moving one.** The morning's spec had four per clip sliders as an AD notes layer
  on top of the shooter's CDL. The AD's notes now go into the colour session with the AD in the
  room, and come back in the CLF. Two places to author a grade is two answers to a question
  that can only have one, and the session is the one with the colourist and the reference
  monitor. QC-037 and OQ-32 retired with the sliders.
- **The plate is graded, which reverses 2026-09-11 on its own terms.** That spec refused a
  graded plate because a baked grade stops matching when the grade moves in the DI. This
  workflow finishes the DI **before** the turnover is ingested, so there is no later grade for
  the plate to stop matching, and the objection expires rather than being overruled. The half
  of it that survives is a requirement on the CLF, not a reason to refuse: it must end in scene
  linear ACEScg with **no display rendering**, or the delivered EXR is display referred and says
  it is linear. QC-039. That failure is invisible on a monitor and expensive in a comp, which is
  why it is an error and why the tool probes rather than trusting a filename.
- **The CLF is applied and the CDL is recorded, and carrying both is not redundancy.** They come
  out of the same session and they answer different questions. A CDL can say only slope, offset
  and power per channel plus one saturation, so a grade containing a curve, a log wheel or a hue
  versus saturation curve, all ordinary primary tools, would arrive silently incomplete; the CLF
  carries all of it, which is why it is the thing applied. The CDL goes in the EXR header as the
  readable version, for the person or the facility that has neither the session nor an OCIO
  install. **Where they disagree the CLF is what is in the pixels**, and the header says so.
- **The CLF hash is what identifies the grade.** A re-exported and redelivered CLF has a
  different hash, so the deliverables rendered from the old one stay findable afterwards. That
  is the whole reason a graded plate is auditable at all.
- **One studio standard log encoding, and it is worth defending.** The user's first description
  of the workflow said "log encoded ProRes per shot", which was read as camera original, and a
  whole per shot IDT apparatus was specified: a sidecar IDT field, a Resolve to OpenColorIO
  name map, QC-038 on an unknown name, two open questions. The user corrected it within the
  hour and all of that was deleted. **One encoding on every file means one input transform
  forever**, and the camera specific work stays in the shooter's Resolve project where the
  camera metadata actually is. If a future session finds itself building a table of IDT names,
  it has taken a wrong turn. Which encoding it is, is OQ-39; ACEScct makes the transform
  identity, because the colour session's CLF starts there.
- **The viewers are gone, and the trimming they were attached to is not.** The user removed the
  three viewers hours after specifying them that morning. The thing they existed for, judging
  a cut point on a picture, moved to the colour session, which has the AD in the room, a real
  viewer and a calibrated monitor. What stayed is In/Out editing in the list, deliberately, as
  **the quick one-off**: the trim that would otherwise mean asking Ben to reopen Resolve and
  export a new EDL for one shot. That framing matters more than the feature, because it is the
  difference between an exception and a second editing surface.
- **A trim is safe against the grade, and that is why the exception is affordable.** A CDL is
  one set of numbers for the whole shot rather than a curve over time, so moving In or Out
  carries it unchanged. The single caveat is that extending into the handles applies the
  approved grade to frames nobody saw in the session.
- **QC-045 is new rather than QC-035 being redefined.** There are now three In/Out states worth
  distinguishing: what the shooters delivered, what Ben and the AD approved, and what actually
  rendered. QC-035 already meant the first against the last and is implemented, so it keeps its
  meaning; QC-045 reports the middle against the last, at warning severity, because a delivered
  shot that is not the shot the AD signed off is a louder fact than an editorial trim. The QC
  log's Shots sheet carries all three columns.
- **The list is the only surface that writes to a row again.** No viewers, no colour controls,
  no editable metadata pane. That was the original design, was briefly untrue on 2026-09-11 when
  the viewers were given trim buttons, and is true again. It is worth stating because FR-5 spent
  a day carrying an explicit exception to it.
- **The stringout is dropped and M6 with it.** The colour session exports a reference QT with
  the look and burn-ins. Three artifacts claiming to be the stringout is two too many. What it
  gives up is real and is recorded in PRD FR-9: the tool's would have been the only one cut to
  the **edited** In/Out, since the session's QT and the shooters' offline are both cut to the
  turnover as delivered. If the vendor turns out to need that, it comes back as a milestone.
- **Rendering now depends on something that is not media.** A batch scans and reviews without a
  colour session and cannot render final deliverables without one (QC-008, QC-009). That is a
  new shape for the user flow, written into PRD section 6 as its own step, and it is why Run
  can be blocked by something with nothing wrong with the pictures.
- **QC IDs were retired rather than repurposed.** QC-006, QC-007, QC-017, QC-037, QC-140 and
  QC-141 stay in the table marked RETIRED with what they used to mean. Reusing an ID would make
  an old log line resolve to the wrong rule, and the whole reason the IDs are stable is that
  they turn up in spreadsheets that outlive the code.
- **OpenImageIO stays out.** The proposed workflow wrote EXRs with OIIO. `core/exr.py` already
  writes AP1 chromaticities, DWAA, timecode and arbitrary named attributes through the
  `OpenEXR` bindings, with 45 tests behind it, so OIIO would be a second large dependency
  inside a 300 MB installer budget in exchange for no capability. DWAA 45 stays the default
  over PIZ for the same kind of reason, and is OQ-36 rather than closed.
- **Tetrahedral interpolation is specified, not defaulted.** Trilinear is the default in
  several tools, it is visibly worse on saturated colour, and it is a one word difference that
  nobody notices being wrong. It is stated for both the OCIO transform and the ffmpeg `lut3d`.

These carry over from 2026-09-11 unchanged, because they never depended on where the grade came
from:

- **ACEScg over scene linear Rec.709, because of negatives.** Converting a wide gamut camera
  image into 709 primaries pushes saturated colour out of gamut, where it becomes negative
  float, and negatives misbehave in comp. Resizing a linear image in too small a gamut
  manufactures them on its own, and this tool resizes every plate to HD. AP1 is wide enough
  that the question does not arise. ACES has an entire Reference Gamut Compression spec because
  of this problem; picking AP1 avoids needing it.
- **The viewing LUT now has one consumer, and it survives anyway.** It was justified as one
  definition shared by the encoder and the on-screen viewers, so the two could not drift, which
  was a good argument until the viewers were removed. What holds it up now is duller and still
  sufficient: ffmpeg has no OCIO filter and does have `lut3d`, so baking the transform to a cube
  is how an OCIO result reaches the encoder at all, and it is what keeps the reference a single
  pass with no frames crossing into Python. If a viewer returns in v02, the cube is the thing to
  hand it, and the original argument comes back with it.
- **The view branch stays bounded until the final encode**, because everything before the
  output transform happens in ACEScct. swscale clamps float to 0..1, so this is what lets
  ffmpeg keep doing the reference resize in a single pass with no frames crossing into Python.
  The plate branch is unbounded and resizes in numpy, which is what `resize.py` is for.
- **OCIO's packaging objection was checked and does not exist.** 5.7 MB arm64 wheel, built-in
  configs so nothing ships on disk, Windows wheel available for v02. The alternative considered
  was `colour-science`; OCIO wins because it also loads a CLF and does ACES properly rather
  than just the curves.

**Phase B verification, where it runs and what it keeps (M4.2).**

- **It runs inside the worker, right after the atomic rename.** `render_job` calls
  `qc.run_phase_b` before it returns, so a Deliverable that comes back `done` has been
  checked and a caller never has to remember to verify. The two rules that cannot run
  there, QC-150 and QC-151, run in `render.apply_results`: one asks whether a whole row
  landed and the other reads every name in the batch, and a worker sees one job.
- **A failed check keeps the file and writes a `.failed` sidecar.** That is the opposite
  of a render failure, which leaves nothing at all, and the difference is deliberate: a
  file that failed a check is evidence someone has to be able to open, a file that was
  never finished is garbage. The marker is the one `batchfile.reconcile_with_filesystem`
  already looked for, so a crash straight after the check still reopens as failed.
- **`run_phase_b` takes the job as well as the deliverable.** ARCHITECTURE.md calls it
  `qc.run_phase_b(job)`; QC-106 and QC-120 compare against checksums the writer recorded,
  which a job cannot know. The useful consequence is that every check can be cornered by
  handing it a job that disagrees with a real file, which is how QC-111 to QC-114 are
  tested without fabricating a broken encode.
- **One result per rule for a sequence, naming the first offender.** A sequence whose
  every frame is the wrong compression is one defect. 240 identical rows would bury the
  rest of the report, and the name of one bad frame is what someone actually needs.
- **QC-111 decodes rather than reading the index.** The render already compared
  `container_frame_count`; an index can claim 240 over a file that stops at 12, and the
  delivered reference is what the vendor plays. QC-115 reads the box order for the same
  reason: `-movflags +faststart` is a request, and a trailing moov plays locally and
  stalls over a Drive link.
- **QC-121 is an error only for extracted audio.** A wav source is delivered as a byte
  copy per COLOR_AND_FORMAT section 3, so a 24 bit source delivers 24 bit by design and
  failing it would fail a deliverable that is exactly what the spec asks for. QC-044
  already warned about it at scan time. `docs/QC_RULES.md` said error unconditionally and
  was corrected.
- **`file_digest` moved from `render.py` to `qc.py`**, where the checks that compare
  against it live. `render.file_digest` stays as the same object under the old name, so
  nothing that called it had to change.

**The phase A rule registry, and what scopes a rule (M4.1).**

- **Rules are scoped by what the row is, in one place.** `qc.is_picture_row` and
  `qc.is_plate` decide it and nothing else does. An aux still is a single frame at its
  own size, so the resolution, range, handle, duration and timecode rules skip it; only
  the plate owes audio (QC-040) and side files (QC-050, QC-051), because only the plate
  delivers them. Firing QC-033 on every colour chart in a turnover would bury the
  warnings the editor is actually meant to read.
- **Every threshold lives in `qc.RuleSettings`, never as a literal at the point of use.**
  It maps one to one onto FR-12's Rules section, round-trips through
  `Batch.settings_overrides["rules"]`, and **refuses an unknown key**: a typo in a
  settings file that silently changed nothing is the failure mode that costs a whole
  delivery. `proingest scan --rules <json>` is the headless way in until M5's Settings
  page exists, and it saves what it read into the batch so a later run or QC applies the
  same numbers the scan did.
- **The rules that touch the disk are a separate pass, `qc.preflight`.** Model rules
  re-run after every edit and must stay cheap; QC-022, 052, 054, 057, 062 and 063 cost
  stat calls, an EXR header read and an ffmpeg invocation, and their answers change
  without the model changing. `proingest run` calls preflight once, prints what it found,
  and stops only on a batch-scope error: a turnover with no lens grid is a warning the
  editor reads, not a reason to render nothing.
- **QC-022 is pure even though it lives in preflight.** `check_source_codec` takes the
  decoder set as an argument, so it tests headless like every other rule; preflight is
  merely the only caller that knows to ask ffmpeg. An ffmpeg that will not answer yields
  an empty set and the rule falls silent, because failing every row in the batch over a
  build detail is worse than missing one undecodable file.
- **QC-062 is batch scope and tolerates a root that does not exist.** `docs/QC_RULES.md`
  said row scope and was corrected. There is one delivery root, the run creates every
  folder under it, and a per-row check is N stat calls on a network mount for one answer.
  The write probe goes to the nearest existing ancestor, because the root itself is
  usually the thing about to be created.
- **Fixture media had to stop pretending to be clean.** A 64x36 four frame turnover
  legitimately fails QC-023, QC-030 and QC-033 now, and the honest fix was to give the
  tests real settings (`tests/fixtures/media.py::SMALL_RULES`) rather than to soften the
  rules. `make_turnover(side_files=True)` writes the HDRI and camData a plate is supposed
  to arrive with, off by default so the side file tests can still place their own.

**Apple Silicon only, Windows 11 a v02 intention (OQ-24, confirmed 2026-09-10).**

- The arm64 bundle stands. No universal2 build, no second lock entry, no installer budget
  spent on an Intel Mac that is not in scope.
- **No runtime architecture guard, deliberately.** macOS refuses to launch an arm64-only
  `.app` on Intel with a better message than this tool could print. The leak is running
  from source on an Intel Mac: `resolve_tool` tests `is_file`, not whether this machine
  can execute the file, so the first ffprobe call fails with `Exec format error`. A
  developer's problem on a machine confirmed not to exist.
- The v02 Windows build will have to revisit `BUNDLED_PLATFORM`, which is pinned to
  `darwin`, and `_platform_binary`, which already knows about `.exe`. That is why the
  `.exe` branch stays rather than being cleaned away as dead.

**Audio runs cut point to cut point (OQ-27, answered 2026-09-10).**

- If a clip has audio the wav starts where the picture starts and ends where it ends.
  `render._audio_skip` assumed exactly that and is confirmed rather than changed.
- **The half that mattered was "ends with".** The wav does not run past the delivered
  range, so extending Out into the handles outruns it, and FR-5 says extending Out is how
  a shot gets longer. `-shortest` ends the output at whichever stream finishes first, so
  that truncated the picture: 24 frames asked for, 12 delivered, measured. The M3.5 frame
  count check caught it, but it would have failed a legitimate render.
- `-af apad,atrim=duration=<seconds>` is one idiom, not two options, and **neither half
  is about the other stream**. The pad makes the audio endless, so a wav the picture
  outruns becomes silence, which is the honest answer for a shot extended past the sound;
  the trim cuts one that overruns back to the delivered range. Both directions are pinned
  by tests. **It was `apad` and `-shortest` until 2026-09-12**, and `-shortest` is a
  heuristic: it lets audio buffer ahead of a video stream still inside a filtergraph, by
  a margin that varies with the ffmpeg version. M4.5.4 put a `lut3d` in that graph and
  ffmpeg 9.0.1 delivered 0.98 seconds of sound against a third of a second of picture.
  The duration is computed from integer frames and the exact rational rate, divided only
  at the ffmpeg boundary, so 23.976 cannot drift over a long shot.
- QC-043 now has an expectation rather than a guess, and the same warning means two
  different things: before an edit a malformed turnover, after an edit the editor's own
  trim, since the wav deliverable is a byte copy and is never trimmed.

**The lens grid is manual in v01 (OQ-20, answered 2026-09-10).**

- It arrives as **a folder in the turnover package**, not a clip on the timeline, and the
  editor moves it to the delivery root and renames its files themselves. The tool neither
  plans nor writes one.
- **The folder half is what dissolved the question.** All three undecided things assumed a
  timeline clip. The scan iterates clips, so it will never meet a lens grid and the QC-010
  it was supposedly going to raise cannot happen; and with no deliverable planned there is
  no show to file it under and nothing to version. That entry was carried for weeks on a
  premise nobody had checked.
- Not silent, in two places, because the studio's sheet marks the lens grid **Required**
  and an unreminded manual step is a forgotten one. QC-054 is reworded from "clip" to
  "folder" and stays a warning for a turnover that has none; **QC-057 is new**, info, for
  a turnover that has one. Neither is implemented: both are M4 with the rest of the
  registry.
- `naming.lens_grid_png` and `naming.parse_lens_grid_name` stay, built and tested. They
  are the spelling the editor now types by hand, and a tool that can check a name it no
  longer writes costs nothing to keep.

**The tool asks where the files are; it does not look (OQ-25, answered 2026-09-10).**

- The editor points at a **source root** and a **delivery root**, a folder chooser each, and
  both happen to be on a Google Drive mount. Nothing probes
  `~/Library/CloudStorage/GoogleDrive-*/My Drive` or `/Volumes/GoogleDrive` any more, and
  first run detects nothing. A dialog opens at the last used folder.
- **This deleted planned work rather than adding any.** The discovery only ever existed in
  the docs, written from Google's published conventions rather than from a machine anyone
  had seen, and no code was built for it. The CLI already takes a turnover folder and a
  `--delivery-root`, which is the same shape. UI_SPEC section 13 has the spec; the metadata
  pane stayed section 12 so the cross-references in four files still point at it.
- A wrong default is worse than none: probing would have opened the dialog somewhere
  plausible and empty on a machine where the guess missed.
- **"Source root" was read as the folder turnovers are added from, not as a replacement for
  picking them.** Multi-turnover batches are untouched and adding one from outside the root
  just moves the root. Flagged to the user as an assumption; it is a two line change.
- **It does not settle FR-2.** See section 9: a Windows shooter's OTIO carries `G:\...`
  paths regardless of where the editor's Drive is mounted.

**The reference encode is one ffmpeg pass over the source, not a decode and re-feed.**

- The raw path pulls frames into this process because it has to: EXR output goes through
  the OpenEXR bindings, and swscale would clamp float to 0-1 on the way. An mp4 has no
  such need. x264 wants every frame anyway, so decoding into numpy first would copy 95 MB
  a frame across a pipe to hand straight back. `ffmpeg.encode_reference` runs one command.
- **The price is paid in two places, and both are real.** A reference reports no progress
  between its start and its finish, and a cancelled run waits for an encode already in
  flight rather than stopping it. Both are in section 9; neither is worth a frame-by-frame
  pipe, and `-progress pipe:1` would buy the first back on its own if it is ever wanted.
- The seek is `decode_command`'s, unchanged: `-start_number` for a sequence, the
  frame-counting `trim` for a container, never `-ss`. Section 7 has the two traps that
  come with using it for an encode rather than a decode.
- **Superseded by M4.5.4:** the transfer used to come from `color.display_transform`, which
  returned a linear-to-sRGB filter or None. There is no such function now. The colour that
  reaches ffmpeg is one baked cube applied with `lut3d`, built by `render._view_lut` from the
  shot's own chain. The scale still runs before it, so the downscale sees the log values, which
  are bounded the way swscale needs them (COLOR_AND_FORMAT sections 1 and 4).
- Audio is a second input, AAC 192k, cut to the picture with `apad,atrim`, and **seeked by
  the in-point offset** so the sound stays with a trimmed picture. That the wav starts
  where the picture media starts is an assumption, logged as OQ-27.

**Witness cam is a normal deliverable (confirmed by the user 2026-09-10).**

- The spec PDF lists the two `wit` raw rows with a bare filename, no frame range and no
  subfolder columns, where every other raw sequence row has all three. It reads as though
  witness cam were a single file, or delivered under some different rule. It is not. `wit`
  is treated exactly like any other clip on the timeline: the same four picture
  deliverables as `cp`, `el` and `re`, no audio, and a sequence for its raw outputs.
- **Nothing was built for this.** The planner type table already gave every element type
  the four picture deliverables, so the answer matched what was there. The value is in not
  re-deriving it: the PDF gap looks like it means something, and the next reader who finds
  it would go looking. NAMING_SPEC section 3 and the OQ-5 row now say so, and
  `tests/test_planner.py::TestTypeTable` pins both halves.
- The 2161/2162 heights in that table are still real typos, treated as 3840x2160.

**Platform: v01 is macOS on Apple Silicon (changed 2026-09-10).**

- The primary user is on a Mac. Windows moved to the v02 backlog, swapping places with the
  macOS build that was sitting there. Confirmed with the user: macOS only for v01, Apple
  Silicon, **no Apple Developer account**, and **no Mac available to build or test on**.
- **The switch was cheap, and the reason is worth keeping.** Core never imports Qt, uses
  `pathlib` throughout, and had no win32 API anywhere; the process pool already used the
  spawn context on every platform; `media.url_to_path` already handled both `file:///G:/...`
  and `/Volumes/...`. The whole of M1 to M3.4 needed exactly one code change, the
  `sys.platform` guard in section 3. Everything else was docs. The discipline in CLAUDE.md
  paid for itself here.
- **ffmpeg had to be re-sourced entirely.** gyan.dev publishes Windows builds only, which
  was checked rather than assumed: 419 assets across the 100 most recent releases, none
  macOS. v01 now bundles the martin-riedl.de macOS arm64 GPL v3 build of ffmpeg 9.0.1.
  `build/ffmpeg.lock.json` went to schema 2 to describe per-download archives, because the
  new source ships ffmpeg and ffprobe as separate zips rather than one archive with members.
  Full rationale and the rejected alternatives are in `proingest/resources/ffmpeg/PROVENANCE.md`.
- **The bundled ffmpeg features were verified by reading the binary, not by running it**, since
  an arm64 Mach-O will not execute on this machine. The configure line, the symbol table and
  the linked frameworks confirm libx264, libzimg, libfreetype and `h264_videotoolbox` are
  compiled in. That is strong evidence, not proof the encoder opens on real hardware. OQ-23.
- **NVENC is gone and is not being replaced in M3.** `has_nvenc()` is dead code. VideoToolbox
  is the macOS equivalent but has no CRF and an uncalibrated `-q:v` scale, so shipping it
  would mean shipping a quality setting nobody has measured. Software x264 CRF 18 is what the
  spec pins and it is deterministic, which QC-106 depends on. Hardware encode is an M5
  Settings toggle at the earliest.
- **Gatekeeper is the one place macOS is genuinely worse.** OQ-9 was a shrug on Windows (a
  SmartScreen warning) and is a blocker here: an unsigned, un-notarized, quarantined `.app`
  is refused outright. The bundled ffmpeg binaries are themselves Developer ID signed with
  the hardened runtime (`CS_RUNTIME`, read out of their code directory), so they are fine;
  ProIngest's own bundle is the problem. Decide before handover, not at handover.

**Colour (OQ-17, answered by the studio 2026-09-10). SUPERSEDED 2026-09-11, twice.**
Kept as the record of what M3 was built against and why its reference encodes looked the way
they did. The live policy is COLOR_AND_FORMAT section 1: a studio standard log source, a CLF
per shot applied, a graded ACEScg plate. **Nothing in this block is still in the code.** The
display referred premise it describes lived under a fence in `core/color.py` until M4.5.4
deleted it along with `TestSupersededDisplayEncode`.

- Everything the shooters deliver today, **EXRs included, has the sRGB curve baked in**.
  The source is display referred, not scene referred. The EXRs are expected to become
  scene linear sRGB later, so `core/color.py` holds a two-value setting rather than a
  constant, defaulting to `srgb_display`.
- The reference encode is the thing that depends on it, and it is inverted from what
  the docs originally assumed: a baked source gets **no** transfer, a scene linear
  source gets the linear-to-sRGB curve. Both outputs are tagged the same (`bt709`
  primaries and matrix, `iec61966-2-1` transfer); only the work to get there differs.
  Getting this backwards does not fail loudly, it just washes out or crushes every
  reference deliverable. Read it from `color.display_transform`, never re-derive it.
- Raw EXR output is untransformed either way and states which it is in
  `proingest/colorspace`. The attribute labels the file; it never claims a conversion.
- The HD downscale runs on the delivered values, curve and all. Resampling in linear
  light would be defensible for a display referred source, but ffmpeg's `scale` on the
  container path is gamma-unaware, so linearizing only the EXR path would make the two
  paths disagree.

**Frame rate.**

- **The timeline rate is authoritative.** Shooters set all footage to 24 fps in Resolve
  before exporting, so the timeline is what the media is played at. `MediaInfo.rate` is
  that effective rate and drives all frame math and timecode conversion.
  `MediaInfo.stated_rate` records what the media itself claims, purely so QC-026 can
  report a disagreement. Nothing computes with it.
- A frame count is counted at the file's own rate, because a file holds the frames it
  holds.
- Timecode counts at `nominal_rate(fps)` (23.976 counts at 24). The float fps is a
  playback rate and never enters frame math.

**Versioning.**

- Version is scoped to the **shot folder**, not the individual deliverable. NAMING_SPEC
  section 4 said "per shot" and section 7 said "the kind being planned", which
  contradicted each other; section 4 won because it is the half that explains why
  (partial version sets confuse downstream), and section 7 was corrected. Consequence:
  a shot whose `cp01` shipped at v01 starts its `pl01` at v02.
- Version is resolved at plan time, immediately before a run, never at scan time.
  `plan_batch` replaces each row's deliverable list, so recorded render state belongs
  to the version that produced it.

**Running a batch (M3.4).**

- **The pool uses the spawn context on every platform**, not just where it is forced.
  macOS, now the target, spawns by default, so spawning on the Linux dev machine too
  means the pickling constraints are identical in testing and in the field. A job that
  only works under fork would otherwise pass every test here and fail on the user's
  machine. This was written when Windows was the target and needed no change when it
  stopped being one, which is the whole argument for the choice.
- **A failed job is a result, not an exception.** `execute` returns one Deliverable per
  job whatever happened: `done`, `failed` carrying QC-100, or `skipped` when cancelled.
  One bad row must not stop a 100 shot run. Results come back in job order, not
  completion order, so a caller can line them up against what it planned.
- **QC-100 is new**: "render did not complete". Every other QC-1xx is NA when it fires,
  because there is no file to check. It is also the exception to the phase B rule that a
  failed deliverable keeps its file with a `.failed` marker: a render failure leaves
  nothing at all, by design.
- Progress and cancellation cross the process boundary as a `multiprocessing.Queue` and
  `Event` handed over in `initargs`. That is the only way: a Queue cannot be pickled
  through a task submission, only inherited at process creation. `render_job` itself
  takes two plain callables instead, so it stays free of multiprocessing and both hooks
  are unit-testable without a pool.
- `on_progress` is called on a drain thread in the **calling** process, so a UI callback
  marshals to the main thread the way it normally would.
- `DEFAULT_WORKERS` is 4, capped rather than one per core: each worker may run its own
  ffmpeg and ffmpeg is already multi-threaded, so more mostly buys contention. Tuning it
  against a real turnover is M8.

**Rendering (M3.3).**

- **A deliverable either exists complete or does not exist.** Every job writes to
  `job.temp` and renames on success, and every failure path discards the temp. A render
  failure therefore leaves nothing at all. That is deliberately different from a phase B
  QC failure, which QC_RULES says keeps the file for inspection with a `.failed` marker:
  a file that failed a check is evidence, a file that was never finished is garbage.
- **An occupied destination is refused, never overwritten.** The planner resolves a free
  version immediately before the run, so a destination that already exists means a
  concurrent run or a bug. A delivered frame is not ours to replace.
- `Deliverable.frame_checksums` holds the per frame xxhash64 QC-106 needs; `checksum`
  stays the whole file digest a single file gets. The field is additive with a default,
  so `SCHEMA_VERSION` stays 1: bumping it would reject every existing `.pibatch` with no
  migration, for a field an older file simply does not have.
- `DeliverableJob` gained `source_size`, `rate`, `source_start_frame` and
  `source_start_timecode`. Reprobing in the worker was the alternative, and it would let
  the render disagree with the scan about the source.
- Source timecode counts from the **media start**, not from the In point:
  `frames.timecode_frames_for(source_frame, source_start, source_start_timecode)`. A
  sub range starting at 1004 of a sequence that starts at 1001 carries start TC plus 3.

**Model and structure.**

- Models are plain dataclasses with explicit dict conversion, not pydantic, so core
  stays dependency-light and `mypy --strict` clean.
- Shot number and element index stay strings so leading zeros survive.
- Job kinds reuse `naming.parse_output_name`'s vocabulary, so QC-151 in M4 is a direct
  equality between the planned kind and the parsed filename rather than a translation
  table. `tests/test_planner.py::TestOutputNamesReadBack` already asserts it.
- Audio format is left flexible on purpose. Sample rate, bit depth and channel count
  are not constrained; what matters is whether it syncs, which is QC-043.
- `core/qc.py` exists early holding only the rate and sync rules. Rules there are pure
  functions of the model and re-run after every edit; `apply_row_rules` owns only the
  IDs it produces, so results raised during the scan survive. `planner` follows the
  same discipline for QC-056 and QC-060.

---

## 7. Findings worth keeping

**Three ways a reference encode goes wrong without failing.**

- **A sequence input has no frame rate, and image2 invents 25.** Every reference built
  from an EXR or DPX sequence would play 4% fast with nothing in the log. `-framerate` is
  passed before the input from the timeline rate, as an exact rational: 23.976 is
  24000/1001, and a decimal there drifts against the timecode.
- **`trim` keeps the source timestamps.** The first delivered frame lands at its original
  offset, so the mp4 opens with a gap that long. Measured on four frames at 24: 0.25s of
  container against 0.17s of picture. `setpts=PTS-STARTPTS` follows every trim.
- **ffmpeg exits 0 when the source runs out before the range does.** Asked for 100 frames
  of a 4 frame plate it writes 4, says nothing, and the deliverable would be recorded as
  done. The raw path already counted what it wrote; the encode now reads `nb_frames` back
  off the container (`ffmpeg.container_frame_count`, the index rather than a decode, which
  on a 4k reference is the difference between nothing and minutes) and refuses a short
  file. Pinned by a test.

**A mov's timecode track rides along into the reference.** `-map 0:v:0 -an` drops the
audio but the mp4 muxer still writes a `tmcd` data stream from the source timecode. That
is useful rather than not, but a test asserting "one stream" will fail on it.

**OpenEXR bindings.**

- `OpenEXR.File(header, channels)` takes the header **first**.
- **DWAA is lossy.** At level 45 a frame comes back about 0.1% off proportionally at
  every brightness (0.5 -> 0.0005 out, 64.0 -> 0.0625 out). "Pixels in, pixels out"
  means no colour transform, not a byte copy. QC-106 hashes the written file rather
  than comparing pixels, which is sound because the encoder is byte-deterministic for
  identical input. Both facts are tested.
- The bindings **cannot write a `Rational` attribute**, so `framesPerSecond` cannot be
  written correctly. An int or string is accepted under that name but is the wrong
  attribute type for a reader expecting a rate, so output carries a per-frame
  `timeCode` and no rate. Reading a rate still works, which is all QC-026 needs.
- `chromaticities` wants an **8-tuple** (red, green, blue, white). The binding's error
  message says "expected a 6-tuple", which is wrong and cost a few minutes.
- `OpenEXR.TimeCode` has no four-argument constructor: build an empty one and assign
  `hours`, `minutes`, `seconds`, `frame`.

**ffmpeg and ffprobe.**

- ffmpeg *does* have an `exr` encoder, contrary to what CLAUDE.md said. It only offers
  none/rle/zip1/zip16 and no `timeCode` attribute, so the OpenEXR bindings are still
  the right call. CLAUDE.md corrected.
- ffprobe reports `r_frame_rate` 25/1 for a single EXR frame, which is a guess. Sequence
  rate therefore comes from the EXR header first, then the timeline, then ffprobe.
- ffprobe exits 0 on a corrupt EXR and reports a 0x0 stream, logging the real complaint
  to stderr only. QC-014 cannot rely on the exit code, so zero dimensions mean
  unreadable.
- **swscale takes float pixel formats and clamps them to 0-1.** An earlier note here said
  it could not carry float at all, which is wrong and understates the danger: it accepts
  `gbrpf32le` in and out and silently flattens everything above 1.0 to white and
  everything below 0.0 to black. Measured: 4.0 in, 1.0 out; -0.5 in, 0.0 out. That is the
  real reason the EXR path resamples in numpy, and it becomes a live hazard the day the
  shooters switch to scene linear. The container path is safe because every container
  format the spec accepts is integer and already bounded.

**CLI progress (M3.4).**

- Per-job progress lines redrawn in place are unreadable the moment two workers run:
  they interleave into a wall of text, and `\r` does nothing useful in a redirected log.
  The CLI prints **one aggregate line** (deliverables done, frames done, percent) and
  only on a tty; a redirected run gets the per-deliverable result lines alone, which is
  what a log wants. Found by running it, not by testing it, and now pinned by tests.

**Writing through ffmpeg (M3.3).**

- **An ffmpeg output written to a `.part` path must state `-f` explicitly.** ffmpeg infers
  the muxer from the extension, and `.wav.part` tells it nothing: it fails with "Unable to
  choose an output format". The atomic write discipline and format inference are in direct
  conflict, and every ffmpeg written deliverable hits this, so M3.5's mp4 encodes need
  `-f mp4` for the same reason. Found by a test, not by reading.

**Decoding (M3.2).**

- `gbrpf32le` is planar and stores **G, then B, then R**. RGB is planes 2, 0, 1. Nothing
  errors if this is wrong; red and blue simply swap, on every deliverable. There is a flat
  colour fixture and a test that pins it.
- **Frame seeking.** A container seeks with `trim=start_frame=<in>:end_frame=<out+1>`, whose
  end is exclusive. It counts frames after the decoder has reordered them, so it is exact on
  a long GOP h.264 source; verified against a full decode. `-ss` is never used: it takes a
  float number of seconds and lands on the wrong frame at 23.976. A sequence uses
  `-start_number`, which is a real seek and never opens the frames ahead of the range.
- `-fps_mode passthrough` is required. Without it ffmpeg is free to duplicate or drop frames
  to hit a constant rate, which would quietly break the 1:1 source-to-output mapping that
  COLOR_AND_FORMAT section 6 defines.
- `-map 0:v:0 -an` is required too: a source with audio otherwise reaches the rawvideo muxer
  as a second stream.
- ffmpeg's stderr goes to a temp file, not a pipe. A decode that complains once per frame can
  write more than a pipe buffer holds, and nothing is draining it while frames are being read.
- The decode is a generator and owns the process. Its `finally` kills and reaps, so abandoning
  a shot part way through does not leave ffmpeg running. That is why it is annotated
  `Generator`, not `Iterator`: closing it is part of the contract.

**Resampling (OQ-7, answered by building it).**

- `core/resize.py` is antialiased Lanczos-3 in numpy. Checked directly against
  `scale=...:flags=lanczos`: on a hard edge the two outputs are **identical**, on a
  gradient they differ by under one 8 bit level, and on full-bandwidth random noise
  they diverge (mean 7/255) because swscale quantizes its kernel into fixed point.
  Structured content, which is what a plate is, agrees. Both comparisons are tests.
- scipy was rejected: `ndimage.zoom` is a cubic spline with no antialiasing, so a 2:1
  reduction of fine texture aliases instead of averaging, and it is a large dependency
  against a 300 MB installer budget.

**Timeline.**

- An EDL states no frame rate anywhere in the file. The otio adapter silently assumes
  24, so the project rate is passed explicitly, and a timecode mismatch is reported as
  QC-025 rather than a generic QC-002 parse failure.
- otio rejects a drop-frame timecode at a non-drop rate with a generic parse error, so
  drop frame is detected from the EDL text before parsing and reported as QC-027.
- The CMX3600 adapter left otio core at 0.17 and is now `otio-cmx3600-adapter`. FR-1
  needs it for the EDL fallback, so it is a real dependency.

**Side files.**

- They were matched on the name fragment alone, so a `..._HDRI_preview.jpg` could be
  picked up and then delivered under an `.exr` name, because delivery renames without
  converting. The scan now filters to the extensions NAMING_SPEC section 2 states
  (`*HDRI*.exr`, `*camData*.txt|rtf`).

**Qt, two defaults that do not do what the spec assumes.**

- **`QTreeView` ships with tab key navigation off; `QTableView` ships with it on.** With
  it off, Tab moves focus out of the view entirely and `moveCursor` is never asked, so
  UI_SPEC section 4's walk across the editable cells only worked while a cell editor
  happened to be open (the delegate asks for the next item itself). `ShotListView` turns
  it on and a test pins it. Found by driving a real window, which is the second finding
  in two chunks that no test would have produced.
- **An editor commits on a queued connection, not when Return is pressed.**
  `QAbstractItemDelegate` posts `_q_commitDataAndCloseEditor` so the editor can validate
  its own contents first, so the model still holds the old value for the rest of that
  event loop turn. Nothing in the suite depends on it, because the tests commit through
  `setData` the way the delegate does; it is written down so that a test which sends
  Return and asserts immediately is recognised as testing Qt's scheduling rather than
  the code.

---

## 8. Repo conventions and session-specific facts

- **Three things are deliberately untracked**, all at the user's request: `docs/ROADMAP.md`
  and `docs/ROADMAP.docx`, a manager-facing plan, and the whole of `preview/`. The ROADMAP
  All three are in `.gitignore`, and all three are still on disk. The ROADMAP pair was
  held by convention alone until a `git add docs/` swept it in, so it is enforced now.
  Stage files by name anyway: `git add -A` and `git add <dir>` are both how this happens.
  The .docx was generated from the .md with `python-docx`; no converter is kept in the
  repo, so if the .md changes and a new .docx is wanted, write one and throw it away.
- **Build track artifact**, a readable M1-M8 status board for the user:
  https://claude.ai/code/artifact/c0e6b8ac-6673-4e28-833d-7d85b5f7273a
  Source is `build-track.html` at the repo root, which *is* tracked. It is a generated
  view of this file, not spec. To update it, edit that file and republish it with the
  artifact URL above passed as `url`.
- **Interface preview**, a front-end mock of `docs/UI_SPEC.md` for showing producers what
  the tool will look like before M5 exists:
  https://claude.ai/code/artifact/a9efaeb7-f890-4f24-a6a3-4bd92ad844eb
  Source is `preview/index.html`, one file, React from a CDN, no build step. **The folder
  is untracked**, so the artifact and the copy on this machine are the only versions of it;
  a fresh clone will not have it. Its data is entirely invented and it is wired to nothing
  in `proingest/`. It is a picture of the
  spec, never a statement of behaviour: if the two disagree, `docs/UI_SPEC.md` wins and the
  mock is stale. `preview/README.md` lists which parts are taken from the spec and which
  are made up.
- Commit messages: say what changed and why, name the rule or doc section involved, and
  flag anything a reader would otherwise have to rediscover. No em dashes anywhere,
  in any file (user's global rule).
- Definition of done for a feature is in `CLAUDE.md`: core function with unit tests,
  wired into the UI with a manual test note, new QC rule IDs added to
  `docs/QC_RULES.md`, `docs/OPEN_QUESTIONS.md` updated for anything assumed.

---

## 9. Open items

Nothing blocks the next task. These are live, in rough priority order:

- **The Settings page offers no input transform overrides and no output quality, and both
  are for the same reason.** Every one of them is applied inside a **spawned worker**, so
  the value has to travel on the `DeliverableJob` rather than be read from a settings file
  the worker does not have. That is real plumbing and it is a chunk of its own; the page
  lists the two sections and says so rather than offering a control that would do nothing.
  FR-12 asks for the overrides, so this is a deferral rather than a decision.

- **Pre-flight and planning run on the UI thread, and nobody has measured them on a real
  turnover.** Both write to the batch, which is why they are not on the worker thread, and
  both touch the disk: pre-flight stats the delivery root and asks ffmpeg for its decoders
  once, and planning lists one delivery folder per shot code to resolve the version. On
  fixtures it is instant; on a hundred shot batch over a Drive mount it is a window that
  does not paint for as long as those listings take. Measure it in M8 with the rest of the
  network mount work, and if it has to move, what moves is a copy of what planning needs
  rather than the batch (the M5.5 note in section 1 has the shape).

- **Closing the window during a run waits for the jobs in flight.** `closeEvent` cancels
  the pool and then waits up to two minutes, because a `QThread` still running when its
  owner is collected is a crash on the way out. A cancelled job stops at its next frame
  boundary, so the wait is usually a frame; the exception is a reference encode, which
  cannot be interrupted at all and can be a whole 4k encode per worker. Nothing asks the
  editor first, which is worth a sheet on the Mac pass rather than a guess from here.

- **The rendering dot is not animated.** UI_SPEC section 3 asks for an accent dot that
  moves; the dots are drawn once per state and cached, which is what keeps a hundred shot
  repaint cheap, and an animated one needs a repaint timer and a cache key that carries a
  phase. The state is live and the colour is right; only the movement is missing.

- **QC-039's probe cannot separate a dark C-Log3 grade from a display rendering (OQ-47).**
  New 2026-09-12, found while building M4.6.2, and the most important open item because it is
  the only one that can refuse a valid delivery. The probe wants the CLF's white above 2.0,
  which was calibrated when white meant ACEScct's 222; out of C-Log3 white is worth 14.7, so a
  CLF graded four stops down answers 0.92 and a display rendering answers 1.0. The direction of
  the failure is the safe one, an error on a good CLF rather than a bad plate delivered.
  **The fix is measured and written up in OQ-47**: `out(1.0) / out(0.9)`, which is invariant to
  how dark the grade is and separates every encoding in play by an order of magnitude. Left
  alone in M4.6.2 because it is QC-039's definition rather than the chain.

- **Where the source encoding comes from is built, and the field name is a guess.** The
  encoding is read at scan time from `Input Color Space` on the clip, or
  from the container's tags, resolved through the input transform table, reported by
  QC-046, QC-047 and QC-048, and recorded with its origin in the header and the QC log
  (M4.6.5). **The field name is Resolve's own column name and nothing has
  confirmed Resolve exports it** (OQ-44): one real export from the shooters either confirms it
  or moves one string in `scan.py`. Until then a real turnover may scan with QC-046 on every
  row, which is loud and harmless and exactly what it is for.

- **QC-046's error scope has a seam in it between the scan and the ingest.** It is an error
  on an aux still and lesser elsewhere, as `QC_RULES.md` specifies. A row with no CLF and no
  encoding also has nothing to render through, and the rules cannot say so at scan time because
  no row has a CLF until a session has been ingested. The render refuses that chain and QC-100 carries the reason. Section 1
  has the whole of it.

- **A row whose clip names no encoding cannot render an ungraded plate, and that is
  deliberate.** `color.DEFAULT_SOURCE_ENCODING` is deleted (M4.6.1) rather than given a new
  value, because OQ-39 dissolved: there is no batch-wide source encoding to fall back on.
  A graded row is unaffected, since the CLF is the whole chain there. A row with no CLF, and
  an aux still on any row, now has nothing to convert with and `ShotColor.plate_transforms`
  refuses rather than passing log pixels through under an ACEScg header. **Since M4.6.4 the scan fills the row in**, so this
  is the clip that named nothing rather than every clip.

- **No colour session has ever exported for this tool (OQ-31).** Every claim in
  COLOR_AND_FORMAT section 1 about what arrives is a specification, not an observation, until
  one session has run end to end on one shot. That single exercise answers OQ-29, OQ-30, OQ-33
  and OQ-39 at the same time, and it is the cheapest thing on this list: it needs one graded shot,
  not a whole turnover.

- **A scanned turnover cannot be re-scanned without losing the edits on it (OQ-48).**
  `Scan` re-tries only the turnovers with no rows. There is deliberately no way to re-scan
  one that has them, because a scan rebuilds rows from the timeline and the rows carry In,
  Out, shot code, notes and the skip reasons. The version worth building is a merge that
  keeps the overrides and reports what moved underneath them, which wants QC-035's snapshot
  machinery; nobody has asked for it, and in the workflow as described a turnover is
  re-delivered rather than re-scanned.

- **The Issues dock's Fix column is text and nothing else.** UI_SPEC section 6 says
  "Locate media" opens a file picker and writes a path override into the batch. That is a
  batch edit made from outside the list, and section 1 says the list is the only thing that
  writes to the model, so the two want reconciling before one of them is built past a hint.

- **A reference encode reports no progress and cannot be cancelled mid-encode.** It is one
  ffmpeg process, so the job goes from started to done with nothing in between, and a
  cancelled run finishes the encodes already in flight before it stops. Worst case is the
  length of one 4k encode per worker. `-progress pipe:1` parsed off stdout would give
  per-frame progress, and a `Popen` with a poll on the cancel flag would give the kill;
  neither is built because neither is worth it until someone has watched a real 100 shot
  run. Section 6 has the reasoning.
- **The reference path resamples through swscale, which clamps float to 0-1.** This is load
  bearing rather than a hazard, and COLOR_AND_FORMAT section 1 depends on it: ffmpeg sees the
  log source going in and display sRGB coming out, both bounded, and the unbounded stretch is
  inside the cube. **The plate branch must never go near it**, which is why `core/resize.py`
  exists and why M4.5.4 kept the two branches apart rather than letting the plate borrow the
  reference's resize. What is worth measuring once is OQ-43: the log resize happens before the
  transform rather than after it.
- **The delivered EXR header is missing three fields the spec lists.**
  `proingest/tool_version`, the shot ID and the frame range are in COLOR_AND_FORMAT's EXR
  metadata list and are not written; the colour provenance and the `timeCode` attribute are.
  They are cheap, they need only what the job already carries, and nothing has asked for them,
  so the doc now says "not yet written" rather than describing them as built.

- ~~A frozen `.app` needs `multiprocessing.freeze_support()` and there is no entry point to
  put it in yet.~~ **Built in M7**, in `build/entry.py`, which exists for that one line. The
  reasoning was right and the mechanism was not what this entry assumed: see M7's detail in
  section 5, because CPython's `freeze_support` does nothing at all on macOS and the line
  works anyway.

- **QC-024, a letterboxed source, is the one phase A rule that cannot be a model
  function.** QC-023 now catches a source that is not 3840x2160, but a source that *is*
  3840x2160 with black bars baked into it looks identical in a header. Detecting it means
  decoding a frame and measuring the black rows and columns, which is a scan-time cost on
  a network mount and false-positives on a genuinely dark plate. Nothing is built and
  nothing pretends to be. Worth doing next to the colour space heuristic below, since
  both want the same "read one frame during the scan" machinery.
- **Letterboxing a non 16:9 source is still not implemented, and the toggle for it now
  exists.** QC-023 blocks such a row, which is the half that mattered: `render._fit` can
  no longer squash a plate without anyone being told. COLOR_AND_FORMAT section 4 says the
  row is letterboxed when a Settings toggle allows it, and M5.7.2 put `allow_non_4k` on
  the Rules page - so turning it on downgrades QC-023 to a warning and **still resamples**,
  which is now a control the editor can reach rather than a value only a JSON file held.
  The letterbox itself is the work that is left.
- **QC-111 decodes every delivered reference, twice over on a 100 shot run.**
  `ffmpeg.count_frames` runs `-count_frames`, which is a full decode, and it runs inside
  the worker for each of the two references per row. On tiny fixtures it is free; on a
  240 frame 4k reference it is not, and nobody has measured it on real media. The cheap
  alternative, the container's own index, is already checked by the render and is exactly
  the check QC-111 exists to not trust. Measure it in M8 before deciding, and if it has
  to go, make it a setting rather than a silent downgrade.
- **QC-053 and QC-061 are the two phase A rules with nothing behind them.** QC-053
  (camData parsed, N key/value pairs) needs the parser that fills the exports' Camera
  Data sheet, so it lands with M4.3 and OQ-11. QC-061 (a complete QC-passing set exists,
  row skipped) needs a Force re-render setting and a planner that can be told to respect
  it; the planner raises QC-060 today and always writes the next version.
- **OQ-21, alpha from a container source.** The EXR path preserves a source alpha;
  the container path decodes `gbrpf32le` and drops it. Two things are undecided and neither
  can be settled from the docs: what counts as a *real* alpha rather than the opaque one a
  codec always carries, and whether a plate consolidated out of Resolve ever legitimately has
  one. `MediaInfo` records no alpha field, so nothing could set a flag even if the decoder
  took one. Decoding `gbrapf32le` instead is a one line change once there is something to
  switch on.
- **Nothing detects what a turnover's pixels actually are.** The source encoding comes from
  Settings and the file is decoded as whatever it is told (QC-018 only compares the container's
  own tags, which are usually absent or wrong). A source that is not the studio standard
  therefore renders silently wrong. A cheap heuristic exists, since a log signal and a display
  referred one have very different histograms, but it needs the scan to read a frame's pixels
  rather than just a header. Worth a warning eventually; it is not what QC-018 does today.
- **The metadata pane (FR-14) is new scope, added 2026-09-10 at the user's request.** It was
  not in any doc before: the closest thing was the bottom dock's Deliverables tab, which
  describes outputs rather than the source. Spec is `docs/UI_SPEC.md` section 12, field list
  taken from what `core/models.py` actually holds rather than invented. Three decisions in it
  are worth not relitigating: it is **read only**, because the list already owns every edit
  under FR-5 and two writable surfaces over one model means two places for validation to
  disagree; it **never takes focus**, because Tab has a job in the list already; and it
  deliberately **does not repeat the list columns**, only the fields that have none. Nothing
  in core needs to change for it, which is why it costs M5 time and nothing before that.
  Which fields actually earn their place is OQ-26, and it wants a real review session.
- **One M5 decision still unlogged.** Progress on the app icon is now a macOS Dock tile
  rather than a Windows taskbar button; Qt 6 exposes no API for either, so it needs a small
  `NSDockTile` shim through PyObjC in `ui/platform_mac.py`. It is decoration, and the status
  bar carries the same information if it is never built. The other one was the frozen left
  columns and their overlaid second view, which is built and written up (M5.9).
- **OQ-2 (tracker columns) is still open** and wants a real turnover; it has a default
  template loaded from a file, so it blocks nothing. OQ-3's container half is settled and its
  encoding half became OQ-39.
- **A Mac is still needed, but for less than before.** CI now runs the suite on arm64 macOS
  every push (section 3), which was the larger half of OQ-22. What a runner still cannot do:
  judge whether a reference encode looks right, exercise the Dock and menu-bar behaviour in
  UI_SPEC section 11, or run M8 against turnovers that live on the editor's Drive. M7
  packaging is not wired up because `build/build.py` and `proingest.spec` do not exist yet;
  it belongs on the same runner when they do. Renting an hourly Mac is the cheap answer for
  the M5 UI work where someone has to actually look at it.
- **A Windows shooter's media paths are still unresolved in practice.** OQ-25 removed the
  mount question but not this half of it: an OTIO written on Windows carries `G:\...`
  paths that mean nothing on the editor's Mac. `scan._resolve_media` already falls back to
  a filename search over the chosen source root, which needs no configuration and should
  cover it; the FR-2 path map is the belt to that pair of braces. Which one actually does
  the work is a real turnover question, now on the Mac session list.
- **The old Windows binaries are still in `proingest/resources/ffmpeg/`** as `ffmpeg.exe`
  and `ffprobe.exe`, 446 MB of untracked dead weight. Nothing references them any more and
  the lock file no longer knows how to fetch them. Safe to delete; left in place because
  deleting 446 MB the user might want is not this session's call.
- A real end-to-end run against a shooter's turnover has never happened. That is M8,
  and it is where reality will disagree with the spec.
