# Naming Spec

Source of truth: the shooters' spec PDF. This doc restates it as rules the code follows. All output names are produced by `core/naming.py`.

## 1. Shot identity (input contract)

> **Settled, 2026-09-21 (OQ-62, OQ-70, OQ-72).** The shooters do not rename clips. Files and
> timeline clips keep the camera's names (`C0145.MP4`), and identity arrives as metadata, through
> the Media Pool CSV exported beside the media (`docs/SAMPLE_TURNOVER_199.md` section 4):
> **`Shot` carries the shot code** (`MELT0001`) and **`Shot Type` carries the element code**
> (`pl`, `cp`, `el`, `wit`, `re`, or a reference still's name). The grammar below still describes
> what a full identity looks like; it is assembled from two fields rather than parsed out of one
> name, and nothing parses a filename any more.
>
> Three reading rules, all from the user 2026-09-21:
>
> - **A bare code means index `01`.** `pl` is `pl01`. Each shot code has exactly one of each
>   reference still, so a bare `colorChart` is `colorChart_01`. `pl02` and `cp02` still occur.
> - **Parsing is case insensitive**, because the shooters do not keep the camel case. Output
>   always uses the spelling in this document. This is safe rather than lenient: the nine codes
>   are distinct when casefolded, so nothing is ambiguous.
> - **Clean plate is accepted as either `cl` or `cp` and always written `cp`** (OQ-72).
>
> **Built 2026-09-22.** `naming.ShotIdentity` is `(shot_code, kind, index)`, `naming.parse_shot_type`
> carries the three reading rules, and `core/metacsv.py` assembles an identity from the two CSV
> fields. The scan is built on the CSV, and nothing parses a clip name.


```
[SHOW][NNNN]_[TYPE][II]
MELT0001_pl01
```

The two fields are read separately (show prefix configurable, default `[A-Z]{2,6}`):

```
Shot        ^(?P<show>[A-Z]{2,6})(?P<shot>\d{4})$
Shot Type   ^(?P<kind>[A-Za-z]+)(?P<index>\d{1,2})?$   kind, casefolded, one of
            pl cp el wit re colorChart mirrorBall greyBall sizeRef   (cl accepted as cp)
```

- `show` + `shot` = shot code (`MELT0001`).
- `kind` + `index` = element id (`pl01`), the index zero-padded to two digits and `01` when bare.
- A `kind` that is one of the four reference stills marks a single-frame reference still. **Changed 2026-09-21 by the shooters' updated spec**: a reference still is keyed to the **shot code**, not to an element, and its delivered name no longer carries one.

  ```
  new   MELT0001_colorChart_01_4k_v01.exr
  old   MELT0001_pl01_colorChart_01_4k_v01.exr
  ```

  Same for `mirrorBall`, `greyBall` and `sizeRef`. `naming.aux_still_exr` builds these from the shot code, and the `aux_still` pattern in `_output_patterns` matches without the element segment, so QC-151 round-trips them.
- A `Shot Type` that is none of the nine, or a `Shot` that is blank or not a shot code, is a QC-010 error on the row; the row still appears so the editor can see it, and correct a shot code in place (section 6). A clip with no `Shot Type` at all is not a row: it is ignored and counted by QC-064.

## 2. Type table

| type | meaning | deliverables |
|---|---|---|
| pl | main plate | raw 4k exr seq, raw HD exr seq, ref 4k mp4, ref HD mp4, audio wav |
| cp | clean plate | raw 4k, raw HD, ref 4k, ref HD |
| el | element plate | raw 4k, raw HD, ref 4k, ref HD |
| wit | witness cam | raw 4k, raw HD, ref 4k, ref HD |
| re | recon plate | raw 4k, raw HD, ref 4k, ref HD |
| aux still | reference still, keyed to the shot code | single 4k exr, converted and never graded |

**Nothing else is a deliverable** (2026-09-22). HDRI, camData, BTS stills, the lens grid and the
stringout carry no `Shot Type`, which is the whole of the tool's scope, so the tool neither
reads, copies nor renames any of them; they are Ben's or they are manual. `BTS` and `lensgrid` are
not types either: a `Shot Type` of either is unrecognised and QC-010 (D5). Noted because the studio's own sheet marks **HDRI and Camera Data as Required**, so they
still have to reach the vendor; they reach it without passing through this tool.

## 3. Output filename templates

Tokens: `{shotcode}` `{elem}` `{kind}` `{res}` `{ver}` `{frame}` `{aux}` `{auxidx}`

| deliverable | template | example |
|---|---|---|
| raw exr frame | `{shotcode}_{elem}_raw_{res}_v{ver}.{frame}.exr` | `MELT0001_pl01_raw_4k_v01.1001.exr` |
| raw exr folder | `{shotcode}_{elem}_raw_{res}_v{ver}` | `MELT0001_pl01_raw_4k_v01` |
| ref mp4 | `{shotcode}_{elem}_ref_{res}_v{ver}.mp4` | `MELT0001_pl01_ref_HD_v01.mp4` |
| audio | `{shotcode}_{elem}_audio_v{ver}.wav` | `MELT0001_pl01_audio_v01.wav` |
| aux still exr | `{shotcode}_{aux}_{auxidx}_4k_v{ver}.exr` | `MELT0001_colorChart_01_4k_v01.exr`. **No element segment** (shooters' spec, 2026-09-21): a reference still is keyed to the shot code |

The HDRI, camData, BTS, lens grid and stringout templates were removed on 2026-09-22 with the deliverables (section 2).

`{res}` is `4k` or `HD` exactly. `{ver}` is two digits. `{frame}` is four digits starting at 1001.

### Known defects in the studio's own table

The tables above are what this tool implements. The studio's sheet is in `docs/` in two
forms, the PDF and a CSV export of it; read the CSV, it needs no viewer. Every difference
between it and the tables above is listed here, because each one reads like it means
something and none of them do. OQ-5.

| in their sheet | reality |
|---|---|
| Heights of `3840x2161` and `3840x2162` on the element, witness, recon and lens grid rows | Typos. 4k is `3840x2160` everywhere |
| Witness cam raw rows carry a bare filename, with no frame range and no subfolder columns, where every other raw row has all three | **`wit` is a normal deliverable, treated exactly like any other clip on the timeline**, confirmed by the user 2026-09-10. Its raw output is a sequence like every other row |
| The HDRI row's naming convention ends `.mp4` | Its own example and its codec column say `.exr`, and an HDRI is an EXR. The convention cell is wrong |
| Two rows are both labelled `HD Reference Recon Plate` | The first is the 4k row: its resolution and its own example say `re01_ref_4k_v01`. A label typo, not a missing deliverable or a duplicate one |
| The element raw rows' subfolder *examples* read `MELT0001_el01_ref_4k_v01` | The subfolder convention column next to them reads `raw`, and a raw sequence folder is what those rows deliver. The convention is right and the example is wrong |

None of these changed anything this tool does. They are recorded so the next person to read
the sheet does not go looking for the rule behind one of them.

## 4. Versioning

- Version is per shot per run. Before rendering a shot, list existing `v??` for any of its deliverables in the destination; new version = max + 1, or 01 if none.
- "Per shot" means per shot folder, so the scope of that listing is the whole `<delivery_root>/<show>/<shotcode>/` directory and every element of the shot in the run shares the result. A shot whose `cp01` was delivered at v01 therefore starts its `pl01` at v02. Element versions can skip numbers; a shot's deliverables never disagree.
- All deliverables for that shot in this run get the same version, even if only one of them was missing. Partial version sets are confusing downstream.
- Reference stills follow the same version as the shot in that run. **There are no side-file copies to version** (2026-09-22): HDRI, camData, BTS and the lens grid are not tool deliverables.
- A `.part` file or folder is never counted as an existing version.

## 5. Delivery folder layout (proposed default, editable template in Settings, OQ-1)

```
<delivery_root>/
  <show>/
    <shotcode>/
      <shotcode>_<elem>_raw_4k_v01/   (exr frames)
      <shotcode>_<elem>_raw_HD_v01/
      <shotcode>_<elem>_ref_4k_v01.mp4
      <shotcode>_<elem>_ref_HD_v01.mp4
      <shotcode>_<elem>_audio_v01.wav
      <shotcode>_colorChart_01_4k_v01.exr     (keyed to the shot code, not an element)
    _reports/
      shot_tracker_<batchname>_<date>.xlsx      (<date> is YYYYMMDD, so name order is date order)
      qc_ingest_log_<batchname>_<date>.xlsx
```

## 6. Shot code edits

The editor may correct a shot code in the list (typo from the shooter). The tool re-derives all names from the corrected value and records `original -> final` in the QC log Shots sheet. The source file is never renamed.

## 7. Output name parsing (QC-151)

QC-151 requires every written deliverable to re-parse from its filename back to the same shot code, element, kind, resolution and version that the planner intended. The section 3 templates are therefore a two-way contract: `naming.build_*` writes them and `naming.parse_output_name` reads them. Both live in `core/naming.py` and are tested against the same example table.

`{kind}` is the literal segment that identifies the deliverable (`raw`, `ref`, `audio`, or one of the aux names). It is not a free variable; the token list in section 3 names it only so the type table and the parser can talk about it.

Shared fragments:

```
shotcode  (?P<show>[A-Z]{2,6})(?P<shot>\d{4})
elem      (?P<type>pl|cp|el|wit|re)(?P<idx>\d{2})
res       (?P<res>4k|HD)
ver       v(?P<ver>\d{2})
```

One anchored pattern per kind, tried in order. They are mutually exclusive because the literal kind segment differs, so a match is unambiguous. `<sc>` below stands for `shotcode_elem` joined with `_`, and `<shotcode>` for the shot code alone.

| kind | pattern |
|---|---|
| raw exr frame | `^<sc>_raw_(?P<res>4k\|HD)_v(?P<ver>\d{2})\.(?P<frame>\d{4})\.exr$` |
| raw exr folder | `^<sc>_raw_(?P<res>4k\|HD)_v(?P<ver>\d{2})$` |
| ref mp4 | `^<sc>_ref_(?P<res>4k\|HD)_v(?P<ver>\d{2})\.mp4$` |
| audio | `^<sc>_audio_v(?P<ver>\d{2})\.wav$` |
| aux still exr | `^<shotcode>_(?P<aux>colorChart\|mirrorBall\|greyBall\|sizeRef)_(?P<auxidx>\d{2})_4k_v(?P<ver>\d{2})\.exr$` |

The `show` prefix pattern is the same configurable value as section 1, so a Settings change applies to both directions at once.

Version discovery (section 4) uses the same patterns: an entry in the shot folder counts as an existing version if it parses as any deliverable this tool writes, not only as the kind being planned, because section 4 versions the shot rather than the individual output. This is what keeps a stray file from inflating the version number, and it is why `.part` names can never match.
