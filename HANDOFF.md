# Handoff, 7 October 2026

**Start here after a cleared context.** This is the short version. `PROGRESS.md` section 1 is the
record: one entry per change, newest first, each with the user's words and how it was verified.
If this file disagrees with `PROGRESS.md` or the docs, they are right and this file is wrong.
Then read `docs/WORKFLOW.md`, and `CLAUDE.md` for the ground rules.

## State

- **Version 0.5.31 on branch `hdri/prerender`, PR #19 open, not merged.** Merge only when the
  user asks. `main` has 0.5.25 (PR #18, merged 2026-10-06 at the user's request).
- PR #19 holds 0.5.26 to 0.5.31, each built by CI on the PR. The latest run:
  `gh run list -R shango/ProIngest --branch hdri/prerender --limit 1`. Hand a build over as
  `gh run download <run-id> -R shango/ProIngest -n ProIngest-macos-arm64 -D ~/Downloads/ProIngest-<version>`
  plus the artifact's web link (`gh api repos/shango/ProIngest/actions/runs/<run-id>/artifacts`),
  and download it into `~/Downloads/ProIngest-<version>/` too (the user asked for that).
- 1915 tests pass locally (1 skipped); `ruff`, `ruff format` and `mypy --strict` are clean.
- Nothing uncommitted except the untracked samples listed under Working notes. Nothing in flight.

## What this session built (6 and 7 Oct 2026, all user requests)

| version | what |
|---|---|
| 0.5.25 | `User_Generated` and `User_Uploads`, empty, at the delivery root after any run that delivers (`render.make_user_folders`) |
| 0.5.26 | **HDRI**: a frame hold on the HDRI EXR with a pan. The EXR is delivered byte for byte as `<shot>_pl01_HDRI_<idx>_v<ver>.exr`, no checks (`qc.is_hdri`, QC-080). The stringout plays Ben's pre-render, a video under the EXR's stem beside it, read as sRGB Linear and graded through the HDRI's AMF with a 1D shaper; missing is **QC-083**. **QC-084**: a cut outside the file by its own timecode but inside by Resolve's (the CSV's `Start TC`) is a warning and cut by Resolve's clock; QC-029 is said in timecode. **Accept As Is** renders every clip that can (`planner.QC_CANNOT_RENDER`) |
| 0.5.27 | **The stringout is cut from the delivered EXRs** (no switch): each EXR read with OpenEXR, through OCIO, into a lossless ffv1 intermediate (`stringout._picture`, `ffmpeg.write_frames`); insets too; plate sound from the wav. ffmpeg's own DWAA decoder is avoided (it blacked out rows). OQ-80 |
| 0.5.28 | **Everything in the stringout is graded**: a reference clip's EXR gets its clip's looks; source fallbacks graded through their AMF; an HDRI with no pre-render is its EXR held, graded |
| 0.5.29 | **Reference clips play** (charts, balls, size refs are videos): their event plays its cut at full speed from the source, graded. Only a freeze or a one frame cut is held. Delivery is still one 4k EXR frame |
| 0.5.30 | **Take on the burn-in**: `SECA0009_pl01 Take 02` bottom right when the CSV's `Take` is above 1 (OQ-81) |
| 0.5.31 | **Every Fix-it line names its shot**: no "Every clip in this turnover (N)" shortcut; a clip whose identity did not read is named from the CSV's Shot and Shot Type |

Also: **Ben's page** for turnovers 134 and 135 (https://claude.ai/artifact/DFshCWhWiGYsEuH35NPAy3,
version 2, private, the user shares it) now says the mirror balls were never linked to the proxies
(the earlier diagnosis was wrong: `Proxy/` holds the camera originals and the cause was Resolve's
media management timecode), turnover134 blocks nothing, and asks for the HDRI pre-renders. The
older per-turnover pages (134: https://claude.ai/artifact/GX82xM9xvaZnjzoWFBkUaL, 135:
https://claude.ai/artifact/9Bynj3M6E2t23n2WB5PtDZ) were not updated and still carry the proxy
wording.

## Open, with the user (newest first)

- **Ben's HDRI renders are named differently from what the tool expects.** The user's
  screenshot of a newer turnover134 export (not in the repo) shows `SECA0009_pl01_HDRI_01_v01.exr
  Render 1.mov` on the timeline typed HDRI, missing from the folder (QC-012), and the EXRs off the
  cut (QC-066). The tool expects the render as `<EXR stem>.<mp4|mov|mxf>` beside the EXR, and the
  EXR as the timeline clip typed `HDRI`. Not asked yet in so many words: ask how Ben will name and
  place them before changing anything, and get that export into the repo root to test against.
- **OQ-81, the take**: "only if there's more than one take" was read as a Take above 1. Told the
  user; no reply.
- **The HDRI EXR "you don't need to touch"** was read as "copy it, never alter it". If it meant
  "do not deliver it", `planner._hdri_plan` is the one place to stop it. Told the user; no reply.
- **QC-084 uses Resolve's clock only when the file's own fails**, because Turnover199 showed the
  CSV `Start TC` stale while the EDL followed the file. So turnover134's C003 and C012 are cut by
  the file's timecode, 7 and 3 frames off Resolve's. The user said this was fixed in Resolve. A
  warning whenever the two clocks disagree was offered and not answered.
- **Turnover134 as in the repo** scans with 0 errors (0.5.26 on). Its HDRI EXRs have no Shot or
  Shot Type in that CSV, so they are ignored, and no sample has a pre-render yet.
- **Turnover135 cannot run**: one AMF where 18 clips need one; the SECA0012 references on its
  timeline are `..._raw_4k_v01.exr` files from another export, not in the folder; a duplicate CSV
  row. Waiting on Ben's re-export.
- **Mac checks** in `docs/MAC_SESSION.md`, newest first: the stringout from the EXRs against a
  plate's HD reference (0.5.27), the HDRI pre-render look (0.5.26), expiry and the CDL grade
  (0.5.23), burn-in boxes (0.5.22), and older ones.
- **"Fix in Resolve" rule list** was chosen by Claude (`models.RESOLVE_FIX_RULES`); the user may
  adjust it.
- **Log CSV Level column**: the user reported INFO on blocking errors; the supplied
  `ProIngest-logs-20261005-1301.csv` does not show that. Asked what they saw; no reply.
- `docs/COLOR_INPUTS_TURNOVER121.md` went into PR #18 by mistake; left in, nobody objected.

## Older, still open

- **Inset assumptions, told the user**: cp top left and wit top right (their first message said
  "left is the pl"); the label bottom left inside the inset; labels on the insets only.
- **The name at top centre clears the insets by about 20 px** (x 499 to 1411 against 480 and
  1440); a longer shooter name could touch them. The user said adjust later if so.
- **Ben saw a "very slight shift"** between his Resolve output and the tool's. Ask which file,
  which clip and where it was viewed. A tool render against a Resolve render of the same frame
  has never been made (OQ-77 (1)).
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
  (the worker pool spawns). To rebuild only the stringout, run `stringout.build` on the batch the run
  saved: it reads each row's delivered HD EXR folder, wav and still EXR from `deliverables`.
- **Memory** (`~/.claude/projects/...ProIngest/memory/`): `hdri-is-a-video-clip` was rewritten
  on 2026-10-07 for the frame hold with a pan; read it before any HDRI work.
- **Per-change rules:** `PROGRESS.md` entry in the same commit; a `docs/MAC_SESSION.md` line for
  anything only a Mac can confirm; no em dashes in any file.
