"""Command line entry point.

`proingest` with no subcommand launches the UI (M5). The subcommands exist so core
can be driven headless, which is how the scan, render and QC stages are exercised
without Qt.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any

from proingest import __version__
from proingest.core import batchfile, clf, exports, logsetup, naming, planner, qc, render, scan
from proingest.core.models import DEFAULT_WORKERS, Batch, Deliverable, ShotRow, Turnover

COLUMNS = ("STATUS", "SHOT", "ELEM", "SOURCE", "RES", "FPS", "IN", "OUT", "DUR", "MAX", "AUDIO")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="proingest", description=__doc__)
    parser.add_argument("--version", action="version", version=f"proingest {__version__}")
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="log every ffmpeg command (subcommands only; the app takes its level from Settings)",
    )
    subparsers = parser.add_subparsers(dest="command")
    pattern_help = (
        "the show code pattern, a regular expression, when the Settings page has a custom one "
        f"(default {naming.DEFAULT_SHOW_PATTERN})"
    )

    scan_parser = subparsers.add_parser("scan", help="scan turnover folders and print the row table")
    scan_parser.add_argument("folders", nargs="+", type=Path)
    scan_parser.add_argument("--save", type=Path, help="write the result to a .pibatch file")
    scan_parser.add_argument("--name", default="untitled", help="batch name")
    scan_parser.add_argument("--show-pattern", default=naming.DEFAULT_SHOW_PATTERN, help=pattern_help)
    scan_parser.add_argument(
        "--rules",
        type=Path,
        help="JSON file of rule threshold overrides (FR-12); saved into the batch",
    )

    run_parser = subparsers.add_parser("run", help="plan and render a saved batch")
    run_parser.add_argument("batch", type=Path, help="a .pibatch file")
    run_parser.add_argument("--delivery-root", type=Path, help="overrides the batch's own root")
    run_parser.add_argument(
        "--jobs",
        type=int,
        default=DEFAULT_WORKERS,
        help=f"worker processes (default {DEFAULT_WORKERS})",
    )
    run_parser.add_argument("--dry-run", action="store_true", help="print the plan and write nothing")
    run_parser.add_argument("--show-pattern", default=naming.DEFAULT_SHOW_PATTERN, help=pattern_help)

    qc_parser = subparsers.add_parser("qc", help="write the QC log and shot tracker for a batch")
    qc_parser.add_argument("batch", type=Path, help="a .pibatch file")
    qc_parser.add_argument("--delivery-root", type=Path, help="overrides the batch's own root")
    qc_parser.add_argument(
        "--out", type=Path, help="write both files here instead of the show's _reports folder"
    )
    qc_parser.add_argument("--show-pattern", default=naming.DEFAULT_SHOW_PATTERN, help=pattern_help)

    args = parser.parse_args(argv)
    # Console only: the log file lives in a folder `ui/paths.py` asks Qt for, and the
    # subcommands are the headless half that must not import PySide6 to print a table.
    logsetup.configure(level=logging.INFO if args.verbose else logging.WARNING)

    if args.command == "scan":
        return _scan(args.folders, args.save, args.name, args.rules, args.show_pattern)

    if args.command == "run":
        return _run(
            args.batch,
            args.delivery_root,
            args.jobs,
            args.dry_run,
            args.show_pattern,
        )

    if args.command == "qc":
        return _qc(args.batch, args.delivery_root, args.out, args.show_pattern)

    return _launch_ui()


def _launch_ui() -> int:
    """No subcommand: the app. Qt is imported here rather than at module scope.

    Every subcommand above runs headless, and importing PySide6 to print a scan table
    would cost the import and would fail on a machine with no Qt at all. The UI is the
    one path that needs it, so it is the one path that imports it.
    """
    from proingest.ui import app

    return app.run()


def _scan(
    folders: list[Path],
    save: Path | None,
    name: str,
    rules_path: Path | None,
    show_pattern: str = naming.DEFAULT_SHOW_PATTERN,
) -> int:
    missing = [folder for folder in folders if not folder.is_dir()]
    if missing:
        for folder in missing:
            print(f"error: {folder} is not a directory", file=sys.stderr)
        return 2

    try:
        overrides = _load_rule_overrides(rules_path)
    except (OSError, TypeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    settings = scan.ScanSettings(show_pattern=show_pattern, rules=qc.RuleSettings.from_dict(overrides))
    batch = scan.scan_batch(folders, name=name, settings=settings)
    if overrides:
        batch.settings_overrides[qc.RULES_OVERRIDE_KEY] = overrides
    _print_batch(batch)

    if save is not None:
        written = batchfile.save(batch, save)
        print(f"\nwrote {written}")

    return 1 if _has_errors(batch) else 0


def _print_preflight(batch: Batch) -> bool:
    """Print what the pre-flight rules found and say whether the run must stop.

    **Any must-fix anywhere stops it** (D8, `qc.must_fix`): the batch waits for the
    folder to be corrected and re-scanned. Warnings about the batch and its turnovers are
    printed too, because they are what the editor reads before a delivery.
    """
    results = list(batch.qc) + [result for turnover in batch.turnovers for result in turnover.qc]
    for result in results:
        if result.severity != "error":
            print(f"  {result.severity.upper():7} {result.rule_id}  {result.message}")
    found = qc.must_fix(batch)
    for where, result in found:
        print(f"error: {where}: {result.rule_id}: {result.message}", file=sys.stderr)
    return bool(found)


def _load_rule_overrides(path: Path | None) -> dict[str, Any]:
    """Read a rule overrides file, or return no overrides at all.

    Kept as a plain dict so the batch stores exactly what the user wrote, rather than
    a full settings object that would bake today's defaults into a saved file.
    """
    if path is None:
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} must hold a JSON object of rule settings")
    qc.RuleSettings.from_dict(data)
    return dict(data)


def _run(
    batch_path: Path,
    delivery_root: Path | None,
    jobs: int,
    dry_run: bool,
    show_pattern: str = naming.DEFAULT_SHOW_PATTERN,
) -> int:
    """Plan a saved batch and render it.

    Planning happens here rather than at scan time because the version depends on what
    is in the delivery folder at the moment the run starts (NAMING_SPEC section 4).

    The cut and the grade were read at scan from the EDL in the turnover folder and are
    on the rows. Any must-fix stops the run before anything is planned (`qc.must_fix`).
    """
    try:
        batch = batchfile.load(batch_path)
    except batchfile.BatchFileError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    root = delivery_root or batch.delivery_root
    if root is None:
        print("error: no delivery root: pass --delivery-root, or set one on the batch", file=sys.stderr)
        return 2

    batch.delivery_root = root
    qc.preflight(batch)
    if _print_preflight(batch):
        return 2

    try:
        planned = planner.plan_batch(batch, root, show_pattern)
    except (ValueError, clf.ClfError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if not planned:
        print("nothing to render: every shot is complete, skipped or waiting for a Reset")
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
    render.apply_results(batch, written, show_pattern)
    try:
        batchfile.backup(batch_path)
        batchfile.save(batch, batch_path)
    except OSError as exc:
        print(f"error: the run finished but the batch could not be saved: {exc}", file=sys.stderr)
        return 2

    return _report_run(written, batch_path)


def _qc(
    batch_path: Path,
    delivery_root: Path | None,
    out: Path | None,
    show_pattern: str = naming.DEFAULT_SHOW_PATTERN,
) -> int:
    """Re-run the rules over a saved batch and write both spreadsheets.

    The rules are re-run rather than read back off the batch file, because a batch can
    be reopened after an edit and the log has to describe the batch as it is now. Phase
    B is re-applied from what the render recorded; it does not re-read the deliverables.
    """
    try:
        batch = batchfile.load(batch_path)
    except batchfile.BatchFileError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    batch.delivery_root = delivery_root or batch.delivery_root
    qc.apply_batch_rules(batch, qc.settings_for(batch))
    qc.preflight(batch)
    qc.apply_phase_b(batch, show_pattern)

    try:
        log_path, tracker_path = _report_destinations(batch, out)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    exports.write_qc_log(batch, log_path)
    exports.write_shot_tracker(batch, tracker_path)

    counts = exports.severity_counts(batch)
    rows = sum(1 for row in batch.rows if not row.skipped)
    print(f"{log_path}")
    print(f"{tracker_path}")
    print(
        f"\n{rows} rows, {sum(len(r.deliverables) for r in batch.rows)} deliverables, "
        f"{counts['error']} errors, {counts['warning']} warnings"
    )
    return 1 if counts["error"] else 0


def _report_destinations(batch: Batch, out: Path | None) -> tuple[Path, Path]:
    """Where the two files go: `--out`, or the show's `_reports` folder."""
    if out is None:
        if batch.delivery_root is None:
            raise ValueError("the batch has no delivery root; pass --delivery-root or --out")
        return exports.report_paths(batch, batch.delivery_root)
    log_name, tracker_name = exports.report_names(batch)
    return out / log_name, out / tracker_name


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
    # Every deliverable that has anything to say, not only the failed ones: phase B
    # warnings such as QC-107 and QC-114 land on a deliverable that is still done.
    for deliverable in written:
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
