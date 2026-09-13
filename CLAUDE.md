# CLAUDE.md - ProIngest

## What this is
A single-user macOS desktop app (PySide6, Python 3.11+) that ingests VFX shot turnovers. It reads an OpenTimelineIO file exported from DaVinci Resolve, matches timeline clips to media in a turnover folder on a Google Drive mount, lets the VFX editor adjust In/Out per shot, then transcodes and names all deliverables per the studio spec, runs automated QC, and exports spreadsheets.

Read `PROGRESS.md` section 1 first: it is the handoff record, it says what is built, what is next and what was decided, and it is written to be picked up cold. Then `docs/WORKFLOW.md`, which is who does what in twenty lines. Then `PRD.md` and the docs it points to.

The docs are the spec. `PROGRESS.md` is the state. When code and docs disagree, fix one and say which; when `PROGRESS.md` disagrees with either, it is the one that is stale.

**Update `PROGRESS.md` in the same commit as the work it describes.** A handoff written from memory at the end of a session is the thing it exists to prevent.

## Ground rules
- Core logic lives in `proingest/core/` and must not import Qt. The UI in `proingest/ui/` is a thin layer over core. Everything in core must be testable headless.
- No rendering inside the UI thread. Long work runs in a worker process pool and reports progress through queues/signals.
- Frame math is integer only. Never store or compare timecode as floats. Use `opentimelineio.opentime.RationalTime` at the boundary and integers internally.
- Every deliverable is written atomically: render to a temp name in the destination folder, verify, then rename. A crash must never leave a file that looks finished.
- Every check in `docs/QC_RULES.md` has a stable rule ID (e.g. `QC-012`). Log messages, row warnings, and spreadsheet exports reference the ID.
- Output names come only from `proingest/core/naming.py`. No string formatting of filenames anywhere else.
- Settings have sane defaults and are editable in the Settings page. Do not hardcode frame-length limits, handle expectations, or paths.
- ffmpeg and ffprobe are called as subprocesses through `proingest/core/ffmpeg.py`. Never shell out from elsewhere. All commands are logged verbatim so the user can reproduce a render.
- EXR output uses the `OpenEXR` Python bindings (3.2+ numpy API), not ffmpeg. ffmpeg does have an `exr` encoder, but it only offers none/rle/zip1/zip16 compression and cannot write the DWAA the spec requires, nor a `timeCode` header attribute.
- Write tests alongside features. Synthetic test media is generated with ffmpeg in a pytest fixture, never committed.
- macOS on Apple Silicon is the target for v01; Windows moved to v02. Use `pathlib` everywhere. Assume paths may be on a slow network mount; avoid repeated stat calls in loops (scan once, cache).
- Never hardcode a platform path. There is no `G:`, and the Google Drive mount is not detected either: the user points at a source root and a delivery root and both are remembered (OQ-25, `docs/UI_SPEC.md` section 13). Settings and logs go to `~/Library/Application Support/ProIngest` and `~/Library/Logs/ProIngest`. See `docs/PACKAGING.md`.
- CI runs the full suite on an arm64 macOS runner, so most work needs no Mac. If you write something whose behaviour can only be confirmed by a person on a Mac, add a line to `docs/MAC_SESSION.md` **in the same commit**. A checklist assembled later from memory is what that file exists to prevent.

## Style
- Python 3.11, type hints everywhere, `ruff` and `mypy --strict` clean.
- Dataclasses or pydantic for data models; batch files are JSON with a schema version.
- Short functions, explicit names. Comments explain why, not what.
- No em dashes in UI strings or docs.

## Commands
```
uv sync --extra dev          # installs exactly what uv.lock pins; or: pip install -e .[dev]
pytest
ruff check . && ruff format --check . && mypy proingest tests
python -m proingest          # run the app
python build/build.py        # PyInstaller .app + dmg, macOS only (see docs/PACKAGING.md)
```

## Definition of done for a feature
1. Core function with unit tests
2. Wired into UI with a manual test note in the PR description
3. QC rule IDs added to `docs/QC_RULES.md` if new checks were introduced
4. `docs/OPEN_QUESTIONS.md` updated if you had to assume something
