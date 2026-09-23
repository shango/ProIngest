# To a working build

Written 2026-09-22 at the user's request: **everything needed from them, and the instructions to do
the work.** Read `PROGRESS.md` section 1 and `docs/REVIEW_2026-09-22.md` first; this page is the
plan, not the diagnosis.

**Definition of a working build**, the thing this page is aimed at, and the acceptance test for it:

> Point the tool at one folder holding Ben's media, his EDL and his CSV. Scan. Every clip carrying a
> `Shot Type` becomes a row with a shot code, a clip type, an encoding, an approved In/Out and a
> CDL, and no blocking QC. Press Run. Every deliverable lands, named to the spec, verified, with
> both spreadsheets written.

Nothing below is worth doing if that sentence is wrong. Say so before the work starts rather than
after.

---

## Part 1. What is needed from the user

### 1.1 One decision that blocks everything

**Q1. QC-026 fires on every clip of every real turnover.** The delivered files state `24000/1001`
and always will: the shooters conform to 24.000 in Resolve, but a conform is a **timeline** property
and Copy with trim does not rewrite the file's rate. `check_source_rate` compares the file's stated
rate to the project's 24 and raises an **error**, which auto-skips the row (PRD FR-6).

Demonstrated on `Turnover199`: `C0145`, `C0148`, `C0152` all `stated_rate=24000/1001` ->
QC-026 error. The suite never caught it because `tests/fixtures/media.py` sets `FPS = 24` and
generates containers at exactly `24/1`.

| option | behaviour |
|---|---|
| **(b), recommended** | A `1000/1001` relationship to the project rate is the normal conform and passes **silently**. A genuinely unconformed 25 or 30 fps file still errors |
| (a) | Downgrade to warning. Every row of every turnover carries a warning forever |
| (c) | Retire the rule |

**(b)** keeps the rule meaningful for the case it was written for and silent for the case that is
now universal. **Until this is answered, no row of any real turnover can render**, so it is the one
item on this page that stops the work rather than shaping it.

### 1.2 One artifact that is worth more than all the others

**A real turnover folder as Ben hands it over: the media, his EDL, and his CSV, together.** One shot
is enough. `Turnover199` is the shooters' handover and has **no `.edl`**, so nothing in the
EDL half of the tool has ever been tested against a real file.

Everything in this list is currently **built to a default and unverified**:

- **Which EDL field identifies an event** (OQ-30). `clf.MATCH_FIELD` is `FROM CLIP NAME`, matched
  without extension or case, with a reel-plus-source-timecode fallback. Whether Resolve's CDL export
  populates that field at all on this export is unknown. **Matching on the wrong field silently
  applies a neighbouring clip's grade**, which looks plausible and is wrong.
- The exact shape of the `*ASC_SOP` / `*ASC_SAT` comment lines Resolve writes.
- Whether the event's source In/Out is where the approved cut actually is.
- Whether one event exists per CSV row, and in what order.

Without it, chunk 3 below is written against an assumption in exactly the way the
`verified-facts-only` rule exists to prevent. **With it, chunk 3 is a morning's work.**

### 1.3 One artifact for the largest known colour defect

**One original camera file, straight off the card, or its `M01.XML` sidecar** (OQ-60). The decode
currently asserts no matrix and no range, and is measurably a BT.601 decode where it should almost
certainly be BT.709: **1.94% mean and 21.3% peak error in the delivered plate**. This is the only
defect in the tool that ships wrong pixels under a correct filename; everything else fails loudly.

The consolidated files cannot answer it, because Resolve's rewrap strips Sony's metadata track. The
delivered MP4's only tags are `encoder`, `handler_name` and `timecode`.

### 1.4 One export that validates the colour chain, and can arrive with 1.2

**OQ-55's test export**: one shot graded with the wheels in node one of an ACEScct colour-managed
session, handed over as the folder in 1.2 **plus the stringout**. The tool renders that shot and its
reference mp4 is compared against Ben's stringout. That single comparison confirms four things at
once, none of which has ever been observed:

1. the session's timeline really is ACEScct, not ACEScc;
2. Resolve's CDL export out of node one round-trips the wheels closely enough;
3. **the tool's input transform for that camera lands where Resolve's own `Input Color Space` for the
   same camera lands** - the two now convert the same clip independently from the same string and
   would disagree silently;
4. the CDL replayed in ACEScct matches what the room approved.

`docs/COLOUR_SESSION_EXPORT.md` is the page to hand Ben. It already asks for exactly this.

### 1.5 Decisions that will be built to a stated default unless corrected

These do not block. Each has a defensible default and the default is what gets built. **Correcting
one later is cheap; finding out afterwards that it was wrong is not.**

| # | question | default to be built |
|---|---|---|
| Q2 | A CSV row with no EDL event; an EDL event with no CSV row | Row with no event is an **error on the row** under a new ID beside QC-009: it has no approved cut and no grade, so it cannot render. Event with no row is **turnover-scope info**, since Ben cutting something the CSV does not describe is his business until it is not |
| Q3 | Which frame of a reference still is delivered | **The EDL event's In.** The stills are one timeline frame inside a 49-frame file, so something has to choose, and the event's In is the only frame anybody approved. Makes the EDL load bearing for stills |
| Q4 | Asymmetric handles | **Normal.** Measured: `C0145` has 24 head and 24 tail, `C0152` has 24 head and **8** tail. Nothing asserts symmetry; QC-030 stays a warning on the "expected handle frames" setting |
| Q5 | Old `.pibatch` files | **Refuse, do not migrate.** Bump `schema_version` to 2 and refuse 1 with a clear message. Less code than a migration nobody will run - **wrong if any real batch already exists**, so say so if one does |
| Q6 | Precedence for the encoding lookup | **Two tiers, not three**: the CSV's `Gamma Notes` + `Color Space Notes`, then OQ-59's per-turnover default. The container-tag tier is dropped, because real media carries nothing |
| OQ-59 | The per-turnover default input transform | **Applies only where the clip names nothing**, never overriding a name the table cannot resolve, and **one camera per turnover**. A misspelt Sony clip falling back to a Canon default is the silent wrong plate the table exists to prevent |
| OQ-35 | EXR frame numbers | **1001.** The studio's own spec sheet says so and source timecode is already in every EXR header |

---

## Part 2. The build

Seven chunks, in dependency order. **One commit each**, `PROGRESS.md` updated in the same commit
(`CLAUDE.md`), a line in `docs/MAC_SESSION.md` in the same commit for anything only a person on a
Mac can confirm, and `build-track.html` republished with whichever commit lands the work
(memory `keep-build-track-current`).

**Green before every commit**, no exceptions:

```
pytest
ruff check . && ruff format --check . && mypy proingest tests build
```

### Chunk 1. The metadata CSV reader

New module, `proingest/core/metacsv.py`. Nothing like it exists: there is no `import csv`, no
`utf-16`, no `Shot Type` anywhere in `proingest/` today.

- UTF-16 with a BOM. **`csv.reader`, never `csv.DictReader`**, because of the duplicate column.
- **Dynamic columns.** Resolve writes only the columns that carry a value, so an absent column is
  the normal way a field is empty, not a malformed file.
- **The duplicate `Shot Type` column (QC-065).** Positions 12 and 44 in the real file: Resolve's
  built-in **framing** field and the shooters' custom field of the same name. Take the column that
  resolves to a known clip type, prefer the custom field where both resolve, warn when they differ.
- Rows keyed by `File Name`, compared casefolded.
- **Read identity and encoding and nothing else.** `Frames`, `Start TC`, `End TC` and
  `Clip Directory` in the real file describe the **pre-consolidation originals** and are wrong for
  the delivered media by 2x to 8x. ffprobe is the authority on every media fact.

**Verify**: reads `Turnover199/Turnover199.csv` to five rows with `Shot Type` of `pl01`,
`colorChart`, `mirrorBall`, `greyBall`, `cp01` and `S-Log3 S-Gamut3.Cine` on all five. A synthetic
fixture covers an absent `Shot Type` column, two that disagree, a blank `Shot`, and a row whose
`File Name` matches nothing in the folder.

### Chunk 2. The identity model

`naming.ShotIdentity` is `(show, shot, elem_type, elem_index, aux, aux_index)`, where a reference
still hangs off an element. **That shape is wrong**, not just its values: in the CSV `colorChart` is
a `Shot Type`, a peer of `pl01`.

- Reshape to **`(shot_code, kind, index)`**, `kind` drawn from the plate types **and** the still
  types.
- **A reference still is keyed to the shot code**: `MELT0001_colorChart_01_4k_v01.exr`, no element
  segment. Both `aux_still_exr` and the `aux_still` row of `_output_patterns` move together, because
  QC-151 round-trips them.
- Parse casefolded; **a bare code means index `01`**. Load bearing, not lenient: three of the five
  real rows are bare.
- Delete `parse_clip_name`, `LENS_GRID_PATTERN`, `parse_lens_grid_name`, `LensGridIdentity`.
- `planner.effective_identity` loses its premise that element and index come from the clip name.

**Verify**: QC-151's round trip; a golden test per naming example in the shooters' spec CSV; the
casefold-injectivity proof re-run over the pinned config.

### Chunk 3. The scan, rebuilt

**Wants 1.2.** Buildable without it, but then the EDL half is written on an assumption.

- Inputs are **the folder, one `.edl`, one `.csv`**. Drop OTIO: `timeline.TIMELINE_EXTENSIONS`,
  `find_timeline_files`'s `.otio` preference, the `.otio` branch of `load`.
- **Rows come from CSV rows**, not from timeline clips. A clip with **no `Shot Type` is ignored** and
  counted by **QC-064** at turnover scope.
- QC-001 rescoped to "Ben's EDL or his metadata CSV is missing". QC-003 retired, the ID not reused.
- `scan.SOURCE_ENCODING_KEY` dies; the encoding comes from the CSV's two fields joined in order.
- **Move the EDL read into the scan** (review finding G). `plan_batch`'s docstring still describes
  the two-phase ingest OQ-74 collapsed. `clf.ingest` survives for a **revised** EDL only.
- `Turnover` grows an `edl_path` and a `csv_path` in place of `timeline_path`.

**Verify**: the real folder plus a real EDL scans to one row per `Shot Type` row; the folder without
an EDL is QC-001 with no rows; a folder whose CSV has no `Shot Type` column produces zero rows and
one QC-064 naming all five files.

### Chunk 4. Q1

Whatever 1.1 decides. **Until this lands every row of every real turnover is auto-skipped**, so the
acceptance test at the top of this page cannot pass without it.

**Verify**: real media at `24000/1001` against a project rate of 24 behaves as Q1 says, and a 25 fps
file still errors.

### Chunk 5. The removals

Nothing here is subtle; it is large and it is mechanical. `docs/REVIEW_2026-09-22.md` sections D, E
and the `_color` half of B are the inventory.

Side files (HDRI, camData), BTS, the lens grid, the stringout, the cube, `_color`, and the three
pieces of UI that now do nothing: `_color` discovery (M5.13), the held-back-turnover behaviour
(M5.7.1), normal-case ingest (M5.7.3). Whole files: `proingest/core/camdata.py`,
`tests/test_camdata.py`.

Removals reach further than `core/`: `ui/metadata.py`, `ui/shot_model.py` and `core/exports.py` all
surface side files and camData in columns and sheets that will have nothing to show.

**QC-055 survives and matters more than before**: a reference still is one timeline frame inside a
49-frame file, so "more than one frame, first will be used" is now the normal case.

**Verify**: suite green; `grep -rn "hdri\|camdata\|stringout\|lens_grid\|\.cube\|_color" proingest/`
returns only deliberate mentions; no orphaned imports.

### Chunk 6. OQ-60, the decode

**Wants 1.3** to confirm the direction. The assertion itself is buildable now and is worth building
either way, because asserting the wrong matrix loudly beats assuming one silently.

- `models.MediaInfo` grows `color_range`, `color_space`, `color_transfer`, `color_primaries`. **It
  has none of them today, which is why QC-018 could never have been written.**
- `media.probe` fills them from ffprobe.
- `ffmpeg.decode_command` passes **an explicit `-color_range` and matrix**, from what the file
  declares. The only `bt709` in that file today is at line 496 and tags the **output** mp4.
- **QC-018 built**: fires when the container's own tags contradict the encoding the CSV names, and
  when the file declares nothing.

**Verify**: the decode command contains the flags; a BT.709-tagged file and a BT.601-tagged file
decode to measurably different RGB; QC-018 fires on a contradiction and on a silent file.

### Chunk 7. The build itself

- Bump the version, `pyproject.toml` and `proingest/__init__.py` together. **Also
  `build/build.py:66` and `docs/guide/install.md:16`**, which both name the dmg.
- `bash build/mac_build.sh` on the Mac, or let CI produce the artifact: it builds the dmg on any PR,
  on a push to `main`, and on `workflow_dispatch`.
- `python build/smoke_test.py dist/ProIngest/ProIngest` through the frozen binary.
- Work the `docs/MAC_SESSION.md` checklist. **Neither shell script has ever run on a Mac**, and CI's
  macOS jobs do the same steps from their own YAML rather than by calling either.

**Verify**: the acceptance test at the top of this page, on the real folder, on the Mac.

---

## Part 3. The shortest path

If only some of Part 1 arrives, this is the order that wastes least.

| what arrives | what becomes possible |
|---|---|
| **Q1 alone** | Chunks 1, 2, 4, 5. A tool that scans a real folder, names every row correctly and refuses nothing it should not. **No rendering**, because the cut and the grade come from the EDL |
| **Q1 + the real EDL folder (1.2)** | All of chunks 1 to 5. **This is the working build.** The acceptance test passes |
| **+ the camera file (1.3)** | Chunk 6. Plates that are right rather than plausible |
| **+ the test export (1.4)** | The colour chain confirmed end to end rather than reasoned about |

**Q1 and 1.2 are the two that matter.** Everything else improves a build that already works; those
two are the difference between a build that ingests a turnover and one that cannot.
