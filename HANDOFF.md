# Session close, 18 September 2026 (the grade is the CDL, applied in ACEScct)

**This file is disposable and it is not the handoff record.** `PROGRESS.md` section 1 is, and it
is written to be picked up cold. Delete this once it has been read. **If it disagrees with
`PROGRESS.md` or the docs, they win.**

## What this session did

The user decided the colour carrier: **the grade is the ASC CDL on each event of the final EDL,
applied in ACEScct, with the input transform chosen by the clip's metadata**, and ACEScct is the
standard the colourist's session is set to. A `.cube` per shot is no longer required; one
delivered for a shot is a grade-only cube out of the same managed session and takes the CDL's
place for that shot. Built and documented on the branch `color/cdl-in-acescct`, one commit.
`PROGRESS.md` section 1 has the note "The grade is the CDL, applied in ACEScct" with the detail.

## What a new session should know first

- The chain is `ShotColor.plate_transforms` in `core/clf.py` and nowhere else: into ACEScct
  (`color.to_working`), the CDL (`color.cdl_transform`) or the cube, out to ACEScg
  (`color.from_working`). One leg (`color.input_transform`) only where there is no grade.
- `color.WORKING_SPACE = "ACEScct"` is a constant shown read-only on the Settings page, not a
  setting. A value that disagreed with the session would grade wrong silently.
- QC-046 and QC-047 are errors on every plate now. Every test row fixture names an encoding.
- QC-039 measures a **step** in ACEScct through the cube alone, floor 0.07. The ratio is gone.
- `docs/COLOUR_SESSION_EXPORT.md` is the page for the colourist and **OQ-55 is the test export**
  that checks the decision. Nothing about this chain has been seen from a real session yet.
- Do not rename `core/clf.py`, `clf_path` or the `proingest/clf` attributes: schema for a word.
