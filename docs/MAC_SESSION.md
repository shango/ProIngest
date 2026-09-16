# Mac session plan

## Why this file exists

The dev machine is Linux and the target is macOS on Apple Silicon. Almost everything is
verifiable without a Mac: CI runs the full suite on an arm64 runner on every push, and any
deliverable the tool produces (mp4, xlsx, EXR) can be inspected on any machine. What is left
is a small residue that needs a person looking at a screen, or the real turnover data.

This file is that residue. It exists so that a paid Mac session is **execution, not
exploration**. An hour of unplanned poking about costs more than the machine does.

**Getting the repo running on the machine is `docs/MAC_SETUP.md`, not this file.** Do that
first, including the ffmpeg binaries and the PATH line that stops the media tests skipping
themselves, and start here once `python -m proingest` opens a window.

**The rule, also in `CLAUDE.md`:** if you write something whose behaviour can only be
confirmed on a Mac, add a line here in the same commit. A checklist assembled at the end from
memory is the thing this is meant to prevent.

## What never needs a Mac

Do not rent for any of these. Listed because the instinct to rent is usually wrong.

- **Building the `.app`.** CI compiles it, and since M7 that is a fact rather than a plan: the
  `package-macos` job builds the bundle and the dmg on an arm64 runner every push and uploads
  the image as a run artifact. Download it; do not build it.
- **Whether the bundle works at all.** `build/smoke_test.py` runs in that job and drives the
  packaged binary through a whole turnover - scan, a two worker render, both spreadsheets. A
  missing hidden import, an uncollected otio plugin manifest or a broken worker pool fails CI.
  What it cannot judge is anything with a window in it, which is what the checklist below is.
- **Measuring the installed size.** `build/build.py` prints it and the dmg's size into the run
  summary on every build, against PRD section 8's budget.
- **Judging encode quality.** A reference mp4 is a normal file. Download the CI
  artifact and watch it on Linux or Windows.
- **Spreadsheets, QC rules, naming, frame math, the batch file.** Pure logic, fully covered by
  the suite.
- **Most of the UI.** Qt is cross-platform: the shot list, delegates, keyboard model,
  validation colouring, docks, metadata pane and theme are all built and iterated locally.
  Only the platform-specific surface below needs a Mac.

## Session 1: a rented Mac, one day, at the end of M5

### Do not rent until all of these are true

- [x] CI is green on `main`.
- [x] M5 is feature-complete and behaves correctly on Linux. (M6, the stringout, was dropped
      on 2026-09-11; this line used to name it.)
- [x] **The M7 packaging job produces a downloadable dmg and its headless smoke test passes.**
      Done 2026-09-13. Renting in order to discover that PyInstaller missed a hidden import is
      the expensive way to learn it, and it is now learned for free on every push.
- [x] Everything on the checklist below is written and pushed. Nothing on it is still in
      progress. **Done 2026-09-14.** `REVIEW.md`'s S1 and S2 closed on the same day and were
      the last code this project had that did not want a Mac, so nothing is half built
      underneath this list.

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

- [ ] **`bash build/mac_build.sh` runs start to finish.** It is the first thing typed at the
      machine and the one file here that CI never executes: the workflow does the same steps
      as its own YAML rather than by running the script. Every line in it is a line
      `docs/MAC_SETUP.md` documents and CI proves, so what is being checked is the wrapper -
      that `uv` is found, that the arm64 guard passes, that the `PATH` export reaches the
      suite, and that it ends holding a dmg.
- [ ] **The CI-built bundle launches from the Finder.** Headlessly it already scans, renders
      and reports on every push, so what is being checked here is the half a smoke test cannot
      reach: double-click the app and get a window.
- [ ] **The dmg mounts and reads as a drag-to-install.** `hdiutil` with an `/Applications`
      symlink beside the app, no background image (PACKAGING.md), so the question is whether
      that looks deliberate or unfinished at the volume's default window size.
- [ ] **Press Run and count the Dock icons.** The smoke test proves a spawned worker comes back
      as a worker rather than dying, which is the failure that breaks a render. It cannot prove
      the other half: a child spawned from a *windowed* bundle might still bounce an icon into
      the Dock even though it never builds a window. Watch the Dock through one render.
- [ ] **There is no application icon.** Confirm that what PyInstaller's default looks like in
      the Dock and the Finder is tolerable for v01, or that one needs drawing.
- [ ] About and Preferences appear in the application menu, not a window menu. Needs
      `QAction.AboutRole` and `PreferencesRole`. `UI_SPEC.md` section 11.
- [ ] Cmd+S, Cmd+R, Cmd+F, Cmd+T, Cmd+K, Cmd+I and Cmd+. all fire. Qt maps the portable
      `Ctrl` modifier to Cmd on its own, so this is confirming a belief, not wiring.
      `UI_SPEC.md` section 4.
- [ ] Cmd+, opens Settings. `UI_SPEC.md` section 11.
- [ ] Dock tile progress during a render. Decoration only: if the `NSDockTile` shim is not
      built, the status bar carries the same information. `UI_SPEC.md` section 11.
- [ ] **The frozen left columns hold together at 2x Retina, and the seam is the thing to
      watch.** Built as an overlaid second view (M5.9, `UI_SPEC.md` section 2), so what a
      person has to confirm is that it reads as one list rather than two: the three headers
      lining up with the twelve beside them, the row separators meeting across the seam, and
      the turnover sentence crossing it without a visible join - it is drawn twice, by two
      views, pinned to land in the same place. Scroll right and left, drag Shot wider by its
      header and by the overlay's, wheel over the left three columns, and edit a Shot cell
      with the list scrolled right. A Retina half pixel is the failure this cannot be tested
      for on Linux.
- [ ] **The two line In/Out cell is legible at 2x Retina.** The demoted line is drawn at 85% of
      the cell font (M5.2) and that number was picked against a Linux font stack at 1x. If it
      reads as noise rather than as a second value, the number is one constant in
      `ui/shot_list.py`. `UI_SPEC.md` section 2.
- [ ] **The status dot reads at a glance in all seven states.** Nine pixels, filled or hollow,
      against the row tint behind it (M5.2, `UI_SPEC.md` section 3). Amber on faint amber is
      the pair to look at. **It was not drawn at all until 2026-09-13** - the tree indentation
      took the whole of the status column's width and Qt drew nothing - so this line is now
      about whether it reads, not whether it is there. `INDENT` is set explicitly for the same
      reason: a style that indented further on a Mac would take the room away again, and the
      test that holds it asserts the view's own geometry rather than a picture.
- [ ] **The inline red on a mistyped In or Out is legible against the editor's own background.**
      The cell editor colours what was typed rather than replacing it (M5.3, `UI_SPEC.md`
      section 5), and the red is the same `#cf5a52` as the error dot, chosen against the list's
      dark rows rather than against a macOS line edit, which draws itself in the system palette.
- [ ] **Tab across the editable cells does what an editor expects on a Mac.** Shot, In, Out and
      Notes, wrapping to the next row (M5.3, `UI_SPEC.md` section 4). `QTreeView` ships with tab
      key navigation off and the list turns it on, which means **Tab can no longer move focus out
      of the list**; whether that is right or maddening is a judgement to make while using it.
- [ ] **Ctrl+K's reason prompt is a `QInputDialog` and it has not been looked at.** It should be
      a sheet on the window rather than a free-floating box, and its Cancel should read as
      cancelling the skip rather than cancelling the reason. `UI_SPEC.md` section 4.
- [ ] **The file dialogs are the native ones and they open where an editor expects.** New,
      Open, Save and Add Turnover all go through `QFileDialog`, which is the macOS panel rather
      than Qt's own, and what it does with a starting folder on a Drive mount is not something
      Linux can answer (M5.4, `UI_SPEC.md` sections 11 and 13). Watch in particular that Save
      offers the batch name with the `.pibatch` suffix and does not hide it.
- [ ] **The unsaved-batch prompt on close should be a sheet.** It is a `QMessageBox` today and
      it is the one modal the editor meets without asking for it (M5.4). Check its three buttons
      read the way macOS orders them, and that Cancel really leaves the window open.
- [ ] **The delivery root in the batch bar shows a whole Drive path.** It is a flat button with
      the full path on it (M5.4, `UI_SPEC.md` section 13), and a Google Drive path on a Mac is
      long enough that this is a layout question rather than a styling one.
- [ ] **A real render from the window, watched from start to banner.** Run, the row bars
      filling, the status bar's percent, throughput and ETA, Stop part way through a second
      run, and the banner above the list (M5.5, `UI_SPEC.md` section 7). This is the first
      chunk whose whole point is watching something move, and five repaints a second was
      chosen against a Linux compositor.
- [ ] **The banner's link opens the `_reports` folder in the Finder.** `QDesktopServices`
      on a Drive mount path (M5.5), which is the one thing in that banner Linux cannot
      answer. Check the whole sentence fits at the window's default width, since a Drive
      path is long.
- [ ] **The slim progress bar in the Progress column reads as a bar at 2x Retina.** Four
      pixels tall on the demoted line (M5.5, `ui/shot_list.py`), under a `3/5` count. If it
      disappears into the row separator, the height is one constant.
- [ ] **The strip above the list reads as one band, in all three of its states.** Empty, then
      the four pixel batch bar with its line of words, then the completion banner, and never
      two of them at once (M5.10, `ui/run_strip.py`, `UI_SPEC.md` section 7.1). What Linux
      cannot answer is whether four pixels is still a bar at 2x when it spans the whole window
      rather than a 90 pixel cell, and whether the band jumping in and out at the start and
      end of a run shifts the list under the pointer enough to be annoying.
- [ ] **The step line is legible and does not truncate a deliverable name.** It names jobs like
      `MELT0001_pl01_raw_4k_v01` (M5.10). At the default width on a Mac font stack, check the
      longest name the naming spec can produce still fits.
- [ ] **The metadata pane reads as a column, not a wall.** Select a shot and read down it
      (M5.6, `UI_SPEC.md` section 12). Every value is one elided line, so what Linux cannot
      answer is whether the label column is wide enough on a Mac font stack and whether the
      values are elided so hard at the default width that the pane stops being readable.
      Drag it wider and narrower and decide where the default should sit.
- [ ] **Ctrl+I toggles the pane and Tab still walks the row's cells afterwards.** Click a
      value in the pane to select text, then press Tab (M5.6, section 12.1). Tab must still
      be in the list. This is the one behaviour in the pane that a test asserts by policy
      flags rather than by pressing the key.
- [ ] **The camData section is what to show the AD.** A real turnover's camData in the pane
      is the only place lens, filter and body appear in the window (section 12.2, OQ-26).
      Read it with the editor and settle which fields earn their place, which is the open
      question against this chunk.
- [ ] **The rendering dot is not animated and section 3 asks for it to be.** Look at a run in
      progress and decide whether the static accent dot plus a moving bar is enough, before
      anybody builds a repaint timer for it (`PROGRESS.md` section 9).
- [ ] **Closing the window mid-run waits for the jobs in flight and says nothing.** Up to two
      minutes if a reference encode is going (M5.5). Decide whether that wants a sheet
      explaining itself, or a prompt before the close.
- [ ] **Take the user guide's screenshots** (FR-17, M9.4): `python build/screenshots.py`. The
      harness builds a demo batch and grabs the window, so this is running a script and
      collecting the files rather than posing the app by hand - but the shipped set has to come from **this** machine, because a guide
      illustrated with a Linux font stack and Linux window furniture is a guide to a tool the
      editor does not have. Budget a slot for it late in the day, after the interface has been
      looked at and anything embarrassing has been fixed. **Commit what it writes**:
      `docs/guide/images/` is empty in the repo on purpose, so the quickstart's images are
      broken until this is done and a Linux draft cannot be committed by accident. The
      quickstart references seven of them by name and `tests/test_guide.py` fails if one is
      renamed, so what is needed here is the files rather than any editing.
- [ ] **Read `docs/guide/` at the window** (M9.1, M9.2, M9.3) while doing the pass above. All
      three pages were written on Linux from the specs and the code, so what they cannot know is
      whether the quickstart's seven steps are the order a person actually works in and whether
      the reference section describes anything that does not look like that on screen. That is
      the one thing a document like this is wrong about, and it is not visible from here. The
      install page's Gatekeeper section is the other half: **check what the dialog actually
      says** when the dmg is opened after a download, because the page quotes it.
- [ ] Metadata pane: width and section states persist, long paths elide in the middle, values
      copy. `UI_SPEC.md` section 12.
- [ ] Dark theme and font rendering at Retina, including the IBM Plex fallback chain.
- [ ] Window geometry and dock state persist to `~/Library/Application Support/ProIngest`.
- [ ] Geometry saved on one display arrangement reopens **on screen** under another. M5.1
      restores Qt's own blob and Qt clamps it to the current screen; whether that is enough
      when a laptop is undocked can only be seen on a Mac with a second display.
- [ ] Logs land in `~/Library/Logs/ProIngest` and rotate.
- [x] Installed size and dmg size. **Measured by CI on 2026-09-13: 251 MB installed, a 110 MB
      dmg**, about a third of PRD section 8's 300 MB installer budget. Read the number in the run
      summary rather than measuring here; the build reports the verdict and does not fail on it.

  (The stringout burn-in line that used to sit here went with M6 on 2026-09-11, OQ-38.)

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
- [ ] **Look at the Settings page in the real style.** Drawn and checked offscreen on
      Linux, where the spin box arrows do not render at all and the form's label alignment
      against the multi-line path map block is a guess. Cmd+, has to open it, and it has to
      arrive in the application menu rather than a window menu (section 11's roles).
- [ ] **Press Run on a batch with no colour session ingested and watch what the editor does.**
      Since M5.7.1 QC-008 holds that turnover back and the run writes nothing, which is the
      right refusal and may read as a dead button. The Issues dock carries the reason and the
      status bar names the turnover; whether that is enough, or whether Run should say it
      itself, is a judgement to make in front of the real window rather than from a test.
- [ ] **Ingest one real session from the window and read the report.** How many rows matched,
      how many got a CLF, and the three lists a person acts on: no event, trim overwritten, more
      than one CLF naming the shot. It is the first time `clf.ingest` meets an EDL it did not
      write. Watch whether a modal is the right place for it, or whether a long list of
      unmatched rows wants somewhere it can be read twice. OQ-31.
- [ ] **Look at `Ingest Colour Session` in the toolbar.** Its label is two and a half times the
      width of every other button, so a once-per-turnover action sits wider than Run. Decide in
      front of the real window whether it should read `Ingest`, remembering that this is a tool
      called ProIngest and `Ingest` alone can be read as the whole job. **The tooltip it needed
      for that now exists** (M5.11), so this is only a judgement about width. Checked offscreen
      on Linux only.
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
- [ ] **Confirm the log really lands in `~/Library/Logs/ProIngest/proingest.log`** and that the
      folder is created on a first launch. `ui/paths.log_dir()` derives it from Qt's generic data
      location's parent rather than writing `~/Library` out, which is only ever exercised on
      Linux here: both runners and this machine take the other branch, and the test that covers
      the macOS half fakes `sys.platform`. Also read one real run's log and judge whether an
      ffmpeg command line per deliverable is the right density, or whether it wants DEBUG.
- [ ] **Read the Log tab during a real run and judge its density and its width.** Drawn and
      checked offscreen on Linux only. Four columns over a bottom dock is tight, and an ffmpeg
      command line is two hundred characters: watch whether the Message column wants the dock
      taller, whether the table wants a monospace font for command lines, and whether Ctrl+C
      out of it pastes into a terminal cleanly. UI_SPEC section 6.1.
- [ ] **Point the ffmpeg override at a Homebrew build and run one turnover through it.** The
      Settings page's Advanced section (M5.8.3) reaches a render's worker processes, and the
      only proof so far is a symlinked binary in a temp folder on Linux. Worth doing once
      against a real build, because the bundled pair is what every other test uses.
- [ ] **Hover every toolbar button on the real window and read the tooltips.** Written and
      measured offscreen on Linux, where the shortcut renders as `Ctrl+R` and on the Mac it is
      `⌘R`, so every line is shorter there than the width test assumes. What a test cannot
      judge: whether two lines is right for a greyed button, whether the shortcut belongs on the
      first line or looks like part of the sentence, and whether the note on an enabled Run
      ("no colour session ingested yet") reads as helpful or as nagging. UI_SPEC section 1.
