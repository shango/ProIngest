# Implementation progress

Durable handoff record. It is written to be picked up cold: everything a new session
needs that is not already in the code or the docs lives here. Update it at every
commit.

---

## 1. Resume here

**State at 2026-09-10.** M1 and M2 complete, M3 in progress (M3.1 to M3.4 done, only
M3.5 left). Working tree clean apart from two deliberately untracked files (section 8).
547 tests passing, `ruff` and `mypy --strict` clean. M3.4 landed as `0c349c9`.

**The target platform changed on 2026-09-10: v01 is now macOS on Apple Silicon, not
Windows.** The primary user turned out to be on a Mac. Section 6 has the decision and what
it cost, which was much less than it might have been because core never imported Qt and
never hardcoded a Windows path. Windows moved to the v02 backlog. Read that entry before
touching packaging, settings paths or the reference encodes.

**Nothing is blocked.**

Verify the state before changing anything:

```
.venv/bin/python -m pytest tests/ -q
.venv/bin/python -m ruff check proingest tests && .venv/bin/python -m mypy proingest tests
.venv/bin/python -m proingest scan <turnover folder> --save <batch>
.venv/bin/python -m proingest run <batch> --delivery-root <root>
```

The last two are a real end to end run and they work today: a scanned turnover renders
its raw EXR sequences, its audio and its side files, and reports the reference mp4s as
QC-100 failures because M3.5 is not built. That is the expected output right now.

**Next task: M3.5, the reference encodes.**

`render.py` dispatches `ref_mp4` to a "not yet" error. Replacing that is the last chunk
of M3. COLOR_AND_FORMAT section 3 has the encode settings and section 1 the colour
policy. Notes for it:

- **Read the transfer decision from `color.display_transform(colorspace)`, never
  re-derive it.** It returns the linear-to-sRGB filter for a scene linear source and
  `None` for the baked sRGB source we actually get today. Getting it backwards does not
  fail loudly, it washes out or crushes every reference (section 6).
- Both outputs are tagged the same either way: `bt709` primaries and matrix,
  `iec61966-2-1` transfer. Only the work to get there differs.
- **State `-f mp4` explicitly.** The output is written to a `.part` path, so ffmpeg
  cannot infer the muxer from the extension. This already bit the audio extract; see
  section 7.
- The encode reads the same source range as the raw pass. `ffmpeg.decode_command` shows
  how the frame seek is built; an encode can use the same `trim` and `-start_number`
  handling rather than piping raw frames back in.
- `job.audio_source` carries the wav to mux, when the row has one. AAC 192k.
- **x264 CRF 18 `-preset slow` is the default and the only thing to build for M3.5.**
  NVENC is gone with the Windows target; the macOS hardware encoder is
  `h264_videotoolbox`, which has no CRF and whose `-q:v` scale is uncalibrated (OQ-23).
  `ffmpeg.has_nvenc()` is now dead code that nothing calls. Leave hardware encoding out
  of M3.5 entirely rather than shipping a quality setting nobody has measured; it is a
  Settings toggle in M5 at the earliest, and it needs a real Mac to calibrate.
  Keyint 24, `-movflags +faststart` (QC-115 checks the moov atom is at the head).
- Cancellation and progress: an encode is one ffmpeg run, not a frame loop, so the
  hooks work differently from `_render_sequence`. Parse ffmpeg's `-progress` output for
  frame counts, and kill the child when the cancel event is set.

After M3.5, M3 is done and M4 (QC rules, both phases, xlsx exports) is next.

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
| `docs/NAMING_SPEC.md` | every input and output name, the type table, versioning, delivery layout |
| `docs/COLOR_AND_FORMAT.md` | colour policy, accepted sources, output formats, frame math, EXR pipeline |
| `docs/QC_RULES.md` | every rule ID, severity and scope. IDs never change meaning |
| `docs/ARCHITECTURE.md` | package layout, data flow, concurrency, batch file |
| `docs/UI_SPEC.md` | the M5 interface, keyboard model, burn-ins |
| `docs/OPEN_QUESTIONS.md` | OQ-1 to OQ-21, with defaults for the unanswered ones |
| `docs/PACKAGING.md` | M7, the `.app` and dmg, ffmpeg bundling, Gatekeeper |

---

## 3. Environment

- venv at `.venv` (Python 3.12, created with `uv venv`); `uv pip install -e ".[dev]"`.
  There is no `pip` inside the venv: use `uv pip install --python .venv/bin/python`.
- otio 0.18.1, OpenEXR 3.4.15 (numpy File API present), numpy 2.5.3.
- Dev machine is Linux/WSL; the target is **macOS on Apple Silicon**, and there is no Mac
  available (OQ-22). Nothing has ever run on the target platform. Everything in core is
  verifiable headless on Linux, which is why the switch was cheap, but M7 cannot be built
  here at all and the reference encodes cannot be quality-checked here either.
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
| `core/models.py` | Batch, Turnover, ShotRow, Deliverable, MediaInfo, AudioInfo, FrameRate, QCResult | 563 |
| `core/ffmpeg.py` | the only place anything shells out; tool lookup, ffprobe, decode, audio extract | 376 |
| `core/media.py` | DirectoryIndex, sequence detection, path remap, probe cache | 465 |
| `core/exr.py` | EXR header and pixel reading, delivery frame writing | 235 |
| `core/resize.py` | antialiased Lanczos downscale for the EXR path | 96 |
| `core/color.py` | source colour space setting; what each deliverable does about it | 61 |
| `core/timeline.py` | OTIO and EDL loading, audio association | 233 |
| `core/scan.py` | turnover folder -> Turnover + ShotRows | 388 |
| `core/planner.py` | type table, deliverable jobs, version resolution | 440 |
| `core/batchfile.py` | `.pibatch` save/load, backup, filesystem reconciliation | 86 |
| `core/render.py` | executing a job and a batch of them: atomic writes, pool, progress, cancel | 469 |
| `core/qc.py` | rule registry; QC-025, QC-026, QC-043 so far | 120 |
| `__main__.py` | `proingest scan` and `proingest run` CLI | 268 |

Not built yet: `core/stringout.py`, `core/exports.py`, `core/settings.py`, and
everything under `proingest/ui/`.

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
  destination. The two hooks are plain callables, so they test synchronously.
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
| M3 | Render | in progress, see below |
| M4 | QC: all rules both phases, xlsx exports, `qc` CLI | not started |
| M5 | UI | not started |
| M6 | Stringout with burn-ins | not started |
| M7 | Packaging: PyInstaller `.app`, dmg, Gatekeeper | not started, and needs a Mac (OQ-22) |
| M8 | Polish, performance on a real turnover, docs | not started |

M3 detail:

| chunk | scope | state |
|---|---|---|
| M3.1 | `exr.write_frame`, `exr.read_pixels`, `core/resize.py` | done, 45 tests |
| M3.2 | container decode to numpy frames in `core/ffmpeg.py` | done, 25 tests |
| M3.3 | `core/render.py`: execution, atomic writes, checksums, copies | done, 35 tests |
| M3.4 | pool, progress, cancellation, `proingest run` CLI | done, 30 tests |
| M3.5 | ref mp4 and stringout encodes | **next**, unblocked |

Tests by file: naming 115, planner 55, frames 55, render 49, media 46, models 37,
timeline 33, exr 29, ffmpeg 25, scan 25, qc 22, batchfile 18, resize 16, cli 16,
color 6.

---

## 6. Decisions taken

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

**Colour (OQ-17, answered by the studio 2026-09-10).**

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

- **Do not `git add docs/ROADMAP.md` or `docs/ROADMAP.docx`.** They are a manager-facing
  plan the user asked to keep outside git, and they are deliberately untracked. Stage
  files by name, never `git add -A`.
  The .docx was generated from the .md with `python-docx`; no converter is kept in the
  repo, so if the .md changes and a new .docx is wanted, write one and throw it away.
- **Build track artifact**, a readable M1-M8 status board for the user:
  https://claude.ai/code/artifact/c0e6b8ac-6673-4e28-833d-7d85b5f7273a
  Source is `build-track.html` at the repo root, which *is* tracked. It is a generated
  view of this file, not spec. To update it, edit that file and republish it with the
  artifact URL above passed as `url`.
- Commit messages: say what changed and why, name the rule or doc section involved, and
  flag anything a reader would otherwise have to rediscover. No em dashes anywhere,
  in any file (user's global rule).
- Definition of done for a feature is in `CLAUDE.md`: core function with unit tests,
  wired into the UI with a manual test note, new QC rule IDs added to
  `docs/QC_RULES.md`, `docs/OPEN_QUESTIONS.md` updated for anything assumed.

---

## 9. Open items

Nothing blocks the next task. These are live, in rough priority order:

- **OQ-20, the lens grid deliverable, is not built.** It is the one row of the type
  table M2 does not cover. Three things are undecided and none can be settled from the
  docs: the scan does not recognise a lens grid clip at all (it fails the shot naming
  regex and lands as QC-010), a lens grid is turnover-level so it carries no show to
  place it under `_turnovers/`, and NAMING_SPEC section 4 versions per shot and says
  nothing about a per camera/lens/mm deliverable. Nothing downstream depends on it.
- **Nothing stops a non 16:9 source being stretched.** `render._fit` resamples to the
  target size, so a source of the wrong aspect would be squashed rather than
  letterboxed. COLOR_AND_FORMAT section 4 says such a row is blocked by QC-023 and only
  letterboxed when a Settings toggle allows it, but **QC-023 is not implemented** (qc.py
  holds only QC-025, QC-026 and QC-043) and there is no Settings module yet, so today
  nothing catches it. The fix belongs in qc.py with the rest of the rules, not as a
  second check inside render.py; letterboxing waits on Settings. M4.
- **OQ-21, alpha from a container source.** The EXR path preserves a source alpha;
  the container path decodes `gbrpf32le` and drops it. Two things are undecided and neither
  can be settled from the docs: what counts as a *real* alpha rather than the opaque one a
  codec always carries, and whether a plate consolidated out of Resolve ever legitimately has
  one. `MediaInfo` records no alpha field, so nothing could set a flag even if the decoder
  took one. Decoding `gbrapf32le` instead is a one line change once there is something to
  switch on.
- **Nothing detects which colour space a turnover actually is.** When the shooters
  switch their EXRs to scene linear and the setting is stale, the references come out
  wrong in the other direction. A cheap heuristic exists (scene linear plates usually
  carry values above 1.0, display referred ones are bounded at 1.0), but it needs the
  scan to read a frame's pixels rather than just its header, and it false-positives on
  a dark plate. Worth adding as a warning before the switch happens.
- **Two M5 decisions still unlogged.** Frozen left columns have no built-in QTreeView
  support and need the overlaid second-view trick. Progress on the app icon is now a
  macOS Dock tile rather than a Windows taskbar button; Qt 6 exposes no API for either,
  so it needs a small `NSDockTile` shim through PyObjC in `ui/platform_mac.py`. It is
  decoration, and the status bar carries the same information if it is never built.
- **OQ-2 (tracker columns) and OQ-3 (what the consolidated media actually is)** are
  still open and both want a real turnover. Neither blocks: OQ-2 has a default template
  loaded from a file, OQ-3 only tunes QC-020 and QC-021 severity.
- **Nothing has ever run on macOS or on arm64.** No Mac is available (OQ-22). The suite is
  green on Linux and that is genuinely most of the value, because core is where the logic
  is, but the reference encodes cannot be quality-checked here, `h264_videotoolbox` cannot
  be proven to open, the Dock and menu-bar behaviour in UI_SPEC section 11 is unverified,
  and M7 cannot start. A `macos-14` CI runner is the cheapest way to close most of that.
- **The Google Drive mount path on the editor's machine is unknown** (OQ-25). Everything
  that used to say `G:` now says "discover it", and the discovery is written from the
  documented Google Drive conventions rather than from a machine anyone has looked at.
- **The old Windows binaries are still in `proingest/resources/ffmpeg/`** as `ffmpeg.exe`
  and `ffprobe.exe`, 446 MB of untracked dead weight. Nothing references them any more and
  the lock file no longer knows how to fetch them. Safe to delete; left in place because
  deleting 446 MB the user might want is not this session's call.
- A real end-to-end run against a shooter's turnover has never happened. That is M8,
  and it is where reality will disagree with the spec.
