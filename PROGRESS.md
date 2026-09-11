# Implementation progress

Durable handoff record. It is written to be picked up cold: everything a new session
needs that is not already in the code or the docs lives here. Update it at every
commit.

---

## 1. Resume here

**State at 2026-09-11. M3 is complete.** M1, M2 and M3 are done; M4 is next and has
not been started. Working tree clean apart from two deliberately untracked files
(section 8). 573 tests passing, `ruff` and `mypy --strict` clean. M3.5, the reference
encodes, landed first, then four open questions were answered in a row; the only one that
changed code was OQ-27, which fixed an encode bug M3.5 had shipped.

**The suite now runs on the target platform.** First green CI run on a `macos-latest`
arm64 runner: 547 passed in 16.85s, lint and types clean, against the bundled
martin-riedl ffmpeg 9.0.1 rather than this machine's Ubuntu 6.1.1. The pinned arm64
binaries were confirmed to actually execute, and `h264_videotoolbox` opened a session
and encoded, which answers half of OQ-23.

**The target platform changed on 2026-09-10: v01 is now macOS on Apple Silicon, not
Windows.** The primary user turned out to be on a Mac. Section 6 has the decision and what
it cost, which was much less than it might have been because core never imported Qt and
never hardcoded a Windows path. Windows moved to the v02 backlog. Read that entry before
touching packaging, settings paths or the reference encodes.

**Nothing is blocked.** OQ-5, OQ-20, OQ-24, OQ-25 and OQ-27 were all answered by the user
on 2026-09-11 and are in section 6. Two of them removed planned work rather than adding any;
OQ-20 added one new QC rule ID, QC-057, to be built with the rest in M4; and OQ-27 found a
real bug in the encode that had already shipped. **573 tests.**

Verify the state before changing anything:

```
.venv/bin/python -m pytest tests/ -q
.venv/bin/python -m ruff check proingest tests && .venv/bin/python -m mypy proingest tests
.venv/bin/python -m proingest scan <turnover folder> --save <batch>
.venv/bin/python -m proingest run <batch> --delivery-root <root>
```

The last two are a real end to end run and they now go all the way: a scanned turnover
renders its raw EXR sequences, its reference mp4s at both resolutions with audio muxed,
its audio and its side files. Verified on a two shot synthetic turnover: **10 written, 0
failed, 0 skipped**, and the references came back 3840x2160 and 1920x1080, H.264 High,
yuv420p, `bt709` primaries, `iec61966-2-1` transfer, 24/1, with AAC at 193 kbit/s. No
`.part` left anywhere. That is the expected output now.

**Next task: M4, QC and exports.**

Nothing is half done behind it. `qc.py` already holds QC-025, QC-026 and QC-043 and the
rest of both phases is unwritten; `exports.py` does not exist. Two things M3 left that M4
is the right place for, both in section 9: QC-023 (a non 16:9 or non 4k source is not
caught by anything today) and the post-render QC-1xx family, which is what
`Deliverable.checksum`, `frame_checksums` and the new container frame count were recorded
for.
- **x264 CRF 18 `-preset slow` is what shipped, and hardware encoding stayed out.**
  NVENC went with the Windows target; the macOS hardware encoder is
  `h264_videotoolbox`, which has no CRF and whose `-q:v` scale is uncalibrated (OQ-23).
  `ffmpeg.has_nvenc()` is dead code that nothing calls. Shipping a quality setting nobody
  has measured was not worth it: hardware encode is a Settings toggle in M5 at the
  earliest and needs a real Mac to calibrate. Keyint 24 and `-movflags +faststart` are
  in the command; QC-115 will check the moov atom is at the head.
- **M3.5 deliberately did not build the two things the plan for it named last.** It said
  to parse ffmpeg's `-progress` for frame counts and to kill the child on cancel. Neither
  is there: a reference goes from started to done with nothing in between, and a cancelled
  run finishes the encodes in flight. The reasoning is in section 6 and the gap is in
  section 9, so this is a decision to revisit rather than an oversight to rediscover.

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
| `docs/OPEN_QUESTIONS.md` | OQ-1 to OQ-26, with defaults for the unanswered ones |
| `docs/PACKAGING.md` | M7, the `.app` and dmg, ffmpeg bundling, Gatekeeper |
| `docs/MAC_SESSION.md` | the only work that needs a real Mac, and what to do on the day |

The shooters' own spec sheet sits in `docs/` in two forms, the PDF and a CSV export of the
same document. They are source material, not spec: what the app does with them is settled
in `NAMING_SPEC.md`, which is where the known defects in their type table are recorded.
Read the CSV when the question is what a row of that table actually says, since it needs no
PDF viewer.

---

## 3. Environment

- venv at `.venv` (Python 3.12, created with `uv venv`); `uv pip install -e ".[dev]"`.
  There is no `pip` inside the venv: use `uv pip install --python .venv/bin/python`.
- otio 0.18.1, OpenEXR 3.4.15 (numpy File API present), numpy 2.5.3.
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
| M3 | Render | complete, 172 tests |
| M4 | QC: all rules both phases, xlsx exports, `qc` CLI | **next**, not started |
| M5 | UI, including the FR-14 metadata pane | not started |
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
| M3.5 | ref mp4 encode, audio muxed, frame count verified | done, 23 tests |

The stringout moved off this table: it is M6 and always was. The M3.5 row said "ref
mp4 and stringout" and that was a mistake in the row, not a change of plan.

Tests by file: naming 115, render 62, planner 55, frames 55, media 46, ffmpeg 38,
models 37, timeline 33, exr 29, scan 25, qc 22, batchfile 18, resize 16, cli 16,
color 6.

---

## 6. Decisions taken

**Apple Silicon only, Windows 11 a v02 intention (OQ-24, confirmed 2026-09-11).**

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

**Audio runs cut point to cut point (OQ-27, answered 2026-09-11).**

- If a clip has audio the wav starts where the picture starts and ends where it ends.
  `render._audio_skip` assumed exactly that and is confirmed rather than changed.
- **The half that mattered was "ends with".** The wav does not run past the delivered
  range, so extending Out into the handles outruns it, and FR-5 says extending Out is how
  a shot gets longer. `-shortest` ends the output at whichever stream finishes first, so
  that truncated the picture: 24 frames asked for, 12 delivered, measured. The M3.5 frame
  count check caught it, but it would have failed a legitimate render.
- `-af apad` with `-shortest` is one idiom, not two options. The pad makes the audio
  endless so the shortest stream is always the picture, which `-frames:v` bounds. Audio
  that runs out becomes silence, which is the honest answer for a shot extended past the
  sound. Both directions are pinned by tests.
- QC-043 now has an expectation rather than a guess, and the same warning means two
  different things: before an edit a malformed turnover, after an edit the editor's own
  trim, since the wav deliverable is a byte copy and is never trimmed.

**The lens grid is manual in v01 (OQ-20, answered 2026-09-11).**

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

**The tool asks where the files are; it does not look (OQ-25, answered 2026-09-11).**

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
- The transfer is read from `color.display_transform`, never re-derived. It returns the
  linear-to-sRGB filter for a scene linear source and None for the baked sRGB source the
  turnovers actually carry today, and the wrong branch washes out every reference without
  failing. The scale runs before it, so the resample sees the values as delivered
  (COLOR_AND_FORMAT section 4).
- Audio is a second input, AAC 192k, `-shortest`, and **seeked by the in-point offset** so
  the sound stays with a trimmed picture. That the wav starts where the picture media
  starts is an assumption, logged as OQ-27.

**Witness cam is a normal deliverable (confirmed by the user 2026-09-11).**

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

- **A reference encode reports no progress and cannot be cancelled mid-encode.** It is one
  ffmpeg process, so the job goes from started to done with nothing in between, and a
  cancelled run finishes the encodes already in flight before it stops. Worst case is the
  length of one 4k encode per worker. `-progress pipe:1` parsed off stdout would give
  per-frame progress, and a `Popen` with a poll on the cancel flag would give the kill;
  neither is built because neither is worth it until someone has watched a real 100 shot
  run. Section 6 has the reasoning.
- **The reference path resamples through swscale, which clamps float to 0-1.** Inert
  today: every source is display referred and bounded. The day the EXRs go scene linear a
  highlight at 4.0 will clamp to 1.0 *before* the HD downscale averages it, so a bright
  edge reduces differently than it should, and the raw path (which resamples in numpy for
  exactly this reason) will disagree with the reference. Whoever flips the colour setting
  should read this line first.

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
- **OQ-2 (tracker columns) and OQ-3 (what the consolidated media actually is)** are
  still open and both want a real turnover. Neither blocks: OQ-2 has a default template
  loaded from a file, OQ-3 only tunes QC-020 and QC-021 severity.
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
