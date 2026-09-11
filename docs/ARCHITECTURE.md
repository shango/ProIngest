# Architecture

## Package layout

```
proingest/
  __main__.py            # launches UI; `proingest scan|run|qc` subcommands for headless use
  core/
    models.py            # Batch, Turnover, ShotRow, Deliverable, QCResult (dataclasses, JSON schema v1)
    timeline.py          # OTIO/EDL load, clip extraction, audio association, path mapping
    naming.py            # parse clip names, build output names, delivery layout, versioning
    media.py             # ffprobe wrapper, sequence detection, probe cache
    frames.py            # integer frame math, TC conversion, input parsing
    scan.py              # turnover folder -> Turnover + ShotRows (data flow steps 1-4)
    planner.py           # ShotRow -> list[DeliverableJob]
    ffmpeg.py            # subprocess wrapper, command builder, progress parsing, hardware encoder detection
    exr.py               # EXR read/write (OpenEXR), DWAA, header checks
    resize.py            # antialiased Lanczos downscale for the EXR path
    color.py             # source color space setting; what each deliverable does about it
    render.py            # job execution, process pool, atomic writes, cancellation
    qc.py                # rule registry, phase A and B checks
    stringout.py         # concat plan and drawtext filter builder
    exports.py           # openpyxl writers for tracker and QC log
    settings.py          # defaults, load/save, validation, platform paths (PACKAGING.md)
    batchfile.py         # .pibatch load/save, backup, migration
  ui/
    app.py               # QApplication, theme load
    main_window.py
    shot_model.py        # QAbstractItemModel over Batch (two-level)
    delegates.py         # In/Out editors, status dot, progress cell
    docks.py             # Issues, Log, Deliverables
    metadata_pane.py     # read-only right pane over the selected row (UI_SPEC section 12)
    settings_dialog.py
    theme.qss
    workers.py           # QThread bridge to core.render, signal plumbing
    platform_mac.py      # the only macOS-specific UI code: Dock tile progress via PyObjC
  resources/             # icons, font, default tracker template
tests/
  fixtures/media.py      # generates synthetic exr/mov/wav with ffmpeg
  test_naming.py test_frames.py test_timeline.py test_planner.py test_qc.py test_render.py
build/
  build.py proingest.spec dmg.py    # PyInstaller .app then create-dmg; Inno Setup returns with v02 Windows
  fetch_ffmpeg.py ffmpeg.lock.json
```

## Data flow

1. `timeline.load(path)` returns `list[ClipRecord]` (name, media url, source range, record range, track, audio candidates).
2. `naming.parse_clip_name` attaches `ShotIdentity` or a QC-010 result.
3. `media.resolve` and `media.probe` fill `MediaInfo`, cached.
4. `frames.derive` computes source frame indices, max available, snapshots.
5. `qc.run_phase_a(batch)` fills `row.qc`. Steps 1 to 4 are orchestrated by `scan.py`, which
   raises only the results discovered while scanning (media missing, ambiguous, unreadable,
   remapped). Rules that are pure functions of the model live in `qc.py` so they re-run after
   every edit.
6. UI edits mutate `ShotRow.in_frame/out_frame/shot_code/notes/skip`, then `qc.run_phase_a_row`.
7. `planner.plan(row, settings, destination)` produces `DeliverableJob`s with final and temp paths, version resolved at plan time (right before render, not at scan).
8. `render.execute(jobs)` runs in a `ProcessPoolExecutor`; each worker runs one job, streams progress via a `multiprocessing.Queue`, and on success calls `qc.run_phase_b(job)`.
9. `exports.write_all(batch)` after run or on demand.

## Concurrency

- Process pool for jobs (ffmpeg is already multi-threaded; EXR writing is CPU bound in numpy and OpenEXR, so processes not threads).
- One coordinator thread in the UI process drains the progress queue and emits Qt signals.
- Jobs for one row may run in parallel. The EXR 4k and HD passes for one row are separate jobs.
- Cancellation: a shared `multiprocessing.Event`; workers check between frames and terminate the ffmpeg child.

## Batch file

JSON, `schema_version: 1`. Top level: settings overrides, delivery root, turnovers (folder, otio path, number, date, shooter), rows (full ShotRow including snapshot, edits, qc results, deliverables with status and checksums), probe cache. Written with a temp+rename. On open, a `.bak` copy is made. Loader reconciles deliverable status with the filesystem (existence and `.failed` markers) so the display never lies after a crash.

## Testing

- Fixture generates: a 3840x2160 EXR sequence (300 frames, 24 fps, TC 01:00:00:00), a ProRes 4444 mov of the same, a 48k 16 bit wav, a small OTIO built with the otio API referencing them.
- Golden tests for every naming example in the shooters' spec.
- Frame-math tests for all four input formats and both TC modes.
- Render tests run at reduced resolution flag for speed but assert real EXR headers, DWAA compression, frame counts, and checksums.
- QC tests: one test per rule ID that constructs the failing condition.

## Third-party

`opentimelineio`, `OpenEXR` (3.2+), `numpy`, `openpyxl`, `PySide6`, `xxhash`, `pydantic` (or dataclasses + `cattrs`), `ffmpeg`/`ffprobe` binaries (bundled). The EXR downscale is plain numpy (`core/resize.py`), so neither `scipy` nor `OpenImageIO` is a dependency. See OQ-7.
