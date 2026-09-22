# Sample turnover 199: what the files actually contain

Written 2026-09-19 from the folder `Turnover199/` the user dropped into the working tree. The
folder is 775 MB and is ignored by git, so this page is the durable record of what was in it.
Everything under "Verified" was read out of the files with ffprobe, ffmpeg and Python, or out of
a named document; everything under "Not verified" is an inference or a question, with its owner.
`docs/REVIEW_2026-09-19.md` is the review this sample was requested by, and
`docs/OPEN_QUESTIONS.md` carries each open item with an ID.

> **Superseded in part on 2026-09-22.** The user replaced `Turnover199/` with
> **`Turnover199_ForBEN/`**: the same five camera files, a re-exported `.drt` and a re-exported
> CSV, this time **with the metadata filled in**. Section 7 at the bottom of this page is that
> folder, and where it contradicts sections 2 to 6 it wins. What did not change: the media, the
> encoding fields, and the finding that the `.drt` carries no per-clip metadata values. What did:
> `Shot Type` exists and is filled, `Shot` is now `TEST0002`, and the CSV has grown from 37
> columns to 44.

## 1. The folder

Flat, three kinds of file, no side files:

| file | what it is | size |
|---|---|---|
| `C0145.MP4`, `C0148.MP4`, `C0149.MP4`, `C0150.MP4`, `C0152.MP4` | camera clips as Resolve's Media Management wrote them (section 2) | 337, 59, 59, 59, 298 MB |
| `Turnover199.drt` | a DaVinci Resolve Timeline file, a zip of Resolve's own XML (section 3) | 36 KB |
| `Turnover199.csv` | a Resolve Media Pool metadata export, UTF-16 (section 4) | 4 KB |

## 2. The clips

### Verified

Every one of the five files is the same shape. ffprobe on `C0148.MP4`:

```
format:  isom / isomiso2mp41, encoder "Blackmagic Design DaVinci Resolve Studio"
video:   h264, profile "High 4:2:2 Intra", level 51, yuv422p10le, 3840x2160,
         r_frame_rate 24000/1001, time_base 1/24000, ~229 Mbit/s,
         color_range=pc, color_space=unknown, color_transfer=unknown, color_primaries=unknown,
         chroma_location=left, field_order=progressive, bits_per_raw_sample=10
audio:   pcm_s16be, 48000 Hz, 2 channels
data:    tmcd (TimeCodeHandler), timescale 24000, frame duration 1001, 24 frames per second,
         tag timecode=09:38:17:03
```

- **Written by Resolve, not by the camera.** The container's only user data is Resolve's encoder
  tag (`udta/meta/ilst`, 72 bytes). There is no Sony `rtmd` metadata track and no `uuid` box: the
  MP4 has exactly three tracks, video, audio and timecode. The Sony acquisition metadata that
  carries the gamma and gamut (`CaptureGammaEquation`, `CaptureColorPrimaries`, per-frame in the
  camera's `rtmd` track and in its `M01.XML` sidecar) **is not in these files**. Confirmed three
  ways: the box walk, `strings` on the whole file, and ffprobe's colour fields all reading
  `unknown`.
- **The range flag survives and says full, and the colour description is written as unspecified
  on purpose.** The H.264 sequence header (read with ffmpeg's `trace_headers` filter) has
  `video_full_range_flag` = 1 and `colour_description_present_flag` = 1 with `colour_primaries`,
  `transfer_characteristics` and `matrix_coefficients` all equal to 2, the code for "unspecified".
  The three travel together under that one flag (H.264 Annex E), and no standard code point exists
  for S-Gamut3.Cine or S-Log3, so this is what a camera writing S-Log3 is expected to write. The
  header's timing is 1001/48000, the camera's 23.976, not the project's 24. The stream has AUD, SPS,
  PPS and slice NAL units and no SEI. Profile 122 (High 4:2:2), level 51, `constraint_set3`,
  4:2:2 10 bit, square pixels, no HRD, no bitstream restriction. Whether the camera's original
  header reads the same is what the original file shows; nothing here suggests Resolve rewrote it.
  Sony's technical summary for S-Gamut3.Cine/S-Log3 states S-Log3 is recorded full range in XAVC
  with no legal-range option, which matches.
- **Timecode survives and is the camera's.** The `tmcd` track carries each trimmed file's start
  timecode, and it is offset into the original clip by exactly the trim (section 5).
- **Every file has an audio track**, 16 bit stereo PCM with signal in it (`C0148` peaks at
  -22.9 dBFS), including the three that are single-frame stills on the timeline. Section 4 notes
  that the CSV lists those four originals with no audio at all.
- Frame counts: 280, 49, 49, 49, 248. Start timecodes: 09:37:02:18, 09:38:17:03, 09:38:40:03,
  09:38:51:21, 09:40:00:20.

### What the tool does with them today

`media.probe` reads them fine: codec `h264`, `yuv422p10le`, 3840x2160, rate 24000/1001, the
start timecode, stereo 16 bit audio. `naming.parse_clip_name` returns `None` for every name,
with or without the extension, because `C0145` is a camera name and not `SHOW0001_pl01`
(QC-010 on all five). Nothing reads a colour space off them because there is none to read
(QC-046 on all five).

**The decode is wrong by a matrix.** `ffmpeg.decode_command` passes no matrix and these files
declare none, so ffmpeg falls back to its default. Measured on frame 30 of `C0148.MP4`, decoded
to 16 bit RGB: the plain decode is **identical to an explicit BT.601 decode** and differs from an
explicit BT.709 decode by up to 815 of 65535 across **99.35%** of pixels (re-measured 2026-09-21;
an earlier run of this page recorded 97%). Carried through the full OCIO chain to ACEScg that is
**1.94% mean relative error, 7.6% at the 99th percentile, 21.3% peak**, which is the number to
quote, because it is the error in the delivered plate rather than in the intermediate. Which matrix Sony actually
encodes S-Gamut3.Cine with is section 6's question: Sony's summary does not say, and a third-party
dump of a Sony body's acquisition metadata shows `CodingEquations: rec709`; whatever the answer, a UHD
file decoded with the SD default is not it. This is OQ-60, and it is now a measured fact rather than a code-reading.

## 3. The `.drt`

### Verified

A zip archive of four files:

```
project.xml                                   the project: name Turnover199, config
                                              "META_TurnoverNewWorkflow_MAC.Cfg", ProjectVersion 17,
                                              DbAppVer 21.1.0.0017 (the shooters' Resolve)
MediaManagement.dat                           26 bytes
MediaPool/Master/MpFolder.xml                 the media pool: five Sm2MpVideoClip, one Sm2MpTimelineClip
SeqContainer/<uuid>.xml                       the sequence: tracks and timeline clips
```

**Reading it.** The XML is not well formed as written: Resolve uses `::` inside tag names
(`ListMgt::LmPowerNodeList`), which every XML parser rejects. Replacing `::` with `__` before
parsing makes all three files parse. Binary fields are hex-encoded; the larger ones (`FieldsBlob`,
`Clip`, `Body`) are zstd frames (magic `28 b5 2f fd`) behind a short header, and decompress with
the `zstandard` package, **which is not a project dependency**: install it into a scratch
directory rather than the venv, or this page's instructions stop at the first blob. Field blobs
decode as `u32 version, u32 count, then (u32 length,
UTF-16BE key, u32 type, value)`. Doubles are stored as 16 hex bytes: `FrameRate`
`0000000000003840...` is `0x4038000000000000` = 24.0.

**The sequence.** Frame rate **24.0**, resolution 3840x2160, record start frame 86400
(01:00:00:00 at 24). Six video tracks, the first five holding one clip each and the sixth
empty, and one audio track holding `C0145`'s audio. As the file reads, **each clip is on its
own video track**; whether that is how the shooter cut it or an artefact of the export is
section 6's question.

| clip (`Name`) | record `Start` | `Duration` | `In` | `MediaStartTime` (s) | file frames | `MediaFilePath` |
|---|---|---|---|---|---|---|
| `C0145.MP4` | 86400 | 232 | 24 | 34622.75 = 09:37:02:18 | 280 | `/Volumes/WORKING_DRIVE_001/01 Clients/META/125/C0145.MP4` |
| `C0152.MP4` | 86632 | 216 | 24 | 34800.8333 = 09:40:00:20 | 248 | same folder |
| `C0148.MP4` | 86848 | 1 | 24 | 34697.125 = 09:38:17:03 | 49 | same folder |
| `C0149.MP4` | 86849 | 1 | 24 | 34720.125 = 09:38:40:03 | 49 | same folder |
| `C0150.MP4` | 86850 | 1 | 24 | 34731.875 = 09:38:51:21 | 49 | same folder |

Every clip: `MediaFrameRate` 24.0, `MediaReelNumber` empty, `IsForceConformed` true,
`MediaMetadata` empty. The clip `Name` is the filename with its extension.

**What the three stills actually are, looked at 2026-09-21.** Frame 24 of each single-frame clip,
decoded and put through the view transform: `C0148` is a **colour chart** (a ColorChecker held up at
chest height, golden hour, grass field), `C0149` is a **mirror ball** on a rod, `C0150` is an **18%
grey ball** on the same rod. So the sample carries three of the four reference stills the shooters'
spec lists, they are timeline clips rather than side files (the OQ-4 default, now confirmed by
picture), and **not one of them is distinguishable from a plate by any metadata in the delivery**:
all five rows say `Shot` = `TEST0001`, `Scene` = `Reality Burst`. This is the concrete case for
OQ-70's `Shot Type` field, and it is worth showing the shooters.

**Re-verified independently 2026-09-21.** All 81 hex blobs across `MpFolder.xml` and the sequence
file were decoded and searched for `Shot`, `TEST0001`, `Gamma Notes`, `Color Space Notes`,
`S-Log3`, `S-Gamut` and the camera fields. **Not one of them appears anywhere in the `.drt`**,
compressed or not. So the metadata CSV is the sole carrier of both identity and encoding, and the
scan cannot build a row without it. That claim is load bearing for the whole respec, which is why
it has two independent checks behind it.

**What is not in it.** No grade: the version table says `HasCorrection false`, and no CDL,
lift, gain, offset or saturation field exists in any blob, compressed or not. **No colour
space**: a search of every decoded blob for S-Log, gamut, gamma, ACES, Rec.709, `Input Color
Space` and `Radiometry` content finds nothing per clip. The per-clip `Radiometry` blob is 21
bytes and identical across all five clips. The project config blob carries RED, Canon, ARRI and
BRAW raw-decode parameter names and a list of target displays, nothing about these clips.

**Where a `.drt` like this comes from.** The Resolve 18.6 manual, page "Media Management of
Timelines Creates .drt Files": *"When performing Media Management operations to copy or
transcode media from a timeline, a DaVinci Resolve Timeline (.drt) file is automatically created
in the same bin as the resulting media files, linked to the newly created media."* This file's
paths point at the consolidated `125` folder and its `MediaStartTime` values are the trimmed
files' own start timecodes, which is what that by-product would look like.

## 4. The CSV

### Verified

UTF-16LE with a BOM, LF line endings, 37 columns, 5 rows. The column names are Resolve's Media
Pool metadata fields, in the order Resolve's metadata export writes them:

```
File Name, Clip Directory, Duration TC, Shot Frame Rate, Audio Sample Rate, Audio Channels,
Resolution, Video Codec, Audio Codec, Shot, Scene, Start TC, End TC, Start Frame, End Frame,
Frames, Bit Depth, Field Dominance, Data Level, Audio Bit Depth, Date Modified, EDL Clip Name,
Input Gamma, Camera Type, Camera Manufacturer, Camera Format, Camera FPS, Shutter Type,
Shutter Angle, Shutter Speed, ISO, Lens Type, Lens Number, Camera Aperture, Camera Position,
Gamma Notes, Color Space Notes
```

**The rows describe the original camera clips, not the trimmed ones.** `C0145`: Clip Directory
`/Volumes/WORKING_DRIVE_001/01 Clients/META/TO111/Raw`, Start TC 09:36:55:20, 516 frames,
Duration 00:00:21:12; the trimmed file starts 09:37:02:18 and has 280 frames. Date Modified is
27 August 2026 for all five.

Per clip, the same on every row unless noted:

| field | value |
|---|---|
| Shot | `TEST0001` |
| Scene | `Reality Burst` |
| EDL Clip Name | the filename, `C0145.MP4` |
| Shot Frame Rate / Camera FPS | `24.000` / `24` |
| Video Codec | `H.264 High 4:2:2 L5.1` |
| Bit Depth / Data Level | `10` / `Auto` |
| Input Gamma | `Gamma 2.4` |
| Camera Type / Manufacturer / Format | `A7V` / `Sony` / `35.9mm x 24mm` |
| Shutter Type / Angle / Speed | `Rolling` / `170.5` / `1/51` |
| ISO | `250` |
| Lens Type / Lens Number / Aperture / Camera Position | `Tamron 20-40mm` / `40mm` / `2.81` / `1.157m` |
| **Gamma Notes** | **`S-Log3`** |
| **Color Space Notes** | **`S-Gamut3.Cine`** |
| Audio Channels / Bit Depth | `2` / `16` on `C0145`; `0` / blank on the other four |

**This is the only place in the sample where the camera's encoding is named.** Gamma Notes and
Color Space Notes together are exactly the `S-Gamut3.Cine/S-Log3` the tool needs, and they sit
beside exposure, lens and focus-distance values that nobody types by hand.

### Not verified

- **Who wrote those two fields.** Two sources say Resolve does not read Sony acquisition metadata
  out of MP4 files itself: the SLogMetaRaw README ("Resolve reads Sony shooting data only from
  MXF files ... the MP4s contain the same data, but Resolve ignores it") and a Blackmagic forum
  thread titled "Resolve should read Camera Metadata" whose accepted workaround is a script. Two
  community scripts write it into the Media Pool: `deric/DaVinciResolve-metadata` maps exiftool's
  `AcquisitionRecordGroupItemValue` into **Color Space Notes** and can set the clip property
  **Input Color Space** to `S-Gamut3.Cine/S-Log3` from it, and SLogMetaRaw (Resolve 21, macOS)
  reads the `rtmd` track into Media Pool fields and the CSV export. Whether this CSV came from
  Resolve alone, from one of those, or from typing is the user's to say (OQ-68).
- **`Input Gamma: Gamma 2.4`.** No source found for what this metadata column reports. The
  Resolve scripting API's clip property snapshot has `Input Color Space` (a clip property, default
  `Rec.709 (Scene)` in the published example) and no `Input Gamma`; the metadata export has
  `Input Gamma` and no `Input Color Space`. If it reflects the shooter's project default rather
  than the clip, it says the clip's Input Color Space was never set, which would matter for
  OQ-44. Ask, or read it off the project.

## 5. The arithmetic that ties the three together

All at 24 frames per second, which is the rate the `.drt` and the CSV count in.

- `C0145`: original start 09:36:55:20, trimmed start 09:37:02:18, a difference of 166 frames.
  The timeline clip starts 24 frames into the file (`In` 24) and runs 232; the file has 280 =
  24 + 232 + 24. **Copy with trim was run with 24-frame handles on both sides**, one second.
- `C0152`: 248 = 24 + 216 + 8. The tail handle is short because the source ran out: the
  original is 360 frames from 09:39:56:04, the trim starts 112 frames in, and 112 + 248 = 360.
- The three stills: 49 = 24 + 1 + 24, one frame on the timeline with a second either side.
- The two plates are butt-joined on the record side (86400 + 232 = 86632) and the stills follow
  at 86848, 86849, 86850.
- **The file says 23.976 and Resolve says 24.000.** Container time base 1/24000 with a frame
  duration of 1001, `tmcd` 24000/1001, and the audio confirms it: `C0145` carries 560560 samples,
  which is 280 frames at 48000 Hz and 24000/1001 exactly. The `.drt` timeline and every
  `MediaFrameRate` are 24.0, the CSV says 24.000, and `IsForceConformed` is true on every clip.
  Which rate the camera was set to, and which one the shooter's project imposed, is OQ-69.

## 6. Questions this sample raises, with owners

| ID | question | owner |
|---|---|---|
| OQ-58 | Answered for the file: the trim strips the gamma and gamut metadata. The encoding is in the CSV's Gamma Notes and Color Space Notes, and nowhere else in the sample | closed for the file; the CSV's provenance is OQ-68 |
| OQ-60 | Range flag is full and survives; matrix is unspecified and ffmpeg defaults to BT.601 on these UHD files. Which matrix Sony encodes with wants Sony's own document | Claude, with a Sony source |
| OQ-61 | Copy with trim: one file per timeline clip, timecode kept, 24-frame handles, an audio track on every file, metadata stripped | answered by the sample |
| OQ-62 | Answered: clips keep the camera's names and the shot code is the `Shot` metadata field, carried by the CSV. What carries the element type and the still type is OQ-70 | user, shooters (OQ-70) |
| OQ-68 | Answered in part: Resolve exports the CSV and the shooter types `Gamma Notes` and `Color Space Notes` by hand. Still open: `Input Gamma`, the five tracks, and whether the `.drt` is handed over on purpose | user |
| OQ-69 | Answered: the camera shoots 23.98, the shooters conform to 24.000 in Resolve, the file stays 24000/1001, the outputs must be 24. The tool already treats the timeline as authoritative; QC-026 and the 0.1% audio drift are the respec's | Claude |
| OQ-57 | The `.drt` carries the timeline rate, record positions, source starts and handles that an EDL cannot, and none of the grade. Whether the scan reads it beside Ben's EDL | user, then Claude |
| new | Five video tracks with one clip each: how the shooter cut it, or how the export writes? The CDL export needs one track | user |
| new | One original camera file, or its `M01.XML` sidecar, would show the `rtmd` metadata and the camera's own rate | user |


## 7. `Turnover199_ForBEN/`, the metadata-filled re-export (2026-09-22)

The user replaced the folder with this one. Same five clips, byte-identical sizes; a 39 KB `.drt`
and a 5 KB CSV in place of the 36 KB and 4 KB ones. **It is git-ignored** under its own
`.gitignore` entry, so this section is its durable record.

**It is the shooters' handover to Ben, not Ben's handover to the tool.** The folder name says so
and there is **no `.edl` in it**. Pointed at as it stands it is QC-001 and does not scan, which is
correct: this is workflow step 7, not step 15.

### Verified: `Shot Type` is filled, and it is the vocabulary the spec describes

| file | `Shot` | `Shot Type` | what the picture is (section 2) |
|---|---|---|---|
| `C0145.MP4` | `TEST0002` | `pl01` | plate, 516 frames |
| `C0148.MP4` | `TEST0002` | `colorChart` | ColorChecker |
| `C0149.MP4` | `TEST0002` | `mirrorBall` | mirror ball |
| `C0150.MP4` | `TEST0002` | `greyBall` | 18% grey ball |
| `C0152.MP4` | `TEST0002` | `cp01` | clean plate, 360 frames |

Every reading rule in `docs/NAMING_SPEC.md` section 1 is exercised by those five values, and two
of them are load bearing here rather than hypothetical:

- **Plates carry an explicit index and stills do not.** `pl01` and `cp01` are written out in full;
  `colorChart`, `mirrorBall` and `greyBall` are bare. So "a bare code means index `01`" is what
  turns three of these five rows into a filename.
- **The camel case is kept in this sample**, but the casefolded parse stays, because one shooter
  keeping it is not the same as every shooter keeping it.
- `Shot` moved from `TEST0001` to `TEST0002` and `Scene` from `Reality Burst` to
  `Break apart/shatter`. Nothing reads either, but a page that quotes `TEST0001` is quoting the
  old folder.

`Gamma Notes` = `S-Log3` and `Color Space Notes` = `S-Gamut3.Cine` on all five rows, unchanged, so
the encoding chain verified on 2026-09-21 is verified again on a second export.

### Verified: the CSV has 44 columns and `Shot Type` appears twice

Seven columns are new since the 37-column export: `Shot Type` (position 12), `Color Chart`,
`VFX Grey Ball`, `VFX Mirror Ball`, `Shot Code`, `Intended Effect Type`, and **`Shot Type` again**
(position 44).

**Two columns are called `Shot Type` and both are filled with the same value on all five rows.**
That is not a Resolve bug, it is two different fields with one name: position 12 is Resolve's
built-in Media Pool `Shot Type`, and position 44 is a **user-defined custom field the shooters
created, also called `Shot Type`** (proved below, out of the `.drt`). They agree in this export.
Nothing guarantees they agree in the next one, and Resolve's built-in `Shot Type` is a framing
field whose expected values are things like a wide or a close up, so a shooter using it as
intended would put `Wide` in one and `pl01` in the other.

**`csv.DictReader` silently keeps the last duplicate.** A reader that does not handle this by
design is picking a column by luck. The rule the reader needs: read both, take the one that
resolves to a known clip type, and raise a QC result when they disagree or when neither resolves.

Two more redundancies in the same export:

- **`Shot Code` (position 42) duplicates `Shot` (position 10)**, both `TEST0002` on every row.
  `Shot` is the documented carrier and stays the one that is read.
- **`Color Chart`, `VFX Grey Ball` and `VFX Mirror Ball`** are Resolve built-ins and carry `1` on
  exactly the matching still and empty elsewhere. A second, redundant carrier for three of the
  four reference still types, with **no `sizeRef` equivalent**, which is why `Shot Type` remains
  the carrier and these are at most a cross-check.

`Intended Effect Type` = `Break Apart` on every row. Nothing consumes it.

### Verified: the `.drt` carries the field names but still none of the values

The `.drt` is a zip of four members (`project.xml`, `MediaManagement.dat`,
`MediaPool/Master/MpFolder.xml`, `SeqContainer/<uuid>.xml`). All 75 hex blobs across them were
unhexlified and the 26 that are zstd frames decompressed, then every member and every blob was
searched in ASCII, UTF-16LE and UTF-16BE.

**Found**: `Shot Type`, `Shot Code` and `Intended Effect Type`, in one blob of `project.xml`, as
**field definitions** with a UUID each. **Absent everywhere**: `TEST0002`, `colorChart`,
`mirrorBall`, `greyBall`, `S-Log3`, `S-Gamut`.

So the finding from 2026-09-21 holds on a second, metadata-filled export, and is now sharper than
it was: **the `.drt` carries the schema of the shooters' custom metadata and none of its values.**
The CSV is the sole carrier. That claim now has two independent checks on two different files.

### Verified: the shooters' custom metadata field set

Read out of that `project.xml` blob, in file order:

`Shot Code`, `Intended Effect Type`, `Shot Type`, `Camera Model`, `Sensor Dimentions`,
`Lens Name`, `Lens Focal Length`, `Shutter Angle`, `Shutter Speed`, `ISO or EI`, `Aputure Stop`,
`Camera Height`, `Camera Tilt Degrees`, `Camera Roll Degrees`, `Geo Location`, `Date Filmed`,
`Time Filmed`, `Camera Height`, `Camera Tilt Degrees`, `Camera Roll Degrees`, `Date Filmmed`,
`Time Filmmed`, `Camera Manufacturer`, `HDRI`, `BTS Images`, `Scans`.

Three things in that list are worth acting on:

- **`HDRI`, `BTS Images` and `Scans` are per-clip fields the shooters already have**, and all
  three are empty in this export, so none of them reaches the CSV. If they were filled, a clip
  would state whether it has an HDRI without anything having to scan the folder for one.
- **Six fields are defined twice**: `Camera Height`, `Camera Tilt Degrees` and `Camera Roll
  Degrees` each appear with two different UUIDs, and `Date Filmed` / `Time Filmed` sit beside
  `Date Filmmed` / `Time Filmmed`. A duplicated custom field is how a CSV ends up with two
  columns of one name, which is exactly what happened to `Shot Type`.
- **Four are misspelt in the shooters' own project**: `Sensor Dimentions`, `Aputure Stop`,
  `Date Filmmed`, `Time Filmmed`. Worth showing them, along with the resolution typos in their
  spec sheet.

### How to re-read it

`zstandard` is **not a project dependency**. Install it into a scratch directory, never the venv:

```
pip install --target /tmp/zstdlib zstandard
PYTHONPATH=/tmp/zstdlib python3 -c "..."
```

The `.drt` is a plain zip; read its members with `zipfile`, find `[0-9a-fA-F]{64,}` runs in each,
unhexlify, look for the zstd magic `28 b5 2f fd` and decompress from it. The CSV is UTF-16 with a
BOM: `iconv -f UTF-16 -t UTF-8`, then `csv.reader`, **not** `csv.DictReader`, because of the
duplicate column name.

## 8. The ALE, added 2026-09-22. It answers OQ-75.

> **The ALE is not adopted** (user, 2026-09-22, closing OQ-75). The carriers stay as built: Ben's
> EDL for the cut and the grade, Ben's metadata CSV for identity and encoding. **This section
> stays**, because two of its findings survive the decision and are now load bearing rather than
> comparative: the CSV in this folder is **stale** in every field but `File Name`, and its
> `Shot Type` column is **duplicated**. The rest of the section is the evidence the decision was
> made on, kept so it is not re-measured.

The user dropped `Turnover199.ale` (3.3 KB) into the same folder. It is a shooters' export sitting
in the `_ForBEN` folder, not Ben's, which matters for the CDL values below and **not** for the
finding that decides OQ-75.

### Verified: shape

ASCII, **CRLF**, tab delimited, the three ALE sections. Header: `FIELD_DELIM TABS`,
`VIDEO_FORMAT CUSTOM`, `AUDIO_FORMAT 48khz`, **`FPS 24`** - one rate for the whole file, which is
why a mixed-rate turnover cannot be expressed as one ALE. **50 columns**, 5 data rows, every row
the full width, and a trailing tab that yields one empty column name a reader must drop.

### Verified: it carries everything the CSV carries, and more

`Shot` = `TEST0002`, `Shot Type` = `pl01` / `colorChart` / `mirrorBall` / `greyBall` / `cp01`,
`Gamma Notes` = `S-Log3`, `Color Space Notes` = `S-Gamut3.Cine`, plus `Shot Code`,
`Intended Effect Type`, the three Resolve VFX flags, **`ASC_SOP`**, **`ASC_SAT`** and
`RESOLVE_SIZING`. So the shooters' custom fields do survive a Resolve 21.1 ALE export, as OQ-75
predicted from the 20.3 release note.

**It is better than the CSV in four measurable ways:**

1. **`Shot Type` appears once.** The CSV has it twice, at positions 12 and 44, built-in and custom.
   The ALE has no duplicate column name at all, so the collision the CSV reader has to arbitrate
   does not exist here.
2. **It carries the grade.** `ASC_SOP` and `ASC_SAT` per row. The CSV carries no colour decision.
3. **`Source File Path` points at the delivered media**
   (`/Volumes/.../META/Turnover199_ForBEN/C0145.MP4`), where the CSV's `Clip Directory` still points
   at the pre-consolidation originals.
4. **Its `End - Start` is the delivered file's length**, where the CSV's `Frames` is the original
   clip's. **Its `Start` is still the original clip's**, though, which makes the pair a hybrid that
   describes nothing real. See "the timecodes are a hybrid" below - this is a trap, not a win.

### Verified: the CSV in this folder is stale, and the ALE is not

This was not known before the ALE arrived. The CSV's `Clip Directory` is
`/Volumes/.../META/TO111/Raw` - **the original camera media**, not the consolidated folder - and its
`Frames`, `Start TC` and `End TC` describe those originals:

| clip | delivered file (ffprobe) | CSV `Frames` | ALE `End - Start` |
|---|---|---|---|
| `C0145.MP4` | 280 | 516 | **280** |
| `C0148.MP4` | 49 | 168 | **49** |
| `C0149.MP4` | 49 | 312 | **49** |
| `C0150.MP4` | 49 | 420 | **49** |
| `C0152.MP4` | 248 | 360 | **248** |

**Nothing may read a duration, a frame count or a path out of the CSV.** `File Name` still matches,
because camera filenames are kept, so identity and encoding are still safe to take from it. Every
other field in it describes a file that is not the one in the folder. ffprobe is the authority on
media facts and already is; this is why.

### Verified: the ALE's timecodes are a hybrid, and are wrong for the delivered media

Corrects the first draft of this section, which said the ALE's ranges agree with the delivered
media. **The length does. The timecode does not.**

| clip | delivered file's own TC | delivered len | ALE `Start` | ALE len | CSV `Start TC` | CSV len | ALE `Start` - file TC |
|---|---|---|---|---|---|---|---|
| `C0145.MP4` | 09:37:02:18 | 280 | 09:36:55:20 | 280 | 09:36:55:20 | 516 | **-166** |
| `C0148.MP4` | 09:38:17:03 | 49 | 09:38:15:08 | 49 | 09:38:15:08 | 168 | **-43** |
| `C0149.MP4` | 09:38:40:03 | 49 | 09:38:33:04 | 49 | 09:38:33:04 | 312 | **-167** |
| `C0150.MP4` | 09:38:51:21 | 49 | 09:38:47:08 | 49 | 09:38:47:08 | 420 | **-109** |
| `C0152.MP4` | 09:40:00:20 | 248 | 09:39:56:04 | 248 | 09:39:56:04 | 360 | **-112** |

**The ALE's `Start` is the original camera clip's start timecode** - identical to the CSV's
`Start TC` on all five rows - **while its length is the consolidated file's.** So `Start` and `End`
together describe a range that exists nowhere: it begins at the original clip's head and runs for
the delivered file's duration. The delivered file's own timecode, confirmed independently by
ffprobe and by the `.drt`'s `MediaStartTime`, is **43 to 167 frames later**, and the offset differs
per clip so no constant absorbs it.

The likely cause is ordinary staleness: the Media Pool clip was logged from the original camera
file and relinked to the consolidated one, so its recorded start TC is the original's while its
length is recomputed from the media now on disk. The same staleness is what makes the CSV's fields
wrong, and here it produces a row that is half fresh and half stale.

**Consequence: nothing may conform on an ALE timecode either.** Anything that took `Start` as the
delivered file's head would be out by up to seven seconds, per clip, silently. The delivered media's
own embedded timecode is the authority, as it already is.

### Verified: the ALE does not carry the cut, and that decides OQ-75

**`End - Start` is the whole delivered file on all five clips**, handles included. The `.drt` in
the same folder records a real trim on every one of them:

| clip | media | `.drt` `In` | `.drt` `Duration` | head | tail | ALE length |
|---|---|---|---|---|---|---|
| `C0145.MP4` | 280 | 24 | 232 | 24 | 24 | 280 |
| `C0152.MP4` | 248 | 24 | 216 | 24 | **8** | 248 |
| `C0148.MP4` | 49 | 24 | 1 | 24 | 24 | 49 |
| `C0149.MP4` | 49 | 24 | 1 | 24 | 24 | 49 |
| `C0150.MP4` | 49 | 24 | 1 | 24 | 24 | 49 |

**The export ignored a trim that existed in the same project.** That is the strong form of the
finding: not "this ALE happened to have no trim in it", but "Resolve wrote clip ranges while a
232-frame timeline range sat beside them in the `.drt`". An ALE carries no record timecode and is a
clip log, and this confirms it writes clip-level ranges too.

**So the ALE cannot replace the EDL.** It can replace the CSV outright. The handover that follows
from this evidence is **media + EDL (the cut) + ALE (identity, encoding, grade)**.

Two smaller things fall out of that table. **Tail handles are not reliably 24**: `C0152` has 8.
Anything asserting a symmetric handle count is wrong, and QC-030's "expected handle frames" is a
warning for good reason. And the three reference stills are **one frame on the timeline inside a
49-frame file**, so the still the tool delivers is one frame chosen out of 49.

### Verified: the CDL in this file, and why it is not Ben's

Every row carries the identical CDL: `ASC_SOP (1.2623 1.2764 1.3219)(0 0 0)(1 1 1)`, `ASC_SAT
1.0000`. Slope only, no offset, unit power, unit saturation, and **the same numbers on all five
clips including the three reference stills**. That is one uniform correction across the whole
turnover, not a per-shot grade, which is what a shooters' export before Ben touches it should look
like. It is a shape check, not the grade: do not calibrate anything against these numbers.

It does raise a rule to settle before an ALE is adopted. **The reference stills are delivered
ungraded by design, and this ALE carries a CDL on them anyway.** Whatever reads the ALE has to
ignore the CDL on a `colorChart`, `mirrorBall`, `greyBall` or `sizeRef` row rather than apply it.

### How to read it

CRLF, so strip `\r`. Split the file on the bare lines `Heading`, `Column` and `Data`; the line
after `Column` is the tab-separated column names, every line after `Data` is a row. Drop the empty
trailing column. `Start` and `End` are `HH:MM:SS:FF` at the header's `FPS`, and **`End` is
exclusive**: `End - Start` equals the frame count exactly, with no off-by-one.
