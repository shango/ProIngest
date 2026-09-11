# Session close, 11 September 2026, evening

**This file is disposable and it is not the handoff record.** `PROGRESS.md` section 1 is, and
it is written to be picked up cold. This is a note about what one session did, kept because the
session was unusually decision heavy and ended with context being cleared. Delete it once it
has been read. **If it disagrees with `PROGRESS.md` or the docs, they win.**

## The one paragraph version

No code changed. 718 tests pass, `ruff` and `mypy --strict` clean, and nothing under
`proingest/` was touched. The whole session was specification, and it **replaced a colour
policy that had been written up as settled earlier the same day**. This is the second session
of 2026-09-11; the first one is what it replaced. The user described how colour actually works
at this studio across several messages, each correcting or extending the last, so the docs
moved more than once before settling. **Nine commits, none pushed.**

Start at `docs/WORKFLOW.md`. It is new, it is twenty lines, and it is the shortest correct
statement of who does what.

## What the workflow is now

Colour and the cut are both finished **before** the tool runs.

1. **Shooters** deliver ProRes 4444 in **one studio standard log encoding**, the same on every
   file whatever anybody shot on, plus the `.otio` and the side files. Their offline string-out
   and CDL are a record of intent and **the tool reads neither**.
2. **Ben**, with the AD, runs a Resolve session (ACES 1.3, ACEScct timeline, primary grades
   only) where **the shot trims and the colour both happen**. It exports the **updated final
   EDL** (conform, approved In/Out, and the CDL as `*ASC_SOP` / `*ASC_SAT` lines), **a `.clf`
   per shot**, and the **stringout**.
3. **The tool** checks all media, runs QC, and produces every turnover output, in the user's own
   words. It conforms from the EDL and **applies the CLF** to everything it writes, plates
   included, so the plate is delivered graded.

## The six things that changed shape, five of them instructed

- **The plate is graded.** The morning's spec delivered it ungraded with the CDL in the header.
  Reversed, and not a contradiction: that argument was that the grade moves later in the DI, and
  this workflow does the DI first. The half of it that survives is a requirement on the CLF, and
  it is the first item in the next section.
- **The colour controls are removed.** Four sliders, QC-037 and OQ-32 went with them.
- **The three viewers are removed**, hours after being specified. FR-16 is a removal note,
  UI_SPEC section 14 is empty, `core/preview.py` and M4.5.5 are gone, and a frame viewer is a
  v02 item again, which is where it started before this morning.
- **The stringout is dropped.** M6, `core/stringout.py`, UI_SPEC section 8, QC-140, QC-141,
  OQ-12 and OQ-15 went with it. The colour session exports one.
- **Sources are one studio standard log** (a mid-session correction, see below).
- **In/Out is approved in Ben's session**, and the tool's trimming survives as the deliberate
  exception: the quick one-off not worth asking for a new EDL. QC-045 is new and reports it. The
  list is once again the only surface that writes to a row.

## The four things a cold reader will get wrong

- **The CLF must end in scene linear ACEScg with no display rendering in it.** A CLF carrying an
  output transform or a film emulation produces a plate that is display referred and claims to
  be linear. That comps wrong and looks completely normal until someone works on it. QC-039,
  error, probed rather than trusted. **This is the thing to tell Ben**, and it is the surviving
  half of the argument against a graded plate.
- **The tool carries two grade artifacts on purpose.** Anyone reading the code later will see
  the CDL parsed and never applied and assume it is dead. It is not. **The CLF is applied**,
  because it carries curves, log wheels and hue curves that a CDL cannot. **The CDL is
  recorded**, in the EXR header, as the readable version for a person or a facility with no OCIO
  install. Where they disagree the CLF is what is in the pixels, and the header says so.
- **"Studio standard log" is the most valuable line in the spec.** The user's first description
  said "log encoded ProRes per shot", which was read as camera original, and a whole per shot
  IDT apparatus was specified against it: a sidecar IDT field, a Resolve to OpenColorIO name
  map, QC-038 on an unknown name, OQ-34 and OQ-37. The user corrected it and all of that was
  deleted inside the hour. **One encoding on every file means one input transform forever.** If
  a future session finds itself building a table of IDT names, it has taken a wrong turn.
- **`naming.stringout_mp4` and `naming.normalize_shooter` are now dead code**, reachable from
  tests only. Kept on purpose: the stringout name is something a human types now and the tool
  can still check it, exactly as with the lens grid. Do not delete them without asking.

## Two things about the record itself

- **The grade carrier went CLF, then CDL, then CLF again inside this one session**, as the user
  described the process in pieces. Do not read the intermediate states as anyone changing their
  mind; they were partial descriptions. The landing point is the section above.
- **The colour spec now has three versions and two of them share a date.** 2026-09-10 was wrong,
  2026-09-11 morning was superseded, 2026-09-11 afternoon is current. `PROGRESS.md` section 1
  has the table. **Check the time on anything dated 2026-09-11 before trusting it.** Everything
  in this session was also first written as 2026-09-12 and corrected, so a stray 09-12 anywhere
  is that.

## QC and open questions

QC-006, QC-007, QC-017, QC-037, QC-140, QC-141 **retired**, IDs never reused.
QC-008, QC-009, QC-019, QC-038, QC-039, QC-045 **new**.

QC-009, QC-019 and QC-039 were written, reworded and written back inside the day as the grade
carrier moved. Safe only because nothing had ever referred to them, and `QC_RULES.md` now states
that condition and says explicitly that **it is not a precedent**.

Closed: OQ-12, OQ-15, OQ-32, OQ-34, OQ-37, OQ-38, OQ-40.
New: OQ-35, OQ-36, OQ-39. Closed and reopened the same day: OQ-30, OQ-33.

**Three questions sit with the user:**

| id | question | what it blocks |
|---|---|---|
| **OQ-39** | which log encoding the shooters deliver in. ACEScct makes the input transform identity | **starting M4.5.1** |
| OQ-30, OQ-33 | how an EDL event, and a CLF, each find their row. Both look plausible when wrong | nothing; wants one real export from Ben's session, has defaults |
| OQ-35 | EXR frame numbers at 1001, or derived from source timecode | nothing; default is 1001 |

## Where everything went

| what | where |
|---|---|
| who does what, in twenty lines | `docs/WORKFLOW.md`, **new** |
| the colour spec itself | `docs/COLOR_AND_FORMAT.md` section 1, rewritten |
| sources, and what is accepted | `docs/COLOR_AND_FORMAT.md` section 2 |
| the stringout being dropped | `PRD.md` FR-9, `docs/UI_SPEC.md` section 8 |
| the controls and then the viewers being removed | `PRD.md` section 3 and FR-16, `docs/UI_SPEC.md` sections 1 and 14 |
| trimming as an exception path, and QC-045 | `PRD.md` FR-5, `docs/QC_RULES.md` |
| every rule change | `docs/QC_RULES.md` |
| every question change | `docs/OPEN_QUESTIONS.md` |
| why each choice was made | `PROGRESS.md` section 6 |
| what to do next | `PROGRESS.md` section 1 |
| the management view | `docs/ROADMAP.md` (untracked), `build-track.html` |

## State on disk

- **Nine commits, none pushed.** Pushing is the user's call, as always in this repo.
- Build track artifact republished, **version 22**, now with a date and time stamp in the
  masthead: https://claude.ai/code/artifact/c0e6b8ac-6673-4e28-833d-7d85b5f7273a
- **`preview/` is untracked and badly stale.** It still shows the four colour sliders and the
  three viewers, both of which are gone. `PROGRESS.md` section 8 has its URL.
- `docs/ROADMAP.md` is untracked by convention and was updated: chunk F removed, chunk I
  (colour) added, estimate down from 15 to 20.5 days to **11.5 to 16.5**.

## Not done, deliberately

Nothing was implemented. The next session can start **M4.5.1** the moment OQ-39 is answered, and
can start **M4.5.2** against the documented defaults for OQ-30 and OQ-33 without waiting for
anyone. OQ-35 was raised and left open with 1001 as the default, because changing it touches
`naming.py`, the planner, the EXR writer and their tests, and the studio's own spec sheet is
where 1001 came from.
