# QC Rules

Every rule has a stable ID, a phase, a severity, and a scope. Severity: `error` blocks the row from rendering (row auto-skipped, reason recorded); `warning` colors the row amber and is logged; `info` is logged only. All results appear in the QC log Deliverables sheet with pass/fail per rule.

Rule IDs never change meaning. New rules get new numbers. **The one exception is a rule revised on
the same day it was written, before any code, log line or spreadsheet has used it**, which is what
happened to QC-009, QC-019 and QC-039 on 2026-09-11. The grade carrier was specified as a CLF, then
as a CDL, then as a CLF again, all in one session and none of it built, so these three were written,
reworded and written back. Nothing anywhere had ever referred to them, which is the only condition
under which this is safe. **It is not a precedent**: the moment a rule ID reaches code, a log or a
spreadsheet, it is frozen and a changed rule gets a new number.

A rule whose reason for existing goes
away is marked **RETIRED** and its ID is left in the table rather than deleted, so a log line or
a spreadsheet column from an older run still resolves to what it meant when it was written.

## Phase A: scan and pre-flight (QC-0xx)

| ID | severity | scope | check |
|---|---|---|---|
| QC-001 | error | turnover | No `.otio` (or `.edl`) found in turnover folder |
| QC-002 | error | turnover | Timeline failed to parse |
| QC-003 | warning | turnover | EDL used instead of OTIO (reduced validation) |
| QC-004 | warning | turnover | Timeline contains no video clips on any track |
| QC-005 | info | turnover | Turnover folder name does not match `turnover###_MM_DD_YYYY_name` pattern; fields need manual entry |
| QC-006 | RETIRED | | Was: no EDL carrying CDL found. The tool no longer reads CDL; the grade arrives as a CLF (COLOR_AND_FORMAT section 1). Replaced by QC-008. **The ID is not reused** |
| QC-007 | RETIRED | | Was: CDL found but failed to parse. Replaced by QC-019, which asks the same question of a CLF. **The ID is not reused** |
| QC-008 | error | turnover | No colour session package for the turnover: no final EDL, or no CLFs. Nothing final can be rendered. Scan and review are unaffected, which is the point of it being turnover scope and not batch scope: one turnover can be waiting on colour while another renders. Distinct from QC-001, which is about the shooters' timeline |
| QC-009 | error | row | No CLF for this row: the colour session delivered none that matches it (OQ-33), or the file it names is missing. An error rather than a warning, and this is the deliberate reversal of retired QC-017, which said the same thing about the shooters' CDL and only warned: an ungraded plate used to be a lesser deliverable that was still watchable, and it is now the wrong pixels under the right filename |
| QC-010 | error | row | Clip name does not match the naming regex |
| QC-011 | warning | row | Duplicate clip name within the batch |
| QC-012 | error | row | Media not found (referenced path missing and no unique filename match) |
| QC-013 | error | row | Media ambiguous (multiple filename matches) |
| QC-014 | error | row | Media unreadable by ffprobe/OpenEXR |
| QC-015 | warning | row | Image sequence has gaps in frame numbering |
| QC-016 | warning | row | Media path was remapped via path map (info for trust) |
| QC-017 | RETIRED | | Was: clip has no matching CDL entry in the EDL. Replaced by QC-009. **The ID is not reused** |
| QC-018 | warning | row | The container's own colour tags contradict the source encoding in use, which is the clip's metadata in camera mode and the Settings studio standard in studio mode. No standard transfer tag names a camera log encoding, so the sidecar is the authority and the decode is forced to match it (COLOR_AND_FORMAT section 2); this fires when what the file does claim disagrees. Information, not a veto. **Includes the range and matrix flags**, because a log signal carried as YCbCr with the wrong range decodes to crushed blacks and clipped whites that look almost right |
| QC-019 | error | row | The CLF will not load in OpenColorIO. Distinct from QC-009, which is about the file not being there: this one is about the file there being unusable. Colour that is unknown is worse than colour that is missing, because a deliverable rendered past it silently ships the wrong look |
| QC-020 | error | row | Source pixel format unsupported for a log plate (8 bit, or 4:2:0) |
| QC-021 | warning | row | Source is not the expected delivery format, which is ProRes 4444 or DNxHR 444, 4:4:4, in the log encoding the mode calls for. A 4:2:2 variant decodes correctly and delivers usable work, but subsampled chroma in a log signal is stretched when it is linearised and shows on saturated edges. A source already in ACEScct or ACEScg lands here too: nothing is wrong with it, the IDT stage is simply a no-op |
| QC-022 | error | row | Source codec not decodable |
| QC-023 | error | row | Source resolution is not 3840x2160. Enabling "allow non-4k" downgrades it to a warning rather than silencing it, because `render._fit` resamples to the target either way and a squashed plate should still be said out loud. Aux stills and BTS are not asked: they are delivered at their own size |
| QC-024 | warning | row | Source letterboxed/pillarboxed to 3840x2160 |
| QC-025 | error | turnover | Timeline fps differs from project fps |
| QC-026 | error | row | Source fps differs from project fps |
| QC-027 | error | turnover | Drop-frame timecode |
| QC-028 | warning | row | Source has no embedded timecode |
| QC-029 | warning | row | OTIO source range does not fit inside media (timeline references frames the media does not have) |
| QC-030 | warning | row | Fewer than "expected handle frames" available beyond current Out (or before In) |
| QC-031 | error | row | In or Out outside source range after editing |
| QC-032 | error | row | In greater than Out |
| QC-033 | warning | row | Duration below minimum (default 120 frames) |
| QC-034 | warning | row | Duration above maximum (default 240 frames) |
| QC-035 | info | row | In/Out differ from turnover snapshot. **Unchanged in meaning and mostly changed in cause**: the snapshot is what the shooters delivered, and since 2026-09-11 most of the difference is the colour session's own approved trim rather than anything the editor did. QC-045 is the one that reports the editor |
| QC-045 | warning | row | Current In/Out differ from the **approved** In/Out on the colour session's final EDL. A warning where QC-035 is info, because this is a deviation from an edit the AD signed off rather than a record of one: the delivered shot is not the shot that was approved, and the only place that fact exists is this rule. Fires on a deliberate one-off trim, which is a supported thing to do (PRD FR-5), and on a colour session ingested after a trim was already made, which overwrites it |
| QC-046 | error | row | **Camera log mode only.** The clip's metadata names no source encoding: the field is absent, or empty. The row cannot render, because there is no correct input transform to guess at and the wrong one produces a plate that looks entirely normal and is not. Switching the batch to studio standard mode is the deliberate way past it, and it is a decision rather than a fallback, which is why nothing does it automatically (OQ-44) |
| QC-047 | error | row | **Camera log mode only.** The source encoding the clip's metadata names cannot be resolved to one colour space in the pinned config. Three distinct causes, one severity: the name is unrecognised (a fourth camera nobody has mapped), it is ambiguous ("S-Log3" names four colour spaces, since a curve does not choose a gamut), or it names a variant the config does not carry (LogC3 at an exposure index other than EI800, BMD Film before Gen 5, Canon in BT.2020 rather than Cinema Gamut). **Never a nearest match**: applying the EI800 curve to an EI400 plate is wrong by an amount nobody sees on a monitor and every comp inherits. The message names what was written and what it could not be resolved to (OQ-34) |
| QC-036 | info | row | Shot code edited from original clip name |
| QC-037 | RETIRED | | Was: colour adjusted from neutral, for the four per clip colour controls. **The controls are removed from v01** and there is nothing to report. **The ID is not reused** |
| QC-038 | error | row | The studio standard source encoding named in Settings has no OpenColorIO equivalent, so no input transform can be built. **Studio mode only**; camera mode's equivalents are QC-046 and QC-047, which differ in who has to fix them: this one is a Settings value the editor typed, those are metadata a shooter wrote. Batch wide in practice rather than per row, because the encoding is one constant for every file (COLOR_AND_FORMAT section 1), but it is reported on the row because the row is what cannot render |
| QC-039 | error | row | The CLF appears to contain a display rendering: probing it shows an output that is bounded or otherwise not scene linear ACEScg. The result would be a display referred file claiming to be linear, which comps wrong and looks completely normal until someone tries to work on it (COLOR_AND_FORMAT section 1) |
| QC-040 | warning | row | Plate (pl) has no associated audio clip |
| QC-041 | warning | row | More than one audio clip overlaps the video clip |
| QC-042 | error | row | Associated audio file missing or unreadable |
| QC-043 | warning | row | Audio duration differs from the video In/Out range by more than one frame, in either direction, so it will not sync. Audio format itself is left flexible; this is a sync check, not a format check. OQ-27 makes the expectation firm: a wav runs cut point to cut point, so a mismatch **at scan time** means a malformed turnover, while one **after an edit** is the editor's own trim showing up, because the wav deliverable is a byte copy and is never trimmed to the new range. The reference mp4 syncs either way; it seeks and pads the audio to the picture |
| QC-044 | warning | row | Audio not 16 bit PCM (will be extracted as 16 bit) |
| QC-050 | warning | row | Plate (pl) has no HDRI side file |
| QC-051 | warning | row | Plate (pl) has no camData side file |
| QC-052 | warning | row | HDRI file fails OpenEXR header read |
| QC-053 | info | row | camData parsed; N key/value pairs found. **Raised by `preflight`, not by the model rules**, because it opens the file: the same reason QC-052 lives there. A file that will not open is a warning under this same ID. The count is the check: a file yielding zero pairs is a file whose format has changed, and that is otherwise invisible as an empty sheet. OQ-11 |
| QC-054 | warning | turnover | No lens grid folder in turnover. The studio's sheet marks it Required, so this chases the shooter. It is a folder in the package, never a clip on the timeline (OQ-20) |
| QC-057 | info | turnover | Lens grid folder present. In v01 the tool does not deliver it: the editor moves it to `_turnovers/` and renames it per NAMING_SPEC section 3. Raised so a manual step is not a forgotten one (OQ-20) |
| QC-055 | warning | row | Aux still (colorChart, mirrorBall, greyBall, sizeRef) has more than one frame; first frame will be used |
| QC-056 | warning | row | BTS still is not png, jpg or jpeg, so no delivery name exists for it and it is not planned |
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
- Shots: one row per shot row. Columns: turnover, original clip name, final shot code, elem, source path, source fps, source res, snapshot In/Out (frames and TC), final In/Out, duration, max available, audio path, edited, **CLF** (the filename of the grade the row was rendered through, empty when it rendered ungraded), skip reason, warnings (IDs), errors (IDs)
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
| 7 | `PLATES` | `4K ✓` and `HD ✓` on two lines, one mark per raw sequence delivered, `—` for one that was not |
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
