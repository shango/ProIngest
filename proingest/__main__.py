"""Command line entry point.

`proingest` with no subcommand launches the UI (M5). The subcommands exist so core
can be driven headless, which is how the scan, render and QC stages are exercised
without Qt.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

from proingest import __version__
from proingest.core import batchfile, planner, render, scan
from proingest.core.models import Batch, Deliverable, ShotRow, Turnover

COLUMNS = ("STATUS", "SHOT", "ELEM", "SOURCE", "RES", "FPS", "IN", "OUT", "DUR", "MAX", "AUDIO")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="proingest", description=__doc__)
    parser.add_argument("--version", action="version", version=f"proingest {__version__}")
    parser.add_argument("-v", "--verbose", action="store_true", help="log every ffmpeg command")
    subparsers = parser.add_subparsers(dest="command")

    scan_parser = subparsers.add_parser("scan", help="scan turnover folders and print the row table")
    scan_parser.add_argument("folders", nargs="+", type=Path)
    scan_parser.add_argument("--save", type=Path, help="write the result to a .pibatch file")
    scan_parser.add_argument("--name", default="untitled", help="batch name")

    run_parser = subparsers.add_parser("run", help="plan and render a saved batch")
    run_parser.add_argument("batch", type=Path, help="a .pibatch file")
    run_parser.add_argument("--delivery-root", type=Path, help="overrides the batch's own root")
    run_parser.add_argument(
        "--jobs",
        type=int,
        default=render.DEFAULT_WORKERS,
        help=f"worker processes (default {render.DEFAULT_WORKERS})",
    )
    run_parser.add_argument(
        "--dry-run", action="store_true", help="print the plan and write nothing"
    )

    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )

    if args.command == "scan":
        return _scan(args.folders, args.save, args.name)

    if args.command == "run":
        return _run(args.batch, args.delivery_root, args.jobs, args.dry_run)

    parser.print_help()
    return 0


def _scan(folders: list[Path], save: Path | None, name: str) -> int:
    missing = [folder for folder in folders if not folder.is_dir()]
    if missing:
        for folder in missing:
            print(f"error: {folder} is not a directory", file=sys.stderr)
        return 2

    batch = scan.scan_batch(folders, name=name)
    _print_batch(batch)

    if save is not None:
        written = batchfile.save(batch, save)
        print(f"\nwrote {written}")

    return 1 if _has_errors(batch) else 0


def _run(batch_path: Path, delivery_root: Path | None, jobs: int, dry_run: bool) -> int:
    """Plan a saved batch and render it.

    Planning happens here rather than at scan time because the version depends on what
    is in the delivery folder at the moment the run starts (NAMING_SPEC section 4).
    """
    try:
        batch = batchfile.load(batch_path)
    except batchfile.BatchFileError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    try:
        planned = planner.plan_batch(batch, delivery_root)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if not planned:
        print("nothing to render: no row produced a deliverable")
        return 0

    for job in planned:
        frames = f"{job.frame_count} frames" if job.frame_count else "copy"
        print(f"  {job.kind:10} {job.name:52} {frames}")
    print(f"\n{len(planned)} deliverables from {len({j.shot_code for j in planned})} shots")

    if dry_run:
        return 0

    print()
    reporter = _ProgressPrinter()
    written = render.execute(planned, workers=jobs, on_progress=reporter)
    render.apply_results(batch, written)
    batchfile.backup(batch_path)
    batchfile.save(batch, batch_path)

    return _report_run(written, batch_path)


class _ProgressPrinter:
    """Per-deliverable result lines, plus one aggregate line while frames land.

    Jobs from several workers interleave, so a per-job line redrawn in place turns
    into a wall of text the moment two are running. The running total is one line
    that means something no matter how many workers are going, and it is only drawn
    on a tty: redirected output gets the result lines alone, which is what a log
    wants anyway.
    """

    def __init__(self, interval: float = 0.2) -> None:
        self._done: dict[str, int] = {}
        self._total: dict[str, int] = {}
        self._finished = 0
        self._jobs = 0
        self._last_draw = 0.0
        self._interval = interval
        self._live = sys.stdout.isatty()
        self._width = 0

    def __call__(self, message: render.Progress) -> None:
        if message.state == "started":
            self._jobs += 1
            self._total[message.name] = message.frames_total
            return
        if message.state == "frame":
            self._done[message.name] = message.frames_done
            self._draw()
            return

        self._finished += 1
        self._done[message.name] = self._total.get(message.name, 0)
        self._clear()
        if message.state == "done":
            print(f"  {message.name:52} done")
        elif message.state == "failed":
            print(f"  {message.name:52} FAILED  {message.message}")
        else:
            print(f"  {message.name:52} cancelled")

    def _draw(self) -> None:
        now = time.monotonic()
        if not self._live or now - self._last_draw < self._interval:
            return
        self._last_draw = now
        total = sum(self._total.values())
        done = sum(self._done.values())
        percent = int(100 * done / total) if total else 0
        line = f"  {self._finished}/{self._jobs} deliverables, {done}/{total} frames, {percent}%"
        self._width = max(self._width, len(line))
        print(line.ljust(self._width), end="\r", flush=True)

    def _clear(self) -> None:
        """Wipe the aggregate line so a result line does not land on top of it."""
        if self._live and self._width:
            print(" " * self._width, end="\r")


def _report_run(written: list[Deliverable], batch_path: Path) -> int:
    done = [d for d in written if d.status == "done"]
    failed = [d for d in written if d.status == "failed"]
    skipped = [d for d in written if d.status == "skipped"]

    print(f"\n{len(done)} written, {len(failed)} failed, {len(skipped)} skipped")
    for deliverable in failed:
        for result in deliverable.qc:
            print(f"  {result.severity.upper():7} {result.rule_id}  {result.message}")
    print(f"wrote {batch_path.with_suffix(batchfile.SUFFIX)}")
    return 1 if failed else 0


def _has_errors(batch: Batch) -> bool:
    turnover_errors = any(r.severity == "error" for t in batch.turnovers for r in t.qc)
    return turnover_errors or any(row.errors() for row in batch.rows)


def _print_batch(batch: Batch) -> None:
    for turnover in batch.turnovers:
        rows = batch.rows_for(turnover.turnover_id)
        warnings = sum(len(row.warnings()) for row in rows)
        errors = sum(len(row.errors()) for row in rows)
        label = _turnover_label(turnover)
        print(f"\n{label}  {len(rows)} shots  {warnings} warn  {errors} err")

        for result in turnover.qc:
            print(f"  {result.severity.upper():7} {result.rule_id}  {result.message}")

        if rows:
            _print_table(rows)

    total_rows = len(batch.rows)
    total_errors = sum(len(row.errors()) for row in batch.rows)
    total_warnings = sum(len(row.warnings()) for row in batch.rows)
    print(f"\n{total_rows} rows, {total_errors} errors, {total_warnings} warnings")


def _turnover_label(turnover: Turnover) -> str:
    """Prefer the parsed turnover fields; fall back to the folder when QC-005 fired."""
    if turnover.number is None:
        return str(turnover.folder)
    return (
        f"turnover{turnover.number:03d}  "
        f"{turnover.month:02d}_{turnover.day:02d}_{turnover.year:04d}  {turnover.shooter}"
    )


def _print_table(rows: list[ShotRow]) -> None:
    table = [COLUMNS, *(_row_cells(row) for row in rows)]
    widths = [max(len(row[index]) for row in table) for index in range(len(COLUMNS))]
    for position, cells in enumerate(table):
        line = "  ".join(cell.ljust(width) for cell, width in zip(cells, widths, strict=True))
        print(f"  {line.rstrip()}")
        if position == 0:
            print(f"  {'  '.join('-' * width for width in widths)}")

    for row in rows:
        for result in row.qc:
            code = row.shot_code or row.clip_name
            print(f"    {result.severity.upper():7} {result.rule_id}  {code}: {result.message}")


def _row_cells(row: ShotRow) -> tuple[str, ...]:
    media = row.media
    identity = row.identity
    return (
        _status(row),
        row.shot_code or row.clip_name,
        identity.elem if identity else "-",
        media.path.name if media else "-",
        f"{media.width}x{media.height}" if media else "-",
        str(media.rate) if media else "-",
        str(row.current.in_frame) if row.current else "-",
        str(row.current.out_frame) if row.current else "-",
        str(row.duration) if row.duration is not None else "-",
        str(row.max_available_out) if row.max_available_out is not None else "-",
        "yes" if row.audio_path else "no",
    )


def _status(row: ShotRow) -> str:
    if row.errors():
        return "ERROR"
    if row.warnings():
        return "warn"
    return "ok"


if __name__ == "__main__":
    sys.exit(main())
