# Handoff, 24 September 2026

**This is a short pointer, not the record.** `PROGRESS.md` section 1 holds the record: one entry
per change, newest first, each saying what was built and how it was verified. If this file
disagrees with `PROGRESS.md` or the docs, they are right and this file is wrong.

## Where things stand

- **Version 0.5.4 is on `main`** (`262817e`, PR #16). CI is green on all four jobs. The dmg:
  `gh run download 35944322464 -R shango/ProIngest -n ProIngest-macos-arm64 -D ~/Downloads/ProIngest-0.5.4`
- **Released today, in order:** 0.5.0 (review chunks A to H, PR #12), 0.5.1 (only a pl searches
  for audio, #13, #14), 0.5.2 (cp and el references are silent, #15), 0.5.3 and 0.5.4 (#16: Save
  Logs as CSV, then Turnover121).
- **1662 tests pass**; `ruff`, `ruff format` and `mypy --strict` are clean.
- **Both real turnovers work.** Turnover199 as before. Turnover121 (iPhone, Apple Log, H.264,
  in the repo root, untracked, 90 MB) with the user's corrected CSV scans 7 rows, 0 errors,
  8 warnings; a full render wrote 20 deliverables with none failing phase B.

## What 0.5.4 decided (user, 2026-09-23)

- **The ALE is part of the handover.** It is one row per EDL event in timeline order, so it
  names the events when the EDL does not (`core/ale.py`, QC-071).
- **The CSV has one row per clip per use** (distinct EDL source range); rows pair with uses in
  order (`scan._conform_by_use`).
- **A reference still is delivered once per shot code**, from its first use; a clip cut twice at
  the same frames once (`scan._collapse`, QC-072).
- **A freeze (`M2` at 0) on any clip type** is one frame: a one-frame EXR and a reference held
  5 seconds (`planner.FREEZE_HOLD_SECONDS`). Silent was my call, not the user's. Any other `M2`
  speed is refused (QC-073).
- **Only a pl has audio.** A cp or el is never searched for a wav and its reference is silent.
- **Save Logs as CSV...** on the Log tab and in the File menu, for diagnostics.
- A movie file's rate is its average when ffprobe's `r_frame_rate` disagrees (the iPhone
  reports 480/1); `Input Color Space` names the encoding when the notes columns are empty.

## Open

- **Every Turnover121 event's slope is 4.886**, which renders near white. Taken to Ben as an
  export mistake; the user has not answered yet.
- The Cube Shots had no Shot or Shot Type as delivered; the user is cleaning up the Resolve-side
  handoff folder.
- A changed ALE is not flagged on re-scan (QC-070 digests only the EDL and the CSV).
- Compound clips are still unread (OQ-63); non-square pixels are not handled when letterboxing.

## Working notes

- **Do not update `build-track.html`.** It is retired.
- **Every build gets its own patch version** in the four places plus `uv.lock`, and the reply is
  a `gh run download` command, not a link. CI runs on pull requests and on pushes to `main`,
  not on a branch push. **Merge only when the user asks**; the permission check refuses otherwise.
- **`gh pr edit` fails** on a Projects (classic) GraphQL error; use
  `gh api -X PATCH repos/shango/ProIngest/pulls/<n> -f title=... -f body=...`.
- The turnover folders in the repo root are untracked; never `git add -A`.
- Scratch renders of Turnover121 are in the session scratchpad under `t121/`. Disposable.
- **Per-change rules:** `PROGRESS.md` entry in the same commit; a `docs/MAC_SESSION.md` line for
  anything only a Mac can confirm; no em dashes in any file.
