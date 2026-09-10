# Packaging (Windows v01)

## Build

- PyInstaller `onedir` build (faster start than onefile, no temp extraction). Spec file in `build/proingest.spec` with hidden imports for PySide6 plugins, OpenEXR, and numpy.
- Inno Setup script `build/installer.iss` produces `ProIngest-Setup-<version>.exe`. Per-user install by default (no admin), optional per-machine. Start menu and optional desktop shortcut. Uninstaller included.
- Version comes from `pyproject.toml` and is stamped into the exe metadata, the installer, the About box, and every QC log.
- `build/build.py` runs both steps and writes the artifact to `dist/`.

## ffmpeg

- Bundle an LGPL ffmpeg/ffprobe build (no x264 GPL build). Because x264 is GPL, H.264 encoding uses either NVENC (when present) or the LGPL `openh264` encoder, or the tool can be pointed at a user-installed full ffmpeg in Settings > Advanced. Document this in the About box. OQ-8.
- Binaries live in `resources/ffmpeg/`. `core/ffmpeg.py` resolves the bundled path first, then the Settings override, then PATH.
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
