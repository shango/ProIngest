# Session close, 22 September 2026

**This file is disposable and it is not the handoff record.** `PROGRESS.md` section 1 is. Delete
this once it has been read. **If it disagrees with `PROGRESS.md` or the docs, they win.**

The previous version of this file is superseded: its traps are all cleared. The shooters' spec CSV
in `docs/` **is** the current one now, `Turnover199/` has been replaced by `Turnover199_ForBEN/`
(git-ignored), and the four sessions of uncommitted docs work is committed as of this note.

## Read first, in this order

1. `PROGRESS.md` section 1, the three entries dated 2026-09-22.
2. **`docs/WORKFLOW.md`**. The whole workflow on one page.
3. **`docs/REVIEW_2026-09-22.md`**. The code review: what is stale, what is structurally wrong,
   and six questions nobody has answered.
4. `docs/SAMPLE_TURNOVER_199.md` sections 7 and 8, the real turnover's evidence.

## The state

**Version 0.3.0.** 1739 tests, `ruff`, `ruff format` and `mypy --strict` all green.
**No feature code has changed since 2026-09-16.** The docs are four sessions ahead of it, on
purpose, and the review is the list of what that costs.

## The one thing to know before testing a build

**The tool cannot process a real turnover yet**, and a dmg from this commit will show it. Three
errors fire on every row of `Turnover199_ForBEN`, each enough on its own to skip the row:

- **QC-010**, because `naming.parse_clip_name("C0145.MP4")` returns None. Identity is metadata now.
- **QC-046 / QC-047**, because `scan.SOURCE_ENCODING_KEY` is still `Input Color Space` and there is
  no CSV reader. The data is in the CSV and resolves correctly; nothing reads it.
- **QC-026**, because the files state 24000/1001 while the project asserts 24. **This one is a spec
  defect rather than staleness** and is Q1 of the review.

Also: the folder has no `.edl`, so it is QC-001 before any of that. It is the shooters' handover to
Ben, not Ben's to the tool.

## What is ready to build

`docs/REVIEW_2026-09-22.md` section 4 is the dependency-ordered list. In short: the CSV reader, the
identity model reshaped to `(shot_code, kind, index)`, the scan rebuilt on folder + EDL + CSV, Q1
answered, the EDL read moved into the scan, the removals (side files, camData, BTS, lens grid,
stringout, cube, `_color`), and OQ-60's decode assertions with QC-018.

## Still blocked on a person

| what | ID |
|---|---|
| QC-026 at 23.976: warning, silent on a 1000/1001 conform, or retired | review Q1 |
| One original camera file, for the BT.601/BT.709 decode | OQ-60 |
| The per-turnover default input transform, two decisions | OQ-59 |
| One test export from Ben: EDL, CSV, stringout, one graded shot | OQ-55 |
