"""Turning a turnover folder into shot rows.

**One folder, one phase** (OQ-74, settled 2026-09-22). Ben hands over the media, his
EDL and his metadata CSV together, and there is nothing to scan before he does. So this
reads three things and nothing else: the folder for media, the CSV for **who each clip
is and what it is encoded as**, and the EDL for **the approved cut and the CDL**.

**Rows come from CSV rows, not from timeline clips.** `Shot Type` is the whole of the
tool's scope: a clip that carries one becomes a row, and a clip that carries none is
**ignored** and counted by QC-064 at turnover scope. That rule is why QC-064 exists - a
turnover whose metadata was never filled in would otherwise deliver nothing and say
nothing.

Only the QC results that are *discovered while scanning* are raised here, meaning the
ones that cannot be recomputed from the saved model later: media that could not be
found, matched ambiguously or failed to probe. Rules that are pure functions of the
model, such as duration limits, resolution and fps, belong to the rule registry so they
can re-run after every edit.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from pathlib import Path

from proingest.core import ale, clf, ffmpeg, metacsv, naming, qc
from proingest.core import media as media_module
from proingest.core.models import (
    Batch,
    FrameRate,
    InOut,
    MediaInfo,
    QCResult,
    ShotRow,
    Turnover,
)

EDL_SUFFIX = ".edl"

TURNOVER_FOLDER_PATTERN = re.compile(
    r"^turnover(?P<number>\d{3})_(?P<month>\d{2})_(?P<day>\d{2})_(?P<year>\d{4})_(?P<shooter>.+)$"
)


@dataclass
class ScanSettings:
    """Settings the scan needs. Defaults match docs/OPEN_QUESTIONS.md."""

    show_pattern: str = naming.DEFAULT_SHOW_PATTERN
    path_map: dict[str, str] = field(default_factory=dict)
    project_rate: FrameRate = field(default_factory=lambda: FrameRate(24))
    rules: qc.RuleSettings = field(default_factory=qc.RuleSettings)
    """Thresholds the rule registry compares against, so the scan's first pass of QC
    matches what the Settings page will later re-run with."""


@dataclass(frozen=True)
class TurnoverFields:
    """What the folder name says a turnover is, read off it."""

    number: int
    month: int
    day: int
    year: int
    shooter: str


def parse_turnover_folder(folder: Path) -> TurnoverFields | None:
    """Prefill turnover number, date and shooter from the folder name.

    Returns None when the name does not match, which is QC-005 and means the editor
    types the fields by hand.
    """
    match = TURNOVER_FOLDER_PATTERN.match(folder.name)
    if match is None:
        return None
    return TurnoverFields(
        number=int(match["number"]),
        month=int(match["month"]),
        day=int(match["day"]),
        year=int(match["year"]),
        shooter=match["shooter"],
    )


def scan_turnover(
    folder: Path,
    turnover_id: str,
    settings: ScanSettings | None = None,
    probe_cache: dict[str, MediaInfo] | None = None,
) -> tuple[Turnover, list[ShotRow]]:
    """Scan one turnover folder into a Turnover and its rows.

    Never raises for a bad turnover: a folder missing either handover file, or carrying
    one that will not parse, comes back as a Turnover with QC-001 or QC-002 and no rows,
    so one bad folder cannot take down a batch.
    """
    settings = settings or ScanSettings()
    cache = probe_cache if probe_cache is not None else {}

    turnover = Turnover(turnover_id=turnover_id, folder=folder)
    _prefill(turnover, folder)

    handover = _handover_files(folder, turnover)
    if handover is None:
        return turnover, []
    edl_path, csv_path = handover
    turnover.edl_path, turnover.csv_path = edl_path, csv_path
    turnover.edl_digest, turnover.csv_digest = qc.file_digest(edl_path), qc.file_digest(csv_path)

    try:
        meta = metacsv.read(csv_path, settings.show_pattern)
    except metacsv.MetaCsvError as exc:
        turnover.qc.append(QCResult("QC-002", "error", "turnover", f"{csv_path.name}: {exc}"))
        return turnover, []

    try:
        session = clf.load_session(edl_path, settings.project_rate, settings.show_pattern)
    except clf.ColorSessionError as exc:
        turnover.qc.append(QCResult("QC-002", "error", "turnover", f"{edl_path.name}: {exc}"))
        return turnover, []

    # The EDL is read here rather than ingested later: OQ-74 collapsed the two-phase
    # flow, so there is one moment at which the folder is in front of the tool.
    turnover.color_session_edl = edl_path
    turnover.qc.extend(_ignored_clips(meta.ignored))

    if not meta.rows:
        turnover.qc.append(
            QCResult(
                "QC-004",
                "error",
                "turnover",
                f"{csv_path.name} describes no clip carrying a Shot Type, so there is nothing to deliver",
            )
        )
        return turnover, []
    if not session.events:
        turnover.qc.append(
            QCResult("QC-004", "error", "turnover", f"{edl_path.name} carries no video events")
        )

    session = replace(session, events=_named_events(folder, session.events, turnover))
    index = media_module.index_directory(folder)
    rows = [_build_row(entry, index, turnover_id, settings, cache) for entry in meta.rows]
    turnover.qc.extend(_conform_all(rows, session))
    _refuse_retimes(rows, session.events, settings.project_rate)
    rows = _collapse(rows)
    for row in rows:
        # Only the plate has an associated audio clip (user, 2026-09-23).
        if qc.is_plate(row):
            _attach_audio(row, index, settings)
        qc.apply_row_rules(row, settings.project_rate, settings.rules)
    return turnover, rows


def _prefill(turnover: Turnover, folder: Path) -> None:
    """Number, date and shooter off the folder name, or QC-005 asking for them by hand."""
    prefill = parse_turnover_folder(folder)
    if prefill is None:
        turnover.qc.append(
            QCResult(
                "QC-005",
                "info",
                "turnover",
                f"folder name {folder.name!r} does not match turnover###_MM_DD_YYYY_name; "
                f"number, date and shooter need manual entry",
            )
        )
        return
    turnover.number = prefill.number
    turnover.month = prefill.month
    turnover.day = prefill.day
    turnover.year = prefill.year
    turnover.shooter = prefill.shooter


def _handover_files(folder: Path, turnover: Turnover) -> tuple[Path, Path] | None:
    """Ben's EDL and his metadata CSV, or QC-001 saying which is missing.

    **Exactly one of each, directly in the folder.** Two EDLs is not something to choose
    between: choosing between two cuts is choosing a cut, and the same argument covers
    two CSVs. Not recursive, because the handover is one folder (OQ-74) and a recursive
    search would find a colourist's working copy in a subfolder as readily as the export.
    """
    # By suffix in any case: `.EDL` is as much Ben's export as `.edl` (F27).
    edls = sorted(p for p in folder.iterdir() if p.is_file() and p.suffix.lower() == EDL_SUFFIX)
    csvs = metacsv.find(folder)

    missing = [name for name, found in (("Ben's EDL", edls), ("his metadata CSV", csvs)) if not found]
    if missing:
        turnover.qc.append(
            QCResult("QC-001", "error", "turnover", f"{' and '.join(missing)} is missing from {folder}")
        )
        return None

    for label, found in (("EDL", edls), ("metadata CSV", csvs)):
        if len(found) > 1:
            names = ", ".join(path.name for path in found)
            turnover.qc.append(
                QCResult(
                    "QC-001",
                    "error",
                    "turnover",
                    f"{folder} holds {len(found)} {label} files ({names}); one handover is one of each, "
                    f"and choosing between them would be choosing a cut",
                )
            )
            return None
    return edls[0], csvs[0]


def _ignored_clips(ignored: list[str]) -> list[QCResult]:
    """QC-064: the clips with no `Shot Type`, which are not delivered and are not errors.

    The counterweight to the rule that created it. Ignoring such a clip is the intended
    behaviour; a whole turnover ignored is what wants saying out loud.
    """
    if not ignored:
        return []
    return [
        QCResult(
            "QC-064",
            "warning",
            "turnover",
            f"{len(ignored)} clips carry no Shot Type and were ignored: {', '.join(sorted(ignored))}",
        )
    ]


def _build_row(
    entry: metacsv.MetaRow,
    index: media_module.DirectoryIndex,
    turnover_id: str,
    settings: ScanSettings,
    cache: dict[str, MediaInfo],
) -> ShotRow:
    """One CSV row into one shot row: identity, media and encoding. The EDL comes after,
    across every row at once (`_conform_all`), because a match is only unambiguous when no
    other row claims the same event."""
    row = ShotRow(turnover_id=turnover_id, clip_name=entry.file_name)
    row.qc.extend(entry.qc)
    if entry.kind is not None and entry.index is not None and not row.errors():
        row.identity = naming.ShotIdentity(shot_code=entry.shot, kind=entry.kind, index=entry.index)

    item = _resolve_media(entry.file_name, index, row)
    if item is not None:
        _probe_into(row, item, cache, settings.project_rate)

    # Verbatim, because what QC-047 has to be able to quote back is the string somebody
    # typed. The CSV is the only carrier: the delivered container declares nothing.
    row.source_encoding = entry.written_encoding or None
    row.source_encoding_origin = "clip metadata" if row.source_encoding else None
    return row


def _named_events(folder: Path, events: list[clf.ConformEvent], turnover: Turnover) -> list[clf.ConformEvent]:
    """Name each EDL event from the ALE beside it, row for row (`core/ale.py`).

    Only when the EDL names none of its events itself and the folder holds one ALE. An ALE
    that cannot be paired with the EDL is QC-071 and names nothing, so the scan falls back
    to timecode, which refuses what it cannot tell apart rather than guessing.
    """
    if all(event.clip_name for event in events):
        return events
    found = ale.find(folder)
    if not found:
        return events
    if len(found) > 1:
        listed = ", ".join(path.name for path in found)
        turnover.qc.append(
            QCResult("QC-071", "error", "turnover", f"{folder} holds {len(found)} ALEs ({listed})")
        )
        return events
    try:
        names = ale.read_names(found[0])
    except ale.AleError as exc:
        turnover.qc.append(QCResult("QC-071", "error", "turnover", str(exc)))
        return events
    if len(names) != len(events):
        turnover.qc.append(
            QCResult(
                "QC-071",
                "error",
                "turnover",
                f"{found[0].name} lists {len(names)} clips and the EDL cuts {len(events)} events, "
                f"so its rows cannot name the events",
            )
        )
        return events
    turnover.ale_path = found[0]
    return [
        event if event.clip_name else event.named(name) for event, name in zip(events, names, strict=True)
    ]


def _conform_all(rows: list[ShotRow], session: clf.ColorSession) -> list[QCResult]:
    """Pair every row with its EDL event, and return what the turnover should hear.

    A row with no event (QC-066) or with a match that could go two ways (QC-067) gets
    neither a cut nor a grade and cannot render. Nothing here reaches for the nearest
    event or picks one of two: a neighbour's cut and a neighbour's grade both look
    entirely plausible. Such a row still gets the whole media as its range, so the
    editor can see what arrived. An event no row claims is QC-068, for the record.
    """
    if session.events and all(event.clip_name for event in session.events):
        return _conform_by_use(rows, session.events)
    found = [session.candidates(row) for row in rows]
    claims: dict[int, list[str]] = {}
    for row, events in zip(rows, found, strict=True):
        for event in events:
            claims.setdefault(id(event), []).append(row.clip_name)

    for row, events in zip(rows, found, strict=True):
        if not events:
            row.qc.append(
                QCResult(
                    "QC-066",
                    "error",
                    "row",
                    f"no event in the EDL falls inside {row.clip_name}, "
                    f"so the row has no approved cut and no grade",
                )
            )
            _whole_media(row)
        elif len(events) > 1:
            ids = ", ".join(event.event_id for event in events)
            row.qc.append(
                QCResult(
                    "QC-067",
                    "error",
                    "row",
                    f"EDL events {ids} all fall inside {row.clip_name}; "
                    f"the tool will not choose between them",
                )
            )
            _whole_media(row)
        elif len(claims[id(events[0])]) > 1:
            names = ", ".join(claims[id(events[0])])
            row.qc.append(
                QCResult(
                    "QC-067",
                    "error",
                    "row",
                    f"EDL event {events[0].event_id} falls inside more than one file ({names}); "
                    f"the tool will not choose between them",
                )
            )
            _whole_media(row)
        else:
            _conform(row, events[0])

    unclaimed = [event.event_id for event in session.events if id(event) not in claims]
    if not unclaimed:
        return []
    return [
        QCResult(
            "QC-068",
            "info",
            "turnover",
            f"EDL events {', '.join(unclaimed)} fall inside no file the CSV describes",
        )
    ]


def _conform_by_use(rows: list[ShotRow], events: list[clf.ConformEvent]) -> list[QCResult]:
    """Pair rows with events by name, one CSV row per use of a clip.

    Resolve's CSV carries a row for each **distinct source range** a clip is cut at
    (`ConformEvent.use`), not one per event: a chart cut at frame 212 twice and at 221 once
    is two rows. Verified on all nine rows of Turnover121 (2026-09-23). So a clip's uses, in
    timeline order, pair with its rows in file order, and a count that disagrees is QC-067:
    the tool will not guess which row is which use.
    """
    by_clip: dict[str, list[clf.ConformEvent]] = {}
    for event in events:
        by_clip.setdefault(event.clip_stem.casefold(), []).append(event)
    rows_by_clip: dict[str, list[ShotRow]] = {}
    for row in rows:
        rows_by_clip.setdefault(Path(row.clip_name).stem.casefold(), []).append(row)

    claimed: set[int] = set()
    for key, clip_rows in rows_by_clip.items():
        uses: dict[tuple[int, int], list[clf.ConformEvent]] = {}
        for event in by_clip.get(key, []):
            uses.setdefault(event.use, []).append(event)
            claimed.add(id(event))
        if not uses:
            for row in clip_rows:
                row.qc.append(
                    QCResult(
                        "QC-066",
                        "error",
                        "row",
                        f"no event in the EDL cuts {row.clip_name}, "
                        f"so the row has no approved cut and no grade",
                    )
                )
                _whole_media(row)
        elif len(uses) != len(clip_rows):
            ids = ", ".join(event.event_id for group in uses.values() for event in group)
            for row in clip_rows:
                row.qc.append(
                    QCResult(
                        "QC-067",
                        "error",
                        "row",
                        f"the EDL cuts {row.clip_name} at {len(uses)} different ranges (events {ids}) and "
                        f"the CSV lists it {len(clip_rows)} times; the tool will not pair them by guesswork",
                    )
                )
                _whole_media(row)
        else:
            for row, group in zip(clip_rows, uses.values(), strict=True):
                _conform(row, group[0])
                row.freeze = group[0].freeze

    unclaimed = [event.event_id for event in events if id(event) not in claimed]
    if not unclaimed:
        return []
    return [
        QCResult(
            "QC-068",
            "info",
            "turnover",
            f"EDL events {', '.join(unclaimed)} cut clips the CSV gives no Shot Type or does not list",
        )
    ]


def _refuse_retimes(rows: list[ShotRow], events: list[clf.ConformEvent], rate: FrameRate) -> None:
    """QC-073: a clip the EDL retimes or reverses. Only a freeze is rendered (OQ-63): any
    other speed means the frames shown are not the frames in the range, silently."""
    for event in events:
        if not event.clip_name or not event.retimed(rate):
            continue
        for row in rows:
            if Path(row.clip_name).stem.casefold() == event.clip_stem.casefold():
                row.qc.append(
                    QCResult(
                        "QC-073",
                        "error",
                        "row",
                        f"EDL event {event.event_id} plays {row.clip_name} at {event.speed:g} fps; "
                        f"the tool renders a freeze but not a retime or a reversal",
                    )
                )


def _collapse(rows: list[ShotRow]) -> list[ShotRow]:
    """One row per thing delivered, in timeline order of first use (user, 2026-09-23).

    A reference still (a colour chart, a grey ball) is delivered **once per shot code**,
    from its first use: a chart cut at two frames is the same chart. Any other clip cut
    twice to the same frames, as two holds of one frame are, is delivered once too. The row
    kept says so (QC-072). A row that did not conform is never folded: its error has to show.
    """
    kept: dict[tuple[object, ...], ShotRow] = {}
    result: list[ShotRow] = []
    for row in sorted(rows, key=lambda row: (row.approved is None, row.record_in)):
        key = _delivers(row)
        if key is None or key not in kept:
            if key is not None:
                kept[key] = row
            result.append(row)
            continue
        first = kept[key]
        first.qc.append(
            QCResult(
                "QC-072",
                "info",
                "row",
                f"{row.clip_name} is also cut at {_frames_text(row)}; delivered once, from its first use",
            )
        )
    order = {id(row): index for index, row in enumerate(rows)}
    return sorted(result, key=lambda row: order[id(row)])


def _frames_text(row: ShotRow) -> str:
    if row.current is None:
        return "no range"
    if row.current.in_frame == row.current.out_frame:
        return f"frame {row.current.in_frame}"
    return f"frames {row.current.in_frame}-{row.current.out_frame}"


def _delivers(row: ShotRow) -> tuple[object, ...] | None:
    """What two rows share when they would deliver the same thing, or None to keep it."""
    if row.approved is None or row.identity is None or row.errors():
        return None
    if row.identity.is_still:
        return ("still", row.identity.shot_code, row.identity.kind)
    return ("same", Path(row.clip_name).stem.casefold(), row.identity.kind, row.identity.index, row.current)


def _conform(row: ShotRow, event: clf.ConformEvent) -> None:
    """The approved cut and the CDL off this row's one EDL event."""

    row.record_in, row.record_out = event.record_in, event.record_out
    row.cdl = event.cdl
    approved = clf.approved_in_out(event, row.media) if row.media else None
    if approved is None:
        _whole_media(row)
        return
    row.approved = approved
    row.snapshot = approved
    row.current = approved
    if row.media is not None and (
        approved.in_frame < row.media.start_frame or approved.out_frame > row.media.max_available_out
    ):
        row.qc.append(
            QCResult(
                "QC-029",
                "error",
                "row",
                f"the EDL references frames {approved.in_frame}-{approved.out_frame} but the media "
                f"holds {row.media.start_frame}-{row.media.max_available_out}",
            )
        )


def _whole_media(row: ShotRow) -> None:
    """Every frame there is, for a row the EDL said nothing usable about."""
    if row.media is None:
        return
    chosen = InOut(row.media.start_frame, row.media.max_available_out)
    row.snapshot = chosen
    row.current = chosen


def _resolve_media(
    file_name: str, index: media_module.DirectoryIndex, row: ShotRow
) -> media_module.Sequence | media_module.FileEntry | None:
    """The media the CSV's `File Name` names, found in the turnover folder.

    **By name, and only by name.** The CSV's `Clip Directory` points at the
    pre-consolidation originals in the real sample, so a path out of it would resolve to
    a file on somebody else's drive or to nothing at all; `File Name` is the one field in
    that file measured to still match what was delivered.
    """
    matches = index.media_matching(Path(file_name).stem)
    if not matches:
        row.qc.append(
            QCResult(
                "QC-012",
                "error",
                "row",
                f"the CSV names {file_name!r} and no file in the turnover folder matches it",
            )
        )
        return None
    if len(matches) > 1:
        described = ", ".join(sorted(_describe(match) for match in matches))
        row.qc.append(QCResult("QC-013", "error", "row", f"media ambiguous for {file_name!r}: {described}"))
        return None
    return matches[0]


def _describe(item: media_module.Sequence | media_module.FileEntry) -> str:
    if isinstance(item, media_module.Sequence):
        return f"{item.first_path} ({item.count} frames)"
    return str(item.path)


def _probe_into(
    row: ShotRow,
    item: media_module.Sequence | media_module.FileEntry,
    cache: dict[str, MediaInfo],
    timeline_rate: FrameRate,
) -> None:
    """Probe and attach, turning a probe failure into QC-014 instead of an exception."""
    try:
        row.media = media_module.probe_cached(item, cache, fallback_rate=timeline_rate)
    except (ffmpeg.FFprobeError, ffmpeg.FFmpegNotFound) as exc:
        row.qc.append(QCResult("QC-014", "error", "row", f"media unreadable: {exc}"))
        return

    if isinstance(item, media_module.Sequence) and item.has_gaps:
        missing = item.missing_frames
        shown = ", ".join(str(n) for n in missing[:5])
        more = f" and {len(missing) - 5} more" if len(missing) > 5 else ""
        row.qc.append(QCResult("QC-015", "warning", "row", f"sequence has missing frames: {shown}{more}"))


def _attach_audio(row: ShotRow, index: media_module.DirectoryIndex, settings: ScanSettings) -> None:
    """The audio beside this clip, found by name.

    An EDL cannot associate audio and there is no other timeline, so a same-name search
    is the whole mechanism rather than a fallback (FR-1). Counting rules (QC-040,
    QC-041) are left to the rule registry; this only records what was found.
    """
    by_name = index.audio_matching(Path(row.clip_name).stem)
    row.audio_clip_count = len(by_name)
    if len(by_name) == 1:
        row.audio_path = media_module.remap(by_name[0].path, settings.path_map)

    if row.audio_path is None or not row.audio_path.is_file():
        return
    try:
        row.audio = media_module.probe_audio(row.audio_path)
    except (ffmpeg.FFprobeError, ffmpeg.FFmpegNotFound) as exc:
        row.qc.append(QCResult("QC-042", "error", "row", f"audio unreadable: {exc}"))


TURNOVER_ID_PATTERN = re.compile(r"t(\d+)")


def next_turnover_id(batch: Batch) -> str:
    """`t1`, `t2`, and so on: the id the next turnover added to this batch takes.

    **Counted past the highest in use rather than off how many there are**, because a
    row points at its turnover by id: removing the second of three turnovers and then
    adding one must not hand the new one an id the rows of the old one still carry.

    One authority for both ways a turnover is numbered - `scan_batch` below, and Add
    Turnover in the window - so a batch built by the CLI and one built by hand cannot
    end up numbered differently. An id that is not `t` and a number is left out of the
    count rather than refused: nothing writes one, and a hand edited batch file that
    carries one still has to be able to take another turnover.
    """
    numbered = [TURNOVER_ID_PATTERN.fullmatch(t.turnover_id) for t in batch.turnovers]
    highest = max((int(match.group(1)) for match in numbered if match), default=0)
    return f"t{highest + 1}"


def scan_batch(
    folders: list[Path],
    name: str = "untitled",
    settings: ScanSettings | None = None,
) -> Batch:
    """Scan several turnover folders into one batch, sharing the probe cache."""
    settings = settings or ScanSettings()
    batch = Batch(name=name, project_rate=settings.project_rate)
    for folder in folders:
        turnover, rows = scan_turnover(
            folder, next_turnover_id(batch), settings, probe_cache=batch.probe_cache
        )
        batch.turnovers.append(turnover)
        batch.rows.extend(rows)
    # QC-011 is the one row rule that needs every row, so it can only run once they exist.
    qc.apply_batch_rules(batch, settings.rules)
    return batch


def carry_over(old: Turnover, old_rows: list[ShotRow], new: Turnover, new_rows: list[ShotRow]) -> None:
    """A turnover rescanned, where it was (D8) or from a new folder (D16), keeps what the
    editor did to it.

    Rows are matched by File Name, in CSV order, so a clip used twice (D3) pairs its
    first row with the first and its second with the second. What carries over is the
    editor's: a trim, but only one the editor made, so an EDL that moved the cut is not
    overridden by the cut it replaced; the shot code correction, the skip and its reason,
    the notes, and the delivered state. Everything else is the new scan's.

    A changed EDL or CSV is a warning on the turnover, QC-070: the edits carried over
    were made against the old one.
    """
    waiting: dict[str, list[ShotRow]] = {}
    for row in old_rows:
        waiting.setdefault(row.clip_name.casefold(), []).append(row)
    for row in new_rows:
        matches = waiting.get(row.clip_name.casefold())
        if not matches:
            continue
        before = matches.pop(0)
        if before.was_edited:
            row.current = before.current
        row.shot_code_override = before.shot_code_override
        row.skipped, row.skip_reason = before.skipped, before.skip_reason
        row.notes = before.notes
        row.deliverables = before.deliverables
    changed = [
        name
        for name, was, now in (
            ("EDL", old.edl_digest, new.edl_digest),
            ("CSV", old.csv_digest, new.csv_digest),
        )
        if was and was != now
    ]
    if changed:
        new.qc.append(
            QCResult(
                "QC-070",
                "warning",
                "turnover",
                f"the {' and the '.join(changed)} changed since this batch last scanned "
                f"{old.folder.name}; the trims and skips carried over were made against the old one",
            )
        )
