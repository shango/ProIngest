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
            pl cp el colorChart mirrorBall greyBall sizeRef   (cl accepted as cp; re retired for recon)
Witness     ^(?P<plate>pl\d{0,2})_wit(?P<index>\d{1,2})?$   pl01_wit01, pl02_wit01
            HDRI##, LDRI##, styleFrame, avidRef##, meas## and recon## are read on their own, outside this list
```

- `show` + `shot` = shot code (`MELT0001`).
- `kind` + `index` = element id (`pl01`), the index zero-padded to two digits and `01` when bare.
- **A witness cam names the plate it covers** (user, 2026-10-23): Ben types `pl01_wit01` or `pl02_wit01`, and every one of its deliverables carries both, `MELT0001_pl02_wit01_raw_4k_v01`. A bare `wit01` names no plate and is QC-010. Its stringout inset goes over the plate it names. This replaces the shooters' spec sheet's `MELT0001_wit01_...`, which is out of date.
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
| wit | witness cam, `Shot Type` `pl02_wit01` | raw 4k, raw HD, ref 4k, ref HD, named `{shotcode}_{plate}_wit{idx}_...` |
| ~~re~~ | ~~recon plate~~ | **retired 2026-10-27 (user): "It's now recon"**. `re01` is QC-010 and says to write `recon01` |
| aux still | reference still, keyed to the shot code | single 4k exr, converted and never graded |
| HDRI | the HDRI, `Shot Type` `HDRI01`, `HDRI02` (QC-080; a bare `HDRI` is `HDRI01`, user 2026-10-27) | the EXR, **copied byte for byte** and never checked (user, 2026-10-07), and **Ben's pre-render of its event as an mp4** beside it (user, 2026-10-27): the whole render, the size it is, silent, graded as the stringout shows it |
| LDRI | the LDRI, `Shot Type` `LDRI01` (QC-080): an HDRI whose file is a JPG or PNG | the JPG or PNG, **copied byte for byte** under its own extension and never checked (user, 2026-10-08), and its pre-render as an mp4, as it is |
| styleFrame | a pre-graded PNG or JPG held before the shot's plate (QC-085) | **nothing**: shown on the stringout only, as it is (user, 2026-10-07) |
| avidRef## | an Avid reference (QC-088), its color baked in | **never an EXR** (user, 2026-10-22): a movie (a `Render` mp4 or mov, or an image sequence) is encoded to one mp4 of its cut at 24, the size it is, no grade, no audio; a held still, one image file, is copied byte for byte when a JPG or PNG and otherwise becomes a JPG. Not on the tracker |
| meas##, recon## | a measurement and a recon (QC-088, user 2026-10-27), never color corrected | **as an Avid reference is**: a movie is one mp4 of its cut, a still is itself or a JPG. Not on the tracker |

**Nothing else is a deliverable** (2026-09-22). camData, BTS stills and the lens grid carry
no `Shot Type`, which is the whole of the tool's scope, so the tool neither
reads, copies nor renames any of them; they are Ben's or they are manual. **The stringout is the
exception**: one per turnover, built by the tool from Ben's final EDL (PRD FR-9, since 2026-09-25). `BTS` and `lensgrid` are
not types either: a `Shot Type` of either is unrecognised and QC-010 (D5). Noted because the studio's own sheet marks **Camera Data as Required**, so it still has to
reach the vendor; it reaches it without passing through this tool. (So is HDRI, which the tool
delivers since 2026-10-07.)

## 3. Output filename templates

Tokens: `{shotcode}` `{elem}` `{kind}` `{res}` `{ver}` `{frame}` `{aux}` `{auxidx}`

| deliverable | template | example |
|---|---|---|
| raw exr frame | `{shotcode}_{elem}_raw_{res}_v{ver}.{frame}.exr` | `MELT0001_pl01_raw_4k_v01.1001.exr` |
| raw exr folder | `{shotcode}_{elem}_raw_{res}_v{ver}` | `MELT0001_pl01_raw_4k_v01` |
| ref mp4 | `{shotcode}_{elem}_ref_{res}_v{ver}.mp4` | `MELT0001_pl01_ref_HD_v01.mp4` |
| audio | `{shotcode}_{elem}_audio_v{ver}.wav` | `MELT0001_pl01_audio_v01.wav` |
| HDRI exr | `{shotcode}_pl01_HDRI{idx}_v{ver}.exr` | `SECA0009_pl01_HDRI01_v01.exr`. **`01` is the Shot Type's** (`HDRI01`; bare `HDRI` is 01), with no underscore before it, like every other number (user, 2026-10-27). It was the CSV's `Take`, written `HDRI_01`, from 2026-10-12; that spelling still counts as a version. `naming.hdri_exr` |
| LDRI image | `{shotcode}_pl01_LDRI{idx}_v{ver}.{jpg\|jpeg\|png}` | `SECA0009_pl01_LDRI01_v01.jpg`. The HDRI's name mirrored, with the source's own extension, lowercased (user, 2026-10-08). The tracker has no LDRI column. `naming.ldri_image` |
| HDRI or LDRI pre-render | `{shotcode}_pl01_{HDRI\|LDRI}{idx}_v{ver}.mp4` | `SECA0009_pl01_HDRI02_v01.mp4`, beside the file it is named after (user, 2026-10-27; the name assumed, OQ-88). `naming.hdri_prerender_mp4` |
| Avid reference, measurement, recon | `{shotcode}_{avidRef\|meas\|recon}{idx}_v{ver}.{mp4\|jpg\|jpeg\|png}` | `INCA5002_avidRef01_v01.mp4`, `INCA5002_meas01_v01.mp4`, `INCA5002_recon02_v01.jpg`. No size tag (user, 2026-10-22 and 2026-10-27). `naming.as_is_file` |
| aux still exr | `{shotcode}_{aux}_{auxidx}_4k_v{ver}.exr` | `MELT0001_colorChart_01_4k_v01.exr`. **No element segment** (shooters' spec, 2026-09-21): a reference still is keyed to the shot code |
| stringout mp4 | `turnover{num:03}_{MM}_{DD}_{YY}_{shooter}_SO_v{ver}.mp4`, in `<show>/_reports/` | `turnover121_09_23_26_danielluckett_SO_v01.mp4`. Dated as the turnover folder, not the render; month, day and year are always two digits each (user, 2026-10-05; a folder's four digit year is written as its last two). A stringout written earlier with a four digit year still counts as a version. `naming.stringout_stem` (2026-09-25) |

The camData, BTS and lens grid templates were removed on 2026-09-22 (the HDRI's came back on 2026-10-07) with the deliverables (section 2). The stringout's was removed then too and came back with the stringout on 2026-09-25.

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
- Reference stills follow the same version as the shot in that run. An HDRI's copy is versioned with its shot too (2026-10-07). **There are no other side-file copies to version** (2026-09-22): camData, BTS and the lens grid are not tool deliverables.
- A `.part` file or folder is never counted as an existing version.

## 5. Delivery folder layout (proposed default, editable template in Settings, OQ-1)

```
<delivery_root>/
  User_Generated/   (empty, the user's own; see below)
  User_Uploads/
  <show>/
    <shotcode>/
      <shotcode>_<elem>_raw_4k_v01/   (exr frames)
      <shotcode>_<elem>_raw_HD_v01/
      <shotcode>_<elem>_ref_4k_v01.mp4
      <shotcode>_<elem>_ref_HD_v01.mp4
      <shotcode>_<elem>_audio_v01.wav
      <shotcode>_colorChart_01_4k_v01.exr     (keyed to the shot code, not an element)
      <shotcode>_pl01_HDRI01_v01.exr          (the HDRI, copied as it is)
      <shotcode>_pl01_HDRI01_v01.mp4          (its pre-render)
      <shotcode>_pl01_LDRI01_v01.jpg          (or .png: an LDRI, copied as it is, and its .mp4)
      <shotcode>_avidRef01_v01.mp4            (or .jpg or .png: an Avid reference, never an EXR;
      <shotcode>_meas01_v01.mp4                meas and recon the same)
    _reports/
      shot_tracker_<batchname>_<date>.xlsx      (<date> is YYYYMMDD, so name order is date order)
      qc_ingest_log_<batchname>_<date>.xlsx
      fixit_report_<batchname>_<date>.html      (the Fix-it report for the colorist, UI_SPEC 6.3)
```

**`User_Generated` and `User_Uploads`** (user, 2026-10-06; not in the shooters' spec) are made
empty at the top of the delivery root by any run that delivers a turnover, when missing
(`naming.USER_FOLDERS`, `render.make_user_folders`). The tool never reads, writes or removes
anything inside them, and they never count as a version. One that cannot be made is logged and
does not fail the run.

## 6. Shot code edits

The editor may correct a shot code in the list (typo from the shooter). The tool re-derives all names from the corrected value and records `original -> final` in the QC log Shots sheet. The source file is never renamed.

## 7. Output name parsing (QC-151)

QC-151 requires every written deliverable to re-parse from its filename back to the same shot code, element, kind, resolution and version that the planner intended. The section 3 templates are therefore a two-way contract: `naming.build_*` writes them and `naming.parse_output_name` reads them. Both live in `core/naming.py` and are tested against the same example table.

`{kind}` is the literal segment that identifies the deliverable (`raw`, `ref`, `audio`, or one of the aux names). It is not a free variable; the token list in section 3 names it only so the type table and the parser can talk about it.

Shared fragments:

```
shotcode  (?P<show>[A-Z]{2,6})(?P<shot>\d{4})
elem      (?:(?P<plate>pl\d{2})_(?=wit))?(?P<type>pl|cp|el|wit)(?P<idx>\d{2})   the plate only before wit
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
| HDRI exr | `^<shotcode>_pl01_(?P<aux>HDRI)_?(?P<auxidx>\d{2})_v(?P<ver>\d{2})\.exr$` (`_?` reads the spelling before 2026-10-27) |
| LDRI image | `^<shotcode>_pl01_(?P<aux>LDRI)_?(?P<auxidx>\d{2})_v(?P<ver>\d{2})\.(?P<ext>jpe?g\|png)$` (read back as kind `hdri`) |
| HDRI or LDRI pre-render | `^<shotcode>_pl01_(?P<aux>HDRI\|LDRI)(?P<auxidx>\d{2})_v(?P<ver>\d{2})\.mp4$` (kind `hdri_ref`) |
| Avid reference, measurement, recon | `^<shotcode>_(?P<aux>avidRef\|meas\|recon)(?P<auxidx>\d{2})_v(?P<ver>\d{2})\.(?P<ext>mp4\|jpe?g\|png)$` (kind `avidref`) |
| aux still exr | `^<shotcode>_(?P<aux>colorChart\|mirrorBall\|greyBall\|sizeRef)_(?P<auxidx>\d{2})_4k_v(?P<ver>\d{2})\.exr$` |

The `show` prefix pattern is the same configurable value as section 1, so a Settings change applies to both directions at once.

Version discovery (section 4) uses the same patterns: an entry in the shot folder counts as an existing version if it parses as any deliverable this tool writes, not only as the kind being planned, because section 4 versions the shot rather than the individual output. This is what keeps a stray file from inflating the version number, and it is why `.part` names can never match.
