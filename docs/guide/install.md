# Installing ProIngest

What you get, how it goes on, the one thing macOS will do about it, and where it keeps its
files. On Windows, skip to [Windows](#windows) at the end; the first run is the same on both.

## What you need

- **A Mac with Apple Silicon**, running **macOS 12 or later**. There is no Intel Mac build.
  Or **a Windows 11 PC**; see [Windows](#windows).
- Nothing else. **Python, ffmpeg and everything else are inside the app.** Do not install
  ffmpeg separately; the app ships its own pinned build and names it in every log line, which
  is what makes a render reproducible.

## Putting it on

You are handed one file, `ProIngest-0.5.51.dmg`. The version is in the name so two builds can
sit in the same folder.

1. Double-click the dmg. It opens on a window with the app and a shortcut to Applications.
2. Drag **ProIngest** onto **Applications**.
3. Eject the dmg.

About 250 MB installed, most of which is the video tools.

## The first launch, and what macOS says about it

**ProIngest is not signed by Apple, and macOS does not merely warn about that.** If the dmg
reached you through a browser, a chat app or AirDrop, macOS marks it as downloaded and then
**refuses to open the app at all**: you get a dialog saying it is damaged or cannot be checked
for malicious software, and there is no "open anyway" button worth looking for.

Nothing is wrong with the app. Two ways past it:

- **Get it by a route that does not mark it.** A copy over the network from the build machine,
  or on a USB stick, never picks up the mark. This is the easy answer if somebody hands it to
  you in person.
- **Take the mark off after installing.** Open Terminal and run, once:

  ```
  xattr -dr com.apple.quarantine /Applications/ProIngest.app
  ```

  Then open the app normally. This does not have to be repeated until the next version.

This is a decision the studio has not made yet: buying an Apple Developer ID would sign the app
and make all of the above disappear. Until then, the second launch and every launch after it
behave normally.

## First run

![The window before a batch is open](images/empty-state.png)

The window opens empty, with **New batch or open one**. Nothing is configured and nothing needs
to be: there are no credentials, no server and no paths to fill in before you start.

**The tool does not go looking for your Google Drive**, or for anything else. You point it at a
folder when you add a turnover, and at another one for deliveries, and it remembers both with
the batch. A tool that guessed would open its chooser somewhere plausible and empty, which
reads as the folder being wrong rather than the guess being wrong.

Everything else has a working default. **Settings** is worth opening once to see what is there
rather than to change anything: the thresholds the checks compare against, how many shots are
rendered at once, and where the log file is.

## Where it keeps its files

| | |
|---|---|
| settings and window layout | `~/Library/Application Support/ProIngest/settings.json` |
| logs | `~/Library/Logs/ProIngest/` - today's is `proingest.log`, and a fortnight of dated ones sits beside it |
| batches | wherever you save them, as `.pibatch` files. The delivery root is the usual place |
| deliverables and spreadsheets | under the delivery root you chose. Never inside the app |

The first two are per-user and need no administrator password. Nothing is written anywhere
else, and nothing is written outside your own account.

## Updating

Drag the new **ProIngest** onto **Applications** and replace the old one. Settings, window
layout and logs are untouched, and an existing `.pibatch` opens in the new version.

If the new dmg arrived through a browser, it carries the download mark again and the section
above applies once more.

## Removing it

Drag the app to the Trash. The two folders above are all it leaves behind; delete them too if
you want it gone completely. Your batches and everything it delivered are your own files in
your own folders and are not touched.

## Windows

The same app, the same checks and the same video tools as the Mac, on **Windows 11** (an ARM
PC runs it too, through Windows' own emulation).

**Putting it on.** You are handed one file, `ProIngest-Setup-0.5.51.exe`. Double-click it.
It asks for no administrator password: it installs for you alone, into
`%LOCALAPPDATA%\Programs\ProIngest`, and puts ProIngest in the Start menu. Tick the box for a
desktop shortcut if you want one.

**What Windows says about it.** ProIngest is not signed, so if the setup came through a
browser Windows shows **Windows protected your PC**. Click **More info**, then **Run anyway**.
That is once per downloaded file, and the installed app opens normally after it.

**Where it keeps its files.**

| | |
|---|---|
| settings and window layout | `%APPDATA%\ProIngest\settings.json` |
| logs | `%APPDATA%\ProIngest\logs\` |
| the app | `%LOCALAPPDATA%\Programs\ProIngest\` |

Paste either of the first two into the Explorer address bar to open it.

**Updating.** Run the new setup. It replaces the old version in place; settings, layout and
logs are kept.

**Removing it.** Settings > Apps > Installed apps > ProIngest > Uninstall. Your settings
folder stays; delete `%APPDATA%\ProIngest` too if you want it gone completely.

**One at a time.** Opening ProIngest while it is already open says so, and leaves the open one
as it is.
