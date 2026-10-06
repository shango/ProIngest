"""Turning a turnover folder into shot rows.

**One folder, one phase** (OQ-74, settled 2026-09-22). Ben hands over the media, his
EDL, his metadata CSV and one AMF per EDL event together, and there is nothing to scan
before he does. So this reads four things and nothing else: the folder for media, the CSV
for **who each clip is**, the EDL for **the approved cut**, and each event's AMF with its
CLFs for **the colour** (user, 2026-09-28).

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

import hashlib
import re
from dataclasses import dataclass, field, replace
from pathlib import Path

from proingest.core import ale, amf, clf, color, ffmpeg, frames, metacsv, naming, qc
from proingest.core import media as media_module
from proingest.core.models import (
    Batch,
    FrameRate,
    Grade,
    GradeLook,
    InOut,
    MediaInfo,
    QCResult,
    ShotRow,
    Turnover,
)

EDL_SUFFIX = ".edl"

TURNOVER_FOLDER_PATTERN = re.compile(
    r"^turnover(?P<number>\d{3})_(?P<month>\d{2})_(?P<day>\d{2})_(?P<year>\d{2}|\d{4})_(?P<shooter>.+)$"
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
    types the fields by hand. The date is `MM_DD_YY` (user, 2026-10-05), read as 20YY; a
    four digit year, as older folders carry, is still read.
    """
    match = TURNOVER_FOLDER_PATTERN.match(folder.name)
    if match is None:
        return None
    year = int(match["year"])
    return TurnoverFields(
        number=int(match["number"]),
        month=int(match["month"]),
        day=int(match["day"]),
        year=year + 2000 if year < 100 else year,
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
    grades = _Grades.read(folder)
    turnover.qc.extend(grades.qc)
    turnover.qc.extend(_conform_all(rows, session, grades))
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
                f"folder name {folder.name!r} does not match turnover###_MM_DD_YY_name; "
                f"number, date and shooter need manual entry",
            )
        )
        return
    turnover.number = prefill.number
    turnover.month = prefill.month
    turnover.day = prefill.day
    turnover.year = prefill.year
    turnover.shooter = prefill.shooter


def is_turnover_folder(folder: Path) -> bool:
    """Whether a folder holds an EDL and a metadata CSV directly in it.

    What a drop onto the window asks of each thing dropped (user, 2026-09-25): anything
    else is skipped rather than added and left to fail QC-001. Two of either still counts,
    because that folder is a turnover with a problem to report, not something else.
    """
    try:
        entries = [entry for entry in folder.iterdir() if entry.is_file()]
    except OSError:
        return False
    suffixes = {entry.suffix.lower() for entry in entries}
    return EDL_SUFFIX in suffixes and metacsv.CSV_SUFFIX in suffixes


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
    row = ShotRow(turnover_id=turnover_id, clip_name=entry.file_name, resolve_start_tc=entry.start_tc)
    row.qc.extend(entry.qc)
    if entry.kind is not None and entry.index is not None and not row.errors():
        row.identity = naming.ShotIdentity(shot_code=entry.shot, kind=entry.kind, index=entry.index)

    if entry.hdri:
        _resolve_hdri(entry.file_name, index, row, cache, settings.project_rate)
    else:
        item = _resolve_media(entry.file_name, index, row)
        if item is not None:
            _probe_into(row, item, cache, settings.project_rate)

    row.scene = entry.scene
    return row


def _resolve_hdri(
    file_name: str,
    index: media_module.DirectoryIndex,
    row: ShotRow,
    cache: dict[str, MediaInfo],
    timeline_rate: FrameRate,
) -> None:
    """An HDRI's EXR, which is delivered, and its pre-render, which the stringout shows.

    The two share a name and differ by extension (`xxxx_001.exr` and `xxxx_001.mp4`, user
    2026-10-07), so the one stem resolves to both rather than being ambiguous (QC-013).
    """
    matches = index.media_matching(Path(file_name).stem)
    renders = [item for item in matches if _suffix(item) in media_module.VIDEO_EXTENSIONS]
    images = [item for item in matches if item not in renders]
    if len(images) == 1:
        _probe_into(row, images[0], cache, timeline_rate)
    else:
        _resolve_media(file_name, _only(index, images), row)  # says QC-012 or QC-013
    if len(renders) == 1:
        try:
            row.hdri_render = media_module.probe_cached(renders[0], cache, fallback_rate=timeline_rate)
        except (ffmpeg.FFprobeError, ffmpeg.FFmpegNotFound) as exc:
            row.qc.append(QCResult("QC-014", "error", "row", f"media unreadable: {exc}"))
        return
    stem = Path(file_name).stem
    why = "two or more files are" if renders else "no file is"
    row.qc.append(
        QCResult(
            "QC-083",
            "warning",
            "row",
            f"{why} the pre-render of HDRI {file_name} (a video named {stem}, such as {stem}.mp4), "
            "so the stringout shows the HDRI held still",
        )
    )


def _suffix(item: media_module.Sequence | media_module.FileEntry) -> str:
    return item.ext if isinstance(item, media_module.Sequence) else item.suffix


def _only(
    index: media_module.DirectoryIndex, items: list[media_module.Sequence | media_module.FileEntry]
) -> media_module.DirectoryIndex:
    """The index narrowed to `items`, so `_resolve_media` reports them as it would any clip."""
    singles = [item for item in items if isinstance(item, media_module.FileEntry)]
    sequences = [item for item in items if isinstance(item, media_module.Sequence)]
    return media_module.DirectoryIndex(root=index.root, sequences=sequences, singles=singles)


def read_session(
    turnover: Turnover, rate: FrameRate, show_pattern: str = naming.DEFAULT_SHOW_PATTERN
) -> clf.ColorSession:
    """The turnover's final EDL with its events named as the scan named them.

    For the stringout, which needs every event rather than every row. What the ALE said
    was already reported at scan, so its findings go nowhere here.
    """
    if turnover.edl_path is None:
        raise clf.ColorSessionError(f"{turnover.folder.name} has no EDL")
    session = clf.load_session(turnover.edl_path, rate, show_pattern)
    scratch = Turnover(turnover_id=turnover.turnover_id, folder=turnover.folder)
    return replace(session, events=_named_events(turnover.folder, session.events, scratch))


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


def _conform_all(rows: list[ShotRow], session: clf.ColorSession, grades: _Grades) -> list[QCResult]:
    """Pair every row with its EDL event, and return what the turnover should hear.

    A row with no event (QC-066) or with a match that could go two ways (QC-067) gets
    neither a cut nor a grade and cannot render. Nothing here reaches for the nearest
    event or picks one of two: a neighbour's cut and a neighbour's grade both look
    entirely plausible. Such a row still gets the whole media as its range, so the
    editor can see what arrived. An event no row claims is QC-068, for the record.
    """
    if session.events and all(event.clip_name for event in session.events):
        return _conform_by_use(rows, session.events, grades)
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
            _conform(row, events[0], grades)

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


def _conform_by_use(rows: list[ShotRow], events: list[clf.ConformEvent], grades: _Grades) -> list[QCResult]:
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
                _conform(row, group[0], grades)
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


def _conform(row: ShotRow, event: clf.ConformEvent, grades: _Grades) -> None:
    """The approved cut off this row's one EDL event, and the colour off that event's AMF."""

    row.record_in, row.record_out = event.record_in, event.record_out
    # A file that is not there (QC-012) has its AMF checked once it is.
    if row.media is not None:
        before = len(row.qc)
        grades.attach(row, event)
        if qc.is_hdri(row):
            # Its grade colours the pre-render on the stringout; no check runs on an HDRI
            # (user, 2026-10-07), so what is wrong with its AMF goes unsaid.
            del row.qc[before:]
    approved = clf.approved_in_out(event, row.media) if row.media else None
    if approved is None:
        _whole_media(row)
        return
    media = row.media
    if media is not None and not qc.is_hdri(row) and not _fits(approved, media):
        approved = _outside(row, event, media, approved)
    row.approved = approved
    row.snapshot = approved
    row.current = approved


def _fits(cut: InOut, media: MediaInfo) -> bool:
    return media.start_frame <= cut.in_frame and cut.out_frame <= media.max_available_out


def _outside(row: ShotRow, event: clf.ConformEvent, media: MediaInfo, cut: InOut) -> InOut:
    """A cut the file's own timecode puts outside it. Read by Resolve's clock instead, the
    CSV's `Start TC`, when that puts it inside: Resolve's media management can leave a file
    whose timecode is not the one Resolve shows for it (turnover134's mirror balls), and
    the EDL counts from Resolve's (QC-084, a warning, user 2026-10-07). Otherwise QC-029."""
    rate = (media.stated_rate or media.rate).as_float()
    said = media.start_timecode or 0
    own, edl = _span(said, media.frame_count, rate), _span(event.source_in, event.duration, rate)
    resolve = _resolve_start(row, rate)
    if resolve is not None and resolve != said:
        moved = clf.approved_in_out(event, replace(media, start_timecode=resolve))
        if moved is not None and _fits(moved, media):
            row.qc.append(
                QCResult(
                    "QC-084",
                    "warning",
                    "row",
                    f"the EDL cuts {edl}; {row.clip_name}'s own timecode runs {own}, but Resolve starts "
                    f"it at {row.resolve_start_tc} (the CSV's Start TC), so the cut is read by Resolve's",
                )
            )
            return moved
    row.qc.append(QCResult("QC-029", "error", "row", f"the EDL cuts {edl}, but {row.clip_name} runs {own}"))
    return cut


def _span(first: int, count: int, rate: float) -> str:
    """`15:13:40:00 to 15:13:40:09`: frames as Resolve shows them, never as a file index."""
    return f"{frames.frames_to_timecode(first, rate)} to {frames.frames_to_timecode(first + count - 1, rate)}"


def _resolve_start(row: ShotRow, rate: float) -> int | None:
    try:
        return frames.timecode_to_frames(row.resolve_start_tc, rate) if row.resolve_start_tc else None
    except ValueError:
        return None


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


def next_turnover_ids(batch: Batch, count: int) -> list[str]:
    """The ids the next `count` turnovers take, for several added at once before any is scanned."""
    first = int(next_turnover_id(batch)[1:])
    return [f"t{first + offset}" for offset in range(count)]


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
    the notes, the delivered state, and the mark Re-scan puts on a row for the next Run,
    since that mark is set just before this rescan (user, 2026-09-25). The turnover keeps its stringout
    and its Accept As Is (QC-074, user 2026-09-28). Everything else is the new scan's.

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
        row.delivered_range = before.delivered_range
        row.rerun = before.rerun
    new.stringout = old.stringout
    qc.set_qc_bypassed(new, old.qc_bypassed)
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


@dataclass
class _Grades:
    """The turnover's AMFs by the timeline index each grades (`core/amf.py`), read once.

    An AMF that will not parse, or whose name carries no timeline index, is reported on
    the turnover and matches nothing; two AMFs claiming one event are reported on that
    event's row rather than chosen between. When no AMF at an event's index names its
    clip, the one AMF that does grades it instead: turnover135's only AMF,
    exported on its own, is numbered 0 and names the sixth clip (2026-10-06).
    """

    folder: Path
    by_index: dict[int, list[amf.Amf]] = field(default_factory=dict)
    qc: list[QCResult] = field(default_factory=list)

    @classmethod
    def read(cls, folder: Path) -> _Grades:
        grades = cls(folder)
        for path in sorted(folder.glob(f"*{amf.SUFFIX}")):
            try:
                found = amf.read(path)
            except amf.AmfError as exc:
                grades.qc.append(QCResult("QC-075", "error", "turnover", str(exc)))
                continue
            if found.index is None:
                grades.qc.append(
                    QCResult(
                        "QC-075",
                        "warning",
                        "turnover",
                        f"{path.name} carries no timeline index in its name, so no EDL event can be "
                        "matched to it; ignored",
                    )
                )
                continue
            grades.by_index.setdefault(found.index, []).append(found)
        return grades

    def attach(self, row: ShotRow, event: clf.ConformEvent) -> None:
        """This row's grade from its event's AMF, and what is wrong with it on the row."""
        found = self.by_index.get(event.position, [])
        if not any(item.names(row.clip_name) for item in found):
            named = [item for items in self.by_index.values() for item in items if item.names(row.clip_name)]
            found = named if len(named) == 1 else found
        if len(found) != 1:
            names = ", ".join(item.path.name for item in found)
            why = f"two or more AMFs claim it ({names})" if found else "no AMF in the folder grades it"
            row.qc.append(
                QCResult(
                    "QC-075",
                    "error",
                    "row",
                    f"EDL event {event.event_id} ({row.clip_name}): {why}, so nothing names its input "
                    "transform or its grade",
                )
            )
            return
        (match,) = found
        if not match.names(row.clip_name):
            row.qc.append(
                QCResult(
                    "QC-075",
                    "error",
                    "row",
                    f"{match.path.name} grades video clip {event.position + 1} of the EDL (event "
                    f"{event.event_id}) but names {match.clip_file}, not {row.clip_name}",
                )
            )
            return
        row.grade, findings = _grade_of(match, self.folder)
        row.qc.extend(findings)
        space = color.ACES if match.input_applied else amf.colour_space_for(match.input_transform)
        row.source_encoding = space
        row.source_encoding_origin = "AMF" if space else None


def _grade_of(found: amf.Amf, folder: Path) -> tuple[Grade, list[QCResult]]:
    """What one AMF resolves to, and every look it names that cannot be applied.

    A look already applied to the media is left out without comment. A look the config
    does not define, and anything that is neither an ID nor a CLF, is ignored with a
    warning (QC-077, user 2026-09-28: primaries and simple secondaries only). A CLF that is
    missing, changed since the export, or unreadable is an error (QC-076), because the
    grade it carries is the colourist's and cannot be left out quietly.
    """
    findings: list[QCResult] = []
    looks: list[GradeLook] = []
    names_a_clf = any(look.file and not look.applied for look in found.looks)
    for look in found.looks:
        if look.applied:
            continue
        if look.transform_id:
            name = amf.look_for(look.transform_id)
            if name is None:
                findings.append(
                    _ignored(found, f"the look {look.transform_id}, which {color.BUILTIN_CONFIG} lacks")
                )
            else:
                looks.append(GradeLook("look", name))
        elif look.file:
            problem = _clf_problem(folder / look.file, look.md5)
            if problem:
                findings.append(
                    QCResult("QC-076", "error", "row", f"{found.path.name}: {look.file} {problem}")
                )
            else:
                looks.append(GradeLook("clf", str(folder / look.file)))
        elif look.cdl is not None:
            findings.append(_cdl_finding(found, look.cdl, looks, names_a_clf))
        else:
            findings.append(
                _ignored(found, f"a look that is not a transform ID or a CLF ({look.unsupported})")
            )
    shown = amf.display_view_for(found.output_transform) if found.output_transform else None
    if shown is not None and shown[0] not in ffmpeg.REFERENCE_TRANSFERS:
        findings.append(
            QCResult(
                "QC-079",
                "error",
                "row",
                f"{found.path.name}: the output transform is for {shown[0]}, which an 8 bit Rec.709 "
                "reference cannot be labelled for",
            )
        )
        shown = None
    elif shown is None:
        findings.append(
            QCResult(
                "QC-079",
                "error",
                "row",
                f"{found.path.name}: the output transform {found.output_transform or '(none)'} is not one "
                f"{color.BUILTIN_CONFIG} has, so the references cannot be viewed as the session was",
            )
        )
    if found.preset.casefold() == amf.DAILIES_PRESET.casefold():
        findings.append(
            QCResult("QC-078", "info", "row", f"{found.path.name} is from Resolve's {found.preset} preset")
        )
    grade = Grade(
        amf=found.path,
        input_transform=found.input_transform,
        looks=tuple(looks),
        display=shown[0] if shown else None,
        view=shown[1] if shown else None,
        preset=found.preset,
    )
    return grade, findings


def _cdl_finding(found: amf.Amf, cdl: amf.AmfCdl, looks: list[GradeLook], names_a_clf: bool) -> QCResult:
    """The CLF is the grade; the AMF's own CDL stands in only when it names none (user,
    2026-10-05), applied in the working space it states, and the row says so (QC-082)."""
    if names_a_clf:
        return _ignored(found, "its CDL, since a CLF carries the grade,")
    working = amf.colour_space_for(cdl.working) if cdl.working else None
    if working is None:
        return _ignored(
            found, f"a CDL in a working space {color.BUILTIN_CONFIG} lacks ({cdl.working or 'none stated'})"
        )
    looks.append(GradeLook("cdl", working, (*cdl.slope, *cdl.offset, *cdl.power, cdl.saturation)))
    numbers = " ".join(f"{value:g}" for value in cdl.slope)
    return QCResult(
        "QC-082",
        "warning",
        "row",
        f"{found.path.name}: no CLF carries this clip's grade, so the CDL inside the AMF is used "
        f"(slope {numbers}, in {working}); export the grade with its CLF",
    )


def _ignored(found: amf.Amf, what: str) -> QCResult:
    return QCResult("QC-077", "warning", "row", f"{found.path.name}: {what} is ignored")


def _clf_problem(path: Path, md5: str) -> str:
    """Why a CLF cannot be applied, or empty when it can."""
    try:
        data = path.read_bytes()
    except OSError:
        return "is not in the turnover folder"
    if md5 and hashlib.md5(data).hexdigest() != md5:
        return "has changed since the AMF was exported (its md5 differs)"
    try:
        color.config().getProcessor(color.clf_transform(path))
    except Exception as exc:  # OCIO raises its own Exception type for a file it cannot read
        return f"cannot be read as a CLF: {exc}"
    return ""
