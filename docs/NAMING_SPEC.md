# Naming Spec

Source of truth: the shooters' spec PDF. This doc restates it as rules the code follows. All output names are produced by `core/naming.py`.

## 1. Timeline clip name (input contract)

```
[SHOW][NNNN]_[TYPE][II]
MELT0001_pl01
```

Regex (show prefix configurable, default `[A-Z]{2,6}`):

```
^(?P<show>[A-Z]{2,6})(?P<shot>\d{4})_(?P<type>pl|cp|el|wit|re)(?P<idx>\d{2})(?:_(?P<aux>colorChart|mirrorBall|greyBall|sizeRef|BTS)_(?P<auxidx>\d{2}))?$
```

- `show` + `shot` = shot code (`MELT0001`).
- `type` + `idx` = element id (`pl01`).
- Optional `aux` marks a single-frame reference still tied to the plate (`MELT0001_pl01_colorChart_01`). See OQ-4 for how shooters will actually name these on the timeline.
- Lens grid clips use a different pattern: `^(?P<camera>[A-Za-z0-9]+)_(?P<lens>[A-Za-z0-9\-]+)_lensgrid_(?P<mm>\d+)mm$` and are turnover-level, not shot-level.
- Anything that matches nothing is a QC-010 error on the row; the row still appears so the editor can fix the name in place.

## 2. Type table

| type | meaning | deliverables |
|---|---|---|
| pl | main plate | raw 4k exr seq, raw HD exr seq, ref 4k mp4, ref HD mp4, audio wav |
| cp | clean plate | raw 4k, raw HD, ref 4k, ref HD |
| el | element plate | raw 4k, raw HD, ref 4k, ref HD |
| wit | witness cam | raw 4k, raw HD, ref 4k, ref HD |
| re | recon plate | raw 4k, raw HD, ref 4k, ref HD |
| aux still | reference still on a plate | single 4k exr (BTS: png/jpg/jpeg copy) |
| lensgrid | lens distortion chart | png copy |

Side files discovered next to the media (not on the timeline), matched by shot code and element id in the filename:

| side file | match | deliverable |
|---|---|---|
| HDRI | `*HDRI*.exr` | exr copy, validated |
| camData | `*camData*.txt|rtf` | copied and parsed into QC log |

## 3. Output filename templates

Tokens: `{shotcode}` `{elem}` `{kind}` `{res}` `{ver}` `{frame}` `{aux}` `{auxidx}`

| deliverable | template | example |
|---|---|---|
| raw exr frame | `{shotcode}_{elem}_raw_{res}_v{ver}.{frame}.exr` | `MELT0001_pl01_raw_4k_v01.1001.exr` |
| raw exr folder | `{shotcode}_{elem}_raw_{res}_v{ver}` | `MELT0001_pl01_raw_4k_v01` |
| ref mp4 | `{shotcode}_{elem}_ref_{res}_v{ver}.mp4` | `MELT0001_pl01_ref_HD_v01.mp4` |
| audio | `{shotcode}_{elem}_audio_v{ver}.wav` | `MELT0001_pl01_audio_v01.wav` |
| HDRI | `{shotcode}_{elem}_HDRI_v{ver}.exr` | `MELT0001_pl01_HDRI_v01.exr` |
| camData | `{shotcode}_{elem}_camData_v{ver}.{ext}` | `MELT0001_pl01_camData_v01.rtf` |
| aux still exr | `{shotcode}_{elem}_{aux}_{auxidx}_4k_v{ver}.exr` | `MELT0001_pl01_colorChart_01_4k_v01.exr` |
| BTS | `{shotcode}_{elem}_BTS_{auxidx}_v{ver}.{ext}` | `MELT0001_pl01_BTS_01_v01.png` |
| lens grid | `{camera}_{lens}_lensgrid_{mm}mm_v{ver}.png` | `SonyA7V_Tamron20-40_lensgrid_40mm_v01.png` |
| stringout | `turnover{tno:03d}_{MM}_{DD}_{YYYY}_{firstnamelastname}_v{ver}.mp4` | `turnover001_02_23_2026_danielluckett_v01.mp4` |

`{res}` is `4k` or `HD` exactly. `{ver}` is two digits. `{frame}` is four digits starting at 1001.

Note: the spec PDF has a few resolution typos (2161, 2162); treat 4k as 3840x2160. It also lists witness cam raw without a frame range, which reads as though witness cam were delivered differently or not at all. It is not: **`wit` is a normal deliverable treated exactly like any other clip on the timeline**, confirmed by the user 2026-09-11, so its raw output is a sequence like every other row of this table. That gap in the PDF is a defect in the table and nothing more. OQ-5.

## 4. Versioning

- Version is per shot per run. Before rendering a shot, list existing `v??` for any of its deliverables in the destination; new version = max + 1, or 01 if none.
- "Per shot" means per shot folder, so the scope of that listing is the whole `<delivery_root>/<show>/<shotcode>/` directory and every element of the shot in the run shares the result. A shot whose `cp01` was delivered at v01 therefore starts its `pl01` at v02. Element versions can skip numbers; a shot's deliverables never disagree.
- All deliverables for that shot in this run get the same version, even if only one of them was missing. Partial version sets are confusing downstream.
- Side-file copies (HDRI, camData, stills, lens grid) follow the same version as the shot in that run.
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
      <shotcode>_<elem>_HDRI_v01.exr
      <shotcode>_<elem>_camData_v01.rtf
      <shotcode>_<elem>_colorChart_01_4k_v01.exr
    _turnovers/
      turnover001_02_23_2026_danielluckett_v01.mp4
      <camera>_<lens>_lensgrid_40mm_v01.png
    _reports/
      shot_tracker_<batchname>_<date>.xlsx
      qc_ingest_log_<batchname>_<date>.xlsx
```

## 6. Shot code edits

The editor may correct a shot code in the list (typo from the shooter). The tool re-derives all names from the corrected value and records `original -> final` in the QC log Shots sheet. The source file is never renamed.

## 7. Output name parsing (QC-151)

QC-151 requires every written deliverable to re-parse from its filename back to the same shot code, element, kind, resolution and version that the planner intended. The section 3 templates are therefore a two-way contract: `naming.build_*` writes them and `naming.parse_output_name` reads them. Both live in `core/naming.py` and are tested against the same example table.

`{kind}` is the literal segment that identifies the deliverable (`raw`, `ref`, `audio`, `HDRI`, `camData`, `BTS`, `lensgrid`, or one of the aux names). It is not a free variable; the token list in section 3 names it only so the type table and the parser can talk about it.

Shared fragments:

```
shotcode  (?P<show>[A-Z]{2,6})(?P<shot>\d{4})
elem      (?P<type>pl|cp|el|wit|re)(?P<idx>\d{2})
res       (?P<res>4k|HD)
ver       v(?P<ver>\d{2})
```

One anchored pattern per kind, tried in order. They are mutually exclusive because the literal kind segment differs, so a match is unambiguous. `<sc>` below stands for `shotcode_elem` joined with `_`.

| kind | pattern |
|---|---|
| raw exr frame | `^<sc>_raw_(?P<res>4k\|HD)_v(?P<ver>\d{2})\.(?P<frame>\d{4})\.exr$` |
| raw exr folder | `^<sc>_raw_(?P<res>4k\|HD)_v(?P<ver>\d{2})$` |
| ref mp4 | `^<sc>_ref_(?P<res>4k\|HD)_v(?P<ver>\d{2})\.mp4$` |
| audio | `^<sc>_audio_v(?P<ver>\d{2})\.wav$` |
| HDRI | `^<sc>_HDRI_v(?P<ver>\d{2})\.exr$` |
| camData | `^<sc>_camData_v(?P<ver>\d{2})\.(?P<ext>txt\|rtf)$` |
| aux still exr | `^<sc>_(?P<aux>colorChart\|mirrorBall\|greyBall\|sizeRef)_(?P<auxidx>\d{2})_4k_v(?P<ver>\d{2})\.exr$` |
| BTS | `^<sc>_BTS_(?P<auxidx>\d{2})_v(?P<ver>\d{2})\.(?P<ext>png\|jpg\|jpeg)$` |
| lens grid | `^(?P<camera>[A-Za-z0-9]+)_(?P<lens>[A-Za-z0-9\-]+)_lensgrid_(?P<mm>\d+)mm_v(?P<ver>\d{2})\.png$` |
| stringout | `^turnover(?P<tno>\d{3})_(?P<mm>\d{2})_(?P<dd>\d{2})_(?P<yyyy>\d{4})_(?P<shooter>[a-z0-9]+)_v(?P<ver>\d{2})\.mp4$` |

The `show` prefix pattern is the same configurable value as section 1, so a Settings change applies to both directions at once.

Shooter name: the stringout pattern only accepts lowercase alphanumerics, so the builder normalizes the turnover-level shooter field (lowercase, strip everything outside `a-z0-9`) before substituting it. `Daniel Luckett` and `daniel-luckett` both become `danielluckett`. The unnormalized value is kept on the turnover for the tracker and QC log. See OQ-15.

Version discovery (section 4) uses the same patterns: an entry in the shot folder counts as an existing version if it parses as any deliverable this tool writes, not only as the kind being planned, because section 4 versions the shot rather than the individual output. This is what keeps a stray file from inflating the version number, and it is why `.part` names can never match.
