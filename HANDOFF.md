# Session close, 22 September 2026, evening

**This file is disposable and it is not the handoff record.** `PROGRESS.md` section 1 is, and it
was updated in the same commit as every chunk below. Delete this once it has been read. **If it
disagrees with `PROGRESS.md` or the docs, they win.**

The previous version of this file is superseded: it described a repo whose docs were correct and
whose code was four days behind them. **The code has caught up on five of seven chunks.**

## What happened this session

```
1fff753  Chunk 3: the scan is rebuilt on the handover folder
7f25507  Chunk 2: the identity model is (shot_code, kind, index)
6db01e8  Chunk 5b: no per-shot grade file, anywhere
c7d9597  Chunk 5a: the deliverables that are no longer deliverables
2f0c666  Chunk 1: the metadata CSV reader
26d15c2  The board follows the rename, and Next names the real blockers
aeb3f11  The sample folder is Turnover199 again, and the docs follow it
```

**1605 tests, `ruff`, `ruff format` and `mypy --strict` clean**, green before each commit. The count
is down from 1739 because roughly 150 tests covered things that no longer exist, and about 90 new
ones arrived with the CSV reader and the rebuilt scan.

## Read first, in this order

1. **`PROGRESS.md` section 1.** The five newest entries are this session, newest first.
2. **`docs/TO_A_WORKING_BUILD.md`.** The plan. Chunks 4, 5c, 6 and 7 are what is left.
3. **`docs/QC_RULES.md`.** QC-066 is new; QC-019, QC-039, QC-050 to QC-057 and QC-130 are retired.
4. **`docs/WORKFLOW.md`** if you have not read it: the whole workflow on one page.

## The state, in one paragraph

Point the tool at a folder holding media, Ben's EDL and his metadata CSV and it now scans it: rows
come from CSV rows, identity and encoding come from the CSV, the approved cut and the CDL come from
the EDL, and a clip with no `Shot Type` is ignored and counted. **Verified against the real media in
`Turnover199/`**, with a synthetic EDL standing in for the one that folder does not have: five rows,
the right identities, the right cut, a CDL on each, `S-Log3 S-Gamut3.Cine` resolved on all five.

## Two things block a working build, and one of them is a question for you

**Q1, and it is the only thing between here and rows that render.** Every file Ben delivers states
`24000/1001` and always will: the shooters conform to 24.000 in Resolve, a conform is a timeline
property, and Copy with trim does not rewrite the file. `qc.check_source_rate` compares that to the
project's 24 and raises an **error**, which auto-skips the row, so **every clip of every real
turnover is skipped today**. It is the last of the three blockers the 2026-09-22 review
demonstrated; the other two are fixed. The plan recommends **(b)**: a `1000/1001` relationship to
the project rate passes silently while a genuinely unconformed 25 or 30 fps file still errors.
**It was asked and not answered, so nothing was built for it.** Chunk 4 is about twenty lines once
it is decided.

**One real turnover as Ben hands it over**, media plus his EDL plus his CSV. `Turnover199/` is the
shooters' handover and has no `.edl`. Everything in the EDL half is still built to a default:
`clf.MATCH_FIELD` is `FROM CLIP NAME`, and matching on the wrong field applies a neighbouring clip's
grade, which looks plausible and is wrong.

## What is left to build

| chunk | what | state |
|---|---|---|
| **4** | Q1: `qc.check_source_rate` | **needs Q1.** Verify: real media at `24000/1001` against 24 behaves as Q1 says, and a 25 fps file still errors |
| **5c** | The two UI pieces chunk 3 made dead: the held-back turnover (M5.7.1) and normal-case ingest (M5.7.3) | ready. The scan ingests the EDL itself now, so a turnover can no longer be waiting on colour |
| **6** | OQ-60, the decode. `MediaInfo` grows the four colour fields, `ffmpeg.decode_command` asserts range and matrix, QC-018 gets built | buildable now; **wants one original camera file** to confirm the direction |
| **7** | Version bump (`pyproject.toml`, `proingest/__init__.py`, `build/build.py:66`, `docs/guide/install.md:16`), then the Mac checklist | last |

**One loose end left deliberately**: `opentimelineio` is no longer imported anywhere in
`proingest/` and is still pinned in `pyproject.toml` and hooked in `build/bundle.py`. Removing it is
a separable change that touches packaging, so it belongs with chunk 7 rather than in the middle of
the scan rebuild.

## Three decisions made along the way that are cheap to reverse

**The batch schema is version 2 and a version 1 file is refused rather than migrated**
(`TO_A_WORKING_BUILD.md` Q5). That is the right call only because no real `.pibatch` exists yet.
**If one does, say so** - the migration is small and the refusal is not.

**`ShotIdentity.stem` raises for a reference still** rather than returning
`MELT0001_colorChart01`, which is a name nothing writes. A still that cannot be named beats one
named plausibly wrong. If that is awkward in the UI, the alternative is to return the shot code
alone, never the wrong element name.

**The plan's chunk order was changed twice, both times recorded in `PROGRESS.md`.** Chunk 5 ran
before chunk 2, because the identity reshape would otherwise have carried call sites that were
about to be deleted; and chunk 5 was split into 5a, 5b and 5c, because 5c only becomes dead once
chunk 3 has landed.

## One defect worth knowing about, because it was invisible

`clf.ColorSession.event_for` compared the EDL event's stem to the row's **whole** `clip_name`. That
was correct while a row was called `MELT0001_pl01`. A row is now called `C0145.MP4`, so **every
match would have failed silently** and every row would have carried QC-066 with nothing saying why.
It compares stem to stem now, and `tests/test_scan.py` covers it. This is the exact failure OQ-30
exists to warn about, and nothing found it until real filenames went through the code.

## Where the sample folder stands

`Turnover199/` (git-ignored) is the shooters' handover: five Sony clips, `Turnover199.csv`,
`Turnover199.drt`. The `.ale` was deleted from it this session after OQ-75 closed;
`docs/SAMPLE_TURNOVER_199.md` section 8 is now its only record and says so. `TEST0001/` at the repo
root is a sample of the **exported** folder structure, not a turnover, and stays.

## Verify

```
pytest
ruff check . && ruff format --check . && mypy proingest tests build
```

The board is at <https://claude.ai/artifact/QpaPQN3c7WZn6SE7uhLHcM>.
