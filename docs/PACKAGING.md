# Packaging (Windows v01)

## Build

- PyInstaller `onedir` build (faster start than onefile, no temp extraction). Spec file in `build/proingest.spec` with hidden imports for PySide6 plugins, OpenEXR, and numpy.
- Inno Setup script `build/installer.iss` produces `ProIngest-Setup-<version>.exe`. Per-user install by default (no admin), optional per-machine. Start menu and optional desktop shortcut. Uninstaller included.
- Version comes from `pyproject.toml` and is stamped into the exe metadata, the installer, the About box, and every QC log.
- `build/build.py` runs both steps and writes the artifact to `dist/`.

## ffmpeg

- Bundle the GPL v3 gyan.dev full build, which includes libx264, so H.264 encoding uses `libx264` with CRF as specified in `docs/COLOR_AND_FORMAT.md`. The tool is used inside the studio and is not distributed to third parties, so the GPL triggers no source offer; ProIngest calls ffmpeg as a subprocess and is not linked against it. Hardware encoders (`h264_nvenc`, `h264_amf`, `h264_qsv`, `h264_mf`) are also present. The Settings > Advanced override for a user-installed ffmpeg is retained. Note the license in the About box. OQ-8 resolved.
- Binaries live in `resources/ffmpeg/`. `core/ffmpeg.py` resolves the bundled path first, then the Settings override, then PATH.
- The binaries are ~426 MB and are **not tracked in git**. `build/ffmpeg.lock.json` pins the release, the archive URL and a sha256 per file; `python build/fetch_ffmpeg.py` downloads and verifies them into `resources/ffmpeg/`. Run it once after cloning and before `build/build.py`. Provenance and the GPL note are in `resources/ffmpeg/PROVENANCE.md`.
- Record the ffmpeg version string in every QC log.

## Runtime locations

- Settings: `%APPDATA%\ProIngest\settings.json`
- Logs: `%LOCALAPPDATA%\ProIngest\logs\proingest-YYYYMMDD.log`, rotated daily, 14 kept
- Crash dumps: same folder, with the batch path and last 200 log lines
- Batches: wherever the user saves them; default suggestion is the delivery root

## First run

- Detect G: and offer it as the default browse location.
- Detect NVENC; show a one-time notice of whether GPU encoding is available.
- Create the default tracker template in settings folder if missing.

## Code signing

Unsigned in v01 unless the studio supplies a certificate. Note the SmartScreen warning in the README. OQ-9.

## macOS (later)

Keep everything path-agnostic and avoid Windows-only APIs outside `ui/` platform helpers. A `.app` via PyInstaller and a `.dmg` via `create-dmg` is the plan; not built in v01.
