# Handoff, 30 October 2026

**30 October, 0.5.53**: turnover150. The stringout read a cut by the file's own timecode alone and
failed on `C2098.MP4` (now `scan.cut_in_file`, shared with the scan). An HDRI or LDRI now delivers
only its pre-render's mp4; the EXR is Ben's to deliver by hand and is never looked for (QC-086
retired); the tracker's HDRI column names the mp4 (user). A shot's `colorChart02` is no longer
folded into its `colorChart01` (QC-072), and a stringout segment whose file decodes a frame or two
short holds its last frame rather than failing the stringout.

**29 October, 0.5.52 on branch `fixit-orange`, draft PR #22**: PR #21 (the Windows build, 0.5.50) is merged,
`main` is `81c0358`. The Fix-it report's Fix in Resolve color is orange rather than red
(`fixit._STYLE`, `--resolve`), and **US spelling throughout** (0.5.52): "color", never "colour",
in code, UI, reports and docs. Merge only when the user asks.

**28 October, 0.5.50 on branch `windows`**: PR #20 is merged (`main` is `b8323cd`, 0.5.49). The
Windows build is in progress for parity with the Mac: gyan.dev ffmpeg 9.0.1 pinned beside the
Mac's, an Inno Setup per user installer, `windows` and `package-windows` CI jobs, and a filter
path escape fixed on both platforms. `PROGRESS.md` has the entry, OQ-89 the assumptions, and
`docs/WINDOWS_SESSION.md` what a person on Windows has to check. **Draft PR #21; CI run
40731521748 is green on all six jobs** and uploaded both `ProIngest-macos-arm64` and
`ProIngest-windows-x64`. Merge only when the user asks.

**Open with the user (28 October)**: "We need to also export an RTF file with the turnover
metadata." Asked, not yet answered: one per shot as the spec sheet's
`<shot>_pl01_camData_v01.rtf` or one per turnover; which CSV fields; a sample camData file to
copy; where it goes. Nothing built yet.

# Handoff, 28 October 2026

**28 October, 0.5.49**: `meas##` and `recon##` are delivered as an Avid reference is (a movie
an mp4, a still as itself, never graded, never an EXR); `recon` replaces `re` (`re01` is QC-010).
HDRIs and LDRIs are numbered by the Shot Type, `HDRI01`, `HDRI02` (bare is 01), with no
underscore, `INCA5002_pl01_HDRI02_v01.exr`; QC-087 is retired. The pre-render is delivered too,
`INCA5002_pl01_HDRI02_v01.mp4` (that name assumed, OQ-88).

# Handoff, 23 October 2026

**23 October, 0.5.48**: a witness cam names the plate it covers. Ben types `pl01_wit01` or
`pl02_wit01`, and all four deliverables and the burn-in carry both (`INCA5002_pl02_wit01_raw_4k_v01`).
A bare `wit01` is QC-010. Its inset goes over the plate it names. OQ-87 has the assumptions. The
shooters' spec sheet is out of date (user) and wants remaking.

# Handoff, 22 October 2026

**22 October, 0.5.47**: an `avidRef##` is now delivered, never as an EXR: a movie or an image
sequence as `<shot>_avidRef01_v01.mp4` with no color transform (its color is baked in), a held
JPG or PNG as it is, any other still as a JPG; not on the tracker. Frame rate confirmed as already
24 throughout. `PROGRESS.md` has the entry and OQ-86 the assumptions. The rest of this file is
the 15 October handoff and still stands, except where it says an avidRef is never delivered.

# Handoff, 15 October 2026 (end of session)

**Start here after a cleared context.** This is the short version. `PROGRESS.md` section 1 is the
record: one entry per change, newest first, each with the user's words and how it was verified.
If this file disagrees with `PROGRESS.md` or the docs, they are right and this file is wrong.
Then read `docs/WORKFLOW.md`, and `CLAUDE.md` for the ground rules.

## State

- **Version 0.5.46 on branch `ldri`, PR #20 open.** Merge only when the user asks. `main` has
  0.5.36 (PR #19, `a85cd53`); everything from 0.5.37 to 0.5.46 is on the branch only.
- **0.5.46's CI run is 38706474925** (commit `e68c344`), green, built `ProIngest-0.5.46.dmg`. Its download:
  `gh run download 38706474925 -R shango/ProIngest -n ProIngest-macos-arm64 -D ~/Downloads/ProIngest-0.5.46`.
  0.5.45's run (38641965425) was green and built `ProIngest-0.5.45.dmg`.
- 2028 tests pass locally at 0.5.46 (1 skipped); `ruff`, `ruff format` and `mypy --strict` are
  clean.
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

## What this session built (13 to 15 Oct 2026, all user requests)

| version | what |
|---|---|
| 0.5.41 | QC-073 (retimed) only on the retimed cut; underscores between every part of a burn-in, never a space; a plain PLATES cell |
| 0.5.42 | **An AMF input transform that is an inverse output transform** (`<aces:inverseOutputTransform>`, a display-referred render such as turnover144's `colorChart Render.mov`, Rec709 Gamma 2.2) is read: `Amf.input_inverse_output`, `amf.input_encoding_for`, `color.inverse_view` names it "<display>, inverse of <view>", and `to_aces` inverts the view. Verified: the rendered chart matched its source within 0.16/255 on average |
| 0.5.43 | **A missing file is a MISSING MEDIA card** on the stringout, with the shot label, and the path it looked for (turnover folder plus File Name) wrapped at 90 characters after a `/`. QC-144 says so separately. The CSV's Clip Directory is not used (stale) |
| 0.5.44 | A stringout-only type (then `preVis`), and **`docs/Shot_Types.xlsx`**: every Shot Type and how the tool treats it, a column guide, what is true of every type, how values are read, and yellow Proposed rows. The user wants it kept up to date and used as the place to add new types |
| 0.5.45 | That type renamed `pl##_avidref` |
| 0.5.46 | **Renamed again: `avidRef##`** (user: "Ben will put avidRef## in the metadata ... Later they might change it"). `avidRef01`, any case, bare `avidRef` is 01, QC-088 (info): no grade, no checks, nothing delivered, plays its cut as it is, burned in `INCA5002_avidRef01`. `pl01_avidref` and `preVis01` are QC-010. The spelling is one constant, `naming.AVIDREF_KIND`; `metacsv._AVIDREF` is built from it, so the next rename is that line plus the tests (`grep -rn -i avidref tests`) and the workbook |

**The workbook is generated** by a script that lived in this session's scratchpad
(`shot_types_xlsx.py`), which does not survive. Edit `docs/Shot_Types.xlsx` directly next time
(openpyxl, or by hand), and keep the Downloads copy (`C:\Users\shann\Downloads\Shot_Types.xlsx`)
in step if the user asks.

## Turnover144 (michaelcrigler), read through 14 Oct

- Test copy: `G:\Shared drives\VFX_Assets_&_Tools_Artists_Library\Artist_Library\Software\PRE-PRO INTERNAL\IngestPro\TEST MATERIAL\turnover144_10_06_26_[michaelcrigler]-footage`.
  Ben's original: `G:\Shared drives\VFX_Ingest\turnover144_10_06_26_michaelcrigler`. From WSL,
  G: is reached through `powershell.exe`, not `/mnt/g`.
- Plates pl01 to pl03 are iPhone Apple Log: warnings QC-020, QC-028, QC-030.
- `el01` and `el02` duplicate pl02 and pl03 and are not in the EDL, so nothing is delivered for them.
- The shooter prefills as `[michaelcrigler]-footage`, from the folder name. The user: let wrong
  naming pass through.
- Ben's `INCA5002` folder sat inside the turnover folder; media scanning is recursive, so it is read.
- **The split diopter render is still typed `preVis01`**: it needs retyping `avidRef01` in Resolve
  and the CSV re-exported, or it is a QC-010 error.
- **Asked, no answer**: Ben's hand delivery names the chart
  `INCA5002_pl01_colorChart_01_raw_4k_v01.exr` and numbers frames from `_1001.exr`, which differ
  from the spec. The tool stays on spec until the user says otherwise.

## Open, with the user (newest first)

- **OQ-86's assumptions (the Avid reference), told the user**: it plays its cut rather than
  holding one frame; no `Frame:` counter; the burn-in follows the type as written
  (`<shot>_avidRef01`), the number being the reference's.
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
- **Mac checks** in `docs/MAC_SESSION.md`, newest first: unverified Fix-it claims (0.5.40), the Fix-it report by clip name (0.5.39), the LDRI (0.5.37), the stringout optimised (0.5.36), the stringout's time left (0.5.35), the HDRI pre-render and Fix-it paths (0.5.34), the QC overhaul (0.5.33), style frames
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
