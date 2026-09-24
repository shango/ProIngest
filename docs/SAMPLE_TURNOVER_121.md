# Turnover121: the second official turnover

Measured 2026-09-23 from `turnover121_09_23_2026_danielluckett/` (untracked, 90 MB). The first
sample is `docs/SAMPLE_TURNOVER_199.md`; this one differs from it in camera, in timecode, and in
using the same clip more than once, and each difference found a gap in the tool.

## What is in the folder

- **Seven `.mov` files**: iPhone 16 Pro through the Blackmagic Cam app, H.264 High, **8 bit 4:2:0**,
  3840x2160, BT.709 limited tags, AAC 16 kHz (one at 48 kHz). Encoded `Apple Log`.
- `Turnover121.edl`: 11 events, **no `FROM CLIP NAME`**, every reel `AX`, a CDL on every event.
- `Turnover121.csv`: UTF-16, 45 columns, 9 rows. **No `Gamma Notes` or `Color Space Notes`**;
  Resolve's own `Input Color Space` says `Apple Log`.
- `Turnover121.ale`: 11 data rows. `Turnover121.drt`: a zip holding Resolve's project XML.

## Verified findings

1. **ffprobe reports 480 fps on three of the files.** `r_frame_rate` is 480/1, `avg_frame_rate`
   is 24.004 to 24.014, and `nb_frames` over duration is 24. The iPhone writes uneven
   timestamps and `r_frame_rate` is the grid they fit on. The tool now takes the average,
   rounded to a standard rate within 0.1%, when the two disagree (QC-026).
2. **The timecodes overlap.** Every file's own timecode starts within the first 40 seconds
   of 00:00:00:00, so most EDL events sit inside several files and matching by timecode can
   only refuse (QC-067 on every row). Turnover199 worked because Sony records time of day.
3. **The ALE is one row per EDL event, in timeline order.** 11 and 11 here, 5 and 5 in
   Turnover199, and every event's source timecode falls inside the file its ALE row names.
   That is what names the events now (`core/ale.py`, QC-071). The ALE's `Start`/`End` cover
   the whole clip, not the cut, and it has no speed, so the EDL is still the cut.
4. **The CSV has one row per clip per use**, a use being a distinct source range in the EDL:

   | clip | EDL events | distinct ranges | CSV rows |
   |---|---|---|---|
   | Laser Eyes Effect | 001 | 1 | 1 |
   | Open Door Clean Plate | 002, 007 (freezes of 10 s and 11 s) | 2 | 2 |
   | MacBeth Chart | 003, 008, 010 (frames 212, 221, 212) | 2 | 2 |
   | Cube Shot_S002 | 004, 011 (frame 69 twice) | 1 | 1 |
   | Melting Door - Var 1 | 005 | 1 | 1 |
   | Melting Door- Var 3 | 006 | 1 | 1 |
   | Cube Shot_S001 | 009 | 1 | 1 |

5. **Two freezes.** Events 002 and 007 carry `M2 AX 000.0 00:00:40:10`: the clean plate held
   on source frame 970 for 10 and 11 seconds. The EDL's source out is where the clip would
   have run to, past the end of the file. Delivered as one frame (OQ-63, QC-073).
6. **Every event's slope is 4.886**, on all 11, in the EDL and the ALE alike. Rendered through
   the tool it blows the frame out to white (checked on the cp01 reference). Turnover199's
   was about 1.26. Taken to Ben as a likely export mistake, not a grade.
7. **The CSV's and the ALE's `Start TC` say 00:00:00:00**; the files say, for example,
   00:00:04:20. The file is the authority, as in Turnover199.
8. **The Cube Shots had no Shot and no Shot Type** as delivered. The user corrected the CSV to
   SECA0001 and SECA0002 `sizeRef`, and the Resolve-side handoff is being cleaned up.

## Result

With the CSV as corrected: 7 rows, **0 errors**, 8 warnings (QC-020 on each 8 bit source,
QC-034 on the 264 frame pl02) and QC-072 on the chart and the clean plate. A full render
(before the correction) wrote all 20 deliverables with none failing phase B: the freeze's
references are 120 frames and silent, and its EXRs are one frame each.
