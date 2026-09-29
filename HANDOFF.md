# Handoff, 29 September 2026

**This is a short pointer, not the record.** `PROGRESS.md` section 1 holds the record: one entry
per change, newest first, each saying what was built and how it was verified. If this file
disagrees with `PROGRESS.md` or the docs, they are right and this file is wrong.

## Current (29 Sep 2026)

**0.5.18** is pushed: held frames play a second on the stringout, coloured through their AMF. Before it, **0.5.17**: the version in the window title and on the status bar. Before it, **0.5.16**: each inset labelled with its element (`cp01`). Before it, **0.5.15**: stringout picture in picture (cp top left, wit top right over each pl;
PROGRESS). Before it, **0.5.14**: length limits (QC-033/034) for pl rows only (user), so turnover097 has no
must-fix. Before it, **0.5.13**: OQ-77 (4) to (6) answered by the user (two digit year accepted with QC-081;
QC-070 left alone; AMFs only in the folder pointed at), HDRI rows run no row rules, and
`docs/QC_RULES_SUMMARY.csv` is committed and current. 0.5.12 (CI run 36527984818, green) fixed the
reference label on the Mac's ffmpeg 9. Turnover097's stringout (44.9 s, HD, `bt470m`) was copied to
`turnover097_09_28_26_danielluckett/` for the user; its logs are in
`C:\Users\shann\Downloads\ProIngest-turnover097\`.

**Next:** hand over 0.5.13's dmg when CI is green (`gh run download <run> -R shango/ProIngest -n
ProIngest-macos-arm64 -D ~/Downloads/ProIngest-0.5.18`), then the Mac check in MAC_SESSION ("Colour
from the AMF"). Still to raise: the handover folder was `collected files`, which matches no name
pattern (QC-005), and `docs/COLOR_INPUTS_TURNOVER121.md` is untracked.
**Ben exports no stringout** (user, 2026-09-29): the tool builds it; every doc now says so.
**Stringout PiP built in 0.5.15**; the user is to look at `..._SO_v01_pip.mp4` in the turnover097 folder.
The two HDRI events are black in the stringout: worth raising.

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
- **Stringout leftovers**: the docs are done (2026-09-29); still open: the CLI does not build one;
  a source segment of a plate is silent; a text shadow or box for bright frames is asked, not
  answered; whether to keep the camera timecode as hidden metadata is asked, not answered.
- **Untracked, the user to decide**: `docs/COLOR_INPUTS_TURNOVER121.md`.
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
