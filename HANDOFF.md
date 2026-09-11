# Session close, 12 September 2026

**This file is disposable and it is not the handoff record.** `PROGRESS.md` section 1 is, and
it is written to be picked up cold. This is only a note about what one session did. Delete it
once it has been read. **If it disagrees with `PROGRESS.md` or the docs, they win.**

## What happened

No code changed. 718 tests still pass, `ruff` and `mypy --strict` are clean. The whole session
was specification, and for the second day running it **replaced a colour policy that had been
written up as settled**.

The user described the real colour workflow: colour is finished in a Resolve session where Ben
works with the AD, who also do the shot trims there. That session exports the updated final EDL,
a CLF per shot and the stringout. The tool conforms from the EDL and applies the CLF.
`docs/WORKFLOW.md` is the twenty line version and is new.

**The grade carrier went CLF, then CDL, then CLF again inside one session**, as the user
described the process in pieces. The landing point is that **both artifacts exist and do
different jobs**: the CLF is applied because it carries curves and wheels that a CDL cannot, and
the CDL is recorded in the EXR header as the readable version for anyone without an OCIO
install. Do not read the intermediate states as a change of mind about anything; they were
partial descriptions. QC-009, QC-019 and QC-039 were written, reworded and written back, which
is safe only because nothing had ever referred to them. OQ-30 and OQ-33 each closed and reopened
the same day.

Six things changed shape, five of them at the user's explicit instruction:

- **The plate is graded now.** The 2026-09-11 spec delivered it ungraded with the CDL in the
  header. Reversed, and the reasoning is in `PROGRESS.md` section 6: the old objection was that
  the grade moves later in the DI, and this workflow does the DI first.
- **The colour controls are removed** (user). Four sliders, QC-037 and OQ-32 went with them.
- **The stringout is dropped** (user). M6, `core/stringout.py`, UI_SPEC section 8, QC-140,
  QC-141, OQ-12 and OQ-15 went with it.
- **Sources are one studio standard log** (user, correcting mid-session). See below.
- **The three viewers are dropped** (user). FR-16 is now a removal note, UI_SPEC section 14 is
  empty, `core/preview.py` and M4.5.5 are gone, and a frame viewer is a v02 item again.
- **In/Out is now approved in Ben's session**, and the tool's trimming survives as the deliberate
  one-off: the quick trim not worth asking for a new EDL. QC-045 is new and reports it. The list
  is once again the only surface that writes to a row.

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
| the colour controls and then the viewers being removed | `PRD.md` section 3 and FR-16, `docs/UI_SPEC.md` sections 1 and 14 |
| trimming as an exception path, and QC-045 | `PRD.md` FR-5, `docs/QC_RULES.md` |
| QC-006/007/017/037/140/141 retired, QC-008/009/019/038/039/045 new | `docs/QC_RULES.md` |
| OQ-12/15/32/34/37/38/40 closed, OQ-30 and OQ-33 revived, OQ-35/36/39 new | `docs/OPEN_QUESTIONS.md` |
| why each choice was made | `PROGRESS.md` section 6 |
| what to do next | `PROGRESS.md` section 1 |
| the management view | `docs/ROADMAP.md`, `build-track.html` |

## Things a cold reader will not guess

- **`naming.stringout_mp4` and `naming.normalize_shooter` are now dead code**, reachable from
  tests only. They were kept on purpose: the stringout name is something a human types now, and
  the tool can still check it, exactly as with the lens grid. Do not delete them without asking.
- **The colour spec has been wrong twice.** `PROGRESS.md` section 1 has the table of what each
  version claimed. Take nothing about colour from a file dated before 2026-09-12.
- **`preview/` is untracked on purpose** and still shows the four colour sliders and the three
  viewers, so it is badly stale against UI_SPEC sections 1 and 14. `PROGRESS.md` section 8 has the URL.
- **One answer would unblock M4.5**: OQ-39, which log encoding the shooters deliver in. OQ-30
  and OQ-33, how an EDL event and a CLF each find their row, both want one real export from
  Ben's session and both have workable defaults.
- **The tool carries two grade artifacts on purpose.** Anyone reading the code later will see the
  CDL being parsed and never applied and assume it is dead. It is not: it is what goes in the EXR
  header so a delivered plate is legible to someone with no OCIO install. The CLF is what is in
  the pixels.

## Not done, deliberately

Nothing was implemented. No file under `proingest/` was touched. OQ-35 (EXR frame numbers at
1001 versus derived from timecode) was raised and left open with 1001 as the default, because
changing it touches `naming.py`, the planner, the EXR writer and their tests, and the studio's
own spec sheet is where 1001 came from.
