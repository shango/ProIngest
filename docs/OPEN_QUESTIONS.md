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
