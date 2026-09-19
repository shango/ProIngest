# Session close, 19 September 2026 (the review, and the misalignment it found)

**This file is disposable and it is not the handoff record.** `PROGRESS.md` section 1 is, and it
is written to be picked up cold. Delete this once it has been read. **If it disagrees with
`PROGRESS.md` or the docs, they win.**

## Read first

`docs/REVIEW_2026-09-19.md`. It is the whole session in one page: what the review found, what
the user decided, the verified-against-unverified ledger, and OQ-56 to OQ-67.

## The rule for this project from now on

**Only verified facts go into the plan.** The user said so on 2026-09-19, having suspected the
misalignment the review confirmed. An assumption is researched to a source, asked of the user,
or written as a question with an owner. Nothing is built on it while it is open. The memory
`verified-facts-only` records this.

## What is wrong in the docs right now, and known to be

- Sources are **camera-native**, not ProRes 4444 (OQ-3, COLOR_AND_FORMAT section 2, PRD,
  QC-020, QC-021). Not yet corrected: the respec waits on the clip (OQ-56).
- The scan reads an **OTIO** that will never exist; Ben's EDL with the CDL is the only timeline
  input (OQ-57). Not yet rebuilt.
- `docs/COLOUR_SESSION_EXPORT.md` and the 2026-09-18 CDL decision stand, but say nothing about
  camera-native sources or single-track timelines yet.

## Do not

- Do not start the respec or the EDL-only scan before the clip has been probed (OQ-58, OQ-61,
  OQ-62). That is the "no assumptions" rule applied to the next chunk.
- Do not build the turnover default before OQ-59's two answers.
- Do not merge PR #12 without the user: it is green and mergeable, and the user has not said.

## Code state

Branch `color/cdl-in-acescct`, PR #12 open, CI green on four jobs. 1739 tests, ruff and mypy
clean. This session added no code; it added `docs/REVIEW_2026-09-19.md`, OQ-56 to OQ-67, this
note, the PROGRESS paragraph and the Build Track update.

## When the clip arrives

Probe it with the bundled ffprobe: `color_range`, `color_space`, `color_transfer`, the
`timecode` tag, `pix_fmt`, and every format and stream tag; then `exiftool`-style acquisition
metadata if ffprobe shows none (Sony writes `CaptureGammaEquation` and `CaptureColorPrimaries`).
Compare the filename with the clip name the user gives. Write the answers into the ledger in
`docs/REVIEW_2026-09-19.md` and the OQ rows, then start the respec.
