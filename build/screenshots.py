"""Take the user guide's pictures (M9.4).

The guide is illustrated by running this rather than by pressing a screenshot key,
because a guide illustrated by hand goes stale silently the first time a column moves
and a script makes a changed interface a re-run. It also settles the data question: the
demo batch is the synthetic `MELT` show the test fixtures already build, so no real shot
code, shooter name or Drive path ends up in a document that gets emailed around.

Usage:
    python build/screenshots.py                 # into docs/guide/images
    python build/screenshots.py --out <folder>
    python build/screenshots.py --list          # name what it would write, take nothing

**The shipped set has to be taken on a Mac.** A guide showing a Linux font stack is a
guide to a tool the editor does not have. Images taken here are for laying the document
out. `docs/MAC_SESSION.md` carries that line, and `choose_platform` is why the platform
is chosen rather than forced.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import tempfile
from collections.abc import Callable, Iterator
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from PySide6.QtWidgets import QApplication, QWidget  # noqa: E402

from proingest.core.models import Batch  # noqa: E402
from proingest.core.planner import plan_batch  # noqa: E402
from proingest.core.render import Progress  # noqa: E402
from proingest.ui import app as ui_app  # noqa: E402
from proingest.ui.main_window import BOTTOM_TABS, MainWindow  # noqa: E402
from proingest.ui.runner import RunProgress  # noqa: E402
from tests.fixtures.batches import (  # noqa: E402
    batch,
    delivered,
    fail,
    ingested,
    row,
    turnover,
    warn,
    with_sides,
)

# The fixtures are imported rather than reimplemented on purpose: the demo batch is meant
# to be the same synthetic show the suite uses, so a model change that breaks the pictures
# breaks the tests first. Setting `QT_QPA_PLATFORM` after importing PySide6 is fine: Qt
# reads it when the application is constructed, not when it is imported.

OUT_DIR = REPO_ROOT / "docs" / "guide" / "images"

RUN_SECONDS = 95.0
"""How long the run in the pictures is pretending to have been going."""

WINDOW_SIZE = (1680, 900)
"""Wide enough for all fifteen columns without a horizontal scrollbar, which a picture
of the list wants and a working window often does not have. A Retina grab comes back at
twice this, which is what the guide wants."""


def choose_platform() -> str:
    """Pick the Qt platform plugin, unless the caller already did.

    On macOS this deliberately leaves it alone, which means the real cocoa plugin: the
    offscreen plugin draws with Qt's own Fusion style and its own font fallbacks, so
    forcing it there would produce pictures of a tool that is not the one the editor
    opens - the whole reason the shipped set is taken on a Mac. Everywhere else there is
    no display to draw to, and offscreen is the only thing that works.
    """
    existing = os.environ.get("QT_QPA_PLATFORM")
    if existing:
        return existing
    if sys.platform != "darwin":
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
    return os.environ.get("QT_QPA_PLATFORM", "cocoa")


def demo_batch(work: Path) -> Batch:
    """Six shots over two turnovers, in as many of the seven row states as fit.

    The fixtures build one plausible turnover; the guide needs a list a reader can
    recognise their own work in, so this is that with the states spread across it: one
    delivered, one warned, one failed, one skipped, two untouched.
    """
    first = [
        with_sides(delivered(row("MELT0010_pl01", turnover_id="turnover001", record_in=0))),
        warn(row("MELT0020_pl01", turnover_id="turnover001", record_in=224)),
        row("MELT0030_pl01", turnover_id="turnover001", record_in=448),
    ]
    second = [
        fail(row("MELT0040_pl01", turnover_id="turnover002", record_in=0)),
        row("MELT0050_pl02", turnover_id="turnover002", record_in=224),
        row("MELT0060_pl01", turnover_id="turnover002", record_in=448),
    ]
    second[1].skipped = True
    second[1].skip_reason = "Held back: plate arrives in the next turnover"
    second[2].notes = "Ben asked for four extra frames at the tail"
    first[1].notes = "Handles are short at the head"

    built = batch(
        *first,
        *second,
        turnovers=[turnover("turnover001"), turnover("turnover002")],
        name="melt_turnover_12",
        delivery_root=work / "delivery",
    )
    (work / "delivery").mkdir(parents=True, exist_ok=True)
    return ingested(built, work)


def log_some_lines() -> None:
    """Give the Log tab something to be a picture of.

    Four lines at three levels, shaped like the ones a real run writes: the ffmpeg
    command line is what the tab is widest for, and a picture of an empty table would
    not show that.
    """
    log = logging.getLogger("proingest.render")
    log.info("Planned 6 rows: 14 deliverables, 2 turnovers")
    log.info("MELT0010_pl01_raw_4k_v01: 224 frames, 3840x2160, DWAA")
    log.warning("MELT0020_pl01: handles are 4 frames at the head, expected 8 (QC-030)")
    log.info(
        "ffmpeg -hide_banner -y -framerate 24 -i MELT0010_pl01.%%06d.exr -c:v libx264 "
        "-preset slow -crf 18 -pix_fmt yuv420p MELT0010_pl01_ref_v01.mp4"
    )
    log.error("MELT0040_pl01_raw_4k_v01: render failed, see the Issues tab (QC-012)")


def demo_clock() -> Callable[[], float]:
    """A clock that says the run started `RUN_SECONDS` ago, however fast this is.

    `RunProgress` divides frames by elapsed seconds, and these messages arrive in
    microseconds: a real clock puts "50908 frames/s" in the status bar of a picture
    meant to show what a render looks like.
    """
    calls = iter([0.0])

    def clock() -> float:
        return next(calls, RUN_SECONDS)

    return clock


def mid_run(window: MainWindow) -> None:
    """Put the window into the middle of a render without running one.

    Everything a run draws comes off one `RunProgress` and one method, so this builds
    that object, feeds it the messages a pool would have sent and lets the window draw
    itself: the strip's bar and step line, the status bar's numbers and the per row
    bars all come out consistent because they come from the same place they always do.
    Rendering for real would take a minute and give a different percentage every time.
    """
    jobs = plan_batch(window.batch)
    progress = RunProgress(jobs, clock=demo_clock())
    window._run_progress = progress
    window.shot_model.set_run(progress)
    window.run_strip.start()
    window.progress.setVisible(True)

    for job in jobs[:5]:
        window._run_progressed(Progress(job.name, "done", job.frame_count, job.frame_count))
    running = jobs[5]
    window._run_progressed(Progress(running.name, "frame", running.frame_count // 3, running.frame_count))
    window._show_run_progress()


PICTURES = (
    "empty-state",
    "shot-list",
    "metadata-pane",
    "issues-dock",
    "log-tab",
    "run-in-progress",
    "settings",
)
"""What the guide references, by the name it references it by: one per surface in M9.3,
plus the empty state M9.1's first run section needs. Named here rather than only inside
`scenes` so that a picture that stops being taken fails loudly instead of leaving the
guide with a broken image."""


def scenes(window: MainWindow, work: Path) -> Iterator[tuple[str, QWidget]]:
    """Walk the window through every state a picture is wanted of, pausing at each.

    A generator rather than a dict of widgets because three of these are the same
    widget at different moments: collecting them and grabbing afterwards would give
    three pictures of the last state.
    """
    yield "empty-state", window

    window.set_batch(demo_batch(work))
    # The pane is a dock the editor opens and closes (Ctrl+I), and with it open the
    # list loses the last columns to a scrollbar. It gets its own picture below.
    window.metadata_dock.hide()
    yield "shot-list", window

    window.metadata_dock.show()
    window.shot_list.select_row(window.batch.rows[1])
    yield "metadata-pane", window.metadata_dock
    yield "issues-dock", window.issues

    window.bottom_tabs.setCurrentIndex(BOTTOM_TABS.index("Log"))
    log_some_lines()
    window.log_view.drain()
    yield "log-tab", window.log_view
    window.bottom_tabs.setCurrentIndex(BOTTOM_TABS.index("Issues"))

    mid_run(window)
    window.metadata_dock.hide()
    yield "run-in-progress", window

    dialog = window.settings_dialog()
    dialog.adjustSize()
    yield "settings", dialog


def settle(application: QApplication, rounds: int = 5) -> None:
    """Let Qt finish laying out before anything is grabbed.

    One pass through the event loop is not enough: a widget grabbed too early comes
    back with its rows drawn on top of each other, because the geometry it was given
    has not reached the children yet. This was found by looking at the metadata pane.
    """
    for _ in range(rounds):
        application.processEvents()


def take(widget: QWidget, path: Path) -> None:
    """Grab one widget into a PNG. On a Retina screen this comes back at 2x by itself."""
    picture = widget.grab()
    if picture.isNull() or not picture.save(str(path), "PNG"):
        raise SystemExit(f"could not write {path}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Take the user guide's screenshots.")
    parser.add_argument("--out", type=Path, default=OUT_DIR, help=f"where to write them (default {OUT_DIR})")
    args = parser.parse_args(argv)

    platform = choose_platform()
    out_dir = args.out.expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)

    application = ui_app.build_application([])
    written: list[str] = []
    # Named, because the demo batch's folders end up in the pictures: a CLF path in the
    # metadata pane is read by whoever reads the guide.
    with tempfile.TemporaryDirectory(prefix="MELT-demo-") as tmp:
        work = Path(tmp)
        # A settings file of its own, so the pictures show the defaults and the user's
        # own settings are neither read nor written by taking them.
        window = MainWindow(work / "settings.json")
        window.resize(*WINDOW_SIZE)
        window.show()
        application.processEvents()

        for name, widget in scenes(window, work):
            settle(application)
            take(widget, out_dir / f"{name}.png")
            written.append(name)
            print(f"  {name}.png")

        window.log_view.detach()

    missing = [name for name in PICTURES if name not in written]
    if missing:
        raise SystemExit(f"never taken: {', '.join(missing)}")
    print(f"{len(written)} pictures into {out_dir}, drawn by the {platform} platform")
    if platform != "cocoa":
        print("These are for drafting. The set that ships has to be taken on a Mac.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
