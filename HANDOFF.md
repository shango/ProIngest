# Session close, 22 September 2026

**This file is disposable and it is not the handoff record.** `PROGRESS.md` section 1 is. Delete
this once it has been read. **If it disagrees with `PROGRESS.md` or the docs, they win.**

The previous version of this file is superseded: its traps are all cleared. The shooters' spec CSV
in `docs/` **is** the current one now, `Turnover199/` has been replaced by `Turnover199_ForBEN/`
(git-ignored), and the four sessions of uncommitted docs work is committed as of this note.

## Read first, in this order

1. **`docs/TO_A_WORKING_BUILD.md`.** The plan: what is needed from the user, and the seven chunks
   that get from here to a build that ingests a real turnover. **Start here.** Everything below is
   the reasoning behind it.
2. `PROGRESS.md` section 1, the three entries dated 2026-09-22.
3. **`docs/WORKFLOW.md`**. The whole workflow on one page.
4. **`docs/REVIEW_2026-09-22.md`**. The code review: what is stale, what is structurally wrong, and
   the questions behind Part 1 of the plan.
5. `docs/SAMPLE_TURNOVER_199.md` sections 7 and 8, the real turnover's evidence.

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

**`docs/TO_A_WORKING_BUILD.md` Part 2** is the seven chunks with a verification step each.

## The two things that actually block, out of that page's Part 1

1. **Q1: what should QC-026 do at 23.976?** Recommended: pass silently on a 1000/1001 relationship
   to the project rate, so a genuinely unconformed 25 or 30 fps file still errors. **No row of any
   real turnover can render until this is decided.**
2. **One real turnover folder as Ben hands it over**: media, his EDL, his CSV, together. One shot is
   enough. Nothing in the EDL half of the tool has ever met a real file, and matching an event on
   the wrong field silently applies a neighbouring clip's grade.

Those two are the working build. Two more improve it: **one original camera file** (OQ-60, the
BT.601/BT.709 decode, the only defect that ships wrong pixels quietly) and **OQ-55's test export**,
which can arrive in the same folder as item 2.

Everything else in Part 1 has a stated default and will be built to it.
