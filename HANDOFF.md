# Session close, 12 September 2026 (evening)

**This file is disposable and it is not the handoff record.** `PROGRESS.md` section 1 is, and it
is written to be picked up cold. This is a note about what one session did, kept because context
is being cleared. Delete it once it has been read. **If it disagrees with `PROGRESS.md` or the
docs, they win.**

It replaces the previous session's file of the same name, which closed on M4.6.2.

## The one paragraph version

**M4.6 is finished except for M4.6.5.** Three chunks landed in one run: the source encoding
became a per row fact (M4.6.1), the input transform table was built (M4.6.3), and the scan now
reads the encoding off the clip and reports what it found through QC-046, QC-047 and QC-048
(M4.6.4). **924 tests, `ruff` and `mypy --strict` clean.** Nothing here changes a delivered
plate: M4.6.2, last session, was the chunk that could. **M5 is next**, and M4.6.5 is the small
bookkeeping chunk beside it.

## What each chunk did, in one line

| chunk | what changed |
|---|---|
| M4.6.1 | `ShotRow.source_encoding`; `color.DEFAULT_SOURCE_ENCODING` **deleted**; `plan_batch`, `ColorSession.shot_color` and `run --source-encoding` each lost a parameter |
| M4.6.3 | `color.INPUT_TRANSFORMS` and `color.resolve_encoding`; `clf.resolved_encoding` is where a row's written name becomes a colour space |
| M4.6.4 | `scan.SOURCE_ENCODING_KEY`, `timeline.ClipRecord.metadata`, `MediaInfo.tags`, and QC-046, QC-047, QC-048 |

## The four decisions worth knowing about

- **The default encoding was deleted rather than given a better value.** A batch-wide guess is
  wrong for every clip it was not guessed for, and wrong silently. The cost is that a chain with
  neither a CLF nor an encoding cannot be built: `plate_transforms` refuses it rather than
  writing log pixels under an ACEScg header.
- **`proingest run --source-encoding` is gone.** It was the batch-wide authority under another
  name. Nothing replaces it; the clip's metadata is the only source.
- **OQ-44 is built to a default and the default is a guess with a reason.** The field is
  `Input Color Space`, Resolve's own Media Pool column for the input transform. **Nothing has
  confirmed Resolve exports it into the `.otio`.** One real export settles it and the fix, if it
  is wrong, is one string in `scan.py`. Two lines are now on `docs/MAC_SESSION.md` for it.
- **QC-046 and QC-047 are errors only on an aux still**, which is what `QC_RULES.md` specifies:
  the CLF carries every other row, so blocking a plate over a string the plate never uses is a
  rule that gets switched off. The seam this leaves is in section 1 of `PROGRESS.md`: a row with
  no CLF *and* no encoding also has nothing to render through, and the rules cannot say so at
  scan time because no row has a CLF then. The render refuses it and QC-100 carries the reason.
  **M5 is when that can be reconsidered**, because that is when the rules learn whether a colour
  session exists at all.

## Two things that would have passed unnoticed

- **The fixture turnover now names an encoding in its clips' own metadata**, nested the way
  Resolve nests what it exports, so the scan's walk by field name is exercised rather than a
  flat dict nothing real would produce. The scaffolding M4.6.1 needed in `tests/test_cli.py`,
  which stamped an encoding onto a saved batch, is deleted as promised.
- **`S-Log3` resolving to nothing is the point, not a gap.** It names four colour spaces in the
  pinned config. The error names all four, so the answer is an instruction to the shooters.

## Next task

**M5**, the UI, or **M4.6.5**, which is `proingest/source_encoding_origin` in the EXR header and
the source encoding column in the QC log beside the CLF one. M4.6.5 touches no pixel.

**Nothing is blocked.** OQ-46 wants one real export before a delivery depends on it, OQ-47 wants
a decision rather than an investigation, and OQ-44 is now a line on the Mac session checklist
rather than a question holding anything up.
