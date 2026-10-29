# Windows session plan

## Why this file exists

The Windows build was made on 2026-10-28 for parity with the Mac app (OQ-89). The dev
machine is Linux, and CI runs the full suite, builds the installer, installs it and drives
the installed app through a whole turnover on a `windows-latest` runner on every push. What
CI cannot do is look at a window, or touch the editor's Google Drive. This file is that
residue, the Windows twin of `docs/MAC_SESSION.md`.

**The rule, as for the Mac:** if you write something whose behaviour can only be confirmed by
a person on Windows, add a line here in the same commit.

## What never needs a Windows machine

- **Building the installer.** The `package-windows` job builds `ProIngest-Setup-<version>.exe`
  and uploads it as `ProIngest-windows-x64`. Download it; do not build it.
- **Whether the app works at all.** That job smoke tests the build and then the copy the setup
  installed: a scan, a two worker render, both spreadsheets.
- **Encode quality, spreadsheets, naming, QC.** The same code and the same ffmpeg release as
  the Mac, and the same suite runs on the Windows runner.

## The checklist

Run it with a real turnover on a Windows 11 machine with Google Drive for desktop.

### Installing (2026-10-28, 0.5.50)

- [ ] Download the artifact zip from the CI run, unzip it, double-click
      `ProIngest-Setup-<version>.exe`. SmartScreen should say "Windows protected your PC";
      **More info**, then **Run anyway**. Note the exact wording if it differs, for the guide.
- [ ] The setup asks for no administrator password and installs into
      `%LOCALAPPDATA%\Programs\ProIngest`. A Start menu entry named ProIngest opens the app.
- [ ] Settings land in `%APPDATA%\ProIngest\settings.json` and the log in
      `%APPDATA%\ProIngest\logs\proingest.log` (Settings shows the log folder).
- [ ] Double-click the Start menu entry again while it is open: a box says ProIngest is
      already open, and no second window appears.
- [ ] Install the next version over it: it upgrades in place, with settings kept. Then
      uninstall from Settings > Apps: the folder in `Programs` goes, `%APPDATA%\ProIngest`
      stays.

### The window (2026-10-28, 0.5.50)

- [ ] The window, the shot list and the Settings page read correctly at 100% and at 150%
      display scaling. The menu bar is in the window, as Windows does it, with About, Settings
      and Quit under the ProIngest menu (OQ-89, item 7). Say if Windows users expect File >
      Exit instead.
- [ ] The monospaced values in Settings (the library names) show in Consolas, not a
      proportional fallback.
- [ ] Ctrl+R runs, Ctrl+. stops, Ctrl+K skips, Ctrl+F finds.
- [ ] A turnover folder dragged in from Explorer is added, several at once.
- [ ] Opening a delivery folder from the app opens it in Explorer.
- [ ] No console window flashes up during a scan or a render.

### Google Drive and paths (2026-10-28, 0.5.50)

- [ ] A turnover on the `G:` drive (Google Drive for desktop) scans, and a render to a
      delivery root on `G:` finishes with every deliverable renamed from its `.part`. Drive
      for desktop can hold a file open while it uploads; a rename that fails shows as a
      render error naming the file, so note any.
- [ ] A turnover folder whose name has an apostrophe, a comma or brackets renders burn-ins
      and LUTs (the filter path escape, fixed 2026-10-28 on both platforms).
- [ ] A delivery path longer than 260 characters: PyInstaller's manifest declares the app
      long path aware, but Windows honours that only when `LongPathsEnabled` is set in the
      registry. Note whether a deep delivery root fails, and how.
- [ ] Save logs to CSV from the File menu, and open it in Excel: the header block names
      Windows and ffmpeg `9.0.1-essentials_build-www.gyan.dev`.
