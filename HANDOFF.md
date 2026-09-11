# Session close, 11 September 2026

**This file is disposable and it is not the handoff record.** `PROGRESS.md` section 1 is,
and it is written to be picked up cold. This is only a note about what one session did,
kept because the session was unusually decision heavy and ended with context being cleared.
Delete it once it has been read. **If it disagrees with `PROGRESS.md` or the docs, they win.**

## What happened

No code changed. 718 tests still pass, `ruff` and `mypy --strict` are clean. The whole
session was specification, and it **reversed a decision that was recorded as settled**.

- **OQ-17 was wrong.** It said sources arrive display referred with an sRGB curve baked in.
  They arrive **log encoded**. The user researched it and corrected it.
- A full colour pipeline was designed and written into the docs: ACEScct in, ACEScg
  ungraded plate out, graded sRGB viewing copies, OpenColorIO for every transform, the CDL
  read from the EDL and carried in the EXR header.
- Three steppable viewers and four per clip colour controls were specified. Stepping a
  viewer trims the row.
- `docs/COLOR_AND_FORMAT.md` section 1 was **rewritten, not amended**, because amending it
  would have left two readings in one document.

## Where everything went

| what | where |
|---|---|
| the colour spec itself | `docs/COLOR_AND_FORMAT.md` section 1 |
| the viewers and the colour controls | `docs/UI_SPEC.md` section 14, PRD FR-16 |
| inputs, outputs, FR-1, FR-5, FR-15, FR-16 | `PRD.md` |
| QC-006, 007, 017, 018, 037; QC-020/021 rewritten | `docs/QC_RULES.md` |
| OQ-3 closed, OQ-6 and OQ-17 superseded, OQ-29 to OQ-32 new | `docs/OPEN_QUESTIONS.md` |
| why each choice was made | `PROGRESS.md` section 6 |
| what to do next | `PROGRESS.md` section 1 |

Two commits, both pushed: `df009a0` (the spec) and whatever carries this file.

## Things a cold reader will not guess

- **`preview/` is untracked on purpose.** The interface mock was updated this session with
  the viewers and the colour controls and republished, but there is no commit for it. The
  artifact and the copy on this machine are the only versions. `PROGRESS.md` section 8 has
  the URL.
- **M3 is marked complete and its reference encode is wrong.** It applies no colour
  transform, which was right under OQ-17's old premise. No test can catch it: the tests
  assert the encode does what it was told to do. M4.5.4 fixes it.
- **The next task is a choice**, and `PROGRESS.md` section 1 makes the case for M4.5 over
  M4.3: the QC log wants the CDL and the AD notes as columns, so doing colour first means
  the exports get written once.

## Not done, deliberately

Nothing was implemented. No file under `proingest/` was touched. Four questions stayed
open rather than being guessed at, and they are OQ-29 to OQ-32.
