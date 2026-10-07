# Handoff, 7 October 2026 (end of session)

**Start here after a cleared context.** This is the short version. `PROGRESS.md` section 1 is the
record: one entry per change, newest first, each with the user's words and how it was verified.
If this file disagrees with `PROGRESS.md` or the docs, they are right and this file is wrong.
Then read `docs/WORKFLOW.md`, and `CLAUDE.md` for the ground rules.

## State

- **Version 0.5.33 on branch `hdri/prerender`, PR #19 open, not merged.** Merge only when the
  user asks. `main` has 0.5.25 (PR #18, merged 2026-10-06 at the user's request).
- **0.5.33's CI run, 37681910675, was still building when this was written.** First thing: check
  it (`gh run view 37681910675 -R shango/ProIngest --json conclusion,jobs`). If green, confirm the
  dmg is `ProIngest-0.5.33.dmg` in the package job log, download it with
  `gh run download 37681910675 -R shango/ProIngest -n ProIngest-macos-arm64 -D ~/Downloads/ProIngest-0.5.33`
  and give the user that command. 0.5.32's run (37672405424) was green and is already in
  `~/Downloads/ProIngest-0.5.32/`.
- 1930 tests pass locally (1 skipped); `ruff`, `ruff format` and `mypy --strict` are clean.
- Nothing uncommitted except the untracked samples listed under Working notes.

## The QC model now (0.5.33, user, 2026-10-07)

The user's rule: "nothing prevents rendering an entire batch or turnover. Individual shots can get
blocked ... missing media, or the amf, cfl or an appropriate cdl are missing so the tool cant
recreate the colors." `docs/QC_RULES.md`'s opening section is the authority; in short:

- **An `error` on a row holds that one shot** (`planner.holding_errors`) until it is fixed and
  re-scanned; every other shot renders. The errors left: no file, two files, unreadable or
  undecodable (QC-012, 013, 014, 022); no name (010, 011, 065); no EDL event or two (066, 067); an
  edited In/Out that cannot be (031, 032); a grade it cannot rebuild (046 = no AMF *and* no CSV
  `Input Color Space`, 047, 075 = two AMFs on one clip, 076 = a CLF missing or changed). A moved
  turnover folder holds its rows (QC-069, `planner.held_turnovers`).
- **Only a batch error stops a run**, with the popup "The run cannot start": delivery root not
  writable or too little space (QC-062, 063; `qc.must_fix`).
- **Ungraded is not a problem**: no AMF, or an AMF with no CLF and no CDL, renders through the
  input transform alone. With no AMF the input is the CSV's `Input Color Space` (`Apple Log` in
  134 and 135), the references use `color.DEFAULT_VIEW`, and QC-009 says "Clip ungraded in Resolve
  project".
- **The cut is the EDL's at face value**: the file's own timecode, then the CSV's `Start TC`,
  silently (QC-084 retired); if neither fits, the frames the file has, with a QC-029 info note.
- **Warnings now**: QC-023, 026, 027, 033/034 ("Plate was N frames on the timeline"), 042, 073, 079.
  **Info now**: QC-021, 055. **Gone**: Accept As Is (QC-074), QC-008, the Allow other resolutions
  setting (old batches still load).
- **The QC log has an Issues sheet**: every finding in words, with its Effect (stopped the run,
  held this shot back, rendered). The Fix-it report leaves info out.

## What this session built (6 and 7 Oct 2026, all user requests)

| version | what |
|---|---|
| 0.5.25 | `User_Generated` and `User_Uploads`, empty, at the delivery root after any run that delivers |
| 0.5.26 | **HDRI**: the EXR delivered byte for byte as `<shot>_pl01_HDRI_<idx>_v<ver>.exr`, no checks (QC-080); the stringout plays Ben's pre-render beside it (sRGB Linear, graded through the HDRI's AMF); missing is QC-083 |
| 0.5.27 | **The stringout is cut from the delivered EXRs** (OpenEXR, OCIO, a lossless ffv1 intermediate); ffmpeg's DWAA decoder avoided. OQ-80 |
| 0.5.28 | **Everything in the stringout is graded** |
| 0.5.29 | **Reference clips play** in the stringout from the source; delivery is still one 4k EXR frame |
| 0.5.30 | **Take on the burn-in** when the CSV's `Take` is above 1 (OQ-81) |
| 0.5.31 | **Every Fix-it line names its shot** |
| 0.5.32 | **Style frames** (`Shot Type` `styleFrame`, QC-085): a pre-graded PNG or JPG held as it is for its EDL length, never delivered, `SECA0009 styleFrame`, no counter. **The stringout line** under each turnover: bar while building, ball green when built, red for QC-142 or a black event (QC-144). OQ-82 |
| 0.5.33 | **The QC overhaul** (above). OQ-83 |

## Verified on the samples (0.5.33)

- **Turnover134** scans with nothing held; its mirror balls are cut by Resolve's clock with
  nothing said.
- **Turnover135, which could not run before, now plans 38 jobs.** Only its four SECA0012
  reference stills are held (QC-012: they are `..._raw_4k_v01.exr` files from another export, not
  in the folder). Its six camera plates and clean plates render ungraded from Apple Log;
  `SECA0013_pl01_ref_HD_v01.mp4` was rendered through that path (240 frames, phase B clean) and a
  frame looked right for ungraded Apple Log.

## Open, with the user (newest first)

- **OQ-83's assumptions, made without asking** (the user has not reacted yet): no-AMF clips read
  as the CSV's `Input Color Space`; their references through ACES 2.0 SDR Rec.709 on Gamma 2.2;
  low disk space (QC-063) stops the run like an unwritable root; QC-021 and QC-055 made info; the
  media is still probed to decode it; plate length (QC-033/034) is a warning, so those rows show
  amber.
- **Style frames are untested on real media**: no turnover in the repo has one. Ask for the
  first export that does, and check it against OQ-82 (EDL length kept, no OCIO).
- **Ben's HDRI renders are named differently from what the tool expects.** A newer turnover134
  export (a screenshot, not in the repo) shows `SECA0009_pl01_HDRI_01_v01.exr Render 1.mov` on the
  timeline typed HDRI, with the EXRs off the cut. The tool expects `<EXR stem>.<mp4|mov|mxf>` beside
  the EXR, and the EXR on the timeline typed `HDRI`. Ask how Ben will name and place them before
  changing anything, and get that export into the repo root to test against.
- **OQ-81, the take**: "only if there's more than one take" was read as a Take above 1. No reply.
- **The HDRI EXR "you don't need to touch"** was read as "copy it, never alter it". If it meant
  "do not deliver it", `planner._hdri_plan` is the one place to stop it. No reply.
- **Turnover134's HDRI EXRs carry no Shot or Shot Type** in that CSV, so they are ignored; no
  sample has an HDRI pre-render yet.
- **Mac checks** in `docs/MAC_SESSION.md`, newest first: the QC overhaul (0.5.33), style frames
  and the stringout line (0.5.32), the stringout from the EXRs (0.5.27), the HDRI pre-render look
  (0.5.26), expiry and the CDL grade (0.5.23), burn-in boxes (0.5.22), and older ones.
- **"Fix in Resolve" rule list** was chosen by Claude (`models.RESOLVE_FIX_RULES`; QC-008 and
  QC-029 left it in 0.5.33); the user may adjust it.
- **Log CSV Level column**: the user reported INFO on blocking errors; the supplied
  `ProIngest-logs-20261005-1301.csv` does not show that. Asked what they saw; no reply.
- **Ben's pages**: https://claude.ai/artifact/DFshCWhWiGYsEuH35NPAy3 (version 2, private, for
  134 and 135) predates the QC overhaul, so it still asks Ben to fix things that no longer block
  (turnover135's missing AMFs now just mean ungraded). Offer to update it. The older per-turnover
  pages (134: GX82xM9xvaZnjzoWFBkUaL, 135: 9Bynj3M6E2t23n2WB5PtDZ) are stale too.

## Older, still open

- **Inset assumptions, told the user**: cp top left and wit top right; the label bottom left
  inside the inset; labels on the insets only.
- **The name at top centre clears the insets by about 20 px**; a longer shooter name could touch
  them. The user said adjust later if so.
- **Ben saw a "very slight shift"** between his Resolve output and the tool's. Ask which file,
  which clip and where it was viewed. A tool render against a Resolve render of the same frame
  has never been made (OQ-77 (1)).
- Older still: Turnover121's 4.886 slope (with Ben); Resolve's reference EXR in the repo root (five
  questions, none answered); Drive links in the tracker export (waiting on `xattr -l` from the Mac);
  the CLI does not build a stringout; a source segment of a plate is silent; no text shadow or box
  for bright frames (asked); keeping the camera timecode as hidden metadata (asked); a changed ALE
  is not flagged on re-scan; compound clips are unread (OQ-63); non-square pixels are not
  letterboxed correctly.

## Working notes

- **Do not update `build-track.html`.** It is retired.
- **Every build gets its own patch version** in `pyproject.toml`, `proingest/__init__.py`,
  `build/build.py`, `docs/guide/install.md` and `uv.lock` (line 584, the `proingest` package).
  Push, let CI build (it runs on the open PR), then reply with the `gh run download` command and
  download it into `~/Downloads/ProIngest-<version>/` too.
- **`gh pr edit` fails** on a Projects (classic) GraphQL error; use
  `gh api -X PATCH repos/shango/ProIngest/pulls/<n> -f title=... -f body=...`.
- **Untracked, never `git add -A` or `git add docs`**: the turnover folders, the reference EXR,
  `burn-ins.png`, the log CSV. `git add -u` plus new files by name.
- **Headless runs**: `python -m proingest scan <folder> --save x.pibatch`, then `run x.pibatch
  --delivery-root <scratch>`; since 0.5.33 a row error only holds that row. A scripted run
  (`scan.scan_turnover`, `qc.apply_batch_rules`, `planner.plan_batch`, `render.execute`) must sit
  under an `if __name__ == "__main__":` guard, because the worker pool spawns.
- **The full suite takes about ten minutes**; run it in the background. There is no xdist.
- **Memory** (`~/.claude/projects/...ProIngest/memory/`): read `hdri-is-a-video-clip` before any
  HDRI work.
- **Per-change rules:** `PROGRESS.md` entry in the same commit; a `docs/MAC_SESSION.md` line for
  anything only a Mac can confirm; no em dashes in any file.
