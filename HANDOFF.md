# Handoff, 7 October 2026 (end of session)

**Start here after a cleared context.** This is the short version. `PROGRESS.md` section 1 is the
record: one entry per change, newest first, each with the user's words and how it was verified.
If this file disagrees with `PROGRESS.md` or the docs, they are right and this file is wrong.
Then read `docs/WORKFLOW.md`, and `CLAUDE.md` for the ground rules.

## State

- **Version 0.5.37 on branch `ldri` (2026-10-08): the LDRI, an HDRI whose file is a JPG or PNG**
  (`PROGRESS.md`, OQ-85). Merge only when the user asks. `main` has 0.5.36 (PR #19, `a85cd53`).
- **0.5.36's CI run** is given in the last commit on the branch; check it with
  `gh run list -R shango/ProIngest --branch hdri/prerender -L 3`, and if green hand over
  `gh run download <id> -R shango/ProIngest -n ProIngest-macos-arm64 -D ~/Downloads/ProIngest-0.5.36`. 0.5.35's run (37690475455) was green and is in `~/Downloads/ProIngest-0.5.35/`.
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
| 0.5.34 | **The HDRI pre-render on the timeline**: the `... .exr Render.mov` the timeline cuts is the stringout's event, the EXR named in it is delivered when it is in the folder, else QC-086 "HDRI EXR File Missing from turnover folder, omitted from delivery"; no CLF and no CDL shows it as it is (QC-009). **The Fix-it report** says, per clip, the full path it looked for and which file (CSV, EDL with timecode, AMF) reported it. OQ-84 |
| 0.5.35 | **The stringout's time left** on its line, in Notes, counting down between events |
| 0.5.36 | **The stringout optimised**: turnover135 from 26m15s to 3m00s. The view chain baked into a 65 point ACEScct cube (the exact ACES 2.0 transform was 98% of the time), a UT Video 10 bit intermediate in local temp, the pictures converted and the events encoded `workers` at a time. Fixed on the way: OCIO's cache reused one baked LUT's processor for another. Next lever: x264 `preset slow` for the stringout, the user's call |

## Verified on the samples (0.5.34, the replaced exports of 2026-10-07)

- **Turnover134**: 21 rows, 0 errors. Every camera clip graded from the CDL in its AMF (QC-082,
  no CLFs exported); three short-handle warnings (QC-030). Its three HDRI pre-renders are there,
  ungraded (QC-009); its HDRI EXRs are not in the folder, so QC-086 and no HDRI delivered. 39
  deliverables rendered, 0 failed.
- **Turnover135**: 21 rows, 0 errors, 42 jobs including the three HDRI EXR copies. Every clip now
  has an AMF; SECA0012's are ungraded (QC-009), SECA0013/14 graded from the CDL (QC-082).
  All 42 rendered, 0 failed; its stringout (1920 frames) plays the three HDRI pre-renders as
  they are and cuts the reference stills from their HD references (QC-143, info).

## Open, with the user (newest first)

- **OQ-83's assumptions, made without asking** (the user has not reacted yet): no-AMF clips read
  as the CSV's `Input Color Space`; their references through ACES 2.0 SDR Rec.709 on Gamma 2.2;
  low disk space (QC-063) stops the run like an unwritable root; QC-021 and QC-055 made info; the
  media is still probed to decode it; plate length (QC-033/034) is a warning, so those rows show
  amber.
- **Style frames are untested on real media**: no turnover in the repo has one. Ask for the
  first export that does, and check it against OQ-82 (EDL length kept, no OCIO).
- **OQ-84's assumptions** (the HDRI pre-render): the EXR is the render's name up to `.exr`; a
  render whose AMF does carry a grade keeps the older sRGB Linear treatment, unverified; the HDRI
  row's In/Out in the shot list is meaningless for the copy.
- **OQ-81, the take**: "only if there's more than one take" was read as a Take above 1. No reply.
- **The HDRI EXR "you don't need to touch"** was read as "copy it, never alter it". If it meant
  "do not deliver it", `planner._hdri_plan` is the one place to stop it. No reply.
- **Mac checks** in `docs/MAC_SESSION.md`, newest first: the stringout optimised (0.5.36), the stringout's time left (0.5.35), the HDRI pre-render and Fix-it paths (0.5.34), the QC overhaul (0.5.33), style frames
  and the stringout line (0.5.32), the stringout from the EXRs (0.5.27), the HDRI pre-render look
  (0.5.26), expiry and the CDL grade (0.5.23), burn-in boxes (0.5.22), and older ones.
- **"Fix in Resolve" rule list** was chosen by Claude (`models.RESOLVE_FIX_RULES`; QC-008 and
  QC-029 left it in 0.5.33); the user may adjust it.
- **Log CSV Level column**: the user reported INFO on blocking errors; the supplied
  `ProIngest-logs-20261005-1301.csv` does not show that. Asked what they saw; no reply.
- **Ben's page**: https://claude.ai/artifact/DFshCWhWiGYsEuH35NPAy3 (version 3, private until the
  user shares it) was rewritten on 2026-10-07 for the QC model and the 0.5.34 scan of the new
  exports: 134's three HDRI EXRs to copy in, CLFs missing everywhere, three short handles, and
  SECA0012's plate and clean plate ungraded; plus what is done. The older per-turnover pages
  (134: GX82xM9xvaZnjzoWFBkUaL, 135: 9Bynj3M6E2t23n2WB5PtDZ) are stale and were left alone.

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
