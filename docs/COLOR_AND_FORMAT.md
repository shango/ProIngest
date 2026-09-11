# Color and Format

## 1. Colour policy (v01)

**The working space is ACEScg. Sources arrive log encoded, plates are delivered scene
linear and ungraded, and the grade lives only in the viewing copies.**

This **supersedes OQ-17**, which recorded the opposite premise as resolved: display
referred sources with the sRGB curve baked in, and no transfer applied to the references.
That premise was wrong. Everything built on it has been rewritten here rather than
amended, because amending it would leave two readings in one document.

### What arrives

Shooters convert camera original to a studio standard delivery in Resolve, using a
template project the studio supplies (OQ-31). A turnover therefore carries **one encoding
regardless of what anybody shot on**:

| | |
|---|---|
| encoding | **ACEScct** |
| primaries | **AP1**, the ACES working gamut |
| container | **ProRes 4444**, or DNxHR 444 where ProRes is not available |

The camera specific input transform happens in the shooter's Resolve project, where the
camera metadata actually lives. That is the point of specifying ACEScct rather than a
camera log: this tool has one input transform forever, and "which LogC", "which exposure
index" and "mixed cameras in one turnover" stop being questions it has to answer.

4:4:4 matters more here than it would on a display referred source. Subsampled chroma in a
log signal is stretched when the signal is linearised, and shows up on saturated edges.

### What leaves

| deliverable | space | graded |
|---|---|---|
| raw EXR, 4k and HD | **ACEScg**, scene linear, AP1 primaries | **no** |
| reference mp4, 4k and HD | sRGB display | **yes** |
| stringout | sRGB display | **yes** |

**The plate is ungraded and that is deliberate.** The CDL and the AD notes are creative
intent that will move in the DI. A grade baked into a plate can clip highlights the comp
needs, and work done against a graded plate stops matching the moment the grade changes.
The CDL travels **in the EXR header** instead, so the vendor can apply it as a viewing
transform and see exactly what was intended while working on untouched pixels.

### The two branches

One decode, then branch at the top, because the two deliverables want opposite things:

```
ProRes 4444  -  ACEScct, AP1
        |  decode to float RGB, full range
        |
   +----+------------------------------------+
   |                                         |
 PLATE branch                            VIEW branch
   |                                         |
 ACEScct -> ACEScg   (curve only)        CDL        (in ACEScct)
   |                                         |
 resize in numpy, unbounded              AD notes   (in ACEScct)
   |                                         |
 EXR: ACEScg, CDL in the header          ACEScct -> ACEScg -> ACES output transform
                                             |   ... collapsed into one 3D LUT
                                         ffmpeg lut3d, resize bounded
                                             |
                                         mp4: sRGB display
```

Three properties follow, and each is load bearing rather than incidental.

**ACEScct to ACEScg is a curve, not a gamut change.** Both are AP1, so the plate path
applies no primaries matrix and manufactures no out of gamut negatives of its own. That
matters on the HD downscale in particular: resizing a linear image in a gamut too small
for its content is a documented way to produce negative pixels, and AP1 is wide enough
that the question does not arise. Delivering scene linear in Rec.709 primaries was
considered and rejected for exactly this reason.

**The view branch stays bounded until the final encode.** Everything before the output
transform happens in ACEScct, which an integer container bounds to 0..1. swscale clamps
float to 0..1, so keeping the view branch in log means ffmpeg can do the resize and the
reference stays a single fast pass with no frames pulled through Python, which is what M3
was built around. The plate branch is unbounded scene linear and therefore resizes in
numpy, which is what `core/resize.py` exists for.

**The CDL is applied in ACEScct, its native space.** A CDL means what it means in the space
it was authored in. ACEScct exists so grades can be authored in a log domain inside ACES,
and applying one in linear gives a different and wrong answer.

### The viewing transform is one LUT

The whole view branch (CDL, AD notes, ACEScct to ACEScg, ACES output transform to sRGB)
collapses into a **single 3D LUT per clip**, generated in core. ffmpeg applies it with
`lut3d` for the reference mp4; the three viewers in UI_SPEC section 14 apply the same cube
in numpy. They cannot drift apart, which is the failure mode this codebase keeps nearly
hitting. OQ-7 is the same problem in the resampler and it needed a measured test to settle.

A 3D LUT is accurate here because its input domain is log, which is where LUTs are meant to
be authored, and its output is display referred and therefore bounded. The plate branch
cannot use one, because scene linear output is unbounded; that path does the maths directly.

### OpenColorIO

Transforms come from **OpenColorIO**, not from hand written curves and matrices.
`Config.CreateFromBuiltinConfig("studio-config-latest")` carries the ACES transforms inside
the wheel, so **no config files ship**. The macOS arm64 wheel is 5.7 MB, which is nothing
against the 300 MB budget in PRD section 8, and a Windows wheel exists for v02.
`CDLTransform` applies the CDL.

Hand rolling the curves was considered and rejected. Published camera log parameter tables
are exactly the kind of thing that looks correct and is not.

### EXR metadata

- `chromaticities` states **AP1** primaries, not sRGB. That constant is the difference
  between a file that is ACEScg and a file that lies about being ACEScg.
- `proingest/colorspace` states `ACEScg`.
- The CDL is written **twice**: as machine readable slope, offset, power and saturation
  attributes, and as the original CDL text, so a vendor can recover exactly what was
  authored rather than what this tool re-serialised.
- The AD notes are written alongside it under their own attribute, so a reference that
  looks different from the plate can be explained from the plate itself.

## 2. Source formats accepted

The studio sets the delivery spec and the shooters work to a template project, so this is
a specification rather than a survey of what might turn up.

**Expected**, and what every QC rule is written around:

- **ProRes 4444 or DNxHR 444, ACEScct, AP1 primaries.** 12 bit, 4:4:4, full range.

**Accepted with a warning**, because it decodes correctly and delivers usable work:

- ProRes 422 HQ or any 4:2:2 10 bit variant carrying ACEScct. QC-021: chroma is subsampled,
  and a log signal stretched to linear shows that on saturated edges.
- An EXR sequence already in ACEScg or ACES2065-1. Nothing is wrong with it; it simply is
  not what the template project produces, so it is flagged as an unexpected delivery rather
  than a defect.

**Refused:**

- 8 bit anything, and any 4:2:0 source. QC-020. Neither can carry a log signal without
  banding the moment it is linearised.

A source whose colour space cannot be established is QC-018. The tool cannot read ACEScct
off a container, because no standard transfer tag names it, so the working assumption comes
from Settings and QC-018 fires when the container's own tags contradict it.

## 3. Output formats

| output | spec |
|---|---|
| raw EXR | OpenEXR 2 scanline, DWAA compression level 45, half float RGB (alpha dropped unless source has real alpha, then RGBA), data window = display window, frame numbers start 1001. **ACEScg, scene linear, AP1 chromaticities, ungraded**, with the CDL and the AD notes carried in the header (section 1) |
| ref mp4 4k | 3840x2160, H.264 High, yuv420p, CRF 18 (x264 `-preset slow`) or `h264_videotoolbox` when hardware encoding is enabled, keyint 24, `-movflags +faststart`, AAC 192k if audio associated |
| ref mp4 HD | same, 1920x1080 |
| audio | as delivered. If the source is a wav, byte copy. If audio lives inside a container, extract to PCM 16 bit, same sample rate and channel count, no resampling. QC-044 if not 16 bit after extraction |
| stringout | 1920x1080, H.264 High, CRF 20, burn-ins, audio from associated wavs mixed at unity |
| HDRI, stills, camData | byte copy with rename, checksum recorded |
| lens grid | not written in v01; moved and renamed by hand (OQ-20) |

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
