# QC Rules

Every rule has a stable ID, a phase, a severity, and a scope. Severity: `error` blocks the row from rendering (row auto-skipped, reason recorded); `warning` colors the row amber and is logged; `info` is logged only. All results appear in the QC log Deliverables sheet with pass/fail per rule.

Rule IDs never change meaning. New rules get new numbers.

## Phase A: scan and pre-flight (QC-0xx)

| ID | severity | scope | check |
|---|---|---|---|
| QC-001 | error | turnover | No `.otio` (or `.edl`) found in turnover folder |
| QC-002 | error | turnover | Timeline failed to parse |
| QC-003 | warning | turnover | EDL used instead of OTIO (reduced validation) |
| QC-004 | warning | turnover | Timeline contains no video clips on any track |
| QC-005 | info | turnover | Turnover folder name does not match `turnover###_MM_DD_YYYY_name` pattern; fields need manual entry |
| QC-010 | error | row | Clip name does not match the naming regex |
| QC-011 | warning | row | Duplicate clip name within the batch |
| QC-012 | error | row | Media not found (referenced path missing and no unique filename match) |
| QC-013 | error | row | Media ambiguous (multiple filename matches) |
| QC-014 | error | row | Media unreadable by ffprobe/OpenEXR |
| QC-015 | warning | row | Image sequence has gaps in frame numbering |
| QC-016 | warning | row | Media path was remapped via path map (info for trust) |
| QC-020 | error | row | Source pixel format unsupported for linear plates (8 bit, 4:2:0) |
| QC-021 | warning | row | Source is an integer or 4:2:2 container (DPX, ProRes 4444); linear precision at risk |
| QC-022 | error | row | Source codec not decodable |
| QC-023 | error | row | Source resolution is not 3840x2160 (blocked unless "allow non-4k" enabled) |
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
| QC-035 | info | row | In/Out differ from turnover snapshot (edited during review) |
| QC-036 | info | row | Shot code edited from original clip name |
| QC-040 | warning | row | Plate (pl) has no associated audio clip |
| QC-041 | warning | row | More than one audio clip overlaps the video clip |
| QC-042 | error | row | Associated audio file missing or unreadable |
| QC-043 | warning | row | Audio duration differs from the video In/Out range by more than one frame, in either direction, so it will not sync. Audio format itself is left flexible; this is a sync check, not a format check. OQ-27 makes the expectation firm: a wav runs cut point to cut point, so a mismatch **at scan time** means a malformed turnover, while one **after an edit** is the editor's own trim showing up, because the wav deliverable is a byte copy and is never trimmed to the new range. The reference mp4 syncs either way; it seeks and pads the audio to the picture |
| QC-044 | warning | row | Audio not 16 bit PCM (will be extracted as 16 bit) |
| QC-050 | warning | row | Plate (pl) has no HDRI side file |
| QC-051 | warning | row | Plate (pl) has no camData side file |
| QC-052 | warning | row | HDRI file fails OpenEXR header read |
| QC-053 | info | row | camData parsed; N key/value pairs found |
| QC-054 | warning | turnover | No lens grid folder in turnover. The studio's sheet marks it Required, so this chases the shooter. It is a folder in the package, never a clip on the timeline (OQ-20) |
| QC-057 | info | turnover | Lens grid folder present. In v01 the tool does not deliver it: the editor moves it to `_turnovers/` and renames it per NAMING_SPEC section 3. Raised so a manual step is not a forgotten one (OQ-20) |
| QC-055 | warning | row | Aux still (colorChart, mirrorBall, greyBall, sizeRef) has more than one frame; first frame will be used |
| QC-056 | warning | row | BTS still is not png, jpg or jpeg, so no delivery name exists for it and it is not planned |
| QC-060 | warning | row | Existing deliverables found at version N; new render will be version N+1 |
| QC-061 | info | row | Complete QC-passing set exists; row skipped (Force re-render off) |
| QC-062 | error | row | Delivery destination not writable |
| QC-063 | warning | batch | Free space at delivery root below estimated output size |

## Phase B: post-render verification (QC-1xx)

Run per deliverable immediately after its atomic rename. Any error marks the deliverable failed and leaves the row not-done; the file stays for inspection with a `.failed` marker sidecar.

QC-100 is the exception to that: it reports a render that never produced a file at all, so there is nothing to keep and nothing to mark. A render failure leaves no `.part` and no destination, by design.

| ID | severity | scope | check |
|---|---|---|---|
| QC-100 | error | deliverable | Render did not complete; the reason is recorded. Every other QC-1xx is NA when this one fails, because there is no file to check |
| QC-101 | error | exr seq | Frame count equals duration |
| QC-102 | error | exr seq | First frame is 1001, last is 1000 + duration, no gaps |
| QC-103 | error | exr seq | Every frame opens with OpenEXR and header parses |
| QC-104 | error | exr seq | Data window and display window equal target resolution |
| QC-105 | error | exr seq | Compression is DWAA, channels are R,G,B (or R,G,B,A) half |
| QC-106 | error | exr seq | Per-frame xxhash64 matches what the writer recorded |
| QC-107 | warning | exr seq | Frame file size below 10% of median (likely black or empty frame) |
| QC-110 | error | mp4 | ffprobe opens file, stream count as expected |
| QC-111 | error | mp4 | Frame count equals duration (probed with `-count_frames`) |
| QC-112 | error | mp4 | Resolution equals target |
| QC-113 | error | mp4 | fps equals project fps |
| QC-114 | warning | mp4 | Audio stream present iff audio was associated |
| QC-115 | error | mp4 | faststart moov atom at head |
| QC-120 | error | wav | Duration in samples matches source audio (byte copy: checksum equal) |
| QC-121 | error | wav | 16 bit PCM |
| QC-130 | error | copy | Checksum of copied side file equals source |
| QC-140 | error | stringout | Frame count equals sum of durations of included rows |
| QC-141 | warning | stringout | Any burn-in field was empty for any clip |
| QC-150 | error | row | Every planned deliverable for the row exists and passed |
| QC-151 | error | batch | Filename of every deliverable re-parses with the naming regex to the same shot/elem/kind/res/ver |

## QC log structure

`qc_ingest_log_<batch>_<date>.xlsx`

- Summary: batch name, date, tool version, turnovers, rows, rows done / skipped / failed, rule counts by severity
- Shots: one row per shot row. Columns: turnover, original clip name, final shot code, elem, source path, source fps, source res, snapshot In/Out (frames and TC), final In/Out, duration, max available, audio path, skip reason, warnings (IDs), errors (IDs)
- Deliverables: one row per deliverable. Columns: shot code, elem, kind, res, version, path, frames, size bytes, checksum (or first/last frame hash for sequences), then one column per QC-1xx rule with PASS/FAIL/NA
- Side Files: shot code, type, source path, dest path, checksum
- Camera Data: shot code, key, value (one row per pair parsed from camData)

`shot_tracker_<batch>_<date>.xlsx` columns come from the template file configured in Settings (OQ-2). Default template ships with: Shot Code, Element, Turnover, Shooter, Date, Duration (frames), Source TC In, Source TC Out, Version, Delivery Path, Notes.
