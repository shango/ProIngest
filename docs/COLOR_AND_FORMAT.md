# Color and Format

## 1. Colour policy (v01)

**Colour is finished before the tool runs. A final grade session delivers a CLF per shot, the
tool applies it to everything it writes, and the plate is delivered graded, scene linear
ACEScg.**

This **supersedes the policy of 2026-09-11**, which itself superseded OQ-17. That version had
the shooters delivering ACEScct, the CDL read out of an EDL, an ungraded plate with the CDL
carried in the header, and four colour controls in the tool for the AD's notes. The pipeline
mechanics from it survive almost intact. What changed is where colour is authored and when,
and that moves enough to be worth rewriting rather than amending.

### Two colour stages, and only the second one reaches a deliverable

**Offline.** Shooters deliver a string-out and a CDL with it. The CDL is a starting point and
a record of what the shooter intended, nothing more. **The tool never renders a deliverable
from it.**

**Final.** The AD meeting decides the look, and that decision goes into a colour session in
DaVinci Resolve, where Ben works with the AD. That session exports an **updated final EDL**
carrying the conform, the trims and the CDL, and **a CLF per shot**. The tool conforms from the
EDL and **applies the CLF**. Final colour is applied before every export, the references and the
plates alike.

The consequence to be clear about: **a batch cannot produce final deliverables until the
colour session for it exists.** Scanning, review and In/Out work all happen without it, because
they are about frames rather than pixels. Rendering waits. That is a change of shape in the
user flow and it is written up in PRD section 6.

### The colour session

These are constraints on the session, not descriptions of it. The pipeline below is only
correct if they hold.

| | |
|---|---|
| colour science | DaVinci YRGB Color Managed, **ACES 1.3** |
| timeline space | **ACEScct** |
| input transform | the studio standard log encoding the shooters deliver (OQ-39) |
| grade | **primary only.** No windows, no qualifiers, no tracked secondaries |

**Primary only is a hard requirement rather than a stylistic preference.** A CLF is a static
transform of a pixel value. A window, a qualifier or a tracked secondary is a function of where
the pixel is or what is around it, and none of that survives being written to one. A session
that used one would export a CLF that silently omits it, and the tool would deliver a grade
that is not the grade that was approved.

Everything else a primary can do, the CLF carries: curves, log wheels and hue versus saturation
curves included. **That is the whole reason the CLF is the thing applied rather than the CDL.**
A CDL can say only slope, offset and power per channel plus one saturation, so a grade built
with a curve in it would arrive silently incomplete. The CDL still travels, and it has a job
(see EXR metadata below), but it is a record rather than the transform.

The practical safeguard is that the session also exports the stringout with the real look on it.
**If a reference mp4 from this tool does not match that stringout, something did not survive**,
and that is the comparison to make the first time this runs (OQ-31).

The session exports three things and the tool uses all three:

| export | what it is for |
|---|---|
| the **updated final EDL** | the conform: timecode, shot identity, and the **approved In/Out** from Ben and the AD's trims. It also carries the CDL as `*ASC_SOP` / `*ASC_SAT` comment lines. Supersedes the shooters' EDL entirely |
| a **`.clf` per shot** | **the transform the tool applies**, encoding `ACEScct in > grade > linear ACEScg out`, with no display rendering in it |
| the **stringout** | a ProRes QT with the look and burn-ins. The tool does not build one, and it is what the tool's own references should be checked against |

**The CDL and the CLF both come from this session and they have different jobs**, which is worth
stating plainly because carrying two grade artifacts looks redundant until it is not. The CLF is
applied, because it carries everything a primary grade can contain. The CDL is recorded, in the
EDL and in the EXR header, because it is the form a human or another facility's tool can read,
compare and talk about without an OCIO install. **Where they disagree the CLF is what is in the
pixels**, and the tool never applies both.

**That EDL carries the approved cut as well as the approved colour**, because Ben and the AD
trim in the same session. It is the tool's authority on In and Out. The tool keeps its own
In/Out editing for the one-off trim that is not worth asking for a new EDL (PRD FR-5), and
reports any row that used it (QC-045).

**A trim does not disturb the grade.** A CLF is one static transform for the whole shot rather
than an animated one, so moving In or Out carries it unchanged. The one thing to know is that
extending into the handles applies the approved grade to frames nobody looked at in the session.
For a static primary that is almost always right, and it is the reason the tool's trimming is
described as a one-off rather than a re-edit facility.

### What arrives

| | |
|---|---|
| picture | **ProRes 4444**, one file per shot, with handles beyond the cut |
| encoding | **one studio standard log encoding**, the same for every shooter and every camera (OQ-39) |
| grade | one `.clf` per shot, applied; the CDL travels in the final EDL as the readable record |
| conform | the colour session's final EDL: timecode, shot identity and the approved In/Out |

**The source encoding is a studio standard and is the same on every file, whatever anybody
shot on.** The camera specific input transform happens in the shooter's Resolve project,
where the camera metadata actually lives, and the tool never sees a camera original. This is
the single most valuable property in the whole pipeline and it is worth being explicit about
what it buys: the tool has **one input transform forever**, and "which log", "which exposure
index" (LogC3 is EI dependent where LogC4 is not) and "mixed cameras inside one turnover"
stop being questions it has to answer. It also means no per shot IDT lookup, and no mapping
of Resolve's transform names onto OpenColorIO's, which do not agree and whose near misses
produce plausible looking wrong images.

**Which log is OQ-39**, and the answer changes how much work there is rather than whether it
works. If the studio standard is **ACEScct**, the tool applies no input transform at all:
the colour session's timeline is ACEScct and its CLF starts there, so decode leads straight
into the CLF with nothing in between that could be silently wrong. If it is a camera vendor log
adopted as the house format, the tool applies **one fixed transform** from that encoding to
ACEScct ahead of the CLF. Either way it is a constant, not a per shot decision.

### The chain

One decode, one transform stack, then a branch at the point where the two deliverables stop
wanting the same thing:

```
studio standard log ProRes 4444 (one per shot)
        |
        |  decode to float RGB, colour tags overridden, range confirmed
        |
  input:  studio log -> ACEScct         (one constant, identity if the standard is ACEScct)
        |
     CLF:  the approved grade                     (per shot, from the colour session)
        |
   +----+--------------------------------------------+
   |                                                  |
 PLATE branch                                     VIEW branch
   |                                                  |
 -> linear ACEScg                                 stays in ACEScct
   |                                                  |
 resize in numpy, unbounded                       ACES output transform -> sRGB
   |                                              ... input transform, CLF and output
 EXR: ACEScg, AP1, graded                             collapsed into one 3D LUT
                                                      |
                                                  ffmpeg lut3d, tetrahedral, resize bounded
                                                      |
                                                  mp4: sRGB display
```

**Every transform is a single OCIO `GroupTransform`, interpolated tetrahedrally.** Not a
sequence of separate applications, and not trilinear. Tetrahedral is stated here because the
default in several tools is trilinear, it is visibly worse on saturated colour, and it is a
one word difference that nobody notices being wrong.

Three properties carry over from the previous policy unchanged, because the reasoning behind
them did not depend on where the grade came from.

**The plate branch is unbounded and resizes in numpy.** Scene linear values run past 1.0, and
`core/resize.py` exists so the HD downscale does not go through anything that clamps.

**The view branch stays bounded until the final encode.** Everything before the output
transform happens in ACEScct, which is bounded to 0..1. swscale clamps float to 0..1, so
keeping the view branch in log is what lets ffmpeg do the reference resize in a single pass
with no frames crossing into Python.

**The whole view branch collapses into one 3D LUT per shot**, generated in core: ACEScct in,
sRGB display out, with the CLF and the ACES output transform inside it. **This is how an OCIO
transform gets into ffmpeg**, which has no OCIO filter and does have `lut3d`, and it is what
keeps the reference a single fast pass with no frames pulled through Python.

An earlier version of this section justified the LUT differently, as one definition shared by
the encoder and the on-screen viewers so the two could not drift. **The viewers are gone**
(PRD FR-16), so the LUT now has exactly one consumer and that argument no longer applies. It is
recorded because the argument was a good one and will be tempting again if a viewer ever
returns in v02: the cube is the thing to hand it.

A 3D LUT is accurate here because its input domain is log, which is where LUTs are meant to be
authored, and its output is display referred and therefore bounded. **The plate branch cannot
use one**, because scene linear output is unbounded; that path applies the GroupTransform to
float pixels directly.

### The plate is graded, and what that costs

The 2026-09-11 policy delivered an ungraded plate and carried the CDL in the header. The
argument for it was that a grade baked into a plate can clip highlights the comp needs, and
that work done against a graded plate stops matching the moment the grade moves in the DI.

**The second half of that argument no longer applies**, because this workflow finishes the DI
before the turnover is ingested. There is no later grade for the plate to stop matching. The
first half still applies, and it becomes a requirement on the CLF rather than a reason to
refuse:

**The CLF must end in scene linear ACEScg and must contain no display rendering.** A CLF whose
chain includes an ACES output transform, a film emulation, or any tone curve that lands in a
display range produces a file that is display referred and says it is linear. That file grades
and comps wrong, and it looks completely normal until someone tries to work on it. The tool
probes for it and raises QC-039, because the alternative is trusting a filename.

Within that constraint a grade authored in ACEScct and converted back to linear keeps its float
headroom. Values above 1.0 survive it.

### EXR metadata

The header carries provenance, because a graded plate is only auditable if the file says what
was done to it.

- `chromaticities` states **AP1** primaries. That constant is the difference between a file
  that is ACEScg and a file that lies about being ACEScg.
- `proingest/colorspace` states `ACEScg`.
- `proingest/source_encoding` names the log encoding the source was read as, and therefore
  the input transform that was applied.
- `proingest/clf` names the CLF and `proingest/clf_hash` is its digest. **The hash is what
  identifies the grade**: a CLF that is re-exported and redelivered gets a different one, so the
  deliverables rendered from the old version stay findable afterwards.
- `proingest/cdl` carries the CDL from the EDL, as machine readable slope, offset, power and
  saturation attributes and as the **original `*ASC_SOP` / `*ASC_SAT` text**. It is a readable
  approximation of what the CLF did, for a human or another facility's tool, and the header says
  as much: **the CLF is what was applied.** Writing both is what makes a delivered plate legible
  to someone who has neither the session nor an OCIO install.
- `proingest/tool_version`, the shot ID, the frame range and the source timecode, per the
  proposal's header list.

### OpenColorIO

Transforms come from **OpenColorIO**, not from hand written curves and matrices.
`Config.CreateFromBuiltinConfig(...)` carries the ACES transforms inside the wheel, so **no
config files ship**. The macOS arm64 wheel is 5.7 MB, which is nothing against the 300 MB
budget in PRD section 8, and a Windows wheel exists for v02. `FileTransform` loads the CLF and
`ColorSpaceTransform` supplies the input transform and the output transform.

The session is ACES 1.3, so the config is pinned to an ACES 1.3 built-in config rather than
tracking `studio-config-latest`. Matching the colour session matters more than being current,
and a dependency bump must not change what the references look like. OQ-29.

### The EXR writer stays as it is

The proposal writes EXRs via OpenImageIO. **This keeps the `OpenEXR` Python bindings**, which
is what `core/exr.py` already uses and what CLAUDE.md's ground rules pin. Nothing in the
proposal's header list needs OIIO: the bindings write arbitrary named attributes, AP1
chromaticities, DWAA and timecode already, with 45 tests behind them. OIIO would be a second
large dependency inside a 300 MB installer budget in exchange for no capability. Compression
stays **DWAA at level 45** per section 3; PIZ is a defensible option for a graded final plate
and is recorded as OQ-36 rather than built.

## 2. Source formats accepted

The studio sets the delivery spec and the shooters work to it, so this is a specification
rather than a survey of what might turn up. **One encoding, every file, every shooter**
(section 1).

**Expected**, and what every QC rule is written around:

- **ProRes 4444 or DNxHR 444, the studio standard log encoding, 12 bit, 4:4:4, full range**,
  one file per shot, with handles beyond the cut.

4:4:4 matters more on a log source than it would on a display referred one. Subsampled chroma
in a log signal is stretched when the signal is linearised, and it shows on saturated edges.

**Accepted with a warning**, because it decodes correctly and delivers usable work:

- ProRes 422 HQ or any 4:2:2 10 bit variant carrying the same encoding. QC-021, for the chroma
  reason above.
- An EXR sequence already in ACEScg or ACES2065-1. Nothing is wrong with it; it simply is not
  what the shooters are asked to deliver, so it is flagged as an unexpected delivery rather
  than a defect.

**Refused:**

- 8 bit anything, and any 4:2:0 source. QC-020. Neither can carry a log signal without banding
  the moment it is linearised.

**The tool does not read the colour space off the container, it overrides it.** No standard
transfer tag names ACEScct or any camera log, and a container that does carry tags is as
likely to carry the wrong ones. The studio standard from Settings is the authority and the
decode is forced to match it. QC-018 fires when the file's own tags contradict it, which is
information rather than a veto. **Range is confirmed rather than assumed**: a log signal
carried as YCbCr and decoded at the wrong range gives crushed blacks and clipped whites that
look very nearly right.

## 3. Output formats

| output | spec |
|---|---|
| raw EXR | OpenEXR 2 scanline, DWAA compression level 45, half float RGB (alpha dropped unless source has real alpha, then RGBA), data window = display window, frame numbers start 1001 (OQ-35). **ACEScg, scene linear, AP1 chromaticities, graded with the shot's CLF**, with the source encoding, the CLF name and hash, and the CDL as its readable record, carried in the header (section 1) |
| ref mp4 4k | 3840x2160, H.264 High, yuv420p, CRF 18 (x264 `-preset slow`) or `h264_videotoolbox` when hardware encoding is enabled, keyint 24, `-movflags +faststart`, AAC 192k if audio associated |
| ref mp4 HD | same, 1920x1080 |
| audio | as delivered. If the source is a wav, byte copy. If audio lives inside a container, extract to PCM 16 bit, same sample rate and channel count, no resampling. QC-044 if not 16 bit after extraction |
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
- Shooters set every clip to the project rate in Resolve before export, so **the timeline rate is authoritative**. It is what the media is actually played at and what all frame math and timecode conversion use.
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
ffmpeg -i <src> -f rawvideo -pix_fmt gbrpf32le - | numpy frames
    -> OCIO GroupTransform (input transform, CLF), tetrahedral
    -> float16 -> OpenEXR (DWAA, level 45)
```

- **The colour stage is in numpy, between the decode and the write**, and it is the whole of
  what section 1 calls the plate branch. It is applied to unbounded float, before the HD
  downscale, so the resize happens on the pixels that are being delivered rather than on
  something that still has a transform waiting for it.

- One ffmpeg decode per resolution (4k pass writes 4k EXRs; HD pass adds the Lanczos scale filter). Two passes are simpler than a filtergraph split and cost one extra decode, acceptable at this scale.
- **The frame range is a frame seek, never a time seek.** A container seeks with the `trim` filter, `trim=start_frame=<in>:end_frame=<out+1>`, whose end is exclusive; it counts frames after the decoder has put them back in display order, so a long GOP source lands exactly. A sequence seeks with `-start_number <in>`, which never opens the frames before the range. `-ss` takes a float number of seconds and would land on the wrong frame at 23.976.
- `gbrpf32le` is planar and stores G, then B, then R, so RGB is planes 2, 0 and 1. It carries no alpha, which is OQ-21: the EXR source path preserves a source alpha and the container path cannot yet, because nothing records whether a container has a real one.
- EXR source sequences skip ffmpeg and are read with OpenEXR directly, then downscaled by `core/resize.py`, an antialiased Lanczos-3 in numpy. They have to: ffmpeg's `scale` accepts a float pixel format but **clamps the values to 0-1**, so routing a scene linear EXR through it would flatten every highlight above 1.0 to white without a word. The container path is unaffected because every container format section 2 accepts is integer and already bounded. That is the same filter the container path gets from `flags=lanczos`, so the two paths do not disagree: on a hard edge they are identical, and on smooth content they are within one 8 bit level. OQ-7, resolved.
- **DWAA is lossy.** At level 45 a written frame comes back about a tenth of a percent off the value that went in, proportionally, at every brightness. The plate carries a colour transform by design (section 1), so a delivered frame was never going to equal its source; DWAA means it does not even equal the float that was handed to the writer. QC therefore never compares a rendered frame to its source by equality.
- The encoder is deterministic: the same pixels and header produce the same bytes, which is what makes the QC-106 per-frame hash meaningful across a re-render.
- `framesPerSecond` is **not** written on output. The OpenEXR Python bindings cannot write a `Rational` attribute, and writing an int or a string under that name would be the wrong attribute type for any reader expecting a rate. Delivered frames carry a per-frame `timeCode` instead, which the bindings do write correctly.
- Checksum (xxhash64) of each written frame is recorded in the batch and the QC log.
- The writer does not read each frame back. QC-103 opens every frame of the finished sequence anyway, and the sequence is not renamed off its `.part` name until that passes, so a second read at write time would double the IO to learn nothing new.
