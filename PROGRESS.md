# Implementation progress

Durable handoff record. Updated after each chunk so work can resume from disk.

## Resume here

**State at 2026-09-10:** M1, M2 and M3.1 complete, 457 tests passing, ruff and
`mypy --strict` clean. Verify with:

```
.venv/bin/python -m pytest tests/ -q
.venv/bin/python -m ruff check proingest tests && .venv/bin/python -m mypy proingest tests
.venv/bin/python -m proingest scan <turnover folder>
```

**Next task: M3.2, decoding a source into frames.** `core/ffmpeg.py` gains the decode
command (`-f rawvideo -pix_fmt gbrpf32le`) and a frame reader that yields numpy
arrays for a container source; the EXR source path is already covered by
`exr.read_pixels` plus `resize.lanczos_resize`. After that, M3.3 is `core/render.py`:
job execution, atomic `.part` writes, per-frame xxhash64, side file copies. M3.4 is
the pool, progress, cancellation and the `proingest run <batch>` CLI.

**Still blocked on OQ-17 (colour space):** the ref mp4 and stringout encodes only.
Everything on the raw EXR path is unaffected, which is why M3 was started there.

**Build track artifact** (readable M1-M8 status board, republish the same file path
to update): https://claude.ai/code/artifact/c0e6b8ac-6673-4e28-833d-7d85b5f7273a
Source file: `build-track.html` at the repo root. It is a generated view of this
file, not spec. To update it, edit that file and republish it with the artifact URL
above passed as `url`.

**Manager-facing plan:** `docs/ROADMAP.md` and `docs/ROADMAP.docx`, a chunked feature
list with build estimates. Deliberately untracked (the user asked for them outside
git). Do not `git add` them. The .docx is generated from the .md; regenerate it with
the throwaway converter noted in the M3 findings if the .md changes.

## Modules built so far

| module | what it owns |
|---|---|
| `core/naming.py` | every output name, both directions; `next_version` |
| `core/frames.py` | integer frame math, timecode, In/Out input grammar |
| `core/models.py` | Batch, Turnover, ShotRow, MediaInfo, AudioInfo, FrameRate, QCResult |
| `core/ffmpeg.py` | the only place anything shells out; tool lookup, ffprobe |
| `core/media.py` | DirectoryIndex, sequence detection, path remap, probe cache |
| `core/exr.py` | EXR header and pixel reading, delivery frame writing |
| `core/resize.py` | antialiased Lanczos downscale for the EXR path |
| `core/timeline.py` | OTIO and EDL loading, audio association |
| `core/scan.py` | turnover folder -> Turnover + ShotRows |
| `core/batchfile.py` | `.pibatch` save/load, backup, filesystem reconciliation |
| `core/planner.py` | type table, deliverable jobs, version resolution |
| `core/qc.py` | rule registry; QC-025, QC-026, QC-043 so far |
| `__main__.py` | `proingest scan` CLI |

## M1 Core -- COMPLETE (348 tests)

Goal (PRD section 9): OTIO parse, clip name parse, media resolution, ffprobe cache,
shot model, batch JSON, headless CLI `proingest scan <folder>`, tests.

| chunk | module | state |
|---|---|---|
| M1.1 | scaffolding: pyproject, venv, package skeleton | done |
| M1.2 | `core/naming.py` + `tests/test_naming.py` | done, 106 tests |
| M1.3 | `core/frames.py` + `tests/test_frames.py` | done, 55 tests |
| M1.4 | `core/models.py` + `tests/test_models.py` | done, 37 tests |
| M1.5 | `core/ffmpeg.py`, `core/media.py`, `core/exr.py` + tests | done, 39 tests |
| M1.6 | `core/timeline.py` + tests | done, 33 tests |
| M1.7 | `core/batchfile.py`, `core/scan.py` + tests | done, 49 tests |
| M1.8 | `__main__.py` scan CLI + tests | done, 8 tests |
| M1.9 | `tests/fixtures/media.py` synthetic media | done |

## Environment

- venv at `.venv` (Python 3.12, created with `uv venv`); `uv pip install -e ".[dev]"`
- otio 0.18.1, OpenEXR 3.4.15 (numpy File API present), numpy 2.5.3
- Dev machine is Linux/WSL; target is Windows. The bundled `resources/ffmpeg/*.exe`
  cannot run here, so `core/ffmpeg.py` falls back to ffmpeg/ffprobe on PATH. That
  fallback order is required by PACKAGING.md anyway.
- Binaries are not in git: `python build/fetch_ffmpeg.py` populates them.

## Decisions taken

- Models are plain dataclasses with explicit dict conversion, not pydantic, so core
  stays dependency-light and `mypy --strict` clean. ARCHITECTURE.md names dataclasses.
- Shot number and element index are kept as strings to preserve leading zeros.
- `mypy python_version` is 3.12, not 3.11: numpy's stubs use `type` statement syntax
  that mypy rejects under 3.11, and pytest imports numpy transitively. The runtime
  floor in `requires-python` stays 3.11, which numpy genuinely supports.
- Timecode counts at `nominal_rate(fps)` (23.976 counts at 24). The float fps is a
  playback rate and never enters frame math.

## M2 Naming and planning -- COMPLETE (66 new tests, 414 total)

Goal (PRD section 9): deliverable plan per clip type, versioning, path layout, tested
against the spec examples.

| chunk | module | state |
|---|---|---|
| M2.1 | `core/planner.py` + `tests/test_planner.py` | done, 55 tests |
| M2.2 | `naming.parse_shot_code`, `naming.frame_in_sequence` + tests | done |
| M2.3 | side-file extension filter in `core/scan.py` + tests | done |

## M3 Render -- IN PROGRESS

Goal (PRD section 9): EXR writer, mp4 encoder, audio copy, side file copy, atomic
writes, pool, progress. CLI `proingest run <batch>`.

| chunk | module | state |
|---|---|---|
| M3.1 | `core/exr.py` write, `core/resize.py` + tests | done, 43 tests |
| M3.2 | container decode to numpy frames in `core/ffmpeg.py` | next |
| M3.3 | `core/render.py`: job execution, atomic writes, checksums, copies | |
| M3.4 | process pool, progress, cancellation, `proingest run` CLI | |
| M3.5 | ref mp4 and stringout encodes | held by OQ-17 |

## Blockers

- **OQ-17, colour space. Blocks M3, nothing earlier.** The shooters' spec PDF says
  `Render Color Space: sRGB`; COLOR_AND_FORMAT section 1 assumes scene linear. If the
  delivered EXRs are display-referred, the reference encode double-applies the sRGB
  curve and every ref mp4 and the stringout come out washed out. Raw EXR output is a
  straight pixel copy and is unaffected either way. Resolve by inspecting real
  delivered media alongside OQ-3, not by re-reading the PDF.
- **OQ-20, the lens grid deliverable, is not built.** It is the one row of the type
  table M2 does not cover. Three things are undecided and none can be settled from the
  docs: the scan does not recognise a lens grid clip at all (it fails the shot naming
  regex and lands as QC-010), a lens grid is turnover-level so it carries no show to
  place it under `_turnovers/`, and NAMING_SPEC section 4 versions per shot and says
  nothing about a per camera/lens/mm deliverable. Nothing downstream depends on it.
- Two M5 decisions still unlogged: frozen left columns in QTreeView (needs the
  overlaid second-view trick) and Windows taskbar progress (QtWinExtras was removed
  in Qt 6, so it needs an `ITaskbarList3` shim in a Windows-only UI helper).

## Decisions taken (continued)

- **The timeline rate is authoritative.** Shooters set all footage to 24 fps in
  Resolve before exporting the stringout and EDL, so the timeline is what the media
  is played at. `MediaInfo.rate` is that effective rate and drives all frame math
  and timecode conversion. `MediaInfo.stated_rate` records what the media itself
  claims (EXR `framesPerSecond` header, or a container's stream rate) purely so
  QC-026 can report a disagreement. Frame counts still come from the file's own
  rate, because a file holds the frames it holds. See OQ-19 on QC-026 severity.

- **Audio stays flexible.** Sample rate, bit depth and channel count are not
  constrained. The one thing that matters is whether it syncs, so QC-043 compares
  audio duration against the picture range in frames, in both directions, with one
  frame of slack. Audio recorded against a different rate surfaces as drift here.
- `core/qc.py` exists early, holding only the rate and sync rules. The full phase A
  and B registries are still M4. Rules there are pure functions of the model and
  re-run after every edit; `apply_row_rules` owns only the IDs it produces so the
  scan's results survive.

## Findings worth keeping

- An EDL states no frame rate anywhere in the file. The otio adapter silently
  assumes 24, so the project rate is now passed explicitly, and a timecode
  mismatch (the usual symptom of an EDL cut at another rate) is reported as
  QC-025 rather than a generic QC-002 parse failure.
- ffmpeg *does* have an `exr` encoder, contrary to what CLAUDE.md said. It only
  offers none/rle/zip1/zip16 and no `timeCode` attribute, so the OpenEXR bindings
  are still the right call. CLAUDE.md corrected.
- `OpenEXR.File(header, channels)` takes the header FIRST. DWAA at
  `dwaCompressionLevel` 45.0, a `timeCode` attribute and half-float RGB all
  round-trip. The M3 EXR pipeline is validated ahead of time.
- ffprobe reports `r_frame_rate` 25/1 for a single EXR frame, which is a guess, not
  the truth. Sequence rate therefore comes from the EXR `framesPerSecond` header
  first, then the timeline's rate, then ffprobe.
- ffprobe exits 0 on a corrupt EXR and reports a 0x0 stream, logging the real
  complaint to stderr only. QC-014 cannot rely on the exit code, so zero dimensions
  are treated as unreadable.
- The CMX3600 adapter left otio core at 0.17 and is now `otio-cmx3600-adapter`.
  FR-1 needs it for the EDL fallback, so it is a real dependency.
- otio rejects a drop-frame timecode at a non-drop rate with a generic parse error.
  Drop frame is therefore detected from the EDL text before parsing, so the user
  gets QC-027 ("drop-frame timecode") rather than QC-002 ("failed to parse").

## Findings worth keeping, M2

- Version is scoped to the **shot folder**, not to the individual deliverable.
  NAMING_SPEC section 4 said "per shot" and section 7 said "the kind being planned",
  which contradicted each other. Section 4 wins because it is the one that explains
  why (partial version sets confuse downstream), so section 7 was corrected to match.
  Consequence: a shot whose `cp01` shipped at v01 starts its `pl01` at v02.
- Job kinds deliberately reuse `naming.parse_output_name`'s vocabulary, so QC-151 in
  M4 is a direct equality between the planned kind and the parsed filename rather
  than a translation table. `tests/test_planner.py::TestOutputNamesReadBack` already
  asserts the round trip for every planned name.
- Side files were matched on the name fragment alone, so a `..._HDRI_preview.jpg`
  could be picked up and then delivered under an `.exr` name, because delivery renames
  without converting. The scan now filters to the extensions NAMING_SPEC section 2
  states (`*HDRI*.exr`, `*camData*.txt|rtf`).
- A BTS still that is not png/jpg/jpeg has no delivery name at all. Rather than drop
  it silently, the planner raises the new QC-056 (warning) and plans nothing for it.
- The planner replaces a row's deliverable list, so it must run immediately before a
  run, not when a batch is opened: recorded render state belongs to the version that
  produced it.

## Findings worth keeping, M3

- **DWAA is lossy**, which the docs did not say. At level 45 a frame comes back about
  0.1% off proportionally at every brightness (0.5 -> 0.0005 out, 64.0 -> 0.0625 out).
  "Pixels in, pixels out" means no colour transform, not a byte copy. QC-106 hashes
  the written file rather than comparing pixels to the source, which is sound because
  the encoder is byte-deterministic for the same input. Both facts are now tested.
- The OpenEXR bindings **cannot write a `Rational` attribute**, so `framesPerSecond`
  cannot be written correctly. An int or a string is accepted under that name but is
  the wrong attribute type for a reader expecting a rate, so output carries a
  per-frame `timeCode` and no rate. Reading a rate still works, which is all QC-026
  needs.
- `chromaticities` wants an **8-tuple** (red, green, blue, white). The binding's error
  message says "expected a 6-tuple", which is wrong and cost a few minutes.
- `OpenEXR.TimeCode` has no four-argument constructor: build an empty one and assign
  `hours`, `minutes`, `seconds`, `frame`.
- **OQ-7 answered by building it.** `core/resize.py` is antialiased Lanczos-3 in
  numpy. Checked directly against `scale=...:flags=lanczos`: on a hard edge the two
  outputs are *identical*, on a gradient they differ by under one 8 bit level, and on
  full-bandwidth random noise they diverge (mean 7/255) because swscale quantizes its
  kernel into fixed point. Structured content, which is what a plate is, agrees. Both
  comparisons are now tests. scipy was rejected: `ndimage.zoom` is a cubic spline with
  no antialiasing, so a 2:1 reduction of fine texture aliases instead of averaging,
  and it is a large dependency against a 300 MB installer budget.
- The .docx of the roadmap was produced with a throwaway `md2docx.py` in the session
  scratchpad using `python-docx` installed with `--target` outside the venv, so the
  project's dependency list is untouched. Nothing in the repo depends on it.
