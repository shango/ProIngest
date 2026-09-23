# Packaging (macOS v01)

v01 targets **macOS on Apple Silicon only**. Windows moved to the v02 backlog (PRD section
10).

**M7 is built as of 2026-09-13 and CI packages every push.** `build/build.py` produces the
app, and on macOS the dmg beside it; `build/smoke_test.py` drives the result through a whole
turnover; the `package-macos` job does both on an arm64 runner and uploads the dmg. Nothing in
this document is written from documentation alone any more except the parts marked otherwise.
The residue that still needs a person is `docs/MAC_SESSION.md`.

## Build

- PyInstaller `onedir` build producing `ProIngest.app`. `onedir` over `onefile` for the same
  reason as before: faster start, no temp extraction. On macOS `onefile` is worse still,
  because an app bundle is already a directory and `onefile` would unpack ~200 MB to a temp
  path on every launch.
- Spec file in `build/proingest.spec`, and it is deliberately a **shim**: every decision about
  what goes in the bundle lives in `build/bundle.py`, which `ruff`, `mypy` and
  `tests/test_bundle.py` all see. A `.spec` is executed rather than imported, so nothing reads
  one, and a mistake in one does not fail a build - it ships an app with a file missing.
- **PySide6, OpenEXR, numpy, xxhash and PyOpenColorIO need no help.** PyInstaller's analysis
  follows the imports and its PySide6 hooks are per module, so importing only QtCore, QtGui
  and QtWidgets is what keeps QtWebEngine and the rest out without an exclude list.
  **OpenColorIO needs no data files**: the ACES config is compiled into the wheel and read with
  `Config.CreateFromBuiltinConfig`, so there is nothing to `collect_data_files` and nothing to
  place beside the app.
- **OpenTimelineIO is no longer a dependency** (2026-09-23). It was the one package that needed
  its adapters, manifests and sources collected by hand; `clf.read_final_edl` now reads the EDL
  itself and nothing imports otio, so the bundle carries none of it.
- `Info.plist` needs: `CFBundleIdentifier`, `CFBundleShortVersionString`
  from `pyproject.toml`, `LSMinimumSystemVersion` (macOS 12 is a safe floor for PySide6 6.7),
  and `NSHighResolutionCapable`. No document types and no URL schemes: the app opens
  `.pibatch` files through its own dialogs, not through Launch Services.
- **The identifier names nobody, on purpose.** This document used to specify
  `com.<studio>.proingest`; the studio is not to be named in anything that ships (OQ-52), and
  an identifier does not have to name anyone. It has to be unique and it has to never change.
  Apple does not check that whoever registers one owns the domain in it, so the reverse-DNS
  form is collision avoidance rather than a claim that has to be true. It is
  `io.github.shango.proingest`, the standard form for a project whose namespace is its
  repository: unique because GitHub usernames are, controlled by someone who really holds it,
  and naming only the account that already owns the repo. **Nothing else identifying ships
  either**: the visible name is ProIngest and the only show code in `proingest/` is `MELT` in
  two docstrings, which is the synthetic fixture show.
- `LSApplicationCategoryType` is `public.app-category.video`.
- **The build is arm64 only, and that is now a decision rather than an assumption** (OQ-24,
  confirmed 2026-09-10). Do not spend installer budget on a universal2 build. An Intel Mac
  cannot run it, and needs no handling here: macOS refuses to launch an arm64-only bundle
  itself, with a better message than this tool could print. The one place the architecture
  leaks is running from source on an Intel Mac, where `resolve_tool` hands back the bundled
  arm64 binary (it tests `is_file`, not whether this machine can execute it) and the first
  ffprobe call fails with `Exec format error`. That is a developer's problem, not the
  editor's, and the v02 Windows build will have to revisit `BUNDLED_PLATFORM` regardless.
- Distribution as a `.dmg`, built with **`hdiutil`** rather than the `create-dmg` this
  document used to name. The only part of create-dmg the tool wanted was the drag-to-install
  layout, and that is one symlink to `/Applications` in a staging folder; doing it with
  `hdiutil` means the CI runner installs nothing through Homebrew in order to package a build,
  and there is no cosmetic background image in this repository for create-dmg to place. The
  image is `UDZO` compressed and named `ProIngest-<version>.dmg`.
- **There is no application icon.** None has been drawn, so the bundle carries PyInstaller's
  default. It is cosmetic, it is the sort of thing the editor should have an opinion about, and
  it is one `icon=` argument in the spec once an `.icns` exists.
- **The entry point calls `multiprocessing.freeze_support()` before anything else**, and that
  is the whole reason `build/entry.py` exists. The render pool uses the spawn context on every
  platform (`core/render.py`), and a spawned worker in a frozen bundle re-launches the bundle
  rather than re-importing a module. Without that call, pressing Run in the packaged app opens
  four more copies of the window instead of rendering. Since M5.5 the UI starts a pool of its
  own, so this is no longer only the CLI's problem.

  **Read the next sentence before deleting that line as dead code.** CPython's
  `multiprocessing.freeze_support` is gated on `sys.platform == "win32"` and genuinely does
  nothing on macOS. PyInstaller's `pyi_rth_multiprocessing` runtime hook **rebinds the name**
  to its own implementation, which is gated on nothing, and that hook runs before the entry
  script in any bundle that imports `multiprocessing`. So the call is a no-op from source off
  Windows and load bearing in the shipped app everywhere. Two things hold it: a unit test that
  the call precedes `main()`, and a smoke test step that hands the built binary a
  `--multiprocessing-fork` argument and fails if the argument parser's usage line comes back.
- `build/build.py` runs both steps and writes to `dist/`.
- Version comes from `pyproject.toml` and is stamped into `Info.plist`, the dmg name, the
  About box, and every QC log.

## The build machine problem

**PyInstaller cannot cross-build.** A macOS `.app` must be produced on a Mac: PyInstaller
bundles the interpreter that is running it plus the compiled extension modules for the host, and
PySide6, numpy, OpenEXR, PyOpenColorIO and xxhash all ship platform-specific binaries. There is no
`GOOS=darwin` equivalent, and the same is true of py2app, Briefcase and Nuitka.

**Resolved for correctness, still open for packaging.** `.github/workflows/ci.yml` runs lint,
type checking and the full suite on a GitHub Actions `macos-latest` runner (macOS 26, arm64) on
every push. That covers the larger half: until it existed, no line of this code had ever run on
the target platform, and the dev machine tests against whatever ffmpeg the distro ships while
the product ships 9.0.1. The macOS job puts the bundled arm64 binary on PATH first, so the
suite exercises the configuration that actually ships.

**Resolved for packaging too, as of 2026-09-13.** The `package-macos` job builds the `.app`
and the dmg on the same arm64 runner and uploads the image as a run artifact, so a `.app` is a
download rather than a thing that has to be made on a machine someone rented. `package-linux`
builds the same spec on a free runner and smoke tests it, which is where a lost hidden import
or an uncollected plugin manifest surfaces first: the failure is identical on both platforms
and only one of them costs anything.

One thing CI still cannot do, and it is why a real Mac is needed eventually:

- **M8 validation, and the interface.** The turnovers live on the editor's Google Drive, no
  runner can judge whether a reference encode looks right, and nothing headless can say whether
  the window reads correctly at 2x Retina. That needs a Mac with a person in front of it.

`docs/MAC_SESSION.md` holds the running checklist, so a rented day is execution
rather than exploration. A rented Apple Silicon machine is about EUR 3 for the 24 hour
minimum lease Apple's licence forces, which makes preparation, not price, the thing worth
optimising.

What in this document has still never been seen on a Mac: how the `.app` behaves once
double-clicked, which is Gatekeeper's business (OQ-9) and `MAC_SESSION.md`'s checklist. The
build itself, the bundle's contents and the packaged binary's behaviour are all exercised on
every push. Assumptions that need a Mac to settle are flagged as OQ-22 and OQ-23; OQ-52 is the
bundle identifier, which needs a decision rather than a machine. OQ-25 no longer needs one: the
tool asks for its two roots instead of looking for them.

## Size

Measured by `build/build.py` on every build and printed into the CI run summary, because PRD
section 8 budgets **under 300 MB for the installer** and a budget nobody measures is a number
in a document. The installer is the dmg, so that is what the budget is read against, with the
installed size printed beside it as the thing that explains it. The build prints the verdict
and does **not** fail on it: what to drop when PySide6 gains a megabyte is a person's decision,
not a red `main`.

**Measured 2026-09-13 on the arm64 runner: 251 MB installed, and a 110 MB dmg**, so the installer
sits at about a third of the budget. The Linux build is 236 MB installed for comparison; the two
differ by the Qt platform plugins and by the 132 MB ffmpeg pair that only the macOS bundle
carries, which compresses hard. The packaged app answered `--version` in 0.8s, which is a runner
rather than the target hardware but is the only first launch figure that exists.

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
  `--show` prints the URLs and hashes, `--from <folder>` installs files downloaded by hand or
  copied from another machine, and `--verify` says whether what is installed is the pinned
  build. **The manual route verifies the same sha256 the download does**, so a hand-placed
  binary is as trustworthy as a fetched one and a wrong one is refused rather than silently
  bundled. `docs/MAC_SETUP.md` is the clone-to-running-app version of all of this.
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
- Logs: `~/Library/Logs/ProIngest/`. The file being written now is `proingest.log`; at
  midnight it is renamed `proingest-YYYYMMDD.log` and 14 of those are kept. Built in M5.8.1.
  The live file is undated because a `TimedRotatingFileHandler` holds one path open and dates
  it on the way out, and a handler that reopened a new path every midnight would be a second
  mechanism to get wrong. Off macOS - the Linux dev machine and the Linux CI runner - the
  folder is `logs` beside `settings.json`, because `~/Library/Logs` exists nowhere else and
  `QStandardPaths` models no log location to ask (`ui/paths.py`)
- Crash dumps: same folder, with the batch path and last 200 log lines
- Batches: wherever the user saves them; default suggestion is the delivery root

These are the Apple-sanctioned locations and are what `core/settings.py` must use. They are
also per-user and need no elevated permissions, which matches the single-user design.

## First run

- **Do not detect the Google Drive mount.** OQ-25 was resolved by the user on 2026-09-10:
  the editor points at a source root and a delivery root with a folder chooser each, both of
  which happen to be on a Drive mount, and the tool asks rather than guesses. Nothing probes
  `~/Library/CloudStorage/GoogleDrive-*/My Drive` or `/Volumes/GoogleDrive`, and there is no
  `G:` on macOS to fall back to either. First run therefore opens its dialogs at the user's
  home folder and remembers what was picked. `UI_SPEC.md` section 13.
- Detect `h264_videotoolbox` and show a one-time notice of whether hardware encoding is
  available. Presence in the build is not proof it opens on the hardware, so the check is an
  actual trial encode of a few frames, not a string match on `-encoders`. OQ-23.

## Windows (later)

v02. Keep everything path-agnostic and avoid macOS-only APIs outside `ui/` platform helpers,
which is the same discipline that made this switch cheap in the first place. The Windows plan
is the one this document previously described: PyInstaller `onedir`, Inno Setup producing
`ProIngest-Setup-<version>.exe`, per-user install by default, and the gyan.dev GPL full build
of ffmpeg. `build/ffmpeg.lock.json` will need a platform matrix at that point; it deliberately
does not have one now, because a matrix with one entry is harder to read than a flat file.
