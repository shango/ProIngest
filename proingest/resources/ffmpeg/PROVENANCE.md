# Bundled ffmpeg

| field | value |
|---|---|
| version | `2026-03-01-git-862338fe31-full_build-www.gyan.dev` |
| source | gyan.dev "full" build, Windows x86-64 |
| linkage | static (`--enable-static`), single self-contained exe |
| license | **GPL v3** (`--enable-gpl --enable-version3`) |
| release | https://github.com/GyanD/codexffmpeg/releases/tag/2026-03-01-git-862338fe31 |
| asset | `ffmpeg-2026-03-01-git-862338fe31-full_build.zip` |
| ffmpeg.exe sha256 | `cce4074b7af8e71b4c63f17bec8d36ca3da9b7f84f5bcbb010476164a6cafa85` |
| ffprobe.exe sha256 | `44edce8f24543b17390e7f50e554349998541e6d6b0241f650df1073770d202a` |

`ffmpeg.exe` came from `ExportGenie/bin/win/ffmpeg.exe` and its sha256 was verified byte for byte
against the official release asset above, so it is the unmodified upstream build. `ffprobe.exe` was
taken from that same asset, so both binaries report the identical version string.

`core/ffmpeg.py` reports this version string into every QC log, per PACKAGING.md.

## Features ProIngest depends on (all verified present)

`libx264` (ref mp4 and stringout), `libzimg` for `zscale` (the linear to sRGB transfer in
COLOR_AND_FORMAT section 1), `libfreetype` for `drawtext` (stringout burn-ins, UI_SPEC section 8),
`gbrpf32le` (the EXR decode pipe in COLOR_AND_FORMAT section 7), native EXR / DPX / ProRes decoders,
`pcm_s16le` and `aac`.

Hardware H.264 encoders available: `h264_nvenc` (NVIDIA), `h264_amf` (AMD), `h264_qsv` (Intel),
`h264_mf` (Windows Media Foundation, any GPU).

## License obligation

GPL v3 applies to this binary only. ProIngest invokes it as a subprocess and is not linked
against it. The tool is used inside the studio and is not distributed to third parties, so no
source offer is triggered. If that ever changes, the corresponding ffmpeg source for the exact
build hash above must be offered alongside it.

## Updating this build

Both binaries must always come from the same release, or the version string in the QC log stops
describing what actually ran. gyan.dev's own server rotates nightlies off, but the GitHub releases
above persist, so an old build stays reachable by tag. Latest nightly is redirected from
https://www.gyan.dev/ffmpeg/builds/ffmpeg-git-github

The separate `ffmpeg-tools` package on gyan.dev holds developer utilities (`ffescape`, `ffhash`,
`qt-faststart` and similar). It does not contain ffprobe and is not needed here.

These are static builds, so each exe carries its own copy of every library: 426 MB installed for
the pair, 111 MB compressed in the installer. A shared build would roughly halve the installed
footprint at the cost of loose DLLs. Not worth it while the installer budget has room.
