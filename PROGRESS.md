# Implementation progress

Durable handoff record. Updated after each chunk so work can resume from disk.

## Resume here

**State at 2026-09-10:** M1 complete, working tree clean, 348 tests passing,
ruff and `mypy --strict` clean. Nine commits on `main`. Verify with:

```
.venv/bin/python -m pytest tests/ -q
.venv/bin/python -m ruff check proingest tests && .venv/bin/python -m mypy proingest tests
.venv/bin/python -m proingest scan <turnover folder>
```

**Next task: M2, `core/planner.py`.** ShotRow -> list[DeliverableJob] from the type
table in NAMING_SPEC section 2, version resolved at plan time (not at scan), delivery
layout from NAMING_SPEC section 5. `naming.py` already provides every name builder,
`parse_output_name` and `next_version`, so M2 is the type table plus job construction.
Unblocked.

**Do not start M3** until OQ-17 (colour space) is answered. See Blockers.

**Build track artifact** (readable M1-M8 status board, republish the same file path
to update): https://claude.ai/code/artifact/c0e6b8ac-6673-4e28-833d-7d85b5f7273a
Source file: `scratchpad/proingest-track.html` in this session's scratchpad; if that
is gone, rebuild from PROGRESS.md and docs/OPEN_QUESTIONS.md.

## Modules built so far

| module | what it owns |
|---|---|
| `core/naming.py` | every output name, both directions; `next_version` |
| `core/frames.py` | integer frame math, timecode, In/Out input grammar |
| `core/models.py` | Batch, Turnover, ShotRow, MediaInfo, AudioInfo, FrameRate, QCResult |
| `core/ffmpeg.py` | the only place anything shells out; tool lookup, ffprobe |
| `core/media.py` | DirectoryIndex, sequence detection, path remap, probe cache |
| `core/exr.py` | EXR header reading (writing is M3) |
| `core/timeline.py` | OTIO and EDL loading, audio association |
| `core/scan.py` | turnover folder -> Turnover + ShotRows |
| `core/batchfile.py` | `.pibatch` save/load, backup, filesystem reconciliation |
| `core/qc.py` | rule registry; QC-025, QC-026, QC-043 so far |
| `__main__.py` | `proingest scan` CLI |

## Current milestone: M1 Core -- COMPLETE (348 tests)

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

## Next: M2 naming and planning

`core/planner.py`: ShotRow -> list[DeliverableJob] from the type table in
NAMING_SPEC section 2, version resolved at plan time, delivery layout from section 5.
naming.py already provides the name building, output parsing and next_version that
M2 needs.

## Blockers

- **OQ-17, colour space. Blocks M3, nothing earlier.** The shooters' spec PDF says
  `Render Color Space: sRGB`; COLOR_AND_FORMAT section 1 assumes scene linear. If the
  delivered EXRs are display-referred, the reference encode double-applies the sRGB
  curve and every ref mp4 and the stringout come out washed out. Raw EXR output is a
  straight pixel copy and is unaffected either way. Resolve by inspecting real
  delivered media alongside OQ-3, not by re-reading the PDF.
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
