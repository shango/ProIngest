# Bundled ffmpeg

| field | value |
|---|---|
| version | `9.0.1-https://www.martin-riedl.de` |
| source | martin-riedl.de build service, macOS **arm64** (Apple Silicon) |
| build id | `1787073674_9.0.1` |
| linkage | static third-party libs (`--pkg-config-flags=--static`); links only system frameworks and `/usr/lib` |
| license | **GPL v3** (`--enable-gpl --enable-version3`) |
| ffmpeg url | https://ffmpeg.martin-riedl.de/download/macos/arm64/1787073674_9.0.1/ffmpeg.zip |
| ffprobe url | https://ffmpeg.martin-riedl.de/download/macos/arm64/1787073674_9.0.1/ffprobe.zip |
| ffmpeg sha256 | `393e4c395020a1cb7cbd77fbe00599ce69d1c6466fee0dbd59d13f86a81a1611` |
| ffprobe sha256 | `7abc49fb2bdf2204f018e76dc6e0a8ae7643313bae09a9fa43e7eb12442271bc` |

Both binaries come from the same build id, so they report an identical version string.
`core/ffmpeg.py` reports that string into every QC log, per PACKAGING.md.

## Why not gyan.dev

The v01 Windows build bundled the gyan.dev full build. **gyan.dev publishes Windows builds
only.** Checked directly against the release API: 419 assets across the 100 most recent
`GyanD/codexffmpeg` releases, every one a `.zip` or `.7z` of a Windows build, zero assets
matching mac, darwin, osx, arm64, universal or dmg. gyan.dev is a Windows ffmpeg service and
there is nothing there to switch to. That pin returns with the v02 Windows target.

`BtbN/FFmpeg-Builds` was the other GitHub-hosted candidate and publishes Windows and Linux
only. `ffbinaries` has macOS x86_64 at ffmpeg 6.1 and no arm64. `eugeneware/ffmpeg-static`
does carry `ffmpeg-darwin-arm64`, but it sits at 6.1.1. martin-riedl.de tracks upstream (9.0.1
here, the same version gyan.dev ships for Windows), publishes arm64 explicitly, offers ffmpeg
and ffprobe as separate downloads, and resolves its `latest` redirect to an immutable
versioned URL, which is exactly what a lock file wants.

evermeet.cx is the other well-known macOS source and is also at 9.0.1 with a clean JSON info
API. It was not chosen because its published architecture is not stated in that API and its
builds have historically been x86_64. Worth revisiting only if martin-riedl.de goes away.

## Features ProIngest depends on

| feature | needed by | present |
|---|---|---|
| `libx264` | ref mp4 and stringout, CRF 18 | yes (`--enable-libx264`) |
| `h264_videotoolbox` | optional hardware encode, replaces NVENC on macOS | yes |
| `libzimg` for `zscale` | linear to sRGB transfer, COLOR_AND_FORMAT section 1 | yes (`--enable-libzimg`) |
| `libfreetype` for `drawtext` | stringout burn-ins, UI_SPEC section 8 | yes (`--enable-libfreetype`, plus harfbuzz and fontconfig) |
| `gbrpf32le` | the EXR decode pipe, COLOR_AND_FORMAT section 7 | yes |
| EXR / DPX / ProRes decoders | source formats, COLOR_AND_FORMAT section 2 | yes |
| `pcm_s16le`, `aac`, mp4 muxer | audio deliverables and ref encodes | yes |

**How this was verified, and its limit.** The dev machine is Linux x86-64 and cannot execute
an arm64 Mach-O binary, so `ffmpeg -encoders` could not be run. Every row above was confirmed
by reading the configure line and the symbol table out of the downloaded binary, and by
confirming it links `VideoToolbox.framework`. That is strong evidence a feature is compiled
in; it is not proof the encoder initialises on real hardware. **First run on the target Mac
must confirm `h264_videotoolbox` actually opens a session**, which is a runtime property of
the machine, not of the build. Tracked as OQ-23.

## macOS specifics

- **arm64 only.** This binary will not run on an Intel Mac; Rosetta translates x86_64 onto
  Apple Silicon, not the reverse. See OQ-24.
- **The exec bit is not in the archive as Python sees it.** The zips record mode `0755`, but
  `zipfile` does not carry mode across on extraction, so `build/fetch_ffmpeg.py` sets it
  explicitly from the lock file. A binary that lands without it fails with "Permission
  denied" and nothing explains why.
- **The download needs a User-Agent.** ffmpeg.martin-riedl.de answers the default
  `Python-urllib/3.x` agent with HTTP 403.
- **Gatekeeper quarantines these binaries** when the app itself is unsigned. See PACKAGING.md;
  this is OQ-9 and it is a real distribution blocker, not a warning to dismiss.

## License obligation

GPL v3 applies to these binaries only. ProIngest invokes them as subprocesses and is not
linked against them. The tool is used inside the studio and is not distributed to third
parties, so no source offer is triggered. If that ever changes, the corresponding ffmpeg
source for the exact build above must be offered alongside it. OQ-8.

The GPLv3 text in `LICENSE.ffmpeg.txt` comes from the FFmpeg source at tag `n9.0.1`, because
the martin-riedl.de archives carry the binary alone with no license member. Its sha256 is
identical to the text the gyan.dev archive shipped, as expected for the same license.

## Footprint

66 MB per binary, 132 MB for the pair, ~57 MB compressed. That is a large improvement on the
Windows pair (446 MB installed, 111 MB compressed) and leaves real room under the 300 MB
installer budget in PRD section 8.
