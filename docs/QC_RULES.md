# QC Rules

Every rule has a stable ID, a phase, a severity, and a scope. Severity: `error` blocks the row from rendering (row auto-skipped, reason recorded); `warning` colors the row amber and is logged; `info` is logged only. All results appear in the QC log Deliverables sheet with pass/fail per rule.

Rule IDs never change meaning. New rules get new numbers. **The one exception is a rule revised on
the same day it was written, before any code, log line or spreadsheet has used it**, which is what
happened to QC-009, QC-019 and QC-039 on 2026-09-11. The grade carrier was specified as a CLF, then
as a CDL, then as a CLF again, all in one session and none of it built, so these three were written,
reworded and written back. On 2026-09-18 the carrier became the CDL for good, applied in ACEScct,
with the built rules amended in place and dated rather than renumbered, because the failure each
one names did not change. Nothing anywhere had ever referred to them, which is the only condition
under which this is safe. **It is not a precedent**: the moment a rule ID reaches code, a log or a
spreadsheet, it is frozen and a changed rule gets a new number.

A rule whose reason for existing goes
away is marked **RETIRED** and its ID is left in the table rather than deleted, so a log line or
a spreadsheet column from an older run still resolves to what it meant when it was written.

## Phase A: scan and pre-flight (QC-0xx)

| ID | severity | scope | check |
|---|---|---|---|
| QC-001 | error | turnover | **The folder is not a turnover the tool can read**: Ben's EDL or his metadata CSV is missing from it. Both are required and both live in the same folder as the media (2026-09-21). Without the CSV nothing has a shot code, a clip type or an encoding; without the EDL nothing has an approved cut or a grade. This fires at Add Turnover rather than at Run, because there is nothing to scan |
| QC-002 | error | turnover | Ben's EDL or his metadata CSV failed to parse |
| QC-003 | RETIRED | | Was: EDL used instead of OTIO (reduced validation). **Retired 2026-09-21**: there is no OTIO and never was one, so the EDL is not a reduced anything. **The ID is not reused** |
| QC-004 | warning | turnover | The metadata CSV has no rows, or Ben's EDL has no events |
| QC-005 | info | turnover | Turnover folder name does not match `turnover###_MM_DD_YYYY_name` pattern; fields need manual entry |
| QC-006 | RETIRED | | Was: no EDL carrying CDL found. The tool no longer reads CDL; the grade arrives as a CLF (COLOR_AND_FORMAT section 1). Replaced by QC-008. **The ID is not reused** |
| QC-007 | RETIRED | | Was: CDL found but failed to parse. Replaced by QC-019, which asks the same question of a CLF. **The ID is not reused** |
| QC-008 | error | turnover | **Built 2026-09-12** (M5.7.1), **rescoped 2026-09-21.** Ben's EDL carries no CDL on any event, so nothing final can render from it: a session exported without the grade. It no longer covers "no colour session has been ingested", because the EDL and the CSV arrive in the turnover folder with the media and a folder without them is QC-001 and never scans at all. The run still **holds back the rows of the turnover this fires on** rather than stopping (`qc.blocked_turnovers`), which keeps its one useful property: a turnover exported without its grade waits while the rest of the batch delivers |
| QC-009 | error | row | **Built 2026-09-12** (M5.7.1), **narrowed 2026-09-21.** This row's event carries no CDL, so the row would render ungraded. With per-shot grade files gone the CDL is the only carrier, so there is no longer a second thing to look for and no file to be missing. Silent on a reference still and a BTS frame, which are delivered ungraded by design. An error rather than a warning, deliberately: an ungraded plate is not a lesser deliverable that is still watchable, it is the wrong pixels under the right filename |
| QC-010 | error | row | **The row names a `Shot Type` the tool does not deliver, or names one without a shot code.** `Shot` is blank or does not parse, while `Shot Type` says the row is a deliverable. **Narrowed 2026-09-22**: a row with **no `Shot Type` at all is no longer an error** - the user's rule is that a clip with no `Shot Type` is ignored, so it never becomes a row and QC-064 counts it at turnover scope instead. This rule is now for the half-filled row, which is the one a person can fix |
| QC-011 | warning | row | Duplicate clip name within the batch |
| QC-012 | error | row | Media not found (referenced path missing and no unique filename match) |
| QC-013 | error | row | Media ambiguous (multiple filename matches) |
| QC-014 | error | row | Media unreadable by ffprobe/OpenEXR |
| QC-015 | warning | row | Image sequence has gaps in frame numbering |
| QC-016 | warning | row | Media path was remapped via path map (info for trust) |
| QC-017 | RETIRED | | Was: clip has no matching CDL entry in the EDL. Replaced by QC-009. **The ID is not reused** |
| QC-018 | warning | row | The container's own colour tags contradict the source encoding the clip's metadata names. No standard transfer tag names a camera log encoding, so the sidecar is the authority and the decode is forced to match it (COLOR_AND_FORMAT section 2); this fires when what the file does claim disagrees. Information, not a veto. **Includes the range and matrix flags**, because a log signal carried as YCbCr with the wrong range decodes to crushed blacks and clipped whites that look almost right |
| QC-019 | RETIRED | | Was: the per-shot grade file will not load in OpenColorIO. **Retired 2026-09-21**, when the user removed per-shot grade files entirely: the CDL on the EDL event is the only grade carrier, so there is no file to fail to load. **The ID is not reused** |
| QC-020 | warning | row | Source pixel format is poor for a log plate: 8 bit, or 4:2:0. **Downgraded from error to warning 2026-09-19 by the user**, who allows 4:2:0 sources. Subsampled chroma in a log signal is stretched when it is linearised and shows on saturated edges, which is worth saying and is not worth refusing a delivery over |
| QC-021 | warning | row | **Rebased 2026-09-21.** There is no expected intermediate format: sources are camera native as Copy with trim wrote them, or debayered to a basic file type where the camera system records RAW, so the old test against ProRes 4444 / DNxHR 444 was checking for a file nobody makes. What is left worth reporting is the shape of what arrived - codec, bit depth, chroma - so a turnover of 8 bit 4:2:0 is visible before it is graded rather than after. **RAW is refused outright** by QC-022, since ffmpeg decodes no RAW format. A source already in ACEScct or ACEScg lands here too: nothing is wrong with it, the input transform is simply a no-op |
| QC-022 | error | row | Source codec not decodable |
| QC-023 | error | row | Source resolution is not 3840x2160. Enabling "allow non-4k" downgrades it to a warning rather than silencing it, because `render._fit` resamples to the target either way and a squashed plate should still be said out loud. Aux stills and BTS are not asked: they are delivered at their own size |
| QC-024 | warning | row | Source letterboxed/pillarboxed to 3840x2160 |
| QC-025 | RETIRED | | Was: timeline fps differs from project fps. **Retired 2026-09-21**: there is no timeline file to state a rate. An EDL has no frame rate field and the `.drt` is not read, so the project rate is asserted at 24 and QC-026 is the rule that still means something. **The ID is not reused** |
| QC-026 | error | row | Source fps differs from project fps |
| QC-027 | error | turnover | Drop-frame timecode |
| QC-028 | warning | row | Source has no embedded timecode |
| QC-029 | warning | row | The EDL event's source range does not fit inside the media: the event references frames the file does not have |
| QC-030 | warning | row | Fewer than "expected handle frames" available beyond current Out (or before In) |
| QC-031 | error | row | In or Out outside source range after editing |
| QC-032 | error | row | In greater than Out |
| QC-033 | warning | row | Duration below minimum (default 120 frames) |
| QC-034 | warning | row | Duration above maximum (default 240 frames) |
| QC-035 | info | row | In/Out differ from turnover snapshot. **Unchanged in meaning and mostly changed in cause**: the snapshot is what the shooters delivered, and since 2026-09-11 most of the difference is the colour session's own approved trim rather than anything the editor did. QC-045 is the one that reports the editor |
| QC-045 | warning | row | **Built 2026-09-12** (M5.7.1), in the row rules, so it re-runs after every edit. Current In/Out differ from the **approved** In/Out on the colour session's final EDL, which ingest records on the row as `ShotRow.approved`. Ingest writes `current` from it as well, so this fires on the one-off trim made afterwards rather than on the ingest itself. A warning where QC-035 is info, because this is a deviation from an edit the AD signed off rather than a record of one: the delivered shot is not the shot that was approved, and the only place that fact exists is this rule. Fires on a deliberate one-off trim, which is a supported thing to do (PRD FR-5), and on a colour session ingested after a trim was already made, which overwrites it |
| QC-046 | error on every row the tool transforms, info on BTS | row | **Built 2026-09-12** (M4.6.4), in the row rules, so it re-runs after every edit. The clip's metadata names no source encoding: the field is absent, or empty. **Narrowed 2026-09-12 by OQ-37**, before it was ever built: since the grade file starts at the source encoding, a plate does not need this string to resolve and renders without it, so the row is blocked only where there is an **aux still** to convert, which is the one chain with no grade file in it. Elsewhere the cost is a line of provenance missing from the EXR header, which is worth reporting and is not worth blocking a delivery for. **There is no batch-wide fallback to switch to**, by design: the encoding is a per clip fact and a batch-wide guess would be wrong for every clip it was not guessed for (OQ-44). **An aux still is the row's own kind** (`colorChart`, `mirrorBall`, `greyBall`, `sizeRef`), never BTS, which is copied byte for byte and transformed by nothing. What the error does is fail that one deliverable rather than stop the batch: `ShotColor.plate_transforms` refuses a chain with neither a grade file nor an encoding, so the still comes back as QC-100 with the reason and nothing is written **2026-09-18: an error on every plate.** The grade is the CDL applied in ACEScct and this string is what gets the clip there, so a plate cannot render without it. Info only on a BTS frame, which is copied byte for byte. The narrowing above was written for a grade file that started at the source encoding and is history |
| QC-047 | error on every row the tool transforms, info on BTS | row | **Built 2026-09-12** (M4.6.4), beside QC-046. The source encoding the clip's metadata names cannot be resolved to one entry in the input transform table (`color.resolve_encoding`). Scoped like QC-046 and for the same reason: the plate is rendered by the grade file and does not need the name resolved; the **aux still** is the tool's own conversion and does. Three distinct causes, one severity: the name is unrecognised (a fourth camera nobody has mapped), it is ambiguous ("S-Log3" names four colour spaces, since a curve does not choose a gamut), or it names a variant the config does not carry (LogC3 at an exposure index other than EI800, BMD Film before Gen 5, Canon in BT.2020 rather than Cinema Gamut). **Never a nearest match**: a mis-converted colour chart is the worst failure the tool has, because the chart is delivered precisely to be matched against and a wrong one still looks like a chart. The message names what was written and what it could not be resolved to (OQ-34, OQ-45) **2026-09-18: an error on every plate**, for the reason QC-046 gives |
| QC-048 | info | row | **Built 2026-09-12** (M4.6.4), in the pre-flight. Records which colour chain the row was rendered through, so a delivery can be traced afterwards rather than re-derived from a setting nobody wrote down. **2026-09-21:** with the cube gone the chain is `<source encoding> to ACEScct, the CDL, ACEScct to ACEScg` on a plate, and the one-leg conversion on a reference still, which gets no grade by design. It also records **where the encoding came from** - the metadata CSV, or a per-turnover default (OQ-59) - because a wrong encoding is traced back to whoever typed it |
| QC-036 | info | row | Shot code edited from original clip name |
| QC-037 | RETIRED | | Was: colour adjusted from neutral, for the four per clip colour controls. **The controls are removed from v01** and there is nothing to report. **The ID is not reused** |
| QC-038 | RETIRED | | Was: the studio standard source encoding named in Settings has no OpenColorIO equivalent. **Retired 2026-09-12, before it was ever built**: there is no batch-wide source encoding setting any more, because the encoding is named per clip and DaVinci Wide Gamut is one more entry in the input transform table rather than a mode to switch into. QC-047 asks the same question of the value that actually exists. **The ID is not reused**. Batch wide in practice rather than per row, because the encoding is one constant for every file (COLOR_AND_FORMAT section 1), but it is reported on the row because the row is what cannot render |
| QC-039 | RETIRED | | Was: the grade file appears to contain a display rendering, probed as a step between two samples at the top of ACEScct with a floor of 0.07. **Retired 2026-09-21** with the per-shot cube it inspected: a CDL is four numbers per channel and cannot hide a tone map. The reasoning is kept in `docs/COLOR_AND_FORMAT.md` because the failure it named - a display referred file claiming to be linear, which comps wrong and looks completely normal - is real and would return with any future grade file. **The ID is not reused** |
| QC-040 | warning | row | Plate (pl) has no associated audio clip |
| QC-041 | warning | row | More than one audio clip overlaps the video clip |
| QC-042 | error | row | Associated audio file missing or unreadable |
| QC-043 | warning | row | Audio duration differs from the video In/Out range by more than one frame, in either direction, so it will not sync. Audio format itself is left flexible; this is a sync check, not a format check. OQ-27 makes the expectation firm: a wav runs cut point to cut point, so a mismatch **at scan time** means a malformed turnover, while one **after an edit** is the editor's own trim showing up, because the wav deliverable is a byte copy and is never trimmed to the new range. The reference mp4 syncs either way; it seeks and pads the audio to the picture |
| QC-044 | warning | row | Audio not 16 bit PCM (will be extracted as 16 bit) |
| QC-050 | RETIRED | | Was: plate has no HDRI side file. **Retired 2026-09-22**: an HDRI carries no `Shot Type`, so the tool ignores it and no longer delivers it. Nothing is left to warn about. **The ID is not reused** |
| QC-051 | RETIRED | | Was: plate has no camData side file. **Retired 2026-09-22** with QC-050, for the same reason. **The ID is not reused** |
| QC-052 | RETIRED | | Was: HDRI file fails OpenEXR header read. **Retired 2026-09-22**: the tool does not open an HDRI any more. **The ID is not reused** |
| QC-053 | RETIRED | | Was: camData parsed, N key/value pairs found. **Retired 2026-09-22**: camData is not a deliverable and is not read, so `core/camdata.py` and the QC log's Camera Data sheet go with it (OQ-11 closes unanswered). **The ID is not reused** |
| QC-054 | RETIRED | | Was: no lens grid folder in turnover. **Retired 2026-09-22: Ben delivers the lens grid**, so its absence from the shooters' folder is not the tool's business. **The ID is not reused** |
| QC-057 | RETIRED | | Was: lens grid folder present, a reminder of a manual step. **Retired 2026-09-22** with QC-054. **The ID is not reused** |
| QC-055 | warning | row | Aux still (colorChart, mirrorBall, greyBall, sizeRef) has more than one frame; first frame will be used |
| QC-056 | RETIRED | | Was: BTS still is not png, jpg or jpeg. **Retired 2026-09-22**: BTS is not a tool deliverable (user), so no name is built for one and nothing needs checking. **The ID is not reused** |
| QC-064 | warning | turnover | **N clips in the folder carry no `Shot Type` and were ignored.** New 2026-09-22, and the counterweight to the rule that created it: a clip with no `Shot Type` is not delivered and is not an error, so without this rule a turnover whose metadata never got filled in produces **no deliverables and no complaint**. The message names the count and the file names. Warning rather than error, because ignoring a clip is the intended behaviour; a whole turnover ignored is what wants saying out loud |
| QC-065 | warning | row | **The metadata CSV carries two `Shot Type` columns and they disagree.** New 2026-09-22, measured in `Turnover199_ForBEN`: Resolve's built-in `Shot Type` sits at column 12 and the shooters' **custom field of the same name** at column 44. They agreed in that sample and nothing guarantees it, because the built-in is a **framing** field whose intended values are things like a wide or a close up, so a shooter using it as designed puts `Wide` in one and `pl01` in the other. The reader takes **the column that resolves to a known clip type**, prefers the custom field where both resolve, and raises this when they differ. Neither resolving is QC-010; no `Shot Type` column at all is QC-064's ignored clip. **`csv.DictReader` silently keeps the last duplicate**, which is why this is a named rule and not a parsing detail |
| QC-060 | warning | row | Existing deliverables found at version N; new render will be version N+1 |
| QC-061 | info | row | Complete QC-passing set exists; row skipped (Force re-render off) |
| QC-062 | error | batch | Delivery destination not writable. Batch scope, not row: there is one delivery root and the run creates every folder under it, so checking per row would be N stat calls on a network mount for one answer. The root need not exist yet; the nearest existing ancestor is what gets the write probe |
| QC-063 | warning | batch | Free space at delivery root below estimated output size |

## Phase B: post-render verification (QC-1xx)

Run per deliverable immediately after its atomic rename. Any error marks the deliverable failed and leaves the row not-done; the file stays for inspection with a `.failed` marker sidecar.

QC-100 is the exception to that: it reports a render that never produced a file at all, so there is nothing to keep and nothing to mark. A render failure leaves no `.part` and no destination, by design.

| ID | severity | scope | check |
|---|---|---|---|
| QC-100 | error | deliverable | Render did not complete; the reason is recorded. Every other QC-1xx is NA when this one fails, because there is no file to check |
| QC-101 | error | exr seq | Frame count equals duration |
| QC-102 | error | exr seq | First frame is 1001, last is 1000 + duration, no gaps. OQ-35 asks whether frame numbers should instead derive from source timecode; until it is answered this rule and NAMING_SPEC both say 1001 |
| QC-103 | error | exr seq | Every frame opens with OpenEXR and header parses. Also applied to an aux still, which is one EXR written by the same function: a mirror ball delivered unreadable is the same defect |
| QC-104 | error | exr seq | Data window and display window equal target resolution. Also applied to an aux still |
| QC-105 | error | exr seq | Compression is DWAA, channels are R,G,B (or R,G,B,A) half. Also applied to an aux still. One result per rule for the whole sequence, naming the first offender: 240 identical rows would bury the rest of the report |
| QC-106 | error | exr seq | Per-frame xxhash64 matches what the writer recorded. An aux still is compared against the single whole-file checksum instead. A batch that recorded no checksums (an older one) is not a mismatch, so the rule stays silent |
| QC-107 | warning | exr seq | Frame file size below 10% of median (likely black or empty frame). Median, not mean: a handful of black frames would drag a mean down far enough to hide themselves. Not applied to a sequence under three frames, which has no meaningful median |
| QC-110 | error | mp4 | ffprobe opens file, stream count as expected |
| QC-111 | error | mp4 | Frame count equals duration (probed with `-count_frames`, which decodes). The render already compared the container's own index; this decodes, because an index can say 240 over a file that stops at 12 and the delivered reference is what the vendor plays |
| QC-112 | error | mp4 | Resolution equals target |
| QC-113 | error | mp4 | fps equals project fps |
| QC-114 | warning | mp4 | Audio stream present iff audio was associated |
| QC-115 | error | mp4 | faststart moov atom at head. Read from the file's top level box order, not from the `-movflags +faststart` that asked for it: the flag is a request, and a file that fell back to a trailing moov plays locally and stalls over a Drive link, which is where these go |
| QC-120 | error | wav | Duration in samples matches source audio (byte copy: checksum equal) |
| QC-121 | error | wav | 16 bit PCM. **Error only when the audio was extracted from a container**, where the extraction was supposed to produce 16 bit and did not. A wav source is delivered as a byte copy per COLOR_AND_FORMAT section 3, so a 24 bit source delivers 24 bit by design and this is a warning there; QC-044 already said so at scan time |
| QC-130 | error | copy | Checksum of copied side file equals source |
| QC-140 | RETIRED | | Was: stringout frame count equals the sum of the included rows. **The tool no longer builds a stringout** (PRD FR-9); the colour session exports it. **The ID is not reused** |
| QC-141 | RETIRED | | Was: a burn-in field was empty for some clip. Retired with QC-140. **The ID is not reused** |
| QC-150 | error | row | Every planned deliverable for the row exists and passed. Run by `render.apply_results`, not in a worker: a worker sees one job |
| QC-151 | error | batch | Filename of every deliverable re-parses with the naming regex to the same shot/elem/kind/res/ver. Compared against the plan rather than merely checked for parsing, which is what catches a name that is well formed and wrong. Only delivered names are asked; one that never landed is QC-150's |

## QC log structure

`qc_ingest_log_<batch>_<date>.xlsx`

- Summary: batch name, date, tool version, turnovers, rows, rows done / skipped / failed, rule counts by severity
- Shots: one row per shot row. Columns: turnover, source file name, shot code (from `Shot`), clip type (from `Shot Type`), source path, source fps, source res, snapshot In/Out (frames and TC), final In/Out, duration, max available, audio path, edited, **source encoding** (`Gamma Notes` + `Color Space Notes` verbatim, rather than the colour space they resolve to, empty when the row named none), **Grade** (the CDL from the row's EDL event as `*ASC_SOP` / `*ASC_SAT`, empty when the row rendered ungraded), skip reason, warnings (IDs), errors (IDs)
- Deliverables: one row per deliverable. Columns: shot code, elem, kind, res, version, path, frames, size bytes, checksum (or first/last frame hash for sequences), then one column per QC-1xx rule with PASS/FAIL/NA
- Side Files: shot code, type, source path, dest path, checksum
- Camera Data: shot code, key, value (one row per pair parsed from camData)

`shot_tracker_<batch>_<date>.xlsx` is written to be **pasted into the studio's own tracker**, so its
columns are that tracker's columns and not a layout of ours. **OQ-2 is answered** from the real
sheet (`docs/Pre Pro Shot Tracker - W1.csv`, 790 rows across 55 turnovers). The guessed default
that used to be described here shared exactly one column with it, Shot Code, and is gone.

The studio tracker has 39 columns. **Nine of them are the tool's**; the other thirty are
production state that the vendor's team fills in over the weeks after delivery - statuses,
owners, difficulty grades, callout movies, requesters - and the tool must never write them.
The export is **additive**: one row per shot row of this batch, in the tracker's column order,
with every column it does not own left empty so a paste cannot overwrite anything.

| # | tracker column | what the tool writes |
|---|---|---|
| 2 | `Shot Code (ABCD123)` | the final shot code. The header says ABCD123; the real data is four letters and **four** digits, which is what `naming.py` already parses |
| 3 | `Publish Folder` | the shot folder name, which equals the shot code |
| 4 | `Plate Video` | the **HD** reference mp4's filename. 628 of 782 real values already parse as `ref_mp4` under section 7's grammar; the misses are rows that predate the convention |
| 5 | `HDRI` | the delivered HDRI filename, blank when the shot has none |
| 6 | `CAM Data` | the delivered camData filename, blank when the shot has none |
| 7 | `PLATES` | `4K ✓` and `HD ✓` on two lines, one mark per raw sequence delivered, an em dash for one that was not (the literal glyph `exports.py` writes) |
| 8 | `FPS` | the row's rate. **Not always 24** - see the note below |
| 9 | `Shot Audio?` | `✓` when the row delivered audio, blank otherwise |
| 34 | `Turnover Stringout (Edit)` | **left empty, on purpose.** The tool no longer writes that file (PRD FR-9) and the grammar it would rebuild the name from matches none of the 55 real ones (OQ-41). A blank cell is the honest answer, and it is one line to fill in once OQ-41 is settled |

Column 0 is a checkbox the sheet owns (`FALSE`), and column 1 `Shot#` is a production number with
duplicates in it, so neither is derivable. `Effect Category`, `Audio` (a spoken/effects annotation),
`Pod Point of Contact`, the thumbnails and everything from `Cam Status` rightwards are the vendor's.

**The tool knows more than the tracker has room for.** Duration, source timecode in and out,
version, delivery path and notes have no column here, which is why they stay in the QC log's
Shots and Deliverables sheets above rather than being forced into this one.

**The FPS column says 24 is no longer the only rate**, which matters because QC-026 is an error.
Of 778 rows carrying a rate, 677 are 24 and 101 are not. Splitting by turnover number tells the
real story: every one of the 370 rows on turnovers before number 90 is 24, while the recent
turnovers carry **27 rows at 23.976 and 2 at 30** out of 262. Rows not yet attached to a turnover
are wider still: 29.97, 30, 25, 60 and 120 all appear. The premise under OQ-19, that everything is
24 because the shooters conform in Resolve, held for the earlier turnovers and does not hold now.
Whether that changes QC-026's severity depends on something this sheet cannot say - whether this
column records the timeline rate or the rate the camera shot at - so OQ-19 is reopened rather than
answered. The same rate is also typed both `23.976` and `23.98` here, so the column is hand entered
and is evidence about the shoot rather than a machine record.
