# Session close, 12 September 2026 (afternoon)

**This file is disposable and it is not the handoff record.** `PROGRESS.md` section 1 is, and it
is written to be picked up cold. This is a note about what one session did, kept because context
is being cleared. Delete it once it has been read. **If it disagrees with `PROGRESS.md` or the
docs, they win.**

It replaces the previous session's file of the same name, which closed on a day of specification
changes with no code written. That one was deleted in this session, at its own instruction.

## The one paragraph version

**M4.6.2 is built**, which is the correctness half of M4.6 and the only chunk of it that changes
a delivered plate: the tool no longer converts anything ahead of a CLF. **876 tests, `ruff` and
`mypy --strict` clean.** One new open question came out of building it, **OQ-47**, and it is the
only thing on the board that can refuse a valid delivery. M5 is still next, and so is the rest
of M4.6, starting with M4.6.1.

## What was wrong, and what it is now

`clf.ShotColor.plate_transforms` returned `[input_transform, clf]`. Under the answered OQ-37 the
colourist starts each shot's CLF at whatever that clip is encoded in, so the conversion was
already inside the CLF and the tool applied it a second time. **Nothing raised, every QC check
passed, and the result reads as a grade decision rather than a defect.** Nothing was ever
delivered wrong, because nothing has rendered against a real colour session (OQ-31).

| | before | now |
|---|---|---|
| graded plate | input transform, then the CLF | **the CLF alone** |
| graded reference | the same, plus the output transform | **the CLF plus the output transform** |
| aux still, and any row with no CLF | input transform to ACEScct, then `plate_transform` to ACEScg | **one leg, source encoding to ACEScg** |

`color.WORKING_SPACE` and `color.plate_transform` are **deleted**. `color.input_transform` now
goes straight to `PLATE_SPACE`, so ACEScct is out of the chain entirely and there is no
intermediate space to arrive in with half a chain applied. `clf.ACESCCT_WHITE` is now
`clf.LOG_WHITE`, because the probe value no longer belongs to one encoding.

## The one thing to take from it if nothing else

**The tests now pin which transforms a chain contains, not only what it does to a pixel.** The
extra leg was identity under the default source encoding, so every numeric test in the suite
passed against the bug and always would have. `test_the_tool_converts_nothing_ahead_of_a_clf`
is the numeric test that can see it, and it works by setting the source encoding to something
the CLF does **not** start at, which is the real case rather than the fixture's convenience.

## OQ-47, the new one, and the only item that can refuse a good delivery

**QC-039's scene linear probe is calibrated on ACEScct and the CLF no longer starts there.**
It feeds log white through the CLF and wants the answer above `clf.SCENE_LINEAR_FLOOR`, 2.0.
Measured on 2026-09-12 against the pinned config:

| CLF starts at | white is worth | four stops down |
|---|---|---|
| ACEScct, BMD Film Gen 5 | 222.9 | 13.9 |
| DaVinci Intermediate | 100.0 | 6.3 |
| S-Log3 | 38.4 | 2.4 |
| **C-Log3** | **14.7** | **0.92** |
| a baked display rendering | about 1.0 | about 1.0 |

So for C-Log3, one of the three cameras named for this show, **the probe cannot separate a dark
grade from a display rendering at all**. It fails in the safe direction, an error on a good CLF
rather than a bad plate delivered, and nothing has rendered against a real session yet.

**The replacement is measured, not estimated**: `out(1.0) / out(0.9)` answers 1.88 to 3.37 across
all five encodings and is **exactly invariant to how dark the grade is**, because a grade scales
both samples; a display rendering flattens the top and answers 1.010 to 1.015. Anything near 1.4
splits them with an order of magnitude of margin.

**Not changed in M4.6.2**, because it is QC-039's definition rather than this chunk's chain, and
`docs/QC_RULES.md` is where a rule's meaning lives. It is one small chunk whenever the user wants
it. The full write-up with the numbers is OQ-47 in `docs/OPEN_QUESTIONS.md`, with a pointer in the
QC-039 row and in `PROGRESS.md` section 9.

## Files changed

| file | what moved |
|---|---|
| `proingest/core/color.py` | `WORKING_SPACE` and `plate_transform` deleted, `input_transform` collapsed to source to ACEScg, `DEFAULT_SOURCE_ENCODING` rewritten as the placeholder M4.6.1 removes, module chain diagram redrawn |
| `proingest/core/clf.py` | `plate_transforms` returns the CLF alone when there is one, `ACESCCT_WHITE` renamed `LOG_WHITE`, `SCENE_LINEAR_FLOOR` docstring carries the OQ-47 exposure |
| `tests/test_color.py`, `tests/test_clf.py`, `tests/fixtures/color.py` | the chain tests, three new composition pins, and `CLF_SOURCE` so a fixture no longer borrows a constant of the tool's |
| `docs/OPEN_QUESTIONS.md` | **OQ-47 new** |
| `docs/QC_RULES.md` | QC-039 row points at OQ-47 |
| `PROGRESS.md` | resume block, the M4.6.2 note, the chunk table, section 9's open items, test counts recounted rather than carried forward |
| `build-track.html` | M4.6 from blocked to part built, the chunk in plain terms, an OQ-47 row, stats and footer. Republished, **version 32** |

## Next task

**M4.6.1**, or M5. M4.6.1 is `ShotRow.source_encoding` read per row, and it is what finally
removes `color.DEFAULT_SOURCE_ENCODING` as a batch-wide authority over what is specified to be a
per clip fact. Note that M4.6.1 on its own leaves a row whose metadata names no encoding with
nothing to convert an aux still by; that is what QC-046 and QC-047 are for, and they are M4.6.4,
so the two want to land close together.

**Nothing is blocked.** OQ-44 (which metadata field, and what string) has a default. OQ-46 wants
one real export. OQ-47 wants a decision rather than an investigation.
