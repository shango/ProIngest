#!/usr/bin/env bash
#
# Double-click this in Finder to run ProIngest from this folder.
#
# It is the alternative to the packaged app for when there is no time to build,
# sign or download one: the folder is the program, and this file starts it.
# The first run prepares the environment and fetches the video tools, which
# needs a network connection and takes a few minutes; every run after that
# opens the window in a couple of seconds.
#
# Needs uv (https://astral.sh/uv), which brings its own Python. It says so
# rather than installing one for you.
#
# `docs/MAC_SETUP.md` is the same thing typed out, and `build/mac_build.sh`
# is the version that also runs the tests and builds the app.

set -euo pipefail

# Finder starts a double-clicked script in the home folder, not in this one.
cd "$(dirname "${BASH_SOURCE[0]}")"
REPO_ROOT="$PWD"
PY="$REPO_ROOT/.venv/bin/python"
FFMPEG_DIR="$REPO_ROOT/proingest/resources/ffmpeg"

# Terminal closes on exit and takes the error with it, so anything that goes
# wrong is held on screen until a key is pressed.
hold() {
    printf '\n\033[1;31m%s\033[0m\n' "$1" >&2
    printf 'Press any key to close this window.\n'
    read -r -n 1 -s
    exit 1
}

if ! command -v uv >/dev/null 2>&1; then
    if [[ -x "$HOME/.local/bin/uv" ]]; then
        PATH="$HOME/.local/bin:$PATH"
    else
        hold "uv is not installed. Open Terminal and run:

  curl -LsSf https://astral.sh/uv/install.sh | sh

then double-click this file again."
    fi
fi

if [[ ! -x "$PY" ]]; then
    echo "First run: preparing the environment. This takes a few minutes."
    uv sync --frozen --extra dev --python 3.12 || hold "Could not build the environment."
fi

if ! "$PY" build/fetch_ffmpeg.py --verify >/dev/null 2>&1; then
    echo "First run: fetching the video tools (132 MB)."
    "$PY" build/fetch_ffmpeg.py || hold "Could not fetch the video tools. With them downloaded by hand into a folder:

  .venv/bin/python build/fetch_ffmpeg.py --from <that folder>

See docs/MAC_SETUP.md section 3."
fi

# The app finds its own copy inside this folder, so this is for anything it
# shells out to rather than for the app itself.
export PATH="$FFMPEG_DIR:$PATH"

echo "Starting ProIngest. Closing this window quits it."
exec "$PY" -m proingest
