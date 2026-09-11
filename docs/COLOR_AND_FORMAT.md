# Color and Format

## 1. Color policy (v01)

**The source color space is a setting, not a constant.** OQ-17 is resolved: the turnovers
arriving today have the sRGB curve **baked in on every file, the EXRs included**. They are
display referred, not scene referred. The shooters are expected to move the EXRs to scene
linear sRGB later, so both cases are supported and one setting selects between them. It
lives in `core/color.py` and defaults to baked sRGB.

| setting | what the source is | today |
|---|---|---|
| `srgb_display` | sRGB curve baked in, display referred | **the v01 default** |
| `scene_linear_srgb` | scene linear, sRGB primaries | after the shooters change |

- The tool applies no color transform to raw EXR output in either case. Pixels in, pixels out.
- Reference mp4s and the stringout are display encodes and must end up in display sRGB.
  - From a **baked sRGB** source, no transfer is applied. The pixels are already there.
    Applying the linear-to-sRGB curve to a file that already carries it washes out every
    reference deliverable, which is the failure OQ-17 was about.
  - From a **scene linear** source, the tool applies the linear to sRGB piecewise curve
    (IEC 61966-2-1) with ffmpeg `zscale` (`transferin=linear:transfer=iec61966-2-1`).
  - Either way the output is tagged `bt709` primaries and matrix, `iec61966-2-1` transfer.
    Only the work to get there differs. Settings offers Rec.709 OETF as the alternative
    curve. OQ-6.
- Primaries are the same in both cases: sRGB and Rec.709 share them, so nothing about the
  primaries depends on this setting.
- EXR metadata: write `chromaticities` for sRGB/Rec.709 primaries and a
  `proingest/colorspace` string attribute stating what the pixels are, `sRGB_display` or
  `scene_linear_sRGB`. It labels the file; it does not claim a conversion happened.
- The HD downscale runs on the values as delivered, encoded curve and all, which is what
  ffmpeg's `scale` does on the container path too. Resampling in linear light would be
  defensible on a display referred source but would make the two paths disagree and would
  change pixels in a deliverable that is meant to be a faithful reduction.

## 2. Source formats accepted

The tool must handle whatever Resolve can consolidate to that can carry linear float without damage. Accepted:

- OpenEXR image sequences (preferred, any compression, half or float)
- DPX sequences (10/12/16 bit, logged as QC-021 warning because integer containers with linear data lose shadow precision)
- ProRes 4444 / 4444 XQ `.mov` (QC-021 warning, same reason)
- Anything else decodable by ffmpeg is accepted with QC-020 error (8 bit or 4:2:0 sources cannot be legitimate linear plates)

OQ-3: confirm what the consolidated media actually is so the warning levels can be tightened.

## 3. Output formats

| output | spec |
|---|---|
| raw EXR | OpenEXR 2 scanline, DWAA compression level 45, half float RGB (alpha dropped unless source has real alpha, then RGBA), data window = display window, frame numbers start 1001 |
| ref mp4 4k | 3840x2160, H.264 High, yuv420p, CRF 18 (x264 `-preset slow`) or `h264_videotoolbox` when hardware encoding is enabled, keyint 24, `-movflags +faststart`, AAC 192k if audio associated |
| ref mp4 HD | same, 1920x1080 |
| audio | as delivered. If the source is a wav, byte copy. If audio lives inside a container, extract to PCM 16 bit, same sample rate and channel count, no resampling. QC-044 if not 16 bit after extraction |
| stringout | 1920x1080, H.264 High, CRF 20, burn-ins, audio from associated wavs mixed at unity |
| HDRI, stills, lens grid, camData | byte copy with rename, checksum recorded |

### Hardware encoding on macOS

NVENC was the Windows hardware encoder and **does not exist on macOS**. The macOS equivalent is
`h264_videotoolbox`, which the bundled build carries (PROVENANCE.md).

- **The default is software x264 at CRF 18.** It is deterministic, it is what this spec pins,
  and it is what every QC threshold was written against. Hardware encoding is opt-in in
  Settings, exactly as NVENC was.
- VideoToolbox has no CRF. On Apple Silicon it takes a constant-quality `-q:v` on a 1 to 100
  scale where higher is better, which is **not** convertible to a CRF number by any published
  formula. `-q:v 65` is the starting point, not a specification.
- **That number is uncalibrated and must not be trusted until it is measured** on the target
  Mac against x264 CRF 18 on a real plate. Until then Settings should describe it as an
  approximation. OQ-23.
- Detection is a trial encode of a few frames, not a string match on `-encoders`. A codec
  compiled into the binary can still fail to open a session on the actual hardware, and the
  reference deliverables are not the place to discover that.

## 4. Resolution rules

- 4k deliverables are exactly 3840x2160. HD deliverables are exactly 1920x1080.
- Source must be 3840x2160 for a normal plate. Anything else: QC-023 error, row blocked, unless the user enables "allow non-4k source" in Settings, in which case the tool letterboxes/pillarboxes into 3840x2160 with black and logs QC-024 warning. No cropping ever.
- HD is produced by Lanczos downscale (`scale=1920:1080:flags=lanczos`), no sharpening. It is a second decode of the source, not a second output of the 4k one. Section 7 says why.
- Aspect other than 16:9 is QC-023 as above.

## 5. Frame rate and timecode

- Project fps default 24, editable. Timeline fps from the OTIO must equal project fps or QC-025 error.
- Shooters set every clip to the project rate in Resolve before exporting the stringout and the EDL, so **the timeline rate is authoritative**. It is what the media is actually played at and what all frame math and timecode conversion use.
- A clip's media may still carry a rate of its own: an EXR sequence states one in its `framesPerSecond` header, a container in its stream. After a conform that value can be stale camera metadata. It is recorded as `MediaInfo.stated_rate` and compared against the project rate for QC-026, but nothing computes with it. Computing with a stale rate would misread the source timecode and block every row.
- A frame count is a property of the file, so it is always counted at the file's own rate, never at the timeline's. A 30 fps container conformed to 24 still holds the frames it holds.
- QC-026 therefore fires when the media states a rate and that rate differs from the project rate. Media that states no rate, such as a DPX sequence, cannot disagree. No retiming is ever performed. See OQ-19 on severity.
- Timecode is non-drop only. Drop-frame OTIO: QC-027 error.
- Source TC = media start timecode from the container or EXR header plus frame offset. If the media has no timecode, source TC is displayed as frames only and QC-028 warning is raised.

## 6. Frame math

Definitions, all integers:

- `src_start`: first frame index of the media (0 for containers, first sequence number for sequences)
- `src_len`: total frames in media
- `in`, `out`: inclusive source frame indices chosen for the deliverable
- `duration = out - in + 1`
- `max_available_out = src_start + src_len - 1`

Output frame numbering: output frame `1001 + k` corresponds to source frame `in + k` for `k` in `[0, duration)`.

Editing:
- Absolute frame typed into In/Out is a source frame index.
- Timecode typed is converted with the source start TC (or record start TC when the toggle is on record).
- Relative offset `+n`/`-n` adds to the current value.
- Constraints enforced live: `src_start <= in <= out <= max_available_out`. Violations show max available and color the row (QC-031, QC-032) but the value is kept so the editor sees what they typed.

## 7. EXR writing pipeline

```
ffmpeg -i <src> -f rawvideo -pix_fmt gbrpf32le - | numpy frames -> float16 -> OpenEXR (DWAA, level 45)
```

- One ffmpeg decode per resolution (4k pass writes 4k EXRs; HD pass adds the Lanczos scale filter). Two passes are simpler than a filtergraph split and cost one extra decode, acceptable at this scale.
- **The frame range is a frame seek, never a time seek.** A container seeks with the `trim` filter, `trim=start_frame=<in>:end_frame=<out+1>`, whose end is exclusive; it counts frames after the decoder has put them back in display order, so a long GOP source lands exactly. A sequence seeks with `-start_number <in>`, which never opens the frames before the range. `-ss` takes a float number of seconds and would land on the wrong frame at 23.976.
- `gbrpf32le` is planar and stores G, then B, then R, so RGB is planes 2, 0 and 1. It carries no alpha, which is OQ-21: the EXR source path preserves a source alpha and the container path cannot yet, because nothing records whether a container has a real one.
- EXR source sequences skip ffmpeg and are read with OpenEXR directly, then downscaled by `core/resize.py`, an antialiased Lanczos-3 in numpy. They have to: ffmpeg's `scale` accepts a float pixel format but **clamps the values to 0-1**, so routing a scene linear EXR through it would flatten every highlight above 1.0 to white without a word. The container path is unaffected because every container format section 2 accepts is integer and already bounded. That is the same filter the container path gets from `flags=lanczos`, so the two paths do not disagree: on a hard edge they are identical, and on smooth content they are within one 8 bit level. OQ-7, resolved.
- **DWAA is lossy.** At level 45 a written frame comes back about a tenth of a percent off the value that went in, proportionally, at every brightness. "Pixels in, pixels out" in section 1 means no colour transform is applied, not that the file is a byte copy of the source. QC therefore never compares a rendered frame to its source by equality.
- The encoder is deterministic: the same pixels and header produce the same bytes, which is what makes the QC-106 per-frame hash meaningful across a re-render.
- `framesPerSecond` is **not** written on output. The OpenEXR Python bindings cannot write a `Rational` attribute, and writing an int or a string under that name would be the wrong attribute type for any reader expecting a rate. Delivered frames carry a per-frame `timeCode` instead, which the bindings do write correctly.
- Checksum (xxhash64) of each written frame is recorded in the batch and the QC log.
- The writer does not read each frame back. QC-103 opens every frame of the finished sequence anyway, and the sequence is not renamed off its `.part` name until that passes, so a second read at write time would double the IO to learn nothing new.
