"""Command line entry point.

`proingest` with no subcommand launches the UI (M5). The subcommands exist so core
can be driven headless, which is how the scan, render and QC stages are exercised
without Qt.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from proingest import __version__
from proingest.core import batchfile, scan
from proingest.core.models import Batch, ShotRow, Turnover

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

    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )

    if args.command == "scan":
        return _scan(args.folders, args.save, args.name)

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
