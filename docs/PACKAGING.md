# Packaging (macOS v01)

v01 targets **macOS on Apple Silicon only**. Windows moved to the v02 backlog (PRD section
10). Nothing here is built yet: M7 has not started, and see "The build machine problem" below
for why it cannot start on the current dev machine.

## Build

- PyInstaller `onedir` build producing `ProIngest.app`. `onedir` over `onefile` for the same
  reason as before: faster start, no temp extraction. On macOS `onefile` is worse still,
  because an app bundle is already a directory and `onefile` would unpack ~200 MB to a temp
  path on every launch.
- Spec file in `build/proingest.spec` with `BUNDLE(...)` for the `.app`, hidden imports for
  PySide6 plugins, OpenEXR and numpy.
- `Info.plist` needs: `CFBundleIdentifier` (`com.<studio>.proingest`), `CFBundleShortVersionString`
  from `pyproject.toml`, `LSMinimumSystemVersion` (macOS 12 is a safe floor for PySide6 6.7),
  and `NSHighResolutionCapable`. No document types and no URL schemes: the app opens
  `.pibatch` files through its own dialogs, not through Launch Services.
- `LSApplicationCategoryType` is `public.app-category.video`.
- **The build is arm64 only, and that is now a decision rather than an assumption** (OQ-24,
  confirmed 2026-09-11). Do not spend installer budget on a universal2 build. An Intel Mac
  cannot run it, and needs no handling here: macOS refuses to launch an arm64-only bundle
  itself, with a better message than this tool could print. The one place the architecture
  leaks is running from source on an Intel Mac, where `resolve_tool` hands back the bundled
  arm64 binary (it tests `is_file`, not whether this machine can execute it) and the first
  ffprobe call fails with `Exec format error`. That is a developer's problem, not the
  editor's, and the v02 Windows build will have to revisit `BUNDLED_PLATFORM` regardless.
- Distribution as a `.dmg` built with `create-dmg`, background image and an Applications
  symlink. A plain zip of the `.app` is the fallback and is honestly fine for one user.
- `build/build.py` runs both steps and writes to `dist/`.
- Version comes from `pyproject.toml` and is stamped into `Info.plist`, the dmg name, the
  About box, and every QC log.

## The build machine problem

**PyInstaller cannot cross-build.** A macOS `.app` must be produced on a Mac: PyInstaller
bundles the interpreter that is running it plus the compiled extension modules for the host, and
PySide6, numpy, OpenEXR and xxhash all ship platform-specific binaries. There is no
`GOOS=darwin` equivalent, and the same is true of py2app, Briefcase and Nuitka.

**Resolved for correctness, still open for packaging.** `.github/workflows/ci.yml` runs lint,
type checking and the full suite on a GitHub Actions `macos-latest` runner (macOS 26, arm64) on
every push. That covers the larger half: until it existed, no line of this code had ever run on
the target platform, and the dev machine tests against whatever ffmpeg the distro ships while
the product ships 9.0.1. The macOS job puts the bundled arm64 binary on PATH first, so the
suite exercises the configuration that actually ships.

Two things CI cannot do, and they are why a real Mac is still needed eventually:

- **M7 packaging.** The job is not written because `build/build.py` and `build/proingest.spec`
  do not exist yet. It lands with M7 and is a natural fit for the same runner.
- **M8 validation.** The turnovers live on the editor's Google Drive and no runner can judge
  whether a reference encode looks right. That needs the editor's own Mac.

`docs/MAC_SESSION.md` holds the running checklist for both, so a rented day is execution
rather than exploration. A rented Apple Silicon machine is about EUR 3 for the 24 hour
minimum lease Apple's licence forces, which makes preparation, not price, the thing worth
optimising.

Everything else in this document is still written from the documentation rather than from a
machine anyone has used. Assumptions that need a Mac to settle are flagged as OQ-22 and OQ-23.
OQ-25 no longer needs one: the tool asks for its two roots instead of looking for them.

## ffmpeg

- Bundle the **martin-riedl.de macOS arm64 GPL v3 build**, which includes libx264, so H.264
  encoding uses `libx264` with CRF as specified in `docs/COLOR_AND_FORMAT.md`. It also carries
  `h264_videotoolbox`, which is the macOS hardware encoder and the replacement for NVENC.
  Full rationale, the verified feature list, and why gyan.dev could not be used are in
  `proingest/resources/ffmpeg/PROVENANCE.md`. OQ-8 re-resolved for macOS.
- Binaries live in `proingest/resources/ffmpeg/` and are named `ffmpeg` and `ffprobe`, with no
  extension. `core/ffmpeg.py` resolves the Settings override first, then the bundled path,
  then PATH. **The bundled step is gated on `sys.platform == "darwin"`.** That guard is load
  bearing rather than tidiness: unlike `.exe`, the macOS binary name is exactly what a Linux
  or Windows machine also looks for, so without the guard the Linux dev machine resolves a
  Mach-O binary as a valid file and every subprocess dies with "Exec format error".
- The pair is 132 MB installed, ~57 MB compressed, against a 300 MB installer budget. The
  Windows pair was 446 MB, so the macOS build has considerably more room.
- The binaries are **not tracked in git**. `build/ffmpeg.lock.json` pins the versioned URLs and
  a sha256 per extracted file; `python build/fetch_ffmpeg.py` downloads and verifies them into
  `proingest/resources/ffmpeg/`. Run it once after cloning and before `build/build.py`.
- Two macOS-specific traps, both already handled in `fetch_ffmpeg.py` and worth knowing before
  anyone rewrites it: Python's `zipfile` does not carry the archived mode across, so the
  **exec bit must be set explicitly** or the binary lands unrunnable; and
  ffmpeg.martin-riedl.de answers the default `Python-urllib` User-Agent with **HTTP 403**.
- Record the ffmpeg version string in every QC log.

## Code signing, notarization and Gatekeeper

**This is the one place macOS is materially harder than Windows, and it is unresolved.**

There is no Apple Developer account (confirmed 2026-09-10), so `ProIngest.app` ships
**unsigned and un-notarized**. On Windows that meant a SmartScreen warning the user could
click past. On macOS it means Gatekeeper refuses to open the app: a `.dmg` or zip downloaded
through a browser carries the `com.apple.quarantine` extended attribute, and an unsigned,
un-notarized quarantined app is blocked outright, not merely warned about.

Workarounds, in order of preference:

1. **Get a Developer ID.** $99/year, then `codesign --deep --options runtime` and submit with
   `notarytool`, stapling the ticket to the dmg. This is the only clean answer and the only
   one that survives a macOS release that tightens the rules again.
2. **Transfer without quarantine.** The attribute is applied by the browser and by AirDrop,
   not by `scp`, `rsync`, or a USB drive formatted for the purpose. A tool handed over on a
   stick or copied over the network from the build machine never acquires it.
3. **Strip it on the target machine**: `xattr -dr com.apple.quarantine /Applications/ProIngest.app`,
   run once after install. Right-click and Open no longer reliably suffices on recent macOS.

Note that the **bundled ffmpeg and ffprobe are already Developer ID signed with the hardened
runtime** (`CS_RUNTIME`, verified by reading their code directory), so they are not the
problem and do not need ad-hoc signing to satisfy the arm64 kernel requirement. If ProIngest
is ever signed for real, the nested binaries must be signed as part of the bundle and their
existing signatures will be replaced, which is normal and expected.

OQ-9, and it is a **blocker for handing the tool over**, not a cosmetic note. Decide it before
M7 rather than at delivery.

## Runtime locations

- Settings: `~/Library/Application Support/ProIngest/settings.json`
- Logs: `~/Library/Logs/ProIngest/proingest-YYYYMMDD.log`, rotated daily, 14 kept
- Crash dumps: same folder, with the batch path and last 200 log lines
- Batches: wherever the user saves them; default suggestion is the delivery root

These are the Apple-sanctioned locations and are what `core/settings.py` must use. They are
also per-user and need no elevated permissions, which matches the single-user design.

## First run

- **Do not detect the Google Drive mount.** OQ-25 was resolved by the user on 2026-09-11:
  the editor points at a source root and a delivery root with a folder chooser each, both of
  which happen to be on a Drive mount, and the tool asks rather than guesses. Nothing probes
  `~/Library/CloudStorage/GoogleDrive-*/My Drive` or `/Volumes/GoogleDrive`, and there is no
  `G:` on macOS to fall back to either. First run therefore opens its dialogs at the user's
  home folder and remembers what was picked. `UI_SPEC.md` section 13.
- Detect `h264_videotoolbox` and show a one-time notice of whether hardware encoding is
  available. Presence in the build is not proof it opens on the hardware, so the check is an
  actual trial encode of a few frames, not a string match on `-encoders`. OQ-23.
- Create the default tracker template in the settings folder if missing.

## Windows (later)

v02. Keep everything path-agnostic and avoid macOS-only APIs outside `ui/` platform helpers,
which is the same discipline that made this switch cheap in the first place. The Windows plan
is the one this document previously described: PyInstaller `onedir`, Inno Setup producing
`ProIngest-Setup-<version>.exe`, per-user install by default, and the gyan.dev GPL full build
of ffmpeg. `build/ffmpeg.lock.json` will need a platform matrix at that point; it deliberately
does not have one now, because a matrix with one entry is harder to read than a flat file.
