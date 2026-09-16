# Setting the repo up on a Mac

From `git clone` to a running app on macOS 12 or later, Apple Silicon. Nothing here is
optional and nothing here is exploratory: the list is short because everything difficult
about this repo is already pinned in a lock file.

The one thing that is not a single command is ffmpeg, because the binaries are 132 MB and
are deliberately not in git. Section 3 is that, and it has a manual route.

Once the app runs, `docs/MAC_SESSION.md` is the checklist of what to actually look at.
This document only gets you to the point where that checklist can begin.

## 0. The short way

Everything in sections 2 to 6 is also one script. On a machine that has `git` and `uv`:

```
git clone git@github.com:shango/ProIngest.git ProIngest
cd ProIngest
bash build/mac_build.sh
```

It installs the locked environment, fetches and verifies the ffmpeg pair, puts it on
`PATH`, runs `ruff`, `mypy` and the suite, builds `ProIngest.app` and the dmg, and drives
the frozen binary through a fixture turnover. It stops at the first thing that fails, and
re-running it is safe: every step does nothing when it has nothing to do.

- `bash build/mac_build.sh --from ~/Downloads` installs the ffmpeg pair from files you
  downloaded by hand rather than fetching them (section 3).
- `bash build/mac_build.sh --skip-checks` builds without the lint and the suite first.

The rest of this document is the same thing by hand, and is what to read when a step
fails or when you want only part of it.

## 0.5 Running it without building anything

**Double-click `ProIngest.command` in this folder.** It prepares the environment on the
first run and opens the window; every run after that takes a couple of seconds. This is
the route for when there is no time to build, and the folder is the program.

It needs `uv` and a network connection the first time, because the environment and the
132 MB of video tools are not in the folder as it comes out of git. After that first run
the folder is self-sufficient and can be copied to another Mac of the same architecture.

**There are two different "folders" here and it is worth being clear which one is wanted.**

| | `ProIngest.command` beside the source | `dist/ProIngest.app` |
| --- | --- | --- |
| Needs `uv` and a network on first use | yes | no |
| Needs building first | no | yes, `build/build.py` |
| Size | 5 MB of source, then ~500 MB once prepared | 251 MB, complete |
| Hand to somebody with nothing installed | no | yes |

An `.app` **is** a folder - macOS just draws it as one icon - so "a folder that runs with
nothing installed" is the packaged build rather than a different thing to make. CI builds
one on every push and attaches it to the run.

**Two things about sending either one to somebody else.**

- **Do not send it as a `.zip`.** A zip drops the executable bit, so `ProIngest.command`
  arrives as a file Finder will not run, and an `.app` arrives broken outright. A `.dmg`,
  a `.tar.gz`, `scp`, `rsync` or a USB drive all keep it. The same is true of the zip
  GitHub wraps a CI artifact in, which is why the artifact is a dmg rather than the app.
- **A browser download is quarantined.** For `ProIngest.command` that is a dialog with an
  Open button behind a right-click; for an unsigned `.app` it is a refusal (section 7).
  Either way `xattr -dr com.apple.quarantine <the folder>` clears it in one go.

## 1. What has to be there first

- **Apple Silicon.** The build is arm64 only and deliberately so (OQ-24). Running from
  source on an Intel Mac resolves the bundled arm64 ffmpeg and dies with `Exec format
  error` on the first probe.
- **Xcode command line tools**, for `git`: `xcode-select --install`.
- **uv**, which brings its own Python: `curl -LsSf https://astral.sh/uv/install.sh | sh`.
  The repo needs Python 3.11 or later and is developed and CI-checked on 3.12.

Homebrew is not needed. Neither is a system ffmpeg, a Qt install, or an Apple Developer
account - the last one only matters for signing a build for someone else (OQ-9,
`PACKAGING.md`).

## 2. Clone and build the environment

```
git clone <this repo> ProIngest
cd ProIngest
uv sync --extra dev --python 3.12
```

`uv sync` installs exactly what `uv.lock` pins, which is the same set CI installs with
`--frozen`. Everything afterwards runs out of `.venv/bin/python`.

## 3. The ffmpeg pair

The app ships one specific ffmpeg build - macOS arm64, GPL v3, from martin-riedl.de -
because the version string goes into every QC log and "whatever was on the machine" makes
that a lie. `build/ffmpeg.lock.json` pins the URLs, the sizes and a sha256 per file, and
`build/fetch_ffmpeg.py` is the only supported way to install them.

Three files land in `proingest/resources/ffmpeg/`: `ffmpeg`, `ffprobe` and the GPLv3 text.

### The normal way

```
.venv/bin/python build/fetch_ffmpeg.py
```

It downloads, checks each sha256, sets the executable bit and only then moves each file
into place. Run it again any time: it re-verifies what is already there and downloads
nothing if the bytes are right.

### Adding the files by hand

If you would rather download them in a browser, or the shell on this machine cannot reach
the site, get the list first:

```
.venv/bin/python build/fetch_ffmpeg.py --show
```

That prints each file, the URL it comes from and the sha256 it must have. Put whatever you
downloaded in one folder - the `.zip` archives as the site serves them, or the binaries
already extracted from them, either is accepted - and then:

```
.venv/bin/python build/fetch_ffmpeg.py --from ~/Downloads
```

It unpacks what needs unpacking, **checks every file against the same sha256 the download
path checks**, sets the executable bit and moves each one into place. A file that is not
the pinned build is refused and nothing is left behind, so a hand-placed binary is exactly
as trustworthy as a fetched one. It never copies the file itself, only the bytes, which is
what stops `com.apple.quarantine` riding along from the browser into a binary macOS would
then kill on first exec.

Copying the pair from another machine that already has them works the same way: point
`--from` at wherever you put them.

### Check it, always

```
.venv/bin/python build/fetch_ffmpeg.py --verify
```

Every file `ok`, or it names the ones that are missing or are not the pinned build, and
exits non-zero.

## 4. Put that ffmpeg on PATH before running the tests

```
export PATH="$PWD/proingest/resources/ffmpeg:$PATH"
```

**This matters more than it looks.** The media tests generate their fixtures by shelling
out to a bare `ffmpeg`, and if `shutil.which` finds nothing they **skip** rather than fail.
A suite run without this reports green having never encoded a frame. It is also what makes
the run meaningful: it exercises the 9.0.1 build that ships rather than some other one.

Put the line in your shell profile, or prefix the commands in section 5 with it.

## 5. Prove it works

```
.venv/bin/python -m pytest tests/ -q
.venv/bin/python -m ruff check . && .venv/bin/python -m ruff format --check . && .venv/bin/python -m mypy proingest tests build
.venv/bin/python -m proingest          # the app, in a window
```

The suite takes a couple of minutes and the media tests are most of it. If it reports a
few hundred tests rather than sixteen hundred, section 4 did not happen.

## 6. Build the app

```
.venv/bin/python build/build.py
.venv/bin/python build/smoke_test.py "dist/ProIngest.app/Contents/MacOS/ProIngest"
```

The first writes `dist/ProIngest.app` and `dist/ProIngest-<version>.dmg`, and prints the
installed size and the dmg size against the 300 MB budget. The second drives the packaged
binary through a whole fixture turnover - scan, a two worker render, both spreadsheets -
which is the check that no hidden import or plugin manifest was lost in freezing.

You do not have to build it to have it: CI builds the same dmg on an arm64 runner on every
push and uploads it as a run artifact. Building locally is for when you are changing what
goes into the bundle. `bash build/mac_build.sh --skip-checks` is these two
commands with sections 2 to 4 re-verified ahead of them.

## 7. Gatekeeper, once

An app built on this machine runs from this machine without ceremony. A dmg **downloaded
through a browser** carries `com.apple.quarantine`, and an unsigned app that carries it is
blocked outright rather than merely warned about:

```
xattr -dr com.apple.quarantine /Applications/ProIngest.app
```

`scp`, `rsync` and a USB drive do not apply the attribute in the first place. The real fix
is a Developer ID and notarization, which is OQ-9 and unresolved. `PACKAGING.md` has the
detail.

## 8. Then

`docs/MAC_SESSION.md`. It is the list of everything that could not be settled without a
Mac in front of a person, in the order it is worth doing, and it exists so that a session
on this machine is execution rather than exploration.
