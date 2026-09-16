#!/usr/bin/env bash
#
# Clone to a built app, in one command. macOS on Apple Silicon only.
#
#   git clone git@github.com:shango/ProIngest.git ProIngest
#   cd ProIngest
#   bash build/mac_build.sh
#
# It does exactly what `docs/MAC_SETUP.md` sections 2 to 6 do by hand, in the same
# order and with the same commands, and it stops at the first thing that fails. Re-run
# it as often as you like: every step is a no-op when it has nothing to do.
#
#   --from DIR      install the ffmpeg pair from files already downloaded into DIR
#                   instead of fetching them (MAC_SETUP section 3)
#   --skip-checks   build without running ruff, mypy and the test suite first
#
# What it deliberately does not do: install uv (it tells you the one line), run
# `build/screenshots.py` (that writes files for you to look at and commit, which is a
# Mac-session task rather than a build step) and sign anything (OQ-9, PACKAGING.md).

set -euo pipefail

FROM=""
SKIP_CHECKS=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --from)
            FROM="${2:-}"
            [[ -n "$FROM" ]] || { echo "--from needs a folder" >&2; exit 2; }
            shift 2
            ;;
        --skip-checks)
            SKIP_CHECKS=1
            shift
            ;;
        -h|--help)
            # The header block, down to the first line that is not a comment, so
            # that editing it cannot leave this printing half of itself.
            awk 'NR > 1 && /^#/ { sub(/^# ?/, ""); print; next } NR > 1 { exit }' "${BASH_SOURCE[0]}"
            exit 0
            ;;
        *)
            echo "unknown argument: $1" >&2
            exit 2
            ;;
    esac
done

# Run from the repo root whatever folder the script was invoked from, so that the
# relative paths below and `uv sync`'s choice of .venv land in the right place.
cd "$(dirname "${BASH_SOURCE[0]}")/.."
REPO_ROOT="$PWD"
FFMPEG_DIR="$REPO_ROOT/proingest/resources/ffmpeg"
PY="$REPO_ROOT/.venv/bin/python"

step() {
    printf '\n\033[1m==> %s\033[0m\n' "$1"
}

die() {
    printf '\n\033[1;31m!!  %s\033[0m\n' "$1" >&2
    exit 1
}

# 1. The two things that are true of the machine or are not.

[[ "$(uname -s)" == "Darwin" ]] || die "This is the macOS build script and this is not macOS."

# The bundled ffmpeg is arm64 Mach-O, so an Intel Mac gets Exec format error on the
# first probe rather than a build that merely runs slowly (OQ-24).
[[ "$(uname -m)" == "arm64" ]] || die "Apple Silicon only. This machine reports $(uname -m)."

if ! command -v uv >/dev/null 2>&1; then
    # uv installs itself here and only edits the shell profile, which this shell has
    # already read, so a fresh install is invisible until a new terminal.
    if [[ -x "$HOME/.local/bin/uv" ]]; then
        PATH="$HOME/.local/bin:$PATH"
    else
        die "uv is not installed. Run:  curl -LsSf https://astral.sh/uv/install.sh | sh"
    fi
fi

# 2. The environment, exactly as CI installs it.

step "Installing the locked environment"
# --frozen installs uv.lock as committed and fails if pyproject.toml has moved ahead of
# it. On a build machine that is the behaviour worth having: the alternative silently
# resolves a different dependency set than the one CI proved green.
uv sync --frozen --extra dev --python 3.12

# 3. The ffmpeg pair, which is 132 MB and is not in git.

step "Checking the bundled ffmpeg"
if "$PY" build/fetch_ffmpeg.py --verify >/dev/null 2>&1; then
    echo "already the pinned build"
elif [[ -n "$FROM" ]]; then
    "$PY" build/fetch_ffmpeg.py --from "$FROM"
else
    "$PY" build/fetch_ffmpeg.py
fi
"$PY" build/fetch_ffmpeg.py --verify

# Ahead of the tests, not just the build: the media fixtures shell out to a bare
# `ffmpeg` and skip rather than fail when `shutil.which` finds nothing, so a suite run
# without this line reports green having never encoded a frame (MAC_SETUP section 4).
export PATH="$FFMPEG_DIR:$PATH"
# And prove it execs. A quarantined or wrong-architecture binary dies here, with its
# own error, rather than a hundred confusing skips later.
ffmpeg -hide_banner -version | head -1
ffprobe -hide_banner -version | head -1

# 4. Lint, types and the suite, which is what makes the build worth trusting.

if [[ "$SKIP_CHECKS" -eq 1 ]]; then
    step "Skipping ruff, mypy and the tests (--skip-checks)"
else
    step "Lint, format check and type check"
    "$PY" -m ruff check .
    "$PY" -m ruff format --check .
    "$PY" -m mypy proingest tests build

    step "Tests"
    # A couple of minutes, most of it the media tests. If this reports a few hundred
    # rather than about seventeen hundred, the PATH line above did not take.
    "$PY" -m pytest tests/ -q
fi

# 5. The app, the dmg, and the proof that the frozen thing works.

step "Building the app and the dmg"
"$PY" build/build.py

step "Smoke testing the frozen build"
# Scans a fixture turnover, renders it through a two worker pool and writes both
# spreadsheets, all through the packaged binary: the check that no hidden import or
# plugin manifest was lost in freezing.
"$PY" build/smoke_test.py "dist/ProIngest.app/Contents/MacOS/ProIngest"

step "Done"
echo "app:  $REPO_ROOT/dist/ProIngest.app"
for dmg in "$REPO_ROOT"/dist/ProIngest-*.dmg; do
    [[ -e "$dmg" ]] && echo "dmg:  $dmg"
done
cat <<'NEXT'

Open it with:  open dist/ProIngest.app
Run from source instead:  .venv/bin/python -m proingest

A dmg copied to another Mac through a browser is blocked by Gatekeeper until it is
signed (OQ-9). scp, rsync and a USB drive do not apply the quarantine attribute.

Next, docs/MAC_SESSION.md. Its first line is `.venv/bin/python build/screenshots.py`,
which writes the user guide's pictures and has to run on this machine.
NEXT
