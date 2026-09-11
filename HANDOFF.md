# Session close, 12 September 2026

**This file is disposable and it is not the handoff record.** `PROGRESS.md` section 1 is, and
it is written to be picked up cold. This is only a note about what one session did. Delete it
once it has been read. **If it disagrees with `PROGRESS.md` or the docs, they win.**

## What happened

No code changed. 718 tests still pass, `ruff` and `mypy --strict` are clean. The whole session
was specification, and for the second day running it **replaced a colour policy that had been
written up as settled**.

The user described the real colour workflow: colour is finished in a Resolve session with Ben
after the AD meeting, exported as one CLF per shot, and applied by the tool to everything it
writes. `docs/WORKFLOW.md` is the twenty line version and is new.

Four things changed shape, three of them at the user's explicit instruction:

- **The plate is graded now.** The 2026-09-11 spec delivered it ungraded with the CDL in the
  header. Reversed, and the reasoning is in `PROGRESS.md` section 6: the old objection was that
  the grade moves later in the DI, and this workflow does the DI first.
- **The colour controls are removed** (user). Four sliders, QC-037 and OQ-32 went with them.
- **The stringout is dropped** (user). M6, `core/stringout.py`, UI_SPEC section 8, QC-140,
  QC-141, OQ-12 and OQ-15 went with it.
- **Sources are one studio standard log** (user, correcting mid-session). See below.

## The correction worth reading

The user's first description said "log encoded ProRes per shot". That was read as camera
original, and a full per shot IDT apparatus was specified against it: a sidecar IDT field, a
Resolve to OpenColorIO name map, QC-038 on an unknown name, OQ-34 and OQ-37. The user then
said the shooters deliver a **studio standard** log encoding, and all of it was deleted inside
the hour.

**One encoding on every file means one input transform forever.** No per shot IDT, no name
mapping between two tools that do not agree, no "which exposure index". If a future session
finds itself building a table of IDT names, it has taken a wrong turn. Which encoding it is
is OQ-39, and ACEScct makes the transform identity.

## Where everything went

| what | where |
|---|---|
| who does what, in twenty lines | `docs/WORKFLOW.md`, new |
| the colour spec itself | `docs/COLOR_AND_FORMAT.md` section 1, rewritten again |
| sources, and what is accepted | `docs/COLOR_AND_FORMAT.md` section 2 |
| the stringout being dropped | `PRD.md` FR-9, `docs/UI_SPEC.md` section 8 |
| the colour controls being removed | `PRD.md` section 3 and FR-16, `docs/UI_SPEC.md` section 14 |
| QC-006/007/017/037/140/141 retired, QC-008/009/019/038/039 new | `docs/QC_RULES.md` |
| OQ-12/15/32/34/37/38 closed, OQ-30 superseded, OQ-33/35/36/39 new | `docs/OPEN_QUESTIONS.md` |
| why each choice was made | `PROGRESS.md` section 6 |
| what to do next | `PROGRESS.md` section 1 |
| the management view | `docs/ROADMAP.md`, `build-track.html` |

## Things a cold reader will not guess

- **`naming.stringout_mp4` and `naming.normalize_shooter` are now dead code**, reachable from
  tests only. They were kept on purpose: the stringout name is something a human types now, and
  the tool can still check it, exactly as with the lens grid. Do not delete them without asking.
- **The colour spec has been wrong twice.** `PROGRESS.md` section 1 has the table of what each
  version claimed. Take nothing about colour from a file dated before 2026-09-12.
- **`preview/` is untracked on purpose** and still shows the four colour sliders, so it is now
  stale against UI_SPEC section 14. `PROGRESS.md` section 8 has the URL.
- **Two answers would unblock M4.5**: OQ-39 (which log) and OQ-33 (what the sidecar is). The
  second one genuinely blocks M4.5.2, because it is a reader with no format to read.

## Not done, deliberately

Nothing was implemented. No file under `proingest/` was touched. OQ-35 (EXR frame numbers at
1001 versus derived from timecode) was raised and left open with 1001 as the default, because
changing it touches `naming.py`, the planner, the EXR writer and their tests, and the studio's
own spec sheet is where 1001 came from.
