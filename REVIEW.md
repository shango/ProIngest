# Code review, 2026-09-13

Phase 1 audit of the whole repo. No code was changed. Every finding below was checked against
the code at the cited line, and every bug marked **reproduced** was triggered against the `.venv`
interpreter. Findings are numbered so phase 2 can refer to them.

## 0. Baseline

| item | result |
|---|---|
| Layout | `proingest/core` (17 modules, no Qt), `proingest/ui` (17 modules), `proingest/__main__.py` CLI, `build/fetch_ffmpeg.py` |
| Entry points | `proingest = proingest.__main__:main` (scan / qc / run subcommands, or the UI with none) |
| Tests | `pytest tests/ -q`: **1536 passed** in 66 s (Python 3.12.3, ffmpeg from the distro) |
| Coverage | not configured; `pytest-cov` and `coverage` are not installed |
| `ruff check .` | clean (rules E, F, I, B, UP, SIM, RUF) |
| `mypy --strict proingest tests` | clean, 77 files |
| `ruff format --check .` | **54 of 93 files would be reformatted** (1544 changed lines). Not enforced in CI, so this is style only. See H2 |
| pyright, bandit, vulture, pip-audit | not installed |
| Dependencies | eight runtime, three dev, all lower-bound only; no lock file. See H1 |
| Source size | 13.4 k lines of package code, 15 k of tests |

Ground rules from `CLAUDE.md` that I checked mechanically and found honoured: core imports no Qt;
ffmpeg and ffprobe are only invoked from `core/ffmpeg.py`; subprocess use is list-argv with
timeouts and checked return codes; no `shell=True`, `eval`, `pickle.load` or hardcoded secret
anywhere; no mutable default arguments; deliverable writes go through a `.part` temp name and
`replace`; `clf.py` does no XML parsing of its own (the file goes straight to OCIO), so there is
no XXE surface in Python.

Long functions for reference (the only ones over 60 lines): `settings_form.sections` 184 lines
(a declarative table, fine), `ffmpeg.encode_command` 99, `scan.scan_turnover` 75,
`main_window.run_batch` 74, `__main__._run` 69, `render.execute` 65, `media.probe` 63.

---

## 1. Bugs and latent errors

### Medium

**B1. Packed 8 bit pixel formats are read as 12, 21 or 422 bit.** `proingest/core/qc.py:229-238`.
`bit_depth` strips trailing digits, so `nv12` gives 12, `nv21` gives 21, `uyvy422` and `yuyv422`
give 422 and `rgb0` gives 0. **Reproduced.** An 8 bit `nv12` or `uyvy422` source therefore gets
QC-021 (warning) instead of QC-020 (error), and `rgb0` reports "0 bit". Fix: add the packed
names (`nv12`, `nv21`, `nv16`, `nv24`, `yuyv422`, `uyvy422`, `yvyu422`, `rgb0`, `bgr0`, `0rgb`,
`0bgr`) to `_EIGHT_BIT_NAMES`. Risk: low. Add a parametrised test.

**B2. The post-run name reparse ignores the configured show pattern.**
`proingest/core/render.py:686` calls `qc.apply_phase_b(batch)` with the default pattern, and
`ui/main_window.py:906` and `__main__.py:223` call `apply_results` with no pattern. The window
scans and plans with `settings_form.show_pattern_of(self._settings)` (`main_window.py:648, 821`).
On a custom show pattern every delivered name then fails QC-151 with "does not parse as a delivery
name" as a batch error. No test runs a batch under a non-default pattern. Fix: add a
`show_pattern` parameter to `render.apply_results` and thread it from both callers. Risk: low.

**B3. Closing the window mid-run drops the run's results.** `ui/runner.py:341-357` and
`ui/main_window.py:1329-1347`. `shutdown` cancels and waits for the thread, but the worker's
answer arrives via a queued `done` signal, so `_collect` and the window's `_run_finished`
(`apply_results`, autosave, reports) never execute. Deliverables that finished before Stop exist
on disk but are not recorded in the batch; the next run only survives because
`planner.resolve_version` re-reads the disk. If the 120 s wait times out nothing terminates the
process pool. Fix (minimal): in `closeEvent`, when `runner.busy`, cancel and keep the window open
until `finished` fires, then close. Risk: medium. Unsure of intent: the docstring accepts the
wait but does not mention the results.

**B4. A below-origin In or Out crashes the shot list's `data()`.** `core/frames.py:176-179`,
reached from `ui/shot_model.py:576, 585` and `ui/metadata.py:266`. `source_frame_to_timecode`
computes `origin_timecode + (frame - origin_frame)` and `frames_to_timecode` raises `ValueError`
on a negative total. The model deliberately stores an out-of-range frame ("stored and then
reported, not refused") and then renders it. **Reproduced**: frame 1000 against an origin of
1001 with timecode 0 raises. Media with no embedded timecode (origin collapses to 0 in
`models.py:532`) is exactly the case. Fix: return a sentinel such as `"--:--:--:--"` from
`source_frame_to_timecode` when the total is negative; keep `frames_to_timecode` strict.
Risk: low. Unsure which rendering the UI spec wants.

**B5. A cell edit after Settings Apply re-judges the row with the old thresholds.**
`ui/main_window.py:518-525` writes the new rules onto the batch and refreshes, but
`ShotListModel._rules` (`ui/shot_model.py:326, 337`) is only assigned in `set_batch`, and
`_committed` (`shot_model.py:753`) uses the cached value. The existing Apply test never edits a
cell afterwards. Fix: drop the cache and call `qc.settings_for(self._batch)` in `_committed`.
Risk: low.

**B6. OTIO clip times are not rescaled to the timeline rate.** `core/timeline.py:200-203`
takes `round(t.value)` of each `RationalTime` at whatever rate the clip carries, and
`_timeline_rate` (`timeline.py:232-237`) consults `duration()` before `global_start_time`.
**Reproduced** with otio 0.18.1: a 48 fps clip on a 24 fps timeline gives `record_start=48`
instead of 24, and the rate resolves to 48. Resolve conforms clips to the timeline rate so this
may never occur, but it contradicts the "RationalTime at the boundary" rule. Fix: resolve the
rate first (prefer `global_start_time.rate`), then `round(t.rescaled_to(rate).value)`.
Risk: medium (touches every frame number the scan produces). Unsure of intent.

### Low

**B7. Audio paths from the timeline are never remapped.** `core/scan.py:404` uses
`url_to_path` directly while the picture path at `scan.py:280-281` goes through
`media_module.remap(..., settings.path_map)`. On a mapped mount the audio silently fails
`is_file()` and the row gets neither audio nor QC-042. No scan test uses a `path_map`. Fix: pass
`settings` into `_attach_audio` and remap. Risk: low.

**B8. `read_header` decodes the whole EXR frame and never closes the file.**
`core/exr.py:139-147`. `OpenEXR.File(str(path))` defaults to reading pixels (confirmed on the
pinned 3.4.15 binding) and the handle is not closed; `media.probe` calls it twice per sequence
(`media.py:398, 415`). Also `next(iter(part.channels.values()))` at line 147 is outside the
`try`, so a part with no channels raises bare `StopIteration` past `media._exr_stated_rate`.
Fix: `with OpenEXR.File(...)`, move lines 145-147 inside the `try`, and read the header once in
`probe`. Risk: low.

**B9. Wrong-typed settings values abort launch.** `core/settings.py:151-179`. `load` only
guards `json.loads`; `from_dict` then does `int(...)`, `dict(...)` and a list comprehension.
**Reproduced**: `{"workers": "lots"}`, `{"path_map": [1, 2]}` and `{"metadata_collapsed": 5}`
all escape `load()`, against the module contract "a bad settings file is replaced, never raised
on". Fix: wrap `from_dict` in the same `except` and defaults path as line 193-195. Risk: low.

**B10. Malformed batch files escape `BatchFileError`.** `core/batchfile.py:48-55`. `OSError`
from `read_text`, a top-level list (**reproduced**, `AttributeError`) and `"rows": 5`
(`TypeError`) are not converted. Fix: catch `OSError`, check `isinstance(data, dict)`, add
`TypeError` to the clause. Risk: low.

**B11. Malformed base64 in the settings file prevents launch.** `ui/main_window.py:1317-1320`.
`b64decode` raises `binascii.Error` (a `ValueError`); this runs in `__init__`. The docstring's
"refused by Qt rather than raising" is true of `restoreGeometry`, not of the decode.
**Reproduced**. Fix: `try/except ValueError` around each decode. Risk: low.

**B12. `new_batch` bypasses `_app_rules`.** `ui/main_window.py:455-456` copies
`self._settings.rules` verbatim; `set_batch` then calls `qc.settings_for`, which raises
`ValueError` on an unknown key, inside a slot (swallowed). `_app_rules()` at line 535-546 exists
for exactly this. Fix: use `self._app_rules().to_dict()`. Risk: low.

**B13. Timeline start in the metadata pane is formatted at a hardcoded 24 fps.**
`ui/metadata.py:390-392` while every other timecode in the pane uses the project rate.
Fix: thread the rate through `turnover_fields` (callers at `main_window.py:1219` and
`metadata.py:441`). Risk: low-medium (signature change).

**B14. The "no media" reason in the pane looks at the wrong rule ID.** `ui/metadata.py:192`
matches `("QC-011", "QC-012")`, but QC-011 is the duplicate-name warning and the two no-media
errors are QC-012 and QC-013 (`scan.py:298, 309`). QC-013 rows show a bare "not resolved".
`tests/fixtures/batches.py:100` also fabricates QC-011 as an error. Fix: `("QC-012", "QC-013")`
and correct the fixture. Risk: low.

**B15. The CLI hides row-scope pre-flight errors.** `__main__.py:129-141` prints only batch
and turnover QC, but QC-009/019/022/039 land on `row.qc` (`qc.py:1133-1136`) and
`planner.plannable_identity` silently drops those rows, so `proingest run` can report fewer
shots than expected with no reason. Fix: also print row errors. Risk: low.

**B16. CLI exception coverage.** `__main__.py:109-113` catches `(OSError, ValueError)` for
rule overrides but `RuleSettings.from_dict` raises `TypeError` for `{"target_resolution": 3840}`
(the window at `main_window.py:544` catches both). `__main__.py:222-225` leaves
`render.execute`, `batchfile.backup` and `batchfile.save` uncaught. `__main__.py:70` sets the
`-v` level and then `app.run` reconfigures logging at the default, so `proingest -v` with no
subcommand ignores the flag. Fix: add `TypeError`, wrap the run's save in the same `error:` /
exit 2 path, and pass the level into `app.run`. Risk: low.

**B17. `check_free_space` can raise out of pre-flight.** `qc.py:1058-1062` and `1027-1029`.
`shutil.disk_usage` and `Path.exists` are unguarded; on a network mount a `PermissionError`
escapes `preflight` into the Run button's slot. Fix: `except OSError` returning a QC-062/063
result. Risk: low.

**B18. `_check_numbering` edge cases.** `qc.py:1251-1264`. `expected[0]` raises `IndexError`
when `frame_count == 0` but files are present, and a name that parses with `parsed.frame is None`
is in neither `numbers` nor `unparsed`. Fix: guard the empty case, treat `frame is None` as
unparsed. Risk: low.

**B19. `count_frames` does not guard its JSON parse.** `core/ffmpeg.py:187`, unlike
`probe_raw` at 159-162; callers catch `FFprobeError` only. Fix: parse the same way. Risk: low.

**B20. `_render_sequence` never lets the decoder finish.** `core/render.py:239` zips
`output_frames()` first, so the generator is never advanced past its last yield; `stream.close()`
then kills an ffmpeg that was about to exit and skips the exit-code check at `ffmpeg.py:400`.
Harmless today (every frame was counted) but a late ffmpeg error is discarded and that branch is
dead for this caller. Fix: iterate the stream and stop at `frame_count`. Risk: low.

**B21. Spreadsheets are not written atomically.** `core/exports.py:288, 386` call
`book.save(path)` directly under the delivery root. Fix: save to a `.part` name and `replace`.
Risk: low. Unsure whether reports count as deliverables under the rule.

**B22. Unsupported OTIO rates escape as bare `ValueError`.** `core/timeline.py:236` is
outside the `try` at 140-151, so a rate `from_float` does not know bypasses `TimelineError` and
QC-002. **Reproduced** with 48000/1001. Relatedly `models.py:61-63`: `from_float(119.88)` raises
because the absolute tolerance `1e-4` is too tight for 120000/1001 (**reproduced**), so the 120
entry is dead. Fix: wrap in `TimelineError`; use a relative tolerance. Risk: low.

**B23. EDL error classification and drop-frame detection.** `core/timeline.py:249-251`
returns True for any `EDLParseError` by class name, so a syntactically broken EDL is reported as
a rate mismatch, against the function's own docstring. `timeline.py:254-259` detects drop-frame
by `;` only; the adapter ignores `FCM:` lines (verified), so `FCM: DROP FRAME` with colon
timecodes passes silently. No test covers `EdlTimecodeError`. Fix: match the two adapter
messages that are about rate; also honour `FCM: DROP`. Risk: low.

**B24. Float frame math in `AudioInfo.duration_in_frames`.** `core/models.py:236-240`
rounds `samples * rate.as_float() / sample_rate`; used by QC at `qc.py:537`. Fix:
`round(Fraction(samples * rate.numerator, sample_rate * rate.denominator))`. Risk: low.

**B25. UI slots that can raise on I/O.** `ui/main_window.py:473` `batchfile.backup` is
outside the `try` that guards `load`; a read-only folder aborts Open with no dialog. Fix:
catch `OSError`. Risk: low. Unsure whether Open should proceed without a backup.

**B26. Minor UI state faults.** `ui/shot_list.py:493-499` `select_row` clears the proxy
filter but the search box keeps its text. `ui/shot_model.py:206` counts `skipped` (written only
on Stop) as DONE, so a stopped row gets a green dot beside "0/2". `ui/main_window.py:559-569`
shows "never been saved" when a flush to an existing path failed. `ui/main_window.py:1112-1118`
`ask_turnover` maps by `names.index`, so two folders sharing a basename resolve to the first.
`ui/metadata.py:464-468` `value or MIXED` makes rows that all agree on `""` read "mixed".
Each fix is a line or two. Risk: low. Unsure of intent on `skipped` and on `or MIXED`.

**B27. `autosave.watch` discards a batch whose flush failed.** `ui/autosave.py:174-183`.
Only reachable through the API (the window asks first via `_may_abandon_current`), so a
docstring note or a `bool` return from `flush` is enough. Risk: low.

---

## 2. Structural

**S1. `MainWindow` is a 1160 line god class.** `ui/main_window.py:183-1347` owns batch
file, scanning, ingest, run orchestration, dialogs and window state. The run block (768-948) and
ingest block (700-764) are the natural extractions. Risk: medium, tests drive via actions so
mostly survive. Defer unless the user wants it.

**S2. Batch logic living in the UI.** "A run is blocked" is decided as
`[r for r in batch.qc if r.severity == "error"]` in both `main_window.py:800` and
`__main__.py:138`; belongs in core beside `qc.blocked_turnovers`. `main_window.py:631-641`
`_next_turnover_id` re-implements `scan_batch`'s numbering (its docstring says "counted past the
highest in use" but it starts at `len(used)+1`, so `{t1, t5}` gives `t3`). Fix: one
`qc.blocking_results(batch)` and a core `next_turnover_id`. Risk: low.

**S3. `settings.py` imports `render` for one constant.** `core/settings.py:26` pulls
numpy, OCIO, multiprocessing and the whole render chain into anything that reads settings. No
cycle today, but it is the one edge that would make one. Fix: move `DEFAULT_WORKERS` to
`models.py`. Risk: low.

**S4. Stat storms on the network mount.** `core/media.py:176-180` `index_directory` does
`is_file()` then `stat()` per entry while its docstring says one stat; `core/timeline.py:119-124`
and `core/qc.py:961-968` (`find_lens_grid_folder`) both `sorted(folder.rglob("*"))` and stat
every entry, including every EXR frame, and `rglob` raises `OSError` on an unreadable folder
which escapes `preflight`. `core/scan.py:411` stats `audio_path` per row outside the index. Fix:
one `stat()` with `S_ISREG`; suffix-filter before `is_file()`; catch `OSError`. Risk: low.
Unsure whether "any depth" for the lens grid is a requirement (a test pins it).

**S5. The `row_edited` signal is wired four times.** `ui/main_window.py:363, 367, 1202,
1287`; two of the lambdas are exactly `_show_results`, whose docstring exists so nobody updates
one surface without the other. Fix: connect once. Risk: low.

**S6. Field lists duplicated by hand.** `core/models.py:605-628` re-lists `ShotIdentity`'s
six fields; `core/settings.py:152-165` `known` duplicates `to_dict`'s keys. A new field breaks
the round trip silently. Fix: derive from `dataclasses.fields`. Risk: low.

**S7. Two float boundaries that disagree.** `core/render.py:432` `_audio_skip` divides
through `rate.as_float()` while `core/ffmpeg.py:610` `_seconds` keeps the exact fraction and
claims to be "the only place that division happens". Fix: reuse `_seconds`. Risk: low.

**S8. Logged commands do not reproduce.** `core/ffmpeg.py:129, 382` log with
`" ".join(command)`; the module promises paste-and-reproduce, and paths with spaces are expected
(`test_media.py:511`). Fix: `shlex.join`. Risk: low, log text only.

**S9. UI-thread I/O, acknowledged.** `batchfile.load(reconcile=True)`, `qc.preflight`,
`planner.plan_batch`, `_write_reports` and `_camdata` all run on the UI thread against a slow
mount. The docstrings own the trade-off. Noted, not a defect.

---

## 3. Code smells

**C1. Phase A result scaffolding.** `qc.py` builds
`[QCResult("QC-nnn", sev, "row", f"...")]` by hand in about 35 places (256-273, 286-293,
309-316, 345-363, 383-390, 399-415, 465-473, 509-517, 547-555, 571-579, 612-619 and more).
Phase B already has `_failure`. A `_row(rule_id, severity, message)` helper removes about 120
lines and makes the triple greppable. Risk: low, tests assert on IDs.

**C2. `qc.py:1204-1211`** rebuilds the verifier dict per call with a two-lookup default;
`qc.py:1504-1532` `_verify_audio` returns from inside a `for` and reads the WAV suffix twice.
Risk: low.

**C3. Per-cell recomputation in the shot model.** `ui/shot_model.py:508` computes
`state_for(row)` (two walks of `row.qc`, one of deliverables) for every role of every cell, used
by three; `shot_model.py:540-557` builds a dict of 15 closures per `data()` call. With
`refresh_rows` at 5 Hz on 100 rows this is thousands of wasted calls a second. Fix: compute
`state` inside the three branches; `match column`. Risk: low.

**C4. Palette literals duplicated.** `#cf5a52`, `#cf9a3a`, `#868d9a`, `#5c626d` appear in
`shot_model.py:100-123`, `shot_list.py:64, 68`, `issues.py:54-58`, `log_view.py:86-90`.
Fix: one `ui/palette.py`. Risk: low.

**C5. Encoding not stated.** `core/settings.py:190, 211`, `core/clf.py:485`, `ui/app.py:30`
read or write without `encoding="utf-8"` while `batchfile.py` passes it. Risk: low.

**C6. `render.py:287`** stamps a 24 fps timecode when the job has no rate, where
`_render_reference` at 366 refuses the same case with `RenderError`. Unsure of intent.

**C7. Casefold asymmetry.** `core/clf.py:289` `_event_by_reel` compares case-sensitively
while the primary match at 261 casefolds, for the reason its docstring gives. Risk: low.

**C8. Minor.** `core/naming.py:181-187` `bts()` does not check `identity.aux == "BTS"` while
`aux_still_exr` rejects BTS (**reproduced**). `core/batchfile.py:36` `with_suffix` replaces an
existing suffix (`melt.day1` becomes `melt.pibatch`). `core/models.py:206` `start_timecode` is
the only uncoerced field; `models.py:758` returns the live `settings_overrides` dict.
`core/media.py:267` function-local import with no cycle. `core/planner.py:154` `temp: bool`
flag. `ui/issues.py:121-122` connects both `itemActivated` and `itemDoubleClicked` to the same
slot, so a double-click fires `select_row` twice. `ui/shot_list.py:252` recurses with a
column-SHOT parent index. `ui/log_view.py:228` installs a root handler with no teardown but
`detach`. `ui/settings_dialog.py:164` leaves an unknown log level on "Debug" rather than the
default. `ui/scanner.py:139` copies the cache dict but shares the `MediaInfo` values, against
its docstring's "handed over rather than shared".

---

## 4. Style, docs and dead code

- **Rule violation, intent unclear.** `core/exports.py:335` writes an em dash into the tracker
  cell (`tests/test_exports.py:920` asserts it). CLAUDE.md and the global rule forbid em dashes in
  any file; the comment says it mirrors the studio sheet. Needs a decision: keep with a why
  comment, or use `-`.
- **Stale docs.** `README.md` says "There is no user interface yet". `core/qc.py:10-13` says
  QC-053 is "deliberately not implemented yet" but `check_camdata` at 937-958 implements it.
  `__main__.py:172-173` says a run without ingest "still produces every deliverable, ungraded";
  QC-008 now holds those rows back and `test_cli.py:306-321` asserts nothing is written.
  `tests/test_cli.py:176` "reference encodes are M3.5, so those jobs fail" is stale.
- **QC-018 is documented but raised nowhere** (`docs/QC_RULES.md:38`; no hit in `proingest/`
  or `tests/`). Every other doc ID is either raised or marked RETIRED. Either build it or mark it
  unbuilt like QC-024 and QC-061.
- **Docstrings that contradict the code.** `qc.py:479-485` "only the plate is asked" (QC-041
  fires on any row); `qc.py:1076-1093` `blocked_turnovers` says pre-flight but reads all
  turnover errors (probably right, doc is wrong); `core/camdata.py:53-54` says
  `UnicodeDecodeError` travels but line 56 uses `errors="replace"`; `ui/main_window.py:1235`
  catches the same impossible error; `render.py:432` vs the `_seconds` claim (S7).
- **Dead code.** `ui/shot_list.py:601-603` `display_mode_of` has no callers.
- **Public functions without docstrings** (all are typed): `__main__.main`,
  `frames.source_frame_for`, `metadata.turnover_for`, and the naming builders
  `raw_sequence_dir`, `raw_frame`, `ref_mp4`, `audio_wav`, `hdri_exr`, `camdata`, `bts`,
  `lens_grid_png`, `shot_dir`, `turnovers_dir`, `reports_dir` (a section comment covers them as a
  group). Also `FrameRate.as_float`, `InOut.duration`, `ShotRow.errors`/`warnings` and the
  `to_dict`/`from_dict` pairs.
- **Small inconsistencies.** `exports.py:189` writes `23.976023976023978` where
  `_tracker_fps` formats `23.976`; `shot_model.py:355` vs `387` use `QModelIndex()` and
  `NO_PARENT` for the same thing; `log_view.py:299` clipboard call unguarded where
  `metadata_pane.py:338` guards it; `settings_form.py:243-250` help promises a binary can be
  chosen but the chooser is folder-only; `qc.py:1141-1143` three blank lines.

---

## 5. Tests

**Tautological or under-asserting** (each a one-line fix):
- `tests/test_shot_model.py:97` `assert titles[IN], titles[OUT]` uses the Out title as the
  message; Out is never checked.
- `tests/test_shot_model.py:403-408` asserts `"1 shot" in header`, which `"1 shots"` satisfies.
- `tests/test_timeline.py:157` `assert index >= 0` from `enumerate`.
- `tests/test_ui_shell.py:318-319` `not isVisible()` is always true for an unshown window;
  use `isHidden()`.
- `tests/test_scanner.py:343-350` and `tests/test_runner.py:704-711` `not busy or
  pump_until(not busy)` passes whether or not `shutdown` waited; assert `thread.isFinished()`.
- `tests/test_autosave.py:41-47` proves neither restart nor queue; count `saved` emissions.
- `tests/test_cli.py:170-187` never asserts `main()`'s return value.
- `tests/test_settings.py:33-39` "is atomic" only checks that no `.part` remains.

**Brittle or coupled to internals:** `tests/test_shot_list.py:203-234` encodes the delegate's
3/2 pixel padding as magic numbers; `tests/test_ui_shell.py:1520-1525` pokes
`window.scanner._thread` to fake `busy`, and many tests call underscore methods directly.
`tests/fixtures/batches.py:485-568` use `setattr(**kwargs)`, so a misspelled field silently
passes on the default (`dataclasses.replace` would raise).

**Suite hygiene:** `tests/test_ui_shell.py:130-133` never detaches the window's log handler,
so about 150 `BufferHandler`s accumulate on the root logger across the session
(`test_log_view.py:27-32` gets it right). `tests/test_qc.py:1174-1182` skips itself when the local
ffmpeg writes a leading moov, so QC-115's failure branch may never run in CI.

**Gaps in core logic** (add alongside the fix for the matching bug):
- scan with a `path_map` (B7); a below-origin frame through the model (B4); a run under a
  non-default show pattern (B2); an edit after Settings Apply (B5); wrong-typed settings (B9);
  non-object batch file (B10); malformed base64 (B11); `EdlTimecodeError` and drop-frame EDL
  (B23); packed pixel formats (B1).
- `frames.timecode_frames_for` has no direct test; `AudioInfo` has no round-trip test;
  `ShotRow.edit_context`'s `media is None` branches; `parse_output_name` with a custom pattern;
  `ffmpeg.decode_frames` timeout and non-zero exit; `render.execute` with a raising
  `on_progress` or a dead worker; `OWNED_ROW_RULES` and `OWNED_PREFLIGHT_RULES` pinned against
  the IDs their registries raise, the way `TestDeliverableRuleTable` does.

---

## 6. Hygiene

**H1. No lock file.** All eleven dependencies are lower-bound only and CI installs whatever
resolves that day (the workflow comments say so). A `uv lock` committed and used in CI makes a
green run reproducible. Not blocking; the user chose uv without a lock so far. Ask before adding.

**H2. `ruff format` is not enforced** and 54 files drift from it. Either add
`ruff format --check` to CI and reformat once (a large but mechanical diff), or leave it. Ask.

**H3. Tracked files.** `build-track.html` (133 KB, a published artifact copy) and three
studio source documents (`.csv`, `.pdf`) are tracked at the root and in `docs/`. The README
explains the source documents; the artifact copy is a choice the handoff describes. Noted only.

**H4. `otio-cmx3600-adapter` is never imported by name.** It is loaded through otio's plugin
registry, so it is used, but nothing fails loudly if it is missing until an `.edl` is opened.
A one-line import check at startup or in `timeline.load` would give a clear error. Low priority.

Nothing else: no secrets, no `.gitignore` gaps found, the `Zone.Identifier` sidecar in `docs/`
is ignored and untracked.

---

## 7. Proposed phase 2 order

1. B1, B2, B5, B7, B9, B10, B11, B12, B14, B16, B17, B18, B19, B22 with a test each (all
   low risk, mechanical).
2. B4, B8, B13, B21, B24 (low risk, small design choices called out above).
3. B3, B6 only with explicit approval (medium risk, behaviour visible to the user).
4. S3, S5, S6, S7, S8, C1, C5, C7, the stale docs, the dead function, the tautological tests.
5. S1, S2, S4, C3, C4 deferred unless asked; they are refactors, not fixes.

Decisions needed from you before phase 2: the em dash in the tracker export, H1 and H2, and
whether B3 and B6 are in scope.
