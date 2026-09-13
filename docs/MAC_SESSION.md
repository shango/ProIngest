# Mac session plan

## Why this file exists

The dev machine is Linux and the target is macOS on Apple Silicon. Almost everything is
verifiable without a Mac: CI runs the full suite on an arm64 runner on every push, and any
deliverable the tool produces (mp4, xlsx, EXR) can be inspected on any machine. What is left
is a small residue that needs a person looking at a screen, or the real turnover data.

This file is that residue. It exists so that a paid Mac session is **execution, not
exploration**. An hour of unplanned poking about costs more than the machine does.

**The rule, also in `CLAUDE.md`:** if you write something whose behaviour can only be
confirmed on a Mac, add a line here in the same commit. A checklist assembled at the end from
memory is the thing this is meant to prevent.

## What never needs a Mac

Do not rent for any of these. Listed because the instinct to rent is usually wrong.

- **Building the `.app`.** CI compiles it. There is no need to upload anything anywhere to be
  compiled; the runner that tests the code can package it too (M7).
- **Judging encode quality.** A reference mp4 is a normal file. Download the CI
  artifact and watch it on Linux or Windows.
- **Spreadsheets, QC rules, naming, frame math, the batch file.** Pure logic, fully covered by
  the suite.
- **Most of the UI.** Qt is cross-platform: the shot list, delegates, keyboard model,
  validation colouring, docks, metadata pane and theme are all built and iterated locally.
  Only the platform-specific surface below needs a Mac.

## Session 1: a rented Mac, one day, at the end of M5

### Do not rent until all of these are true

- [ ] CI is green on `main`.
- [ ] M5 and M6 are feature-complete and behave correctly on Linux.
- [ ] The M7 packaging job produces a downloadable `.app` artifact, and its headless smoke
      test passes. Renting in order to discover that PyInstaller missed a hidden import is
      the expensive way to learn it.
- [ ] Everything on the checklist below is written and pushed. Nothing on it is still in
      progress.

### Logistics

- Scaleway Apple Silicon: **M1 EUR 0.11/hr, M2 0.17, M4 0.22 to 0.29.** Apple's licence
  forces a **24 hour minimum lease** on every cloud Mac provider, so budget one whole day
  either way. An M1 day is about **EUR 2.64**. Take the M4 if the render tests want the cores.
- Connect over VNC for the UI work.
- **Getting the app across:** download the CI artifact on the Mac itself, or `scp` it. A
  browser download sets `com.apple.quarantine` and Gatekeeper will refuse to open an unsigned
  bundle, so run `xattr -dr com.apple.quarantine ProIngest.app` once. See `PACKAGING.md` and
  OQ-9.
- **Do not develop on the rented box.** Observe, fix locally, push, let CI rebuild, pull the
  new artifact. The rented machine is a test rig, not a workstation, and nothing done on it
  survives.
- Work top to bottom and log the answer next to each line rather than trusting memory.

### Checklist

Append to this as M5 and M6 are built.

- [ ] The CI-built bundle launches at all.
- [ ] About and Preferences appear in the application menu, not a window menu. Needs
      `QAction.AboutRole` and `PreferencesRole`. `UI_SPEC.md` section 11.
- [ ] Cmd+S, Cmd+R, Cmd+F, Cmd+T, Cmd+K, Cmd+I and Cmd+. all fire. Qt maps the portable
      `Ctrl` modifier to Cmd on its own, so this is confirming a belief, not wiring.
      `UI_SPEC.md` section 4.
- [ ] Cmd+, opens Settings. `UI_SPEC.md` section 11.
- [ ] Dock tile progress during a render. Decoration only: if the `NSDockTile` shim is not
      built, the status bar carries the same information. `UI_SPEC.md` section 11.
- [ ] Frozen left columns hold together at 2x Retina. The overlaid second-view trick is the
      known-awkward part. `UI_SPEC.md` section 2, `PROGRESS.md` section 9.
- [ ] Metadata pane: width and section states persist, long paths elide in the middle, values
      copy. `UI_SPEC.md` section 12.
- [ ] Dark theme and font rendering at Retina, including the IBM Plex fallback chain.
- [ ] Window geometry and dock state persist to `~/Library/Application Support/ProIngest`.
- [ ] Geometry saved on one display arrangement reopens **on screen** under another. M5.1
      restores Qt's own blob and Qt clamps it to the current screen; whether that is enough
      when a laptop is undocked can only be seen on a Mac with a second display.
- [ ] Logs land in `~/Library/Logs/ProIngest` and rotate.
- [ ] Stringout burn-ins are legible at 1920x1080. `UI_SPEC.md` section 8.
- [ ] Installed size against the 300 MB budget in `PRD.md` section 8. PySide6 alone is 422 MB
      of wheels before PyInstaller strips it, so this needs measuring rather than assuming.

## Session 2: the editor's own Mac, free, at handover

Only this machine has the turnovers and the Drive mount, so none of this can be bought.
Treat it as a working session with the editor rather than a delivery.

- [ ] Install, strip quarantine, walk the first-run experience.
- [ ] The editor picks a source root and a delivery root on their Drive mount and both stick
      across a restart. OQ-25 removed the detection, not the need to see this work once.
- [ ] A turnover from a **Windows** shooter resolves its media. Their OTIO can carry `G:\...`
      paths that mean nothing here, so this is what settles whether the FR-2 path map earns its
      place or the filename search over the source root covers it on its own.
- [ ] Scan a real turnover from each of the three shooters. OQ-1 folder structure, OQ-3 what
      the consolidated media actually is, OQ-4 how stills and BTS are named.
- [ ] **Open one of those turnovers and look for `Input Color Space` in the clip metadata.**
      The scan reads the source encoding from that one field (M4.6.4), because it is Resolve's
      own Media Pool column for the input transform, and **nothing has confirmed Resolve exports
      it into the `.otio`**. If it is absent, look at what the clip does carry and at the
      container's tags, which is the second place the tool looks. The fix is one string in
      `scan.SOURCE_ENCODING_KEY`; the point of looking is to find out which string. OQ-44.
- [ ] **Read what the shooters actually wrote in it.** "S-Log3" on its own resolves to nothing,
      deliberately, because it names four colour spaces. If that is what arrives, the outcome is
      an instruction to the shooters rather than a change to the tool: ask for the Resolve input
      transform name verbatim. OQ-34, OQ-44.
- [ ] 100 shots scanned in under 60 seconds from a warm mount. `PRD.md` section 8.
- [ ] **Time QC-111 on a real reference.** It runs `ffmpeg -count_frames`, a full decode, once
      per delivered mp4, and that is two decodes of a 240 frame plate per row on top of the
      encodes. On fixture media it is free; on real media nobody has measured it. If it costs
      real minutes across a hundred shots, the answer is a setting, not a silent downgrade to
      the container index the render already checked. PROGRESS.md section 9.
- [ ] A full run end to end, then read the QC log and tracker with the editor. OQ-2 tracker
      columns, OQ-11 camData format.
- [ ] OQ-21 container alpha, explicitly deferred until a real turnover existed.
- [ ] Confirm the lens grid really does arrive as a folder in the package, and watch the editor
      move and rename it once. OQ-20 made that manual for v01; if it is painful, that is the
      argument for building it in v02.
- [ ] Sit with the AD and cut the metadata pane down to what they actually read. OQ-26.
- [ ] Calibrate `h264_videotoolbox -q:v` against x264 CRF 18 on a real plate. CI has already
      proven the encoder opens; this is the half of OQ-23 about how it looks.
- [ ] Agree how future builds reach the editor without acquiring quarantine. OQ-9.
