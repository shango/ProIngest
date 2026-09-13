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
from proingest.core import camdata, frames, naming, qc
from proingest.core.models import Batch, Deliverable, QCResult, ShotRow

DATE_STAMP = "%Y%m%d"
"""NAMING_SPEC section 5 writes `<date>` in the report names and does not say what it
is. It is this, because a report that sorts by name sorts by date."""

_HEADER_FONT = Font(bold=True)
_SIDE_FILE_KINDS = ("hdri", "camdata", "bts")


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
    return Counter(
        result.severity for results in _every_result(batch) for result in results
    )


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
    "Source encoding", "CLF",
    "Skip reason", "Warnings", "Errors",
)  # fmt: skip
"""The QC log's own columns, QC_RULES "QC log structure".

The CLF column names the grade the row was rendered through, and it is the filename
rather than the path: the session's folder is the same for every row, and the name is
what a reader compares against `proingest/clf` in a delivered EXR header. Empty means
the row rendered ungraded, which is QC-009 once the rules are wired.

Source encoding sits beside it because the two together are the whole of the colour
chain a row was rendered through. It is **what the clip's metadata named, verbatim**,
rather than the colour space that resolved to: this column is read when QC-046 or
QC-047 fires, and what has to be corrected is the string somebody typed. Empty means
the clip named none. Where the name came from is in the delivered EXR header rather
than here (`exr.SOURCE_ENCODING_ORIGIN_ATTRIBUTE`)."""

DELIVERABLE_HEADERS = (
    "Shot code", "Elem", "Kind", "Res", "Version", "Path", "Frames", "Size", "Checksum",
)  # fmt: skip

SIDE_FILE_HEADERS = ("Shot code", "Type", "Source", "Delivered", "Checksum")
CAMERA_DATA_HEADERS = ("Shot code", "Key", "Value")


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
        sheet.append([
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
            row.clf_path.name if row.clf_path else "",
            row.skip_reason or "",
            _rule_ids(row.qc, "warning"),
            _rule_ids(row.qc, "error"),
        ])


def _write_deliverables(book: Workbook, batch: Batch) -> None:
    """One row per deliverable, then one column per rule reading PASS, FAIL or NA."""
    sheet = _sheet(book, "Deliverables", DELIVERABLE_HEADERS + qc.DELIVERABLE_RULES)
    for row in batch.rows:
        for item in row.deliverables:
            sheet.append([
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
            ])


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


def _write_side_files(book: Workbook, batch: Batch) -> None:
    sheet = _sheet(book, "Side Files", SIDE_FILE_HEADERS)
    for row in batch.rows:
        sources = {"hdri": row.side_files.hdri, "camdata": row.side_files.camdata}
        for item in row.deliverables:
            if item.kind not in _SIDE_FILE_KINDS:
                continue
            source = sources.get(item.kind)
            sheet.append([
                row.shot_code or "",
                item.kind,
                str(source) if source else "",
                str(item.path),
                item.checksum or "",
            ])


def _write_camera_data(book: Workbook, batch: Batch) -> None:
    """Every pair out of every camData file (OQ-11, QC-053).

    Unreadable files are left out rather than reported here: QC-053 already said so on
    the row, and a sheet of key/value pairs is no place for an error message.
    """
    sheet = _sheet(book, "Camera Data", CAMERA_DATA_HEADERS)
    for row in batch.rows:
        path = row.side_files.camdata
        if path is None:
            continue
        try:
            pairs = camdata.parse(path)
        except (OSError, UnicodeDecodeError):
            continue
        for key, value in pairs.items():
            sheet.append([row.shot_code or "", key, value])


def write_qc_log(batch: Batch, path: Path, when: date | None = None) -> Path:
    """Write the five sheet QC log. Creates the folder; overwrites an existing file."""
    book = Workbook()
    book.remove(book.active)
    _write_summary(book, batch, when or date.today())
    _write_shots(book, batch)
    _write_deliverables(book, batch)
    _write_side_files(book, batch)
    _write_camera_data(book, batch)
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


def _tracker_fps(row: ShotRow) -> str:
    """The rate as the tracker's own column writes it: `24`, or `23.976`.

    Not `FrameRate.__str__`, which is the exact fraction `24000/1001`. That is the
    right thing for a log and the wrong thing for a cell in a sheet whose other 778
    rows say `23.976`.
    """
    if row.media is None:
        return ""
    rate = row.media.rate
    return str(rate.numerator) if rate.denominator == 1 else f"{rate.as_float():.3f}"


def _plate_marks(row: ShotRow) -> str:
    """`4K ✓` and `HD ✓` on two lines, the way the tracker's own cells are written."""
    delivered = {
        item.res for item in row.deliverables if item.kind == "raw_dir" and item.status != "failed"
    }
    return "\n".join(
        f"{label} {'✓' if res in delivered else '—'}" for label, res in (("4K", "4k"), ("HD", "HD"))
    )


def _named(row: ShotRow, kind: str, res: str | None = None) -> str:
    """The delivered filename for one kind, or empty when the row has none."""
    for item in row.deliverables:
        if item.kind == kind and (res is None or item.res == res) and item.status != "failed":
            return item.name
    return ""


def tracker_row(row: ShotRow) -> list[str]:
    """One shot as the studio's 39 columns, with the thirty that are not ours empty.

    The stringout column is one of ours and is left empty on purpose: the tool no
    longer writes that file (PRD FR-9) and the grammar it would rebuild the name from
    matches none of the 55 real ones in the tracker (OQ-41). A blank cell is the
    honest answer until that is settled, and it is one line to fill in afterwards.
    """
    cells = [""] * len(TRACKER_HEADERS)
    cells[0] = "FALSE"
    cells[2] = row.shot_code or ""
    cells[3] = row.shot_code or ""
    cells[4] = _named(row, "ref_mp4", "HD")
    cells[5] = _named(row, "hdri")
    cells[6] = _named(row, "camdata")
    cells[7] = _plate_marks(row)
    cells[8] = _tracker_fps(row)
    cells[9] = "✓" if row.audio_path else ""
    return cells


def write_shot_tracker(batch: Batch, path: Path) -> Path:
    """Write the rows to paste into the studio tracker. Skipped rows are left out.

    A skipped row delivered nothing, so pasting one would add a shot to the production's
    tracker that does not exist in the delivery.
    """
    book = Workbook()
    book.remove(book.active)
    sheet = _sheet(book, "Shots", TRACKER_HEADERS)
    plates_column = TRACKER_HEADERS.index("PLATES") + 1
    for row in batch.rows:
        if not row.skipped:
            sheet.append(tracker_row(row))
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
