# Implementation progress

Durable handoff record. It is written to be picked up cold: everything a new session
needs that is not already in the code or the docs lives here. Update it at every
commit.

---

## 1. Resume here

**State at 2026-09-12. M1, M2, M3 and M4 complete; M4.5 is done, all four chunks.** The colour
chain now reaches the files: a plate is delivered graded in linear ACEScg with AP1 primaries and
a header that says what was applied to it, and a reference mp4 is encoded through the shot's
grade and the ACES output transform baked into one cube. **M5, the UI, is next.**
873 tests passing, `ruff` and `mypy --strict` clean. **Nothing is blocked.**

**M4 is done.** `core/exports.py` writes both spreadsheets, `proingest qc <batch>` writes them
headless, and QC-053 parses camData through the new `core/camdata.py`. Proved end to end on a two
shot turnover: 14 deliverables, five sheets, and a tracker of two rows filling nine columns and
touching none of the other thirty.

M4.5.1 put OpenColorIO in and rebuilt `core/color.py` as the two ends of the chain: the input
transform from the studio standard log to ACEScct, the plate transform from ACEScct to linear
ACEScg, and the machinery to compose them into one `GroupTransform` and apply it to a decoded
frame in place. It did **not** need OQ-39: the source encoding is one OCIO colour space name in
a constant, so the answer costs one string. **The display referred block it kept under a fence
is gone**, deleted with its tests in M4.5.4 as planned.

### First five minutes

```
.venv/bin/python -m pytest tests/ -q
.venv/bin/python -m ruff check proingest tests && .venv/bin/python -m mypy proingest tests
```

Then read `docs/COLOR_AND_FORMAT.md` section 1 before anything else, because it was rewritten
today and it invalidates things you may already believe, including things written this morning.

### Read this before trusting anything about colour

**The colour spec has now been wrong twice and rewritten twice.** Take nothing about colour
from memory or from a commit message, and check the time on anything dated 2026-09-11 before
trusting it: two of the three versions below share that date.

| dated | what it claimed | status |
|---|---|---|
| 2026-09-10 | sources display referred, sRGB baked in, references apply no transfer | wrong |
| 2026-09-11 am | sources ACEScct, plate **ungraded**, CDL read from the shooters' EDL, four colour controls in the tool | superseded |
| 2026-09-11 pm | colour finished before ingest, **CLF per shot applied**, plate **graded**, no controls, no viewers, no stringout | current |

The mechanics survived both rewrites almost intact: ACEScg working space, OCIO for every
transform, the plate branch unbounded in numpy, the view branch bounded in ACEScct and
collapsed into one 3D LUT. What kept changing is **where colour is authored and by whom**.

### What the tool is for

**Checking all media, running QC, and producing every turnover output.** The user said it in
those words on 2026-09-11. It does not author colour, it does not cut a stringout, and it
decides nothing creative. Everything it writes is either a deliverable named from the spec or
a report about one.

### What the workflow is now

The user described it on 2026-09-11 and it is written up in `docs/COLOR_AND_FORMAT.md`
section 1. In one paragraph: the shooters deliver **ProRes 4444 in one studio standard log
encoding**, the same on every file whatever anybody shot on. Their CDL and their string-out
are offline reference and **the tool reads neither**. After the AD meeting, a **colour session
in Resolve**, where Ben works with the AD (ACES 1.3, ACEScct timeline, primary grades only),
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
- **"Studio standard log" is the single most valuable line in the spec.** The user's first
  description said log encoded ProRes per shot, which was read as camera original, and a full
  per shot IDT apparatus was specified and then deleted within the hour when they corrected
  it. One encoding on every file means **one input transform forever**, no per shot IDT, and
  no mapping Resolve's transform names onto OpenColorIO's, which do not agree. If a future
  session finds itself building an IDT table, it has taken a wrong turn.
- **The tool's stringout would have been the only one cut to the edited In/Out.** The colour
  session's QT and the shooters' offline are both cut to the turnover as delivered. That is
  what dropping M6 gives up, and it is recorded in PRD FR-9 so it reads as a decision rather
  than an oversight.

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

### Next task: M5, the UI

M4.5 is finished and the remaining colour work is not code. `docs/UI_SPEC.md` is the spec and it
was already cut down when the four colour controls and the three viewers were dropped. The
things M5 owes the colour chain are small and known:

- **The Colour settings group**, which is where `--color-session` and `--source-encoding` stop
  being flags: the session's EDL path and the studio standard log encoding, both remembered
  (PRD section 7).
- **Wiring QC-008, QC-009, QC-019, QC-039 and QC-045**, which all read `core/clf.py` and none of
  which can fire until a batch knows where its colour session is. QC-008 is the one that refuses
  a run: a batch cannot produce final deliverables until its session exists.
- **The QC log's CLF column is already written** and so is `ShotRow.clf_path`, so the UI has
  something to show per row without any new plumbing.

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
- **Everything through 2026-09-11 is pushed**, at the user's instruction at the end of that
  day: 14 commits went at once, the nine specification ones from the afternoon session and the
  five from the evening. **That line previously claimed the same thing and was wrong**, which is
  why this one names the number. **Run 34675636686 is green on both runners**, Linux in 1m35s and
  macOS arm64 in 1m24s, and it is the first run to carry OpenColorIO: **the wheel installs on
  Apple Silicon and all 785 tests pass there.** Check CI rather than assuming, and pushing is
  still the user's call rather than an automatic step.

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

- venv at `.venv` (Python 3.12, created with `uv venv`); `uv pip install -e ".[dev]"`.
  There is no `pip` inside the venv: use `uv pip install --python .venv/bin/python`.
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
| `core/models.py` | Batch, Turnover, ShotRow, Deliverable, MediaInfo, AudioInfo, FrameRate, QCResult | 583 |
| `core/ffmpeg.py` | the only place anything shells out; tool lookup, ffprobe, decode, audio extract, reference encode through the viewing LUT | 608 |
| `core/media.py` | DirectoryIndex, sequence detection, path remap, probe cache | 465 |
| `core/exr.py` | EXR header and pixel reading, delivery frame writing, and the provenance a graded plate carries | 299 |
| `core/resize.py` | antialiased Lanczos downscale for the EXR path | 96 |
| `core/color.py` | the pinned OCIO config, every leg of the chain but the CLF, composing and applying them, and the view branch baked to a `.cube` | 209 |
| `core/timeline.py` | OTIO and EDL loading, audio association | 233 |
| `core/clf.py` | the colour session package: the final EDL as the conform, the CDL, the CLF matched per row, loaded, hashed and probed, and `ShotColor`, which is what rides on a job | 471 |
| `core/scan.py` | turnover folder -> Turnover + ShotRows | 388 |
| `core/planner.py` | type table, deliverable jobs, version resolution, the shot's colour attached to each job | 485 |
| `core/batchfile.py` | `.pibatch` save/load, backup, filesystem reconciliation | 86 |
| `core/camdata.py` | key/value pairs out of a camData `.txt` or `.rtf`, RTF stripped pragmatically | 62 |
| `core/exports.py` | the QC log's five sheets and the studio tracker's rows to paste | 378 |
| `core/render.py` | executing a job and a batch of them: atomic writes, the plate and view branches, pool, progress, cancel | 631 |
| `core/qc.py` | rule registry: phase A, `RuleSettings`, `preflight`, phase B | 1416 |
| `__main__.py` | `proingest scan`, `run` and `qc` CLI, `--rules` overrides | 382 |

Not built yet: `core/settings.py`, and
everything under `proingest/ui/`. **`core/stringout.py` will not be built**: M6 is dropped
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
| M4.5 | Colour pipeline, core only. Studio log in, CLF applied, ACEScg out, the viewing LUT | complete, 111 tests |
| M5 | UI: the list, the FR-14 metadata pane, settings, log. **No viewers** | not started |
| M6 | ~~Stringout with burn-ins~~ | **dropped 2026-09-11**, the colour session exports it |
| M7 | Packaging: PyInstaller `.app`, dmg, Gatekeeper | not started, and needs a Mac (OQ-22) |
| M8 | Polish, performance on a real turnover, docs | not started |

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

Tests by file: qc 164, naming 115, render 66, planner 55, frames 55, media 46,
clf 42, ffmpeg 40, models 37, color 35, timeline 33, exr 29, cli 26, scan 25,
exports 24, batchfile 18, resize 16, camdata 12.

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

- **No colour session has ever exported for this tool (OQ-31).** Every claim in
  COLOR_AND_FORMAT section 1 about what arrives is a specification, not an observation, until
  one session has run end to end on one shot. That single exercise answers OQ-29, OQ-30, OQ-33
  and OQ-39 at the same time, and it is the cheapest thing on this list: it needs one graded shot,
  not a whole turnover.

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

- **QC-024, a letterboxed source, is the one phase A rule that cannot be a model
  function.** QC-023 now catches a source that is not 3840x2160, but a source that *is*
  3840x2160 with black bars baked into it looks identical in a header. Detecting it means
  decoding a frame and measuring the black rows and columns, which is a scan-time cost on
  a network mount and false-positives on a genuinely dark plate. Nothing is built and
  nothing pretends to be. Worth doing next to the colour space heuristic below, since
  both want the same "read one frame during the scan" machinery.
- **Letterboxing a non 16:9 source is still not implemented.** QC-023 blocks such a row
  now, which is the half that mattered: `render._fit` can no longer squash a plate
  without anyone being told. COLOR_AND_FORMAT section 4 also says the row is letterboxed
  when a Settings toggle allows it, and that half waits on M5's Settings page. Turning
  `allow_non_4k` on today downgrades QC-023 to a warning and still resamples.
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
- **Two M5 decisions still unlogged.** Frozen left columns have no built-in QTreeView
  support and need the overlaid second-view trick. Progress on the app icon is now a
  macOS Dock tile rather than a Windows taskbar button; Qt 6 exposes no API for either,
  so it needs a small `NSDockTile` shim through PyObjC in `ui/platform_mac.py`. It is
  decoration, and the status bar carries the same information if it is never built.
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
