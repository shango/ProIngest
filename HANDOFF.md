# Handoff, 23 September 2026

**This is a short pointer, not the record.** `PROGRESS.md` section 1 holds the record: one entry
per chunk, newest first, each saying what was built and how it was verified. If this file
disagrees with `PROGRESS.md` or the docs, they are right and this file is wrong. Delete it once
it has been read.

## Where things stand

- **All eight chunks of the 2026-09-23 review are built** (`docs/REVIEW_2026-09-23.md` section 5),
  one commit each, in the order A, B, F, G, E, C, D, H. The version is **0.5.0**.
- Branch `color/cdl-in-acescct` is **17 commits ahead of origin and not pushed.** The permission
  check refused the push, so the user runs it themselves: `! git push origin color/cdl-in-acescct`.
  CI then builds `ProIngest-0.5.0.dmg`.
- **The final check was green:** 1621 tests pass (the count fell because tests for removed code
  went with it), and `ruff`, `ruff format` and `mypy --strict` are clean.
- **The real turnover, `Turnover199`, works end to end:**
  - its five rows scan with no must-fix;
  - all 12 deliverables render;
  - the tracker has one line;
  - a second Run plans nothing.

## Next

1. The user pushes the branch, and CI builds the dmg.
2. On the Mac, work through `docs/MAC_SESSION.md`, "The 0.5.0 build, in order". It opens with the
   acceptance test on Turnover199, then the per-chunk checks for B, G, E and D.

## Calls I made for the user to confirm

These were reported to the user; they are recorded in `PROGRESS.md` too.

- **Scan re-scans every turnover and keeps the editor's edits**, matched by File Name
  (`scan.carry_over`). For that reason the Ingest Colour Session button was removed.
- **A skipped row's must-fix does not block the run** (`qc.must_fix`).
- **A failed row waits for the editor's right-click Reset.** Outputs a stopped run never wrote
  resume on their own, at the same version.
- **Jobs lost when a worker dies get one more pool** (`render._run_pool`). This matters because a
  dead worker takes every job then in flight with it; that was measured on the real turnover.
- **QC-018, an info, fires on every real row**: the files state no colour matrix, so each one is
  decoded as BT.709 (D17, provisional).

## Left open

- PRD FR-10 describes three In/Out columns in the QC log, but the log has two.
- QC-043, QC-120 and QC-121 still describe the wav as a byte copy; it is now trimmed and retimed.
- FR-1's "refuse an M2 motion effect" (OQ-63) is not built.
- Non-square pixels are not handled when letterboxing (COLOR_AND_FORMAT section 4).

## Working notes

- **Do not update `build-track.html`.** It is retired (user, 2026-09-23).
- **Scratch renders of Turnover199** are in the session scratchpad under `g/`: the batch files
  `b.pibatch` and `d.pibatch`, plus `delivery/`. They are disposable.
- **Per-chunk rules:**
  - one commit per chunk, with the `PROGRESS.md` entry in the same commit;
  - a `docs/MAC_SESSION.md` line for anything that only a Mac can confirm;
  - no em dashes in any file.
