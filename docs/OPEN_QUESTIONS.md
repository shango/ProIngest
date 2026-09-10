# Open Questions

Blocker means Claude Code should stop and ask before building the affected part. Non-blocker means build with the stated default and note it.

| ID | question | default if unanswered | blocker |
|---|---|---|---|
| OQ-1 | Exact turnover folder structure from shooters and desired delivery folder layout | Recursive search for media; layout in NAMING_SPEC section 5 | no |
| OQ-2 | Shot tracker column layout | Default template in QC_RULES | no |
| OQ-3 | What codec/container is the consolidated media (EXR sequence? ProRes 4444?) | Accept all in COLOR_AND_FORMAT section 2 with warnings | no, but affects QC-020/021 severity |
| OQ-4 | How shooters name reference stills and BTS on the timeline (as clips named `MELT0001_pl01_colorChart_01`?) or are they side files? | Support both: timeline aux clips and side files matched by name | no |
| OQ-5 | Spec typos: 2161/2162 heights, witness cam listed without frame range | 3840x2160 everywhere; witness cam is a sequence | no |
| OQ-6 | Display transform for ref mp4s and stringout: sRGB piecewise or Rec.709 OETF | sRGB piecewise, Rec.709 selectable | no |
| OQ-7 | Downscale for EXR-source path (numpy/scipy vs OpenImageIO) acceptable? | scipy cubic, note in QC log | no |
| OQ-8 | ~~ffmpeg licensing~~ **RESOLVED 2026-09-09**: ship the GPL v3 gyan.dev full build with libx264, bundled in the installer. The tool stays inside the studio and is not distributed to third parties, so no source offer is triggered. ProIngest calls ffmpeg as a subprocess and is not linked against it, so ProIngest itself is unaffected by the GPL. Settings override retained | GPL v3 full build, x264 with CRF as specified | no |
| OQ-9 | Code signing certificate available? | Unsigned | no |
| OQ-10 | Should a shot with only a `cp` and no `pl` be allowed? | Allowed, info only | no |
| OQ-11 | Camera data file format: free text or key: value lines? Which keys go to the tracker? | Parse `key: value` lines, dump all to Camera Data sheet | no |
| OQ-12 | Stringout audio: include, or video only? | Include associated wavs | no |
| OQ-13 | EXR half vs full float | half | no |
| OQ-14 | Multiple `.otio` files in one turnover folder | Prompt user to pick | no |
| OQ-15 | Shooter name normalization in the stringout filename. `firstnamelastname` must round-trip through the QC-151 parser, so the raw field needs a defined transform | Lowercase and strip everything outside `a-z0-9`; keep the unnormalized value on the turnover for the tracker and QC log | no |
| OQ-16 | ~~`ffprobe.exe` missing~~ **RESOLVED 2026-09-09**: extracted from the same gyan.dev release `2026-03-01-git-862338fe31` and placed in `proingest/resources/ffmpeg/`. Bundled `ffmpeg.exe` was sha256-verified against the official asset and is the unmodified upstream build | both binaries present and version-matched | no |
| OQ-17 | **Color space conflict.** The shooters' spec PDF states `Camera Color Space: Camera Log` and `Render Color Space: sRGB`. `COLOR_AND_FORMAT.md` section 1 instead assumes the delivered EXRs are **scene linear** with sRGB primaries. If "Render Color Space: sRGB" means display-referred sRGB (Resolve's output color space), the EXRs already carry the sRGB curve, and the linear-to-sRGB transfer this tool applies to ref mp4s and the stringout would double-apply it and wash out every reference deliverable. Raw EXR output is unaffected either way (pixels in, pixels out). Resolve by inspecting real delivered media alongside OQ-3, not by reading the PDF | Assume linear as `COLOR_AND_FORMAT.md` states, but verify against a real turnover before the ref encode ships | **yes for M3** |
| OQ-18 | The spec PDF marks HDRI and camData as **Required** per plate, but QC-050 and QC-051 are warnings, so a missing one does not block. Should they be errors? Severity is a studio policy call, not a spec reading | Keep as warnings | no |
| OQ-19 | ~~QC-026 severity~~ **RESOLVED 2026-09-10**: timeline and files are both set to 24 in Resolve, so any other rate means a file escaped the conform and must be flagged. Kept as an error, which names the offending file. Frame math still follows the timeline, so the output is not corrupted either way | error, as QC_RULES states | no |
| OQ-20 | **Lens grid deliverable is not planned yet.** The type table lists a png copy per lens grid, but three things are undecided: the scan does not recognise a lens grid clip at all (it currently fails the shot naming regex and lands as QC-010), a lens grid is turnover-level so it carries no show to place it under `<delivery_root>/<show>/_turnovers/`, and section 4 defines versioning per shot and says nothing about a per camera/lens/mm deliverable. Answer with a real turnover alongside OQ-4 | Not built. Nothing else depends on it; QC-054 already warns when a turnover has no lens grid | no |
