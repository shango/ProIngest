# Handoff, 6 October 2026

**This is a short pointer, not the record.** `PROGRESS.md` section 1 holds the record: one entry
per change, newest first, each saying what was built and how it was verified. If this file
disagrees with `PROGRESS.md` or the docs, they are right and this file is wrong.

## State

- **Version 0.5.23 on branch `app/expiry`, PR #18 open, not merged** (merge only when the user
  asks). 0.5.22 is on `main` (PR #17, `70e1160`).
- **CI run 37415594139 is green on all four jobs** and built the 0.5.23 dmg, handed over as:
  `gh run download 37415594139 -R shango/ProIngest -n ProIngest-macos-arm64 -D ~/Downloads/ProIngest-0.5.23`
  (https://github.com/shango/ProIngest/actions/runs/37415594139)
- **1847 tests pass locally**; `ruff`, `ruff format` and `mypy --strict` are clean.
- Nothing uncommitted except the untracked samples under Working notes. Nothing in flight.

## What 0.5.23 did (5 and 6 Oct 2026, all user requests)

- **Build expiry**: a packaged build refuses New, Open, Add Turnover, drops, Scan, Run, Export and
  Build Stringout one calendar month after its build day, with an "Update ProIngest" modal; the
  last 7 days warn on the status bar; headless subcommands exit 3. Save, Stop, Settings, Save Logs
  stay. Source runs never expire. `core/expiry.py`, `build/build.py` stamps
  `proingest/resources/release.txt` (untracked). PACKAGING "Expiry", OQ-78.
- **Status dots are QC levels again**: the 0.5.22 "dot matches the progress bar" change was
  wrong (user) and is reverted exactly. Memory: status-dots-are-qc-levels.
- **AMF pairing fixed**: Resolve numbers AMFs by video clip; turnover134's EDL numbers its
  audio-only events too, which shifted every later AMF one clip off (34 false errors). Keyed on
  `clf.ConformEvent.position` now.
- **The AMF's CDL is the grade when the AMF names no CLF** (user: "prefer CLF with CDL as backup
  only if CLF is missing, and a warning for Ben on the item. Non blocking."): applied in the AMF's
  `toCdlWorkingSpace` (ACEScg), unclamped, `color.cdl_transform`, with **QC-082** (warning). A CLF
  present wins and the CDL is QC-077. Not yet compared with Resolve's own render (MAC_SESSION).
- **"Fix in Resolve - "** leads every error and warning of the rules in
  `models.RESOLVE_FIX_RULES` (set in `QCResult.__post_init__`); never info. QC_RULES lists them.
- **Folders named `proxy`** (any case, any depth) are never searched for media
  (`media.IGNORED_FOLDERS`).
- **No QC-075 on an HDRI row** (never graded).

## Turnover134 and turnover135 (untracked, in the repo root)

Run headless on 2026-10-06. **Ben's lists** (private pages, the user shares them):
turnover134 https://claude.ai/artifact/GX82xM9xvaZnjzoWFBkUaL and turnover135
https://claude.ai/artifact/9Bynj3M6E2t23n2WB5PtDZ (source: the scratchpad's `ben/make.py`, gone
after this session; republish by editing the page via its URL).

- **Turnover134** scans with only two must-fix: the SECA0009 and SECA0010 mirror balls
  (`A001_09291513_C007`, `A001_09291529_C013`) were conformed against the `Proxy/` copies, whose
  timecode differs, so the EDL cuts fall before the real files (QC-029, "Fix in Resolve").
  With those two skipped, all 37 deliverables render, graded by the AMF CDL. Also for Ben:
  `A001_09291546_C022` is typed SECA0001 (should be SECA0011); the stitched HDRI EXRs sit on the
  timeline with no Shot Type; grades came as CDL with no CLF (QC-082); stray `.drt`, NDA pdf and
  distortion grid in the folder.
- **Turnover135 cannot run**: one AMF (for a SECA0012 size-ref EXR from another export) where 18
  clips need one; the timeline's four SECA0012 reference stills are `..._raw_4k_v01.exr` files not
  in the folder (size ref matches camera clip C028 by timecode; C029, C032, C033 unconfirmed); a
  duplicate CSV row; HDRI EXRs on the timeline; a `LOGS` folder and `.drt` in it.

## Open, with the user

- **Ben's answers** on both turnovers (the pages above). Re-run each when his re-exports land;
  turnover135 may show more once its AMFs exist.
- **The CDL fallback against Resolve**: compare a graded reference with Ben's own playback
  (MAC_SESSION line). Unclamped CDL in ACEScg is assumed to be what Resolve does.
- **"Fix in Resolve" rule list** was chosen by Claude (17 rules plus QC-082); the user may adjust.
- **`docs/COLOR_INPUTS_TURNOVER121.md`** went into PR #18 by mistake (swept in by a `git add`);
  the user said nothing either way and it was left in. The PR description says so.
- **Log CSV Level column**: the user reported it said INFO for blocking errors; the file supplied
  (`ProIngest-logs-20261005-1301.csv`, untracked) does not show that. Asked what they saw; no reply.
- **Mac checks** in `docs/MAC_SESSION.md`: expiry (0.5.23), the CDL grade (0.5.23), burn-in
  boxes (0.5.22), and the older ones.

## What 0.5.22 did (5 Oct 2026, user)

- Turnover dates are `MM_DD_YY` (QC-081 retired; the stringout name has a two digit year).
  Burn-ins sit on a 30% black box, 8 px padding, one font line high.
- `MM_DD_YY` is for turnover-dated names only (folder, stringout); reports and logs keep
  `YYYYMMDD` (memory: two-digit-dates-scope).

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


### Older, still open

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
- **Untracked, never `git add -A` or `git add docs`**: the turnover folders, the reference EXR,
  `burn-ins.png`, the log CSV. Stage files by name.
- **Headless runs**: `python -m proingest scan <folder> --save x.pibatch`, then `run x.pibatch
  --delivery-root <scratch>`; the run refuses while any must-fix stands, so skip rows in a copy of
  the batch (`batchfile.load`, set `skipped`, `batchfile.save`) to exercise the rest.
- **A full turnover097 run** (that folder is no longer in the repo) is a short script: scan `collected files`, type in 97, 9, 28, 2026,
  `danielluckett`, `qc.preflight`, `render.execute(planner.plan_batch(...), workers=4)`,
  `render.apply_results`, `stringout.build`. Put it under an `if __name__ == "__main__":` guard
  (the worker pool spawns). To rebuild only the stringout, point each row's `deliverables` at the
  delivered `<stem>_ref_HD_v01.mp4` and set `delivered_range = current`.
- **Per-change rules:** `PROGRESS.md` entry in the same commit; a `docs/MAC_SESSION.md` line for
  anything only a Mac can confirm; no em dashes in any file.
