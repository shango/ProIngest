# Handoff, 7 October 2026

**This is a short pointer, not the record.** `PROGRESS.md` section 1 holds the record: one entry
per change, newest first, each saying what was built and how it was verified. If this file
disagrees with `PROGRESS.md` or the docs, they are right and this file is wrong.

## State

- **Version 0.5.30 on branch `hdri/prerender`, PR #19 open, not merged** (merge only when the
  user asks). 0.5.25 is on `main` (PR #18). 0.5.26 was built in CI run 37543703620, 0.5.27 in 37546876649, 0.5.28 in 37599362947, 0.5.29 in 37605454442.
- The dmg is built by the PR's CI run; its run ID is in the reply that handed it over, as
  `gh run download <run-id> -R shango/ProIngest -n ProIngest-macos-arm64 -D ~/Downloads/ProIngest-0.5.30`.
- `ruff`, `ruff format` and `mypy --strict` are clean and the full suite passes locally.

## What 0.5.30 did (7 Oct 2026, user)

- **The take on the burn-in**: `SECA0009_pl01 Take 02` bottom right when the CSV's `Take` is
  above 1 (OQ-81: "more than one take" read as a Take above 1).

## What 0.5.29 did (7 Oct 2026, user)

- **Reference clips play in the stringout**: a chart, ball or size ref plays its cut at full
  speed, graded, from the source; only a freeze or a one frame cut is held. Delivery is still
  one EXR frame.

## What 0.5.28 did (7 Oct 2026, user)

- **Everything in the stringout is graded**: a still's EXR takes its clip's looks, the source
  fallback is graded held or not, and an HDRI's held EXR (no pre-render) is graded as linear
  Rec.709.

## What 0.5.27 did (7 Oct 2026, user)

- **The stringout is cut from the delivered EXRs** (no switch), an HDRI from its pre-render.
  Each EXR goes through its clip's output transform into a lossless intermediate; plate sound
  from the wav. OQ-80.
- **Ben's page corrected** (version 2): no proxy relink, turnover134 blocks nothing, HDRI
  pre-renders asked for.

## What 0.5.26 did (7 Oct 2026, all user requests)

- **HDRI**: the timeline HDRI is a frame hold on the HDRI EXR with a pan. Its EXR is delivered
  byte for byte as `<shotcode>_pl01_HDRI_<idx>_v<ver>.exr`, no checks; the stringout cuts the event
  from Ben's pre-render beside it (`xxxx_001.mp4`), sRGB Linear, graded through the HDRI's AMF with
  a 1D shaper. No pre-render is QC-083. Memory: hdri-is-a-video-clip (rewritten).
- **QC-084**: a cut outside the file by its own timecode but inside by Resolve's (the CSV's
  `Start TC`) is a warning and cut by Resolve's; QC-029 is said in timecode.
- **Accept As Is** renders every clip that can render (`planner.QC_CANNOT_RENDER`).

## Open, with the user (0.5.26)

- **Turnover134's HDRI EXRs have no Shot or Shot Type in the CSV**, so nothing delivers them
  until Ben types them `HDRI` with the shot code; no pre-render exists in any sample yet.
- **C003 and C012 of turnover134** are cut by the file's own timecode, 7 and 3 frames off
  Resolve's; the user said this was fixed on the Resolve side. A guard warning for a CSV/file
  timecode disagreement was offered and not answered.
- **"you don't need to touch" the HDRI EXR** was read as "copy it, never alter it". If it meant
  "do not deliver it", `planner._hdri_plan` is the one place to stop it.

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

Run headless on 2026-10-06. **Ben's list**, both turnovers on one page (private, the user shares
it): https://claude.ai/artifact/DFshCWhWiGYsEuH35NPAy3. The earlier per-turnover pages,
turnover134 https://claude.ai/artifact/GX82xM9xvaZnjzoWFBkUaL and turnover135
https://claude.ai/artifact/9Bynj3M6E2t23n2WB5PtDZ, still exist (source: the scratchpad's `ben/make.py`, gone
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

- **The EXR stringout** (user, 2026-10-06): an optional switch to cut the stringout from the
  delivered EXRs. Six design questions are with the user (PROGRESS entry for 0.5.25); nothing
  is built. The EXR path cannot be a baked cube in ffmpeg (scene linear), so it would decode in
  Python through OCIO and pipe to ffmpeg, much slower than today's.

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
