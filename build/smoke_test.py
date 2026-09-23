"""Drive a frozen build through a whole turnover and check what it wrote.

Usage:
    python build/smoke_test.py dist/ProIngest.app/Contents/MacOS/ProIngest

This is the gate `docs/MAC_SESSION.md` puts in front of renting a Mac: it answers
"does the bundle actually work" without a person looking at a screen, so a rented day
is spent on the things only a person can judge.

It is a subprocess test on purpose. Every failure a frozen build has that a source
checkout does not - a plugin manifest that was not collected, a module reached by name
and left out, a data file dropped - shows up as the packaged binary behaving differently
from the one the suite ran against, and the only way to see that is to run the packaged
binary. The fixtures come from `tests/fixtures`, so the demo turnover is the same
synthetic `MELT` show every test uses and no production data is involved.

**The `run` step is the multiprocessing check.** It asks for two workers, so the frozen
binary has to spawn copies of itself and have them come back as render workers rather
than as new instances of the app. Without `freeze_support()` in `build/entry.py` the
children get a `--multiprocessing-fork` argument that the argument parser rejects, they
die on startup, and the pool breaks. A green `run` here is what proves that line works.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from tests.fixtures import media as media_fixtures  # noqa: E402

SHOW = "MELT"
SHOT = "MELT0001"
FRAMES = 4

STEP_TIMEOUT = 600
"""Generous: a cold first launch of a frozen bundle off a slow disk is seconds, and a
four frame render is not the thing being timed."""


class SmokeFailure(RuntimeError):
    """The built app did not do what a working one does."""


def run_step(executable: Path, args: list[str]) -> str:
    """Run one subcommand and return its stdout, or raise with everything it said."""
    command = [str(executable), *args]
    print(f"  $ {' '.join(command)}")
    result = subprocess.run(command, capture_output=True, text=True, timeout=STEP_TIMEOUT, check=False)
    if result.returncode != 0:
        raise SmokeFailure(
            f"`{' '.join(args)}` exited {result.returncode}\n"
            f"--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}"
        )
    return result.stdout


def check_version(executable: Path) -> None:
    """It starts at all, and says who it is. Timed as a proxy for PRD section 8's
    five second first launch, which is a real measurement only on the target hardware."""
    started = time.monotonic()
    out = run_step(executable, ["--version"])
    elapsed = time.monotonic() - started
    if "proingest" not in out:
        raise SmokeFailure(f"--version printed {out!r}")
    print(f"  {out.strip()}, started in {elapsed:.1f}s")


def check_spawn_argument_is_intercepted(executable: Path) -> None:
    """The `freeze_support()` line in `build/entry.py` is still doing its job.

    A spawned worker is this same executable re-launched with `--multiprocessing-fork`
    and two keyword arguments. Handed that by hand, a working bundle gets as far as
    `spawn_main` and dies on the file descriptor, which is not real; a bundle that lost
    the `freeze_support()` call hands it to the argument parser instead, which prints
    its usage and refuses. So the check is that the usage line is *absent*.

    Cheap, and pointed at the one line in this repository most likely to be deleted by
    someone who checked it against the standard library and concluded it was a no-op.
    """
    result = subprocess.run(
        [str(executable), "--multiprocessing-fork", "tracker_fd=-1", "pipe_handle=-1"],
        capture_output=True,
        text=True,
        timeout=STEP_TIMEOUT,
        check=False,
    )
    if "usage: proingest" in result.stdout + result.stderr:
        raise SmokeFailure(
            "a --multiprocessing-fork argument reached the argument parser, so every "
            "render worker will die on startup. build/entry.py has lost its "
            "freeze_support() call, or the multiprocessing runtime hook is not in the "
            f"bundle.\n{result.stderr}"
        )
    print("  spawn arguments are intercepted before the parser")


def check_scan(executable: Path, work: Path) -> Path:
    """Scan a fixture turnover: the EDL, the metadata CSV and ffprobe, in the frozen app."""
    folder = work / "turnover001_09_13_2026_shooterA"
    media_fixtures.make_turnover(folder, shots=1, frames=FRAMES)
    rules = media_fixtures.write_rules_file(work / "rules.json")
    batch = work / "smoke.pibatch"
    out = run_step(executable, ["scan", str(folder), "--rules", str(rules), "--save", str(batch)])
    if SHOT not in out:
        raise SmokeFailure(f"scan did not find {SHOT}:\n{out}")
    if not batch.is_file():
        raise SmokeFailure(f"scan --save wrote no {batch}")
    return batch


def check_run(executable: Path, work: Path, batch: Path) -> Path:
    """Render the batch through a real worker pool and a real colour transform.

    Everything the tool is for passes through here: the spawn pool, ffmpeg, OpenEXR,
    OpenColorIO's built-in ACES config, and the CDL the turnover's EDL carries.
    """
    delivery = work / "delivery"
    out = run_step(
        executable,
        [
            "run",
            str(batch),
            "--delivery-root",
            str(delivery),
            "--jobs",
            "2",
        ],
    )

    shot_dir = delivery / SHOW / SHOT
    plate = shot_dir / f"{SHOT}_pl01_raw_4k_v01"
    expected = [plate, shot_dir / f"{SHOT}_pl01_raw_HD_v01", shot_dir / f"{SHOT}_pl01_audio_v01.wav"]
    missing = [path for path in expected if not path.exists()]
    if missing:
        raise SmokeFailure(f"the run did not write {', '.join(p.name for p in missing)}\n{out}")

    frames = sorted(plate.iterdir())
    if len(frames) != FRAMES:
        raise SmokeFailure(f"{plate.name} holds {len(frames)} frames, expected {FRAMES}")
    if list(shot_dir.glob("*.part")):
        raise SmokeFailure(f"a temporary file was left in {shot_dir}")
    print(f"  wrote {len(frames)} EXRs, a reference and the audio")
    return delivery


def check_qc(executable: Path, work: Path, batch: Path, delivery: Path) -> None:
    """Both spreadsheets, which is the openpyxl check."""
    reports = work / "reports"
    reports.mkdir()
    run_step(
        executable,
        ["qc", str(batch), "--delivery-root", str(delivery), "--out", str(reports)],
    )
    sheets = sorted(reports.glob("*.xlsx"))
    if len(sheets) != 2:
        raise SmokeFailure(f"expected a QC log and a shot tracker, got {[p.name for p in sheets]}")
    print(f"  wrote {', '.join(p.name for p in sheets)}")


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print(__doc__, file=sys.stderr)
        return 2
    executable = Path(args[0]).resolve()
    if not executable.is_file():
        print(f"error: {executable} is not a file", file=sys.stderr)
        return 2

    if not media_fixtures.ffmpeg_available():
        print("error: the fixtures need ffmpeg on PATH to generate the demo media", file=sys.stderr)
        return 2

    print(f"smoke testing {executable}")
    try:
        with tempfile.TemporaryDirectory(prefix="proingest-smoke-") as name:
            work = Path(name)
            check_version(executable)
            check_spawn_argument_is_intercepted(executable)
            batch = check_scan(executable, work)
            delivery = check_run(executable, work, batch)
            check_qc(executable, work, batch, delivery)
    except (SmokeFailure, subprocess.TimeoutExpired) as exc:
        print(f"\nFAILED: {exc}", file=sys.stderr)
        return 1

    print("\nthe bundle scans, renders and reports")
    return 0


if __name__ == "__main__":
    sys.exit(main())
