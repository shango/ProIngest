# Handoff, 25 September 2026

**This is a short pointer, not the record.** `PROGRESS.md` section 1 holds the record: one entry
per change, newest first, each saying what was built and how it was verified. If this file
disagrees with `PROGRESS.md` or the docs, they are right and this file is wrong.

## Where things stand

- **Version 0.5.6 on branch `qc/source-fidelity`**, PR #17 open, not merged. 0.5.4 is on `main`.
  The dmg command is in the reply that pushed this; CI builds it from the PR.
- **1739 tests pass**; `ruff`, `ruff format` and `mypy --strict` are clean.
- **Turnover121 no longer renders anything**, by the user's decision: QC-020 (8 bit or 4:2:0) is
  must-fix now, and every clip in it is 8 bit 4:2:0 H.264. Turnover199 (10 bit 4:2:2) is not
  affected.

## What changed since 0.5.5 (all user decisions, 2026-09-24 and 25)

- **The delivery root defaults to one folder up from the turnover.**
- **Turnover folders can be dropped on the window**, several at once; anything that is not a
  turnover folder is skipped.
- **QC-020, QC-033 and QC-034 are must-fix.**
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
