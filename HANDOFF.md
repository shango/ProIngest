# Session close, 12 September 2026 (evening)

**This file is disposable and it is not the handoff record.** `PROGRESS.md` section 1 is, and it
is written to be picked up cold. This is a note about what one session did, kept because context
is being cleared. Delete it once it has been read. **If it disagrees with `PROGRESS.md` or the
docs, they win.**

It replaces the previous session's file of the same name, which closed on M4.5 complete and
named M5 as the next task.

## The one paragraph version

**No code changed. The specification did, four times, in one conversation.** The source encoding
went back to camera native log, then the colourist's answer removed the tool's input transform
from every graded chain, then the mode that was going to select between two arrangements was
deleted as the wrong shape. 873 tests still pass because nothing in `proingest/` was touched.
**A new milestone M4.6 exists and is unblocked**; M5 is still next and got slightly smaller.
**One correctness question is open, OQ-46**, and it is the only thing here that could produce a
wrong delivery.

## What the user said, in order, because the order is the argument

1. There will likely **not** be one studio standard log. Each camera's native LOG is used and
   the shooters **write the correct LOG for their camera into the clip's metadata**. Keep it
   flexible to go either way; a mode in Settings, and the studio standard would be DaVinci Wide
   Gamut / DaVinci Intermediate.
2. The cameras are likely **S-Log3, C-Log3 and BM Film**, and more may be added.
3. **If camera log, the colourist always starts from camera log**; if studio log, from DaVinci
   Wide Gamut. **ACEScc is no longer planned.**
4. The tool needs **the option of multiple input transforms based on what is written in the file
   metadata**.
5. **No special mode is needed for DaVinci Wide Gamut**: it is just another input transform
   option and should be flagged in the metadata like everything else.

Point 3 is the one that changed the pipeline. Point 5 is the one that simplified it.

## Where it landed

| | |
|---|---|
| source encoding | named **per clip in its own metadata**, always. No mode, no batch-wide value |
| `DaVinci Intermediate WideGamut` | **one entry in the input transform table**, beside the camera logs |
| the CLF | starts at **the source encoding** and ends in linear ACEScg. It is the whole transform |
| the tool's input transform | **not applied ahead of a CLF.** Applied on an aux still, and on a row with no CLF |
| ACEScct | **gone from the chain entirely** |
| a turnover | may **mix encodings** freely, one shooter on a house template and two on their cameras |

## What was checked rather than assumed

All four encodings in play resolve in the pinned config
(`studio-config-v2.2.0_aces-v1.3_ocio-v2.4`) and each built a processor through
`color.input_transform` on 2026-09-12:

| written as | colour space | the catch |
|---|---|---|
| S-Log3 | `S-Log3 S-Gamut3.Cine` and three siblings | **four candidates.** A curve name does not choose a gamut |
| C-Log3 | `CanonLog3 CinemaGamut D55` | the only one. A Canon in BT.2020 gamut has none |
| BM Film | `BMDFilm WideGamut Gen5` | **Gen 5 only.** Gen 4 and legacy "Blackmagic Design Film" are absent |
| house wide gamut | `DaVinci Intermediate WideGamut` | none |

**The transforms are not the problem; the names are.** That is OQ-34, and it is a build
requirement rather than a question now.

## The one thing that could produce a wrong delivery: OQ-46

Two of the user's answers pull in opposite directions and **both produce plausible looking
images**, which is why this is written down rather than decided.

- "The colourist always starts with camera log" reads as **the CLF contains the input
  transform**, so the tool applies the CLF alone.
- "We need multiple input transforms based on the file metadata" is a facility that only changes
  a graded plate if the CLF **does not** contain it.

**Applying both converts twice.** Nothing errors, every QC check passes, and the result reads as
a grade decision rather than a defect. It is invisible until a compositor works against it.

**Built the safe way**: the table exists and is selected per shot from the metadata, exactly as
asked, and it is applied only on chains with no CLF. If a real export shows the CLF starting
after Resolve's own IDT, the fix is one line in `ShotColor.plate_transforms` and it must land
before anything renders against a real session. Confirm it with OQ-31's single graded shot.

**QC-048 exists so a run records which chain it took**, rather than leaving it to be re-derived
from a setting nobody wrote down.

## Why the table is required whatever OQ-46 says

**An aux still is delivered ungraded and never gets the CLF**, so the tool converts it alone.
`planner._aux_plan` already builds a `ShotColor` with the encoding and no CLF. That makes a
colour chart **the one picture the tool transforms on its own authority**, and the sharpest
place in the tool to be wrong: a mis-converted chart still looks exactly like a chart, and the
artist matching against it has no way to tell. An unresolvable encoding blocks that deliverable
rather than approximating it.

Whether the session should hand the stills over already converted, deleting the tool's last
transform of its own, is **OQ-45**.

## The code is still wrong, deliberately and visibly

`clf.ShotColor.plate_transforms` returns `[input_transform, clf]`. Under the answered OQ-37 that
converts twice. **Nothing is wrong on disk**, because nothing has rendered against a real colour
session. **M4.6.2 is the fix** and it is the only chunk of M4.6 that changes a delivered plate.

`color.DEFAULT_SOURCE_ENCODING` is still `ACEScct`. It does not want a new value; it wants to
stop being a batch-wide authority, which is M4.6.1.

## Files changed

Docs only, six commits:

| file | what moved |
|---|---|
| `docs/COLOR_AND_FORMAT.md` | section 1 largely rewritten: one mechanism, no input transform ahead of a CLF, the table and where it may be applied, the aux still. Chain diagram redrawn. Section 2's "one encoding every file" replaced |
| `PRD.md` | section 4 inputs, FR-12 settings, FR-15 rewritten, M4.6 added to section 9 |
| `docs/QC_RULES.md` | **QC-046, QC-047, QC-048 new**; **QC-038 retired**; QC-018 and QC-021 reworded |
| `docs/OPEN_QUESTIONS.md` | **OQ-34 reopened then required**, **OQ-37 answered**, **OQ-39 answered then dissolved**, **OQ-44, OQ-45, OQ-46 new**, OQ-3 and OQ-42 touched |
| `PROGRESS.md` | section 1 resume block, the colour history table, the 2026-09-12 decision table, M4.6 and its five chunks, open items |
| `build-track.html` | M4.6 block, M4.5 and M5 corrected, four question rows, two reversed notes, footer. Republished, version 31 |

## Next task

**M5, the UI.** Unchanged, and slightly smaller than it was this morning: there is no source
encoding mode, so there is no control for one. The Settings Colour group carries the colour
session location, the input transform table and its overrides, the ACES config version and the
output transform.

**M4.6 can go first if preferred.** It is unblocked, it is five small chunks, and M4.6.2 is
worth doing before anyone renders against a real session.

**Two things to ask a person, neither a build task.** Which metadata field the shooters write
the log into and exactly what string (OQ-44, has a default, blocks nothing). And OQ-46 above,
against one real export.

## One thing left undecided rather than invented

There is now **no batch-wide fallback** for a clip that arrives with no encoding in its
metadata, which is right in principle: a batch-wide guess is wrong for every clip it was not
guessed for. Whether the UI should offer a **per row override** as an escape hatch is noted
under OQ-44 and is not specified. It would be new scope against FR-5, which says the list owns
every edit and there is no second surface that writes to a row.
