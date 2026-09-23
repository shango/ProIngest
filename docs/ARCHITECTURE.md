# Architecture

## Package layout

Rewritten 2026-09-23 from the files on disk (review 2026-09-23, section 3). There is no
`core/timeline.py`, `core/camdata.py`, `ui/delegates.py`, `ui/docks.py`, `ui/workers.py`,
`ui/platform_mac.py` or `ui/color_session.py`: the conform and the grade are read from the EDL in
the turnover folder at scan, and there is no timeline input and no separate colour session step.

```
proingest/
  __main__.py            # no subcommand launches the UI; `scan`, `run` and `qc` drive core headless
  core/                  # no Qt anywhere under here
    models.py            # FrameRate, QCResult, MediaInfo, AudioInfo, InOut, CDL, Deliverable, ShotRow,
                         #   Turnover, Batch: dataclasses with explicit to_dict/from_dict, batch schema v2
    batchfile.py         # .pibatch load/save written temp-then-rename, .bak on open, and status
                         #   reconciled against the filesystem so the display never lies after a crash
    settings.py          # AppSettings: defaults, load/save as JSON; the path is handed in by ui/paths.py
    metacsv.py           # Ben's metadata CSV: File Name, Shot, Shot Type, Gamma Notes, Color Space Notes.
                         #   Identity and encoding; QC-010, QC-065, and the ignored clips for QC-064
    clf.py               # Ben's EDL: its own CMX 3600 parser, the approved In/Out and the CDL per event,
                         #   an event matched to a row by source timecode inside the file (QC-066, QC-067),
                         #   and ShotColor, the per-row colour chain
    color.py             # OpenColorIO from the pinned built-in ACES config: input transform table,
                         #   into and out of ACEScct, the CDL transform, the output transform, the view LUT
    naming.py            # ShotIdentity from Shot + Shot Type, every output name, the delivery layout,
                         #   parse_output_name (QC-151) and next_version
    media.py             # the turnover folder indexed once (DirectoryIndex), image sequence detection,
                         #   ffprobe into MediaInfo, the probe cache, audio probing
    frames.py            # integer frame math, timecode conversion, In/Out input parsing
    scan.py              # turnover folder -> Turnover + ShotRows: one EDL and one CSV (QC-001), rows from
                         #   CSV rows, media by File Name, the EDL's cut and CDL, audio by name;
                         #   carry_over keeps the editor's edits across a re-scan by File Name
    qc.py                # the rule registry: row and batch rules re-run after every edit, the pre-flight
                         #   that touches the disk, must_fix (the run gate), phase B verification
    planner.py           # ShotRow -> DeliverableJobs from the type table, version resolved at plan time,
                         #   QC-060 and QC-061
    ffmpeg.py            # the only place ffmpeg and ffprobe run: binary resolution, every command logged,
                         #   decode to float, reference encode through one lut3d, audio extraction
    exr.py               # OpenEXR read and write: DWAA, half float, timeCode, provenance attributes
    resize.py            # antialiased Lanczos downscale and letterboxing for the EXR path, plain numpy
    render.py            # one job to one deliverable: written to its .part, verified there, renamed on
                         #   pass; the spawn process pool, progress, cancellation; apply_results
    exports.py           # openpyxl: the QC log (three sheets) and the shot tracker (one line per shot code)
    logsetup.py          # the rotating log file, and a worker process's log lines routed back into it
  ui/                    # a thin layer over core
    app.py               # QApplication, organisation names, theme load, the window
    main_window.py       # menus, toolbar, docks, empty states, turnover right-click (Re-scan, New Folder
                         #   Location), the locks of D15
    batch_bar.py         # batch name, delivery root, the Frames / Source TC / Record TC toggle, search
    shot_model.py        # QAbstractItemModel over Batch, two levels; columns, row states, the four edits
    shot_list.py         # the view: two-line cells, frozen columns, search filter, Tab across edits
    metadata.py          # what the metadata pane says, worked out without a widget (UI_SPEC section 12)
    metadata_pane.py     # the read-only right dock that draws it
    issues.py            # the Issues dock: one row per QC result
    log_view.py          # the Log tab over a bounded buffer of log records
    deliverables.py      # the Deliverables tab for the selected rows
    run_strip.py         # the strip above the list: bar and line during a run, banner after
    run_controller.py    # one Run: pre-flight, the must-fix gate, plan, pool, results, exports
    runner.py            # core.render.execute on a worker QThread, progress folded for a timer
    scanner.py           # core.scan on a worker QThread, results back as signals
    background.py        # a run's disk work (pre-flight, plan, exports) on a worker QThread, under the lock
    autosave.py          # debounced batch writes
    settings_form.py     # what the Settings page offers, as data
    settings_dialog.py   # the Settings page that draws it
    toolbar_help.py      # each button's tooltip, shared verbatim with the user guide
    paths.py             # QStandardPaths: settings and log locations
    theme.qss
  resources/ffmpeg/      # the bundled binaries, untracked (build/fetch_ffmpeg.py)
tests/
  fixtures/              # synthetic media generated with ffmpeg, never committed; names, colour, batches
  test_<module>.py       # broadly one per module, plus test_guide.py for the user guide
build/
  build.py bundle.py proingest.spec # PyInstaller .app, then the dmg with hdiutil; the spec is a shim
  entry.py smoke_test.py            # the frozen entry point, and a run through a whole turnover
  screenshots.py                    # the user guide's pictures (M9.4)
  fetch_ffmpeg.py ffmpeg.lock.json  # the pinned binaries: download, or --from a folder
  mac_build.sh                      # a fresh Mac clone to a dmg
```

## Data flow

1. **Scan** (`scan.scan_turnover`, on `ui/scanner.py`'s thread). The folder must hold exactly one
   `.edl` and one `.csv` (QC-001). `metacsv.read` gives one `MetaRow` per CSV row carrying a
   `Shot Type`; rows without one are ignored and counted (QC-064). `clf.load_session` reads the
   EDL's events and CDLs.
2. `media.index_directory` walks the folder once; each row's media is the one file or sequence
   whose name matches its `File Name` (QC-012, QC-013), probed through `media.probe_cached`.
3. Each row is matched to its EDL event by source timecode inside the file's range, and takes
   the approved In/Out (`ShotRow.approved`, `snapshot` and `current` alike) and the CDL. Audio is
   found by name. `qc.apply_row_rules` fills `row.qc`, and `qc.apply_batch_rules` adds the rules
   that need every row (QC-011).
4. A **re-scan** of a turnover already in the batch runs the same scan and then `scan.carry_over`,
   which keeps the editor's trims, shot code corrections, skips, notes and delivered state by
   `File Name`, and raises QC-070 when the EDL or CSV changed.
5. UI edits mutate `ShotRow.current/shot_code_override/notes/skipped`, then the row's rules re-run.
6. **Run** (`ui/run_controller.py`). `qc.preflight` (on `ui/background.py`'s thread) checks the
   disk; `qc.must_fix` lists every error outside a skipped row, and any at all stops the run.
7. `planner.plan_batch` (background thread) produces `DeliverableJob`s with final and `.part`
   paths, the version resolved against the delivery folder now, not at scan.
8. `render.execute` (on `ui/runner.py`'s thread) runs the jobs in a spawn `ProcessPoolExecutor`.
   Each worker renders to the `.part`, runs `qc.run_phase_b` there, and renames only on pass. The
   plate branch applies the OCIO chain in numpy before the resize; the view branch hands ffmpeg
   one `lut3d` (COLOR_AND_FORMAT section 1).
9. `render.apply_results` writes the records back onto the rows and runs QC-150 and QC-151.
   `exports.write_qc_log` and `exports.write_shot_tracker` then run on the background thread,
   after a run or on Export.

## Concurrency

- Process pool for jobs (ffmpeg is already multi-threaded; EXR writing is CPU bound in numpy and OpenEXR, so processes not threads).
- One coordinator thread in the UI process drains the progress queue and emits Qt signals.
- Jobs for one row may run in parallel. The EXR 4k and HD passes for one row are separate jobs.
- Cancellation: a shared `multiprocessing.Event`; workers check between frames and terminate the ffmpeg child.

## Batch file

JSON, `schema_version: 2` (`models.SCHEMA_VERSION`; version 1 is refused, D18). Top level: settings overrides, delivery root, turnovers (folder, EDL and CSV paths and their digests, number, date, shooter), rows (full ShotRow including snapshot, approved, edits, qc results, deliverables with status and checksums), probe cache. Written with a temp+rename. On open, a `.bak` copy is made. Loader reconciles deliverable status with the filesystem (does the final name exist) so the display never lies after a crash. There are no `.failed` markers (D11): a file only takes its final name after it passed its checks.

## Testing

- Fixtures generate: a 3840x2160 EXR sequence (300 frames, 24 fps, TC 01:00:00:00), a camera-native H.264 mov of the same, a 48k 16 bit wav, a CMX 3600 `.edl` carrying CDL lines, and a Resolve-shaped metadata CSV (UTF-16, `File Name` / `Shot` / `Shot Type` / `Gamma Notes` / `Color Space Notes`) referencing them.
- Golden tests for every naming example in the shooters' spec.
- Frame-math tests for all four input formats and both TC modes.
- Render tests run at reduced resolution flag for speed but assert real EXR headers, DWAA compression, frame counts, and checksums.
- QC tests: one test per rule ID that constructs the failing condition.

## Third-party

`OpenEXR` (3.2+), `OpenColorIO` (2.4+), `numpy`, `openpyxl`, `PySide6`, `xxhash`, `ffmpeg`/`ffprobe` binaries (bundled). The data model is plain dataclasses. `opentimelineio` is gone: the EDL is parsed in `core/clf.py`, and there is no timeline input. The EXR downscale is plain numpy (`core/resize.py`), so neither `scipy` nor `OpenImageIO` is a dependency. See OQ-7. **OpenImageIO stays out on the EXR write too**: the `OpenEXR` bindings already write AP1 chromaticities, DWAA, timecode and arbitrary named attributes, so OIIO would be a second large dependency inside a 300 MB budget for no capability (COLOR_AND_FORMAT section 1).
