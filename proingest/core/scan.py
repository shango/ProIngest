"""Turning a turnover folder into shot rows.

This is steps 1 to 4 of the data flow in docs/ARCHITECTURE.md: load the timeline,
parse clip names, resolve and probe media, derive frame ranges and snapshots.

Only the QC results that are *discovered while scanning* are raised here, meaning
the ones that cannot be recomputed from the saved model later: media that could not
be found, matched ambiguously or failed to probe, and paths that were remapped.
Rules that are pure functions of the model, such as duration limits, resolution and
fps, belong to the rule registry in M4 so they can re-run after every edit.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from proingest.core import ffmpeg, naming, qc, timeline
from proingest.core import media as media_module
from proingest.core.models import (
    Batch,
    FrameRate,
    InOut,
    MediaInfo,
    QCResult,
    ShotRow,
    SideFiles,
    SourceEncodingOrigin,
    Turnover,
)

TURNOVER_FOLDER_PATTERN = re.compile(
    r"^turnover(?P<number>\d{3})_(?P<month>\d{2})_(?P<day>\d{2})_(?P<year>\d{4})_(?P<shooter>.+)$"
)

HDRI_FRAGMENT = "hdri"
HDRI_EXTENSIONS = (".exr",)
SOURCE_ENCODING_KEY = "Input Color Space"
"""The metadata field the source encoding is read from. OQ-44, and a default until it answers.

Resolve's own Media Pool column of that name holds the input transform, which is the
string COLOR_AND_FORMAT section 1 asks the shooters to write verbatim, so it is the
field most likely to already be filled in rather than a new one somebody has to
remember. **One named field, never a comment somewhere**: a search would be the tool
guessing which of a clip's forty strings is a colour space name.

Settable per scan (`ScanSettings.source_encoding_key`) because the answer to OQ-44 is a
different field name and nothing else.
"""

CAMDATA_FRAGMENT = "camdata"
CAMDATA_EXTENSIONS = tuple(f".{ext}" for ext in naming.CAMDATA_EXTENSIONS)


@dataclass
class ScanSettings:
    """Settings the scan needs. Defaults match docs/OPEN_QUESTIONS.md."""

    show_pattern: str = naming.DEFAULT_SHOW_PATTERN
    path_map: dict[str, str] = field(default_factory=dict)
    project_rate: FrameRate = field(default_factory=lambda: FrameRate(24))
    rules: qc.RuleSettings = field(default_factory=qc.RuleSettings)
    """Thresholds the rule registry compares against, so the scan's first pass of QC
    matches what the Settings page will later re-run with."""

    source_encoding_key: str = SOURCE_ENCODING_KEY
    """Which metadata field names the clip's source encoding (OQ-44)."""


@dataclass(frozen=True)
class TurnoverFields:
    """The stringout name's inputs, read off the folder name."""

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
    timeline_path: Path | None = None,
) -> tuple[Turnover, list[ShotRow]]:
    """Scan one turnover folder into a Turnover and its rows.

    Never raises for a bad turnover: a missing or unreadable timeline comes back as
    a Turnover carrying QC-001 or QC-002 and no rows, so one bad folder cannot take
    down a batch.
    """
    settings = settings or ScanSettings()
    cache = probe_cache if probe_cache is not None else {}

    turnover = Turnover(turnover_id=turnover_id, folder=folder)
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
    else:
        turnover.number = prefill.number
        turnover.month = prefill.month
        turnover.day = prefill.day
        turnover.year = prefill.year
        turnover.shooter = prefill.shooter

    chosen = timeline_path or _choose_timeline(folder, turnover)
    if chosen is None:
        return turnover, []
    turnover.timeline_path = chosen

    try:
        loaded = timeline.load(chosen, settings.project_rate)
    except timeline.DropFrameError as exc:
        turnover.qc.append(QCResult("QC-027", "error", "turnover", str(exc)))
        return turnover, []
    except timeline.EdlTimecodeError as exc:
        turnover.qc.append(QCResult("QC-025", "error", "turnover", str(exc)))
        return turnover, []
    except timeline.TimelineError as exc:
        turnover.qc.append(QCResult("QC-002", "error", "turnover", str(exc)))
        return turnover, []

    turnover.timeline_start = loaded.global_start
    """Kept because record timecode is read against it and the timeline is gone by the
    time anyone asks (UI_SPEC section 2's Record TC display)."""

    turnover.qc.extend(qc.check_timeline_rate(turnover, loaded.rate, settings.project_rate))

    if loaded.is_edl:
        turnover.qc.append(
            QCResult("QC-003", "warning", "turnover", "EDL used instead of OTIO; reduced validation")
        )
    if loaded.is_drop_frame:
        turnover.qc.append(QCResult("QC-027", "error", "turnover", "timeline uses drop-frame timecode"))
    if not loaded.video:
        turnover.qc.append(
            QCResult("QC-004", "warning", "turnover", "timeline contains no video clips on any track")
        )
        return turnover, []

    index = media_module.index_directory(folder)
    rows = [_build_row(clip, loaded, index, turnover_id, settings, cache) for clip in loaded.video]
    return turnover, rows


def _choose_timeline(folder: Path, turnover: Turnover) -> Path | None:
    """Pick the timeline, recording QC-001 when there is none."""
    candidates = timeline.find_timeline_files(folder)
    if not candidates:
        turnover.qc.append(QCResult("QC-001", "error", "turnover", f"no .otio or .edl found in {folder}"))
        return None
    return candidates[0]


def _build_row(
    clip: timeline.ClipRecord,
    loaded: timeline.Timeline,
    index: media_module.DirectoryIndex,
    turnover_id: str,
    settings: ScanSettings,
    cache: dict[str, MediaInfo],
) -> ShotRow:
    """One timeline clip into one shot row, with whatever QC the scan uncovered."""
    row = ShotRow(
        turnover_id=turnover_id,
        clip_name=clip.name,
        track=clip.track,
        record_in=clip.record_start,
        record_out=clip.record_end,
    )

    row.identity = naming.parse_clip_name(clip.name, settings.show_pattern)
    if row.identity is None:
        row.qc.append(
            QCResult(
                "QC-010",
                "error",
                "row",
                f"clip name {clip.name!r} does not match the naming regex",
            )
        )

    item = _resolve_media(clip, index, settings, row)
    if item is not None:
        _probe_into(row, item, cache, loaded.rate)

    row.source_encoding, row.source_encoding_origin = _source_encoding(
        clip, row, settings.source_encoding_key
    )
    _derive_ranges(row, clip)
    _attach_audio(row, clip, loaded, index, settings)
    _attach_side_files(row, index)
    qc.apply_row_rules(row, settings.project_rate, settings.rules)
    return row


def _source_encoding(
    clip: timeline.ClipRecord, row: ShotRow, key: str
) -> tuple[str | None, SourceEncodingOrigin | None]:
    """What this clip says it is encoded in, verbatim, and which carrier said it.

    **The clip's own metadata first and the container's tags second** (OQ-44). The
    timeline is where a person filled the field in; a container tag is the same string
    travelling in the file instead, and it comes second because a consolidated media
    file can outlive the session that wrote it. An empty value is no value, which is
    what QC-046 reports.

    Read here because this is the only moment the timeline and the probe are both in
    front of the tool, and stored as written rather than resolved: what a shooter typed
    is what QC-047 has to be able to quote back.

    The origin travels with the name because a wrong encoding is traced back to whoever
    wrote it, and the two carriers are written by different people at different times
    (`models.SourceEncodingOrigin`). It rides to the delivered EXR header from here.
    """
    sources: list[tuple[SourceEncodingOrigin, Mapping[str, str]]] = [("clip metadata", clip.metadata)]
    if row.media is not None:
        sources.append(("container tag", row.media.tags))
    for origin, fields in sources:
        value = _named_value(fields, key)
        if value is not None:
            return value, origin
    return None, None


def _named_value(fields: Mapping[str, str], key: str) -> str | None:
    """One named field, matched without case or surrounding space. Empty is absent."""
    wanted = key.strip().casefold()
    for name, value in fields.items():
        if name.strip().casefold() == wanted and value.strip():
            return value.strip()
    return None


def _resolve_media(
    clip: timeline.ClipRecord,
    index: media_module.DirectoryIndex,
    settings: ScanSettings,
    row: ShotRow,
) -> media_module.Sequence | media_module.FileEntry | None:
    """FR-2: prefer the referenced URL, then fall back to a filename search."""
    claimed: Path | None = None
    if clip.media_url:
        referenced = media_module.url_to_path(clip.media_url)
        claimed = media_module.remap(referenced, settings.path_map)
        if claimed != referenced:
            row.qc.append(QCResult("QC-016", "warning", "row", f"media path remapped to {claimed}"))
        located = _index_entry_for(index, claimed)
        if located is not None:
            return located

    matches = index.media_matching(clip.name)
    if not matches:
        # The claimed path is named because it is the only record of what the timeline
        # asked for: nothing stores it once the row has no media, and it is the first
        # thing anybody wants when a shot will not resolve (UI_SPEC section 12.3).
        wanted = f"{claimed} is missing" if claimed else "the clip references no path"
        row.qc.append(
            QCResult(
                "QC-012",
                "error",
                "row",
                f"media not found for {clip.name!r}: {wanted} and no file in the turnover matches the name",
            )
        )
        return None
    if len(matches) > 1:
        described = ", ".join(sorted(_describe(match) for match in matches))
        row.qc.append(QCResult("QC-013", "error", "row", f"media ambiguous for {clip.name!r}: {described}"))
        return None
    return matches[0]


def _index_entry_for(
    index: media_module.DirectoryIndex, path: Path
) -> media_module.Sequence | media_module.FileEntry | None:
    """Find the indexed item a resolved path points at.

    The index is consulted rather than the filesystem so that a referenced frame of
    a sequence resolves to the whole sequence, and so nothing stats twice.
    """
    for sequence in index.sequences:
        if sequence.directory == path.parent and sequence.base == _sequence_base(path):
            return sequence
    for entry in index.singles:
        if entry.path == path:
            return entry
    return None


def _sequence_base(path: Path) -> str:
    match = media_module.SEQUENCE_PATTERN.match(path.stem)
    return match["base"] if match else path.stem


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


def _derive_ranges(row: ShotRow, clip: timeline.ClipRecord) -> None:
    """Map the timeline's source range onto real source frame indices.

    The snapshot is set here and never changes again; it is what the turnover
    arrived with and what the QC log compares the editor's final values against.
    """
    if row.media is None:
        return
    start = row.media.start_frame + clip.source_offset()
    chosen = InOut(start, start + clip.duration - 1)
    row.snapshot = chosen
    row.current = chosen

    if start < row.media.start_frame or chosen.out_frame > row.media.max_available_out:
        row.qc.append(
            QCResult(
                "QC-029",
                "warning",
                "row",
                f"timeline references frames {chosen.in_frame}-{chosen.out_frame} but the media "
                f"holds {row.media.start_frame}-{row.media.max_available_out}",
            )
        )


def _attach_audio(
    row: ShotRow,
    clip: timeline.ClipRecord,
    loaded: timeline.Timeline,
    index: media_module.DirectoryIndex,
    settings: ScanSettings,
) -> None:
    """Associate audio from the timeline, or by name when the source was an EDL.

    Counting rules (QC-040, QC-041) are left to the rule registry; this only records
    what was found.
    """
    associated = loaded.audio_for(clip)
    row.audio_clip_count = len(associated)
    if associated and associated[0].media_url:
        # Through the same path map as the picture: the audio URL came from the same
        # machine, so it needs the same rewrite onto the local mount.
        referenced = media_module.url_to_path(associated[0].media_url)
        row.audio_path = media_module.remap(referenced, settings.path_map)
    elif loaded.is_edl:
        # FR-1: an EDL cannot associate audio, so fall back to a same-name search.
        by_name = index.audio_matching(clip.name)
        if len(by_name) == 1:
            row.audio_path = by_name[0].path

    if row.audio_path is None or not row.audio_path.is_file():
        return
    try:
        row.audio = media_module.probe_audio(row.audio_path)
    except (ffmpeg.FFprobeError, ffmpeg.FFmpegNotFound) as exc:
        row.qc.append(QCResult("QC-042", "error", "row", f"audio unreadable: {exc}"))


def _attach_side_files(row: ShotRow, index: media_module.DirectoryIndex) -> None:
    """HDRI and camData discovered next to the media, matched by shot code and element."""
    if row.identity is None:
        return
    stem = row.identity.stem
    row.side_files = SideFiles(
        hdri=_single_match(index, stem, HDRI_FRAGMENT, HDRI_EXTENSIONS),
        camdata=_single_match(index, stem, CAMDATA_FRAGMENT, CAMDATA_EXTENSIONS),
    )


def _single_match(
    index: media_module.DirectoryIndex, stem: str, fragment: str, extensions: tuple[str, ...]
) -> Path | None:
    """A side file must name both the element and the kind, and be a form we can deliver.

    The extension filter is what NAMING_SPEC section 2 states (`*HDRI*.exr`,
    `*camData*.txt|rtf`). Without it a jpeg sitting beside the real HDRI would be
    delivered under an `.exr` name, because the planner takes the extension from the
    delivery template and not from the file.
    """
    hits = [
        entry.path
        for entry in index.containing(fragment)
        if stem.lower() in entry.name.lower() and entry.suffix in extensions
    ]
    return hits[0] if len(hits) == 1 else None


def scan_batch(
    folders: list[Path],
    name: str = "untitled",
    settings: ScanSettings | None = None,
) -> Batch:
    """Scan several turnover folders into one batch, sharing the probe cache."""
    settings = settings or ScanSettings()
    batch = Batch(name=name, project_rate=settings.project_rate)
    for position, folder in enumerate(folders, start=1):
        turnover, rows = scan_turnover(folder, f"t{position}", settings, probe_cache=batch.probe_cache)
        batch.turnovers.append(turnover)
        batch.rows.extend(rows)
    # QC-011 is the one row rule that needs every row, so it can only run once they exist.
    qc.apply_batch_rules(batch, settings.rules)
    return batch
