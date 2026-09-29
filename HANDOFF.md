# Handoff, 29 September 2026

**This is a short pointer, not the record.** `PROGRESS.md` section 1 holds the record: one entry
per change, newest first, each saying what was built and how it was verified. If this file
disagrees with `PROGRESS.md` or the docs, they are right and this file is wrong.

## PAUSED HERE (29 Sep 2026) - pick up exactly this

**State:** 0.5.12 is committed and pushed: the reference label is now set on the frames too
(`ffmpeg.reference_label`, a `setparams` step), because 0.5.11's Mac CI (run 36526442199) showed
the bundled ffmpeg 9.0.1 writes no `color_transfer` from `-color_trc` alone. PROGRESS has the
entry. Suite 1787, ruff, format and mypy clean here.

**Next steps, in order:**
1. Watch 0.5.12's CI (`gh run list -R shango/ProIngest --branch qc/source-fidelity`). **The Mac job
   is the real test**: if ffmpeg 9 still writes no transfer, look at `-bsf:v h264_metadata` or the
   mp4 `colr` atom (`-movflags +write_colr`) next. Don't guess; read the CI output.
2. When green, hand over `gh run download <run> -R shango/ProIngest -n ProIngest-macos-arm64 -D
   ~/Downloads/ProIngest-0.5.12` (memory: release-handoff).
3. Things to raise with the user, below (step 5).
4. **DONE at pause: the re-run finished (30/30, stringout 44.9 s, labelled `bt470m`, frames
   checked: graded, burn-ins right) and is in `C:\Users\shann\Downloads\ProIngest-turnover097\`
   (run log CSV, stringout, QC log, tracker). Only re-run if the user asks.** Background:
   **Turnover097 result for the user** (they asked: the log dump with every QC message, then
   the stringout if QC lets it run). A headless re-run was going in the background at pause
   time: scratchpad `t097/step2_run.py` (Accept As Is ticked, 4 workers; the scan is
   `t097/step1_scan.py`; both run with `uv run python <script> <scratch>/t097 [workers]`, and
   step2 needs its `if __name__ == "__main__"` guard, already there). The scratchpad does not
   survive the session, so **re-run both** if it is gone: the scripts are short, and what they do
   is in this entry and in PROGRESS. The earlier run of the same code: **30 of 30 jobs done**;
   stringout `TEST/_reports/turnover097_09_28_2026_danielluckett_SO_v01.mp4`, 44.9 s, HD h264;
   QC log and tracker written. Deliver to `C:\Users\shann\Downloads\`: the run log CSV
   (`ProIngest-logs-turnover097-run.csv`) and the stringout mp4, then look at a few stringout
   frames before calling it good. **Say plainly** that QC refuses the run on its own (2 must-fix:
   QC-033 C4261 70 frames, QC-034 C4271 353 frames) and it rendered only with Accept As Is ticked;
   and that `collected files` needed number, date and shooter typed in (QC-005: the folder name
   has a two digit year, OQ-77).
5. Things to raise with the user (not yet raised): the two digit year folder name (OQ-77 (4));
   QC-070 does not watch AMFs (OQ-77 (5)); AMFs are read only from the folder pointed at
   (OQ-77 (6)); HDRI rows still show QC-026/QC-032 errors (skipped, non-blocking), which is
   noise worth asking about; `docs/QC_RULES_SUMMARY.csv` (untracked) still lists QC-020 as must-fix.

## In progress: colour from AMF + CLF (user, 2026-09-28) - pick up here

Turnover097 (`turnover097_09_28_26_danielluckett/collected files`, untracked) is the spec
sample: EDL + UTF-16 CSV + one AMF per EDL event + CLF grade nodes. **User decisions,
2026-09-28**, all final:
- **Colour comes from the AMF and its CLFs only.** The CDL in the EDL and the CSV's
  encoding columns are no longer read. "There will be no older turnovers": no fallback path.
- **EDL = the cut, CSV = identity** (File Name, Shot, Shot Type). OTIO and DRT ignored.
- Reference mp4s **follow the AMF's output transform** (here Gamma 2.2 Rec.709, not sRGB).
- A clip whose AMF has no grade: **info**. An AMF from the "Dailies Request" preset: **info**
  (use whichever preset arrives).
- Grades are primaries plus simple sky secondaries; anything a CLF cannot carry is
  **ignored with a warning** if detected.
- **HDRI rows (Shot Type HDRI) are delivered by the shooters**: the tool delivers nothing for
  them; an sRGB reference clip for one may sit in the timeline, shown in the stringout only.
- Ben provides no Resolve frame; the repo's graded EXR is Turnover121's, not comparable.

**Verified facts** (turnover097 + the pinned config):
- AMF index in the filename (`..._C4261_1_...amf`) = EDL event number - 1, 15 of 15. Each
  AMF also names its file (`<aces:file>`, or `<aces:sequence>` for an EXR sequence).
- The pinned config's `interchange: amf_transform_ids` maps every URN the AMFs use: input
  `CSC.Sony.SLog3_SGamut3Cine_to_ACES.a2.v1` -> `S-Log3 S-Gamut3.Cine`; look
  `Look.Academy.ReferenceGamutCompress.a2.v1` -> look `ACES 1.3 Reference Gamut Compression`;
  output `Output.Academy.Rec709-D65_100nit_in_Rec709-D65_Gamma2pt2.a2.v1` -> display colour
  space `Gamma 2.2 Rec.709 - Display` and view transform `ACES 2.0 - SDR 100 nits (Rec.709)`.
- Each CLF: ACES2065-1 in/out, AP0->AP1, lin->ACEScct, one 33^3 LUT3D, back out. OCIO 2.5
  reads `.clf`. The AMF carries each CLF's md5. Pipeline order: IT, RGC, workingLocation,
  CLF nodes, OT. All `applied="false"`. HDRI AMFs have no input transform.

**Chunks** (commit + PROGRESS entry after each):
1. **Done** (commit "AMF reader"). `core/amf.py`: parse an AMF, resolve its URNs through the config, tests. Not wired.
2. **Done** (commit "Colour from the AMF"). Wire it: scan reads each row's AMF by event; `ShotColor` = input space, RGC, CLFs,
   display/view; CDL and CSV encoding removed; QC rules reworked (QC-008/009/046/047, new
   IDs for AMF mismatch, missing/changed CLF, preset info, unapplicable CLF); HDRI rows
   deliver nothing; EXR header provenance; tests.
3. **Done** (commit "0.5.10") except the run. Docs (COLOR_AND_FORMAT, QC_RULES, OQ-71 resolved), version bump, CI, then run
   turnover097: log CSV to the user, run (Accept As Is for QC-033/034 if needed), stringout.

## Where things stand

- **Version 0.5.11 on branch `qc/source-fidelity`**, PR #17 open, not merged. 0.5.4 is on `main`.
  0.5.7 made QC-020 a warning again; 0.5.8 puts every QC result into Save Logs as CSV at its
  own level, plus a session start line, problem dialogs and uncaught exceptions (user, 2026-09-28).
  0.5.9 adds **Accept As Is (Ignore QC)** on a turnover heading (QC-074, OQ-76). 0.5.10 takes
  **colour from each event's AMF and its CLFs** (QC-075 to QC-080; see "In progress" above). 0.5.11 labels each reference for
  the AMF's display (gamma 2.2 is `bt470m`), not always sRGB.
  CI run 36514483081 is green on all four jobs and built `ProIngest-0.5.9.dmg`:
  `gh run download 36514483081 -R shango/ProIngest -n ProIngest-macos-arm64 -D ~/Downloads/ProIngest-0.5.9`
- **1739 tests pass**; `ruff`, `ruff format` and `mypy --strict` are clean.
- **Turnover121 renders again**: QC-020 (8 bit or 4:2:0) is a warning since 2026-09-28 (user),
  and every clip in it is 8 bit 4:2:0 H.264. Turnover199 (10 bit 4:2:2) is not affected.

## What changed since 0.5.5 (all user decisions, 2026-09-24 and 25)

- **The delivery root defaults to one folder up from the turnover.**
- **Turnover folders can be dropped on the window**, several at once; anything that is not a
  turnover folder is skipped.
- **QC-033 and QC-034 are must-fix.** QC-020 was too, and is a warning again in 0.5.7.
- **One right-click entry, Re-scan**, on a shot and on a turnover heading, replaces Reset and
  Re-run. It re-reads the files, shows new warnings or errors, and otherwise marks the shot to
  render again at the next version. **Cancel Re-run** withdraws the mark, and refuses (with the
  reason) when the delivered files no longer match the shot's name or range.
- **A new shot code or a trimmed In/Out puts a delivered shot back for the next Run.**
- **Every deliverable's timecode is its own frame number from 1001** (`00:00:41:17` at 24). The
  camera timecode is left behind.
- **The stringout is built** (`core/stringout.py`, OQ-38): Ben's final EDL as one HD mp4, cut from
  the delivered HD references, with the ungraded source or black standing in, burn-ins copied from
  `burn-ins.png`. Built after a Run and from **Build Stringout** on a turnover heading.
- **A reference still is decoded with its own matrix and range** (it was always BT.709 limited).
- **The config is ACES 2.0** (`studio-config-v4.0.0_aces-v2.0_ocio-v2.5`), view `ACES 2.0 - SDR
  100 nits (Rec.709)` on `sRGB - Display`. The EXRs do not change; the references do.

## Open

- **The display** is sRGB on the user's belief; read it off Ben's project (OQ-29). The config also
  offers `Gamma 2.2 Rec.709` and `Rec.1886 Rec.709`.
- **Ben saw a "very slight shift"** between his Resolve output and the tool's. Plausibly the ACES
  1.3 vs 2.0 view (measured earlier: 3.3% mean, 11% peak in display code), but only for an mp4;
  the EXR path is bit for bit the same under both configs. Ask which file, which clip, and where it
  was viewed, then render that frame under both views.
- **Every Turnover121 event's slope is 4.886**, which renders near white. Still with Ben.
- **Resolve's reference EXR** (`SECA0003_pl01_colorChart_01_raw_4k_v01.exr`, repo root) is not
  linear ACEScg: no `chromaticities`, median about 0.5, max 1.03, camera timecode. Five questions
  asked about it (burn-in, colour encoding, camera metadata and GPS, file name), none answered.
- **Per-clip AMF** from Ben's session, to be read by hand first (OQ-71). Nothing built.
- **Drive links in the tracker export**: waiting on `xattr -l` from the Mac and a paste test.
- **Stringout leftovers**: UI_SPEC section 8, PRD FR-9, NAMING_SPEC section 5 and the QC summary
  rows for QC-142 and QC-143 still to write; the CLI does not build one; a source segment of a
  plate is silent; a text shadow or box for bright frames is asked, not answered; whether to keep
  the camera timecode as hidden metadata is asked, not answered.
- **Untracked, the user to decide**: `docs/QC_RULES_SUMMARY.csv` and
  `docs/COLOR_INPUTS_TURNOVER121.md`.
- From before: a changed ALE is not flagged on re-scan; compound clips are unread (OQ-63);
  non-square pixels are not letterboxed correctly.

## Working notes

- **Do not update `build-track.html`.** It is retired.
- **Every build gets its own patch version** in `pyproject.toml`, `proingest/__init__.py`,
  `build/build.py`, `docs/guide/install.md` and `uv.lock`, and the reply is a `gh run download`
  command, not a link. CI runs on pull requests and on pushes to `main`, not on a bare branch
  push. **Merge only when the user asks.**
- **`gh pr edit` fails** on a Projects (classic) GraphQL error; use
  `gh api -X PATCH repos/shango/ProIngest/pulls/<n> -f title=... -f body=...`.
- The turnover folders, the reference EXR and `burn-ins.png` in the repo root are untracked;
  never `git add -A`.
- **Per-change rules:** `PROGRESS.md` entry in the same commit; a `docs/MAC_SESSION.md` line for
  anything only a Mac can confirm; no em dashes in any file.
