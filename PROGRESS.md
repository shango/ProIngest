# Implementation progress

Durable handoff record. Updated after each chunk so work can resume from disk.

## Current milestone: M1 Core

Goal (PRD section 9): OTIO parse, clip name parse, media resolution, ffprobe cache,
shot model, batch JSON, headless CLI `proingest scan <folder>`, tests.

| chunk | module | state |
|---|---|---|
| M1.1 | scaffolding: pyproject, venv, package skeleton | done |
| M1.2 | `core/naming.py` + `tests/test_naming.py` | in progress |
| M1.3 | `core/frames.py` + `tests/test_frames.py` | todo |
| M1.4 | `core/models.py` | todo |
| M1.5 | `core/ffmpeg.py`, `core/media.py` + tests | todo |
| M1.6 | `core/timeline.py` + tests | todo |
| M1.7 | `core/batchfile.py` + tests | todo |
| M1.8 | `__main__.py` scan CLI | todo |
| M1.9 | `tests/fixtures/media.py` synthetic media | todo |

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

## Blockers

- OQ-17 (color space, PDF says sRGB render space vs docs assuming scene linear)
  blocks M3 ref encoding, not M1.
