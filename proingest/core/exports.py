"""The two spreadsheets a run produces.

`QC_RULES.md` under "QC log structure" is the spec for both, and the difference between
them is who the document belongs to.

**The QC log is ours.** Five sheets, as wide as the tool's own knowledge, written fresh
every time and read by whoever is checking a delivery.

**The tracker is the studio's**, and the tool only ever adds rows to it. Its 39 columns
are the production's own, and thirty of them are filled in by the vendor's team over
the weeks after a delivery: statuses, owners, difficulty grades, callout movies. So the
sheet written here is rows to paste, in that column order, with every column the tool
does not own left empty. A blank cell pastes over nothing.

Both are openpyxl, which is already a dependency, and neither reads a template file.
The tracker's columns were a Settings-configurable template while OQ-2 was open and
nobody knew them; they are known now, and a template loader would be a configuration
point standing where a fact belongs.
"""

from __future__ import annotations

from collections import Counter
from datetime import date
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font
from openpyxl.worksheet.worksheet import Worksheet

from proingest import __version__
from proingest.core import frames, naming, qc
from proingest.core.models import Batch, Deliverable, QCResult, ShotRow

DATE_STAMP = "%Y%m%d"
"""NAMING_SPEC section 5 writes `<date>` in the report names and does not say what it
is. It is this, because a report that sorts by name sorts by date."""

_HEADER_FONT = Font(bold=True)


def report_names(batch: Batch, when: date | None = None) -> tuple[str, str]:
    """The two filenames, `(qc log, tracker)`. NAMING_SPEC section 5."""
    stamp = (when or date.today()).strftime(DATE_STAMP)
    return (
        f"qc_ingest_log_{batch.name}_{stamp}.xlsx",
        f"shot_tracker_{batch.name}_{stamp}.xlsx",
    )


def report_paths(batch: Batch, delivery_root: Path, when: date | None = None) -> tuple[Path, Path]:
    """Those two files under `<delivery_root>/<show>/_reports/`.

    The show comes from the first row that has a shot code, because NAMING_SPEC section
    5 puts `_reports/` under the show and a batch is one turnover set. A batch that
    spans two shows writes both reports under the first, which is visible in the path
    rather than silent, and is a one line change if it ever happens.
    """
    show = next((row.identity.show for row in batch.rows if row.identity), None)
    if show is None:
        raise ValueError("no row in the batch has a shot code, so there is no show to file under")
    folder = naming.reports_dir(delivery_root, show)
    log_name, tracker_name = report_names(batch, when)
    return folder / log_name, folder / tracker_name


def severity_counts(batch: Batch) -> Counter[str]:
    """Every QC result in the batch, counted by severity. The Summary's own tally."""
    return Counter(result.severity for results in _every_result(batch) for result in results)


def _sheet(book: Workbook, title: str, headers: tuple[str, ...]) -> Worksheet:
    """A sheet with a bold, frozen header row and columns wide enough to read."""
    sheet = book.create_sheet(title)
    sheet.append(list(headers))
    for cell in sheet[1]:
        cell.font = _HEADER_FONT
        cell.alignment = Alignment(vertical="top", wrap_text=True)
    sheet.freeze_panes = "A2"
    for index, header in enumerate(headers, start=1):
        sheet.column_dimensions[sheet.cell(row=1, column=index).column_letter].width = min(
            max(len(header) + 2, 10), 42
        )
    return sheet


def _timecode(row: ShotRow, source_frame: int | None) -> str:
    """A source frame as `HH:MM:SS:FF`, or empty when the media states no timecode."""
    media = row.media
    if media is None or media.start_timecode is None or source_frame is None:
        return ""
    total = frames.timecode_frames_for(source_frame, media.start_frame, media.start_timecode)
    return frames.frames_to_timecode(total, media.rate.as_float())


def _rule_ids(results: list[QCResult], severity: str) -> str:
    return ", ".join(sorted({r.rule_id for r in results if r.severity == severity}))


# --- The QC log: five sheets, ours ---------------------------------------------------

SHOTS_HEADERS = (
    "Turnover", "Clip name", "Shot code", "Elem", "Source", "FPS", "Res",
    "Delivered In", "Delivered Out", "Delivered In TC", "Delivered Out TC",
    "Final In", "Final Out", "Duration", "Max available", "Audio", "Edited",
    "Source encoding",
    "Skip reason", "Warnings", "Errors",
)  # fmt: skip
"""The QC log's own columns, QC_RULES "QC log structure".

Source encoding is the whole of the colour chain a row was rendered through that a
reader can check, the CDL itself being in the delivered EXR header. It is **what the
clip's metadata named, verbatim**,
rather than the colour space that resolved to: this column is read when QC-046 or
QC-047 fires, and what has to be corrected is the string somebody typed. Empty means
the clip named none. Where the name came from is in the delivered EXR header rather
than here (`exr.SOURCE_ENCODING_ORIGIN_ATTRIBUTE`)."""

DELIVERABLE_HEADERS = (
    "Shot code", "Elem", "Kind", "Res", "Version", "Path", "Frames", "Size", "Checksum",
)  # fmt: skip


def _write_summary(book: Workbook, batch: Batch, when: date) -> None:
    """One key and one value per line: what was run, and what it said."""
    sheet = _sheet(book, "Summary", ("Item", "Value"))
    counts = severity_counts(batch)
    for label, value in (
        ("Batch", batch.name),
        ("Date", when.isoformat()),
        ("Tool version", __version__),
        ("Delivery root", str(batch.delivery_root) if batch.delivery_root else ""),
        ("Turnovers", len(batch.turnovers)),
        ("Rows", len(batch.rows)),
        ("Rows delivered", sum(1 for row in batch.rows if _row_state(row) == "delivered")),
        ("Rows skipped", sum(1 for row in batch.rows if _row_state(row) == "skipped")),
        ("Rows failed", sum(1 for row in batch.rows if _row_state(row) == "failed")),
        ("Deliverables", sum(len(row.deliverables) for row in batch.rows)),
        ("Errors", counts["error"]),
        ("Warnings", counts["warning"]),
        ("Info", counts["info"]),
    ):
        sheet.append([label, value])
    sheet.column_dimensions["B"].width = 60


def _every_result(batch: Batch) -> list[list[QCResult]]:
    results = [batch.qc] + [turnover.qc for turnover in batch.turnovers]
    for row in batch.rows:
        results.append(row.qc)
        results.extend(item.qc for item in row.deliverables)
    return results


def _row_state(row: ShotRow) -> str:
    """`skipped`, `failed` or `delivered`, which is what the Summary counts.

    A row with nothing planned counts as delivered rather than failed: the planner had
    nothing to do for it, which is a different thing from a render that did not finish.
    """
    if row.skipped:
        return "skipped"
    if row.errors() or any(item.status == "failed" for item in row.deliverables):
        return "failed"
    return "delivered"


def _write_shots(book: Workbook, batch: Batch) -> None:
    sheet = _sheet(book, "Shots", SHOTS_HEADERS)
    for row in batch.rows:
        media = row.media
        snapshot, current = row.snapshot, row.current
        sheet.append(
            [
                row.turnover_id,
                row.clip_name,
                row.shot_code or "",
                row.identity.elem if row.identity else "",
                str(media.path) if media else "",
                media.rate.as_float() if media else "",
                f"{media.width}x{media.height}" if media else "",
                snapshot.in_frame if snapshot else "",
                snapshot.out_frame if snapshot else "",
                _timecode(row, snapshot.in_frame if snapshot else None),
                _timecode(row, snapshot.out_frame if snapshot else None),
                current.in_frame if current else "",
                current.out_frame if current else "",
                row.duration or "",
                row.max_available_out or "",
                str(row.audio_path) if row.audio_path else "",
                "yes" if row.was_edited else "",
                row.source_encoding or "",
                row.skip_reason or "",
                _rule_ids(row.qc, "warning"),
                _rule_ids(row.qc, "error"),
            ]
        )


def _write_deliverables(book: Workbook, batch: Batch) -> None:
    """One row per deliverable, then one column per rule reading PASS, FAIL or NA."""
    sheet = _sheet(book, "Deliverables", DELIVERABLE_HEADERS + qc.DELIVERABLE_RULES)
    for row in batch.rows:
        for item in row.deliverables:
            sheet.append(
                [
                    row.shot_code or "",
                    row.identity.elem if row.identity else "",
                    item.kind,
                    item.res or "",
                    item.version,
                    str(item.path),
                    item.frame_count,
                    item.size,
                    _checksum(item),
                    *(qc.deliverable_rule_state(item, rule) for rule in qc.DELIVERABLE_RULES),
                ]
            )


def _checksum(item: Deliverable) -> str:
    """The whole-file digest, or the ends of a sequence, which is what QC-106 holds.

    A 240 frame sequence has 240 of them and a spreadsheet cell is not where they go;
    the first and the last identify the render, and the batch file keeps them all.
    """
    if item.checksum:
        return item.checksum
    if not item.frame_checksums:
        return ""
    first, last = item.frame_checksums[0], item.frame_checksums[-1]
    return first if len(item.frame_checksums) == 1 else f"{first} .. {last}"


def write_qc_log(batch: Batch, path: Path, when: date | None = None) -> Path:
    """Write the QC log. Creates the folder; overwrites an existing file.

    Three sheets since 2026-09-22, not five: Side Files and Camera Data went with the
    deliverables they described.
    """
    book = Workbook()
    book.remove(book.active)
    _write_summary(book, batch, when or date.today())
    _write_shots(book, batch)
    _write_deliverables(book, batch)
    return _save(book, path)


# --- The tracker: the studio's columns, rows to paste --------------------------------

TRACKER_HEADERS = (
    "", "Shot#", "Shot Code (ABCD123)", "Publish Folder", "Plate Video", "HDRI",
    "CAM Data", "PLATES", "FPS", "Shot Audio?", "Plate Thumbnail", "Effect Category",
    "Storyboard Thumbnail", "Pod Point of Contact", "Audio", "Cam Status", "Owner",
    "Layout Status", "Owner", "cam Callouts / Tracktest Mov", "Difficulty",
    "MM Status", "Owner", "MM Callouts / Tracktest Mov", "Difficulty", "Beeble",
    "Roto Status", "Owner", "Roto Callouts / RotoQC Mov", "Difficulty",
    "CP Status", "Owner", "CP Callouts / CPQC MOV", "Diff",
    "Turnover Stringout (Edit)", "CAM REQUESTER", "MM REQUESTER", "ROTO REQUESTER",
    "CP REQUESTER",
)  # fmt: skip
"""The studio tracker's own header row, verbatim, duplicate `Owner` columns included.

Verbatim because the sheet this pastes into has these headings and a reader compares
them by eye. `Shot Code (ABCD123)` says three digits and the real codes have four;
that is the sheet's wording and not a rule, and `naming.py` reads four.
"""

TOOL_OWNED_COLUMNS = (2, 3, 4, 5, 6, 7, 8, 9, 34)
"""Which indices of `TRACKER_HEADERS` the tool fills. Everything else stays empty."""


TRACKER_FPS = "24"
"""Every deliverable is written at 24, frame for frame (user, 2026-09-23), whatever the
source file states, so that is the rate the tracker records."""

_MISSING = "\u2014"
"""The sheet's own mark for a plate that is not there: `4K \u2014`. Written as an escape
so the source carries no em dash; the studio's cells do."""

_TICK = "✓"
"""The sheet's mark for a plate or a sound that is there."""

_LANDED = ("done", "exists")
"""A deliverable that is on disk and passed: written this run, or already complete."""


def _landed(row: ShotRow) -> bool:
    """Whether this row delivered everything it planned.

    Skipped, blocked, failed and cancelled rows did not, and a tracker line for any of
    them would add a shot to the production's sheet that is not in the delivery.
    """
    if row.skipped or row.errors() or not row.deliverables:
        return False
    return all(item.status in _LANDED for item in row.deliverables)


def _delivered(row: ShotRow, kind: str, res: str | None = None) -> Deliverable | None:
    """The landed deliverable of one kind, or None."""
    for item in row.deliverables:
        if item.kind == kind and (res is None or item.res == res) and item.status in _LANDED:
            return item
    return None


def _plate_marks(row: ShotRow | None) -> str:
    """`4K ✓` and `HD ✓` on two lines, the way the tracker's own cells are written."""
    return "\n".join(
        f"{label} {_TICK if row is not None and _delivered(row, 'raw_dir', res) else _MISSING}"
        for label, res in (("4K", "4k"), ("HD", "HD"))
    )


def _main_plate(rows: list[ShotRow]) -> ShotRow | None:
    """The shot's `pl` row with the lowest index, which is what the tracker describes.

    The sheet has one Plate Video and one pair of plate marks per shot, and every real
    value in it is a `pl01`. A clean plate, an element or a still has no column.
    """
    plates = [row for row in rows if row.identity is not None and row.identity.kind == "pl"]
    return min(plates, key=lambda row: row.identity.index if row.identity else "", default=None)


def tracker_row(shot_code: str, rows: list[ShotRow]) -> list[str]:
    """One shot code as the studio's 39 columns, with the thirty that are not ours empty.

    **One line per shot code** (user, 2026-09-23), as the studio's own sheet has always
    been: a shot's `pl01`, `cp01` and reference stills are one line, described by its
    main plate. `rows` are the shot's rows that landed.

    The stringout column is left empty because Ben produces and exports that file and
    the tool does nothing with it at all (user, 2026-09-22, closing OQ-41).
    """
    plate = _main_plate(rows)
    reference = _delivered(plate, "ref_mp4", "HD") if plate is not None else None
    audio = _delivered(plate, "audio") if plate is not None else None
    cells = [""] * len(TRACKER_HEADERS)
    cells[0] = "FALSE"
    cells[2] = shot_code
    cells[3] = shot_code
    cells[4] = reference.name if reference is not None else ""
    # HDRI and CAM Data stay the studio's columns and stay empty: neither carries a
    # `Shot Type`, so neither is a deliverable of this tool any more (2026-09-22).
    cells[7] = _plate_marks(plate)
    cells[8] = TRACKER_FPS
    cells[9] = _TICK if audio is not None else ""
    return cells


def tracker_rows(batch: Batch) -> list[list[str]]:
    """One line per shot code that delivered anything, in the order the batch lists them."""
    shots: dict[str, list[ShotRow]] = {}
    for row in batch.rows:
        if row.shot_code and _landed(row):
            shots.setdefault(row.shot_code, []).append(row)
    return [tracker_row(code, rows) for code, rows in shots.items()]


def write_shot_tracker(batch: Batch, path: Path) -> Path:
    """Write the rows to paste into the studio tracker, one per shot code that landed."""
    book = Workbook()
    book.remove(book.active)
    sheet = _sheet(book, "Shots", TRACKER_HEADERS)
    plates_column = TRACKER_HEADERS.index("PLATES") + 1
    for cells in tracker_rows(batch):
        sheet.append(cells)
        # The plate marks are two lines in one cell, as they are in the real sheet.
        sheet.cell(row=sheet.max_row, column=plates_column).alignment = Alignment(
            wrap_text=True, vertical="top"
        )
    return _save(book, path)


def _save(book: Workbook, path: Path) -> Path:
    """Atomic, like every deliverable: a crash mid-save must not leave a finished-looking file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".part")
    book.save(temp)
    temp.replace(path)
    return path
