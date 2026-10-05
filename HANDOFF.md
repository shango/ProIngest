# Handoff, 5 October 2026

**This is a short pointer, not the record.** `PROGRESS.md` section 1 holds the record: one entry
per change, newest first, each saying what was built and how it was verified. If this file
disagrees with `PROGRESS.md` or the docs, they are right and this file is wrong.

## State

- **Version 0.5.22 is on `main`**: PR #17 (`qc/source-fidelity`) merged as `70e1160` on 5 Oct
  2026 at the user's request. New work starts on a new branch.
- **CI run 37276656318 is green on all four jobs** and built the 0.5.22 dmg, handed over as:
  `gh run download 37276656318 -R shango/ProIngest -n ProIngest-macos-arm64 -D ~/Downloads/ProIngest-0.5.22`
  (https://github.com/shango/ProIngest/actions/runs/37276656318)
- **1817 tests pass**; `ruff`, `ruff format` and `mypy --strict` are clean.
- Nothing uncommitted except the untracked samples listed under Working notes.
- **Session wrapped up 30 Sep 2026 at the user's request.** Nothing is in flight. Start with "Open,
  with the user" below, HDRI first.

## What 0.5.22 did (5 Oct 2026, user)

- Turnover dates are `MM_DD_YY`: QC-081 retired, the stringout name written with a two digit
  year. Burn-ins sit on a 30% black box. A done row's dot is the progress bar's blue.

## What 0.5.12 to 0.5.21 did (29 Sep 2026, all user decisions)

- **0.5.12** The reference label is set on the frames too (`ffmpeg.reference_label`, a
  `setparams` step): the Mac's bundled ffmpeg 9.0.1 wrote no transfer from `-color_trc` alone.
- **0.5.13** A two digit year in a folder name is read as 20YY with a QC-081 warning. HDRI rows
  (QC-080) run no row rules. `docs/QC_RULES_SUMMARY.csv` committed and current. OQ-77 (4) to (6)
  answered: QC-070 stays EDL and CSV only; AMFs are read only from the folder pointed at.
- **0.5.14** Length limits (QC-033/034) apply to `pl` rows only. Turnover097 now has no must-fix.
- **0.5.15** Stringout picture in picture: over each `pl`, the shot's first cp (EDL order) top
  left and first wit top right, 480x270 (Resolve zoom 0.25), from their delivered HD refs, playing
  from their own cut In and removed when they run out or at the plate's Out.
- **0.5.16** Each inset labelled with its element (`cp01`), 32 px, bottom left inside it.
- **0.5.17** The version always in view: window title and a permanent status bar label.
- **0.5.18** Any held frame on the stringout (a reference still, which is one frame of a video; an
  `M2` hold; any one frame cut) plays for 24 frames, and one taken from the source is coloured
  through its AMF (grade included). Stills were flat because they have no HD reference.
- **0.5.19** A clip typed `HDRI` is a reference movie: its stringout event is the clip itself,
  shown as it is, never given AMF colour. Spelled out in QC-080 and COLOUR_SESSION_EXPORT.
- **0.5.20** A timeline event whose file is present always plays on the stringout, never black: a
  file with no timecode is counted from 00:00:00:00 (where Resolve starts one), a single image is
  its one frame. Delivery stays strict (QC-029).
- **0.5.21** A held HDRI slot keeps the EDL's length (turnover097: 72 and 120 frames); every
  other held frame stays one second.
- **Docs, no code: Ben exports no stringout.** The tool builds it. Every doc says so now.

## Turnover097, the spec sample

`turnover097_09_28_26_danielluckett/collected files` (untracked): EDL + UTF-16 CSV + one AMF per
EDL event + CLF grade nodes. **A turnover is only those four: the CMX 3600 EDL, the CSV, one AMF
per clip and the CLFs** (user); the stray `.otio` and `.drt` in the folder are not part of it and
are never read or cited. It scans with **no must-fix** and runs in full (30 jobs, about 20
minutes here). The latest stringout, 1262 frames with the insets, held stills and both HDRI events playing, is
`turnover097_09_28_26_danielluckett/turnover097_09_28_2026_danielluckett_SO_v01_pip.mp4`; the
first run's logs are in `C:\Users\shann\Downloads\ProIngest-turnover097\`. The handover folder is
named `collected files`, so number, date and shooter are typed in (QC-005).

**Colour decisions (2026-09-28), final:** colour comes from each event's AMF and its CLFs only; the
EDL is the cut and the CSV is identity (File Name, Shot, Shot Type); references follow the AMF's
output transform (here Gamma 2.2 Rec.709, labelled `bt470m`); a clip with no CLF is info (QC-009);
HDRI rows are the shooters' to deliver (QC-080). Verified facts: the AMF index in its filename is
the EDL event number less one (15 of 15); the pinned config maps every URN the AMFs use.

## Open, with the user

- **HDRI, waiting on Ben** (user, 2026-09-29; this kept being lost, so read it first): a clip typed
  `HDRI` is expected to be an **sRGB reference MP4** of what the shooter captured, later stitched
  into an HDRI in another application. The tool never touches an actual HDRI EXR, and the HDRI
  clip plays in the stringout like any other, as it is. **Turnover097's two HDRI-typed clips are
  OpenEXR files by content** (`DALU0012_pl01_02_HDRI.exr`, `DALU0016_pl01_HDRI.exr`, EDL events
  008 and 015, `M2` holds), not MP4s. The user has no access to Ben's timeline and is **asking Ben
  whether placing the EXRs there was intentional**, and if not, for a re-export with the MP4s.
  Either way they play now (0.5.20); the linear DALU0012 reads dark, shown without colour. If Ben
  keeps EXRs there, ask whether they should get their AMF colour.
- **Inset assumptions, told the user**: cp top left and wit top right (their first message said
  "left is the pl"); the label bottom left inside the inset; labels on the insets only.
- **Held stills include Ben's grade** on the stringout; told the user the view-only alternative
  is a one line change.
- **The name at top centre clears the insets by about 20 px** (x 499 to 1411 against 480 and
  1440); a longer shooter name could touch them. The user said adjust later if so.
- **Ben saw a "very slight shift"** between his Resolve output and the tool's. Ask which file,
  which clip and where it was viewed. A tool render against a Resolve render of the same frame
  has never been made (OQ-77 (1)).
- **Mac checks** in `docs/MAC_SESSION.md`: "Colour from the AMF" (0.5.14) and "The version in
  view" (0.5.17, including the title in full screen).
- Older and still open: Turnover121's 4.886 slope (with Ben); Resolve's reference EXR in the repo
  root (five questions, none answered); Drive links in the tracker export (waiting on `xattr -l`
  from the Mac); the CLI does not build a stringout; a source segment of a plate is silent; no text
  shadow or box for bright frames (asked); keeping the camera timecode as hidden metadata (asked);
  a changed ALE is not flagged on re-scan; compound clips are unread (OQ-63); non-square pixels
  are not letterboxed correctly.

## Working notes

- **Do not update `build-track.html`.** It is retired.
- **Every build gets its own patch version** in `pyproject.toml`, `proingest/__init__.py`,
  `build/build.py`, `docs/guide/install.md` and `uv.lock` (line 584, the `proingest` package).
  The reply is a `gh run download` command plus the run's URL. CI runs on pull requests and on
  pushes to `main`; a branch's pushes run only once a PR is open for it.
- **`gh pr edit` fails** on a Projects (classic) GraphQL error; use
  `gh api -X PATCH repos/shango/ProIngest/pulls/<n> -f title=... -f body=...`.
- **Untracked, never `git add -A`**: the turnover folders, the reference EXR, `burn-ins.png`,
  and `docs/COLOR_INPUTS_TURNOVER121.md` (the user to decide).
- **A full turnover097 run** is a short script: scan `collected files`, type in 97, 9, 28, 2026,
  `danielluckett`, `qc.preflight`, `render.execute(planner.plan_batch(...), workers=4)`,
  `render.apply_results`, `stringout.build`. Put it under an `if __name__ == "__main__":` guard
  (the worker pool spawns). To rebuild only the stringout, point each row's `deliverables` at the
  delivered `<stem>_ref_HD_v01.mp4` and set `delivered_range = current`.
- **Per-change rules:** `PROGRESS.md` entry in the same commit; a `docs/MAC_SESSION.md` line for
  anything only a Mac can confirm; no em dashes in any file.
