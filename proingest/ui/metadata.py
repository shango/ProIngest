"""What the metadata pane says, worked out without a widget in sight.

UI_SPEC section 12.2 is the field list and 12.3 is the edge cases. This module turns a
selection into `Section`s of `Field`s and nothing else: no Qt, no I/O, no formatting
decisions that belong to a stylesheet. `ui/metadata_pane.py` draws the answer.

Apart for two reasons. **The field list is the part that gets argued about** (OQ-26 wants
a review session with the AD and the supervisor), and an argument about which fields
earn their place is easier against a list than against a layout. And **the pane redraws
only when this answer changes**, which needs the answer to be a value that can be
compared: a selection that has not moved and a run that has not touched the row produce
an equal list, and the widget does nothing.

**The pane never reads a file.** camData is the one field that lives on disk rather than
in the model, so it arrives through a lookup the caller supplies, which is where the
caching belongs (CLAUDE.md: scan once, cache; a turnover sits on a Drive mount).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from proingest.core import frames, media
from proingest.core.models import (
    AudioInfo,
    Batch,
    FrameRate,
    MediaInfo,
    QCResult,
    ShotRow,
    Turnover,
)

MIXED = "mixed"
"""What a field reads when the selection does not agree on it (section 12.3).

The point of the pane for more than one row: one clip at the wrong resolution in a
turnover of thirty shows up as a Resolution that reads `mixed` rather than as thirty
rows that have to be read one at a time.
"""

UNRESOLVED = "not resolved"
NO_SELECTION = "Select a shot to see its metadata"


@dataclass(frozen=True)
class Field:
    """One `label: value` line.

    `is_path` earns a copy button and middle elision (section 12.1): the filename is
    what identifies a file and the middle of a Drive path is the least informative part
    of it. `rule_id` makes the line click through to the Issues dock.
    """

    label: str
    value: str
    is_path: bool = False
    rule_id: str | None = None


@dataclass(frozen=True)
class Section:
    """One collapsible group. A section with no fields is never shown (section 12.2)."""

    title: str
    fields: tuple[Field, ...]


IDENTITY = "Identity"
SOURCE_MEDIA = "Source media"
FRAME_RATE = "Frame rate"
RANGE = "Range"
COLOUR = "Colour"
AUDIO = "Audio"
TURNOVER = "Turnover"
QC = "QC"

SECTION_ORDER = (
    IDENTITY,
    SOURCE_MEDIA,
    FRAME_RATE,
    RANGE,
    COLOUR,
    AUDIO,
    TURNOVER,
    QC,
)
"""Section 12.2's order, with Colour added where the chain would put it.

**Colour is not in section 12.2's table** and is here deliberately: that table was
written before M4.6 put the source encoding, its origin and the CLF path on the row, and
all three are exactly what the pane is for - facts about a shot with no column in the
list. UI_SPEC 12.2 now carries the row and says when it was added.
"""


# --- formatting ----------------------------------------------------------------------


def format_size(size: int) -> str:
    """`1.4 GB`, `342 MB`, `7.2 KB`, `93 bytes`. Read at a glance, not computed with."""
    if size < 1024:
        return f"{size} bytes"
    value = float(size)
    for unit in ("KB", "MB", "GB", "TB"):
        value /= 1024
        if value < 1024:
            return f"{value:.1f} {unit}"
    return f"{value:.1f} PB"


def format_mtime(mtime: float) -> str:
    """Local time to the minute. Seconds on a file modified time are noise."""
    if not mtime:
        return ""
    return datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")


def format_rate(rate: FrameRate) -> str:
    """`24`, or `23.976 (24000/1001)` for a rate that is not a whole number.

    Both forms, because the decimal is what a person says out loud and the fraction is
    what the frame math uses, and the whole reason `FrameRate` is rational is that those
    two are not the same number.
    """
    if rate.denominator == 1:
        return str(rate.numerator)
    return f"{rate.as_float():.3f} ({rate})"


def format_date(turnover: Turnover) -> str:
    """`02_23_2026`, the form the folder name carries (QC-005), or empty when unparsed."""
    if turnover.month is None or turnover.day is None or turnover.year is None:
        return ""
    return f"{turnover.month:02d}_{turnover.day:02d}_{turnover.year}"


def _plural(count: int, noun: str) -> str:
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


# --- one row ---------------------------------------------------------------------------


def turnover_for(batch: Batch, turnover_id: str) -> Turnover | None:
    for turnover in batch.turnovers:
        if turnover.turnover_id == turnover_id:
            return turnover
    return None


def _identity_fields(row: ShotRow) -> list[Field]:
    fields = [Field("Clip name", row.clip_name)]
    code = row.shot_code
    if code:
        suffix = " (editor override)" if row.shot_code_override else ""
        fields.append(Field("Shot code", f"{code}{suffix}"))
    identity = row.identity
    if identity is not None:
        fields.append(Field("Show", identity.show))
        fields.append(Field("Shot", identity.shot))
        fields.append(Field("Element", f"{identity.elem_type} {identity.elem_index}"))
        if identity.aux:
            aux = identity.aux + (f" {identity.aux_index}" if identity.aux_index else "")
            fields.append(Field("Aux", aux))
    fields.append(Field("Track", row.track))
    fields.append(Field("Turnover id", row.turnover_id))
    if row.skipped:
        fields.append(Field("Skipped", row.skip_reason or "yes"))
    return fields


def _unresolved_reason(row: ShotRow) -> str:
    """Why there is no media, taken from the rule that said so (section 12.3).

    The pane reads the QC result rather than re-deriving it, because the scan is the
    only thing that knows what it looked for and it has already written that down.
    """
    for result in row.qc:
        if result.rule_id in ("QC-012", "QC-013") and result.severity == "error":
            return f"{UNRESOLVED}: {result.message}"
    return UNRESOLVED


def _media_fields(row: ShotRow) -> list[Field]:
    info = row.media
    if info is None:
        return [Field("Media", _unresolved_reason(row))]
    fields = [
        Field("Path", str(info.path), is_path=True),
        Field("Codec", info.codec),
        Field("Pixel format", info.pixel_format),
        Field("Resolution", f"{info.width}x{info.height}"),
        Field("Kind", "image sequence" if info.is_sequence else "single file"),
    ]
    if info.is_sequence:
        last = info.start_frame + info.frame_count - 1
        fields.append(Field("Frames", f"{info.start_frame}-{last}"))
        fields.append(Field("Pattern", _pattern(info), is_path=True))
    fields.append(Field("Frame count", str(info.frame_count)))
    fields.append(Field("First frame", str(info.start_frame)))
    if info.start_timecode is not None:
        started = frames.frames_to_timecode(info.start_timecode, info.rate.as_float())
        fields.append(Field("Start timecode", started))
    if info.size:
        fields.append(Field("Size", format_size(info.size)))
    if info.mtime:
        fields.append(Field("Modified", format_mtime(info.mtime)))
    return fields


def _pattern(info: MediaInfo) -> str:
    """`plate.%04d.exr`, which is where the padding shows (section 12.2).

    The printf form rather than a padding count, because it is the string the tool
    actually hands ffmpeg, so an editor comparing it against what is on disk is
    comparing the same thing the render will use. A path that is not a numbered frame
    cannot produce one, and says so rather than raising.
    """
    try:
        return Path(media.printf_pattern_for(info.path)).name
    except ValueError:
        return ""


def _rate_fields(row: ShotRow, batch: Batch) -> list[Field]:
    info = row.media
    fields = [Field("Timeline rate", format_rate(batch.project_rate))]
    if info is None:
        return fields
    if info.rate != batch.project_rate:
        fields.append(Field("Conformed to", format_rate(info.rate)))
    if info.stated_rate is None:
        fields.append(Field("Stated by the media", "none"))
        return fields
    fields.append(Field("Stated by the media", format_rate(info.stated_rate)))
    if not info.rate_matches_timeline:
        fields.append(
            Field(
                "Disagreement",
                f"the media states {format_rate(info.stated_rate)} and the timeline "
                f"conforms it to {format_rate(info.rate)}; the timeline wins (QC-026)",
            )
        )
    return fields


def _range_fields(row: ShotRow, batch: Batch, turnover: Turnover | None) -> list[Field]:
    start = turnover.timeline_start if turnover else 0
    context = row.edit_context(batch.project_rate, start, "source")
    record = row.edit_context(batch.project_rate, start, "record")

    def source_tc(frame: int) -> str:
        return frames.source_frame_to_timecode(frame, context)

    fields = [
        Field("Record in/out", f"{row.record_in} - {row.record_out}"),
        Field(
            "Record timecode",
            f"{frames.frames_to_timecode(start + row.record_in, record.fps)} - "
            f"{frames.frames_to_timecode(start + row.record_out, record.fps)}",
        ),
    ]
    if row.snapshot is not None:
        fields.append(
            Field(
                "Turnover in/out",
                f"{row.snapshot.in_frame} - {row.snapshot.out_frame}",
            )
        )
    if row.current is not None:
        fields.append(Field("Current in/out", f"{row.current.in_frame} - {row.current.out_frame}"))
        fields.append(
            Field(
                "Source timecode",
                f"{source_tc(row.current.in_frame)} - {source_tc(row.current.out_frame)}",
            )
        )
        fields.append(Field("Duration", _plural(row.current.duration, "frame")))
    if row.max_available_out is not None:
        fields.append(Field("Max available out", str(row.max_available_out)))
    if row.was_edited:
        fields.append(Field("Trimmed", "moved off the turnover's in/out (QC-045)"))
    return fields


def _colour_fields(row: ShotRow) -> list[Field]:
    """The source encoding, where it came from, and the CLF (M4.6, M4.5).

    Three facts the list has no column for and the QC log does. The encoding is the
    string the shooter wrote rather than a colour space name, which is why it is shown
    verbatim: what has to be corrected when it is wrong is the string.
    """
    fields: list[Field] = []
    if row.source_encoding:
        fields.append(Field("Source encoding", row.source_encoding))
        if row.source_encoding_origin:
            fields.append(Field("Named by", row.source_encoding_origin))
    return fields


def _audio_fields(row: ShotRow, batch: Batch) -> list[Field]:
    if row.audio_path is None and row.audio is None:
        return []
    fields: list[Field] = []
    path = row.audio.path if row.audio else row.audio_path
    if path is not None:
        fields.append(Field("Path", str(path), is_path=True))
    info = row.audio
    if info is not None:
        fields.append(Field("Sample rate", f"{info.sample_rate} Hz"))
        if info.channels:
            fields.append(Field("Channels", str(info.channels)))
        if info.bit_depth:
            fields.append(Field("Bit depth", f"{info.bit_depth} bit"))
        fields.append(Field("Duration", _audio_duration(info, batch.project_rate)))
        difference = _sync_difference(row, info, batch.project_rate)
        if difference:
            fields.append(Field("Sync", difference))
    if row.audio_clip_count > 1:
        fields.append(Field("Timeline clips", f"{row.audio_clip_count} overlapped (QC-041)"))
    return fields


def _audio_duration(info: AudioInfo, rate: FrameRate) -> str:
    return f"{info.duration_samples} samples, {_plural(info.duration_in_frames(rate), 'frame')}"


def _sync_difference(row: ShotRow, info: AudioInfo, rate: FrameRate) -> str:
    """How far the audio runs past the picture, or short of it (QC-043).

    Against the record range rather than the chosen in/out: the audio was cut to the
    shot as the turnover delivered it, and the editor's trim is measured elsewhere.
    """
    picture = frames.duration(row.record_in, row.record_out)
    if not picture:
        return ""
    difference = info.duration_in_frames(rate) - picture
    if difference == 0:
        return f"matches the picture ({_plural(picture, 'frame')})"
    direction = "longer" if difference > 0 else "shorter"
    return f"{_plural(abs(difference), 'frame')} {direction} than the picture"


def turnover_fields(turnover: Turnover, rate: FrameRate) -> list[Field]:
    """Section 12.2's Turnover block. Shown alone when a group header is selected."""
    fields: list[Field] = []
    if turnover.number is not None:
        fields.append(Field("Number", str(turnover.number)))
    date = format_date(turnover)
    if date:
        fields.append(Field("Date", date))
    if turnover.shooter:
        fields.append(Field("Shooter", turnover.shooter))
    fields.append(Field("Folder", str(turnover.folder), is_path=True))
    if turnover.timeline_path is not None:
        fields.append(Field("Timeline", str(turnover.timeline_path), is_path=True))
    if turnover.timeline_start:
        started = frames.frames_to_timecode(turnover.timeline_start, rate.as_float())
        fields.append(Field("Timeline start", f"{turnover.timeline_start} ({started})"))
    return fields


def _qc_fields(rows: Sequence[ShotRow]) -> list[Field]:
    """Counts by severity, then one clickable line per result (section 12.2).

    **Built across the whole selection rather than merged field by field**, unlike every
    other section. Two rows with different problems agree on nothing, so a merge would
    reduce this to `mixed`, which is the one answer that helps nobody: what somebody
    selecting a turnover's worth of rows wants is how many problems there are.
    """
    results = [result for row in rows for result in _row_results(row)]
    if not results:
        return [Field("Results", "none")]
    counts = {
        severity: sum(1 for result in results if result.severity == severity)
        for severity in ("error", "warning", "info")
    }
    summary = ", ".join(_plural(count, name) for name, count in counts.items() if count)
    fields = [Field("Results", summary)]
    seen: set[tuple[str, str]] = set()
    for result in results:
        key = (result.rule_id, result.message)
        if key in seen:
            continue
        seen.add(key)
        fields.append(Field(result.rule_id, result.message, rule_id=result.rule_id))
    return fields


def _row_results(row: ShotRow) -> list[QCResult]:
    """A row's own results and its deliverables', which is what the Issues dock lists."""
    return [*row.qc, *(result for item in row.deliverables for result in item.qc)]


def describe_row(row: ShotRow, batch: Batch) -> list[Section]:
    """Every section for one row, empty ones included so a merge can line them up."""
    turnover = turnover_for(batch, row.turnover_id)
    return [
        Section(IDENTITY, tuple(_identity_fields(row))),
        Section(SOURCE_MEDIA, tuple(_media_fields(row))),
        Section(FRAME_RATE, tuple(_rate_fields(row, batch))),
        Section(RANGE, tuple(_range_fields(row, batch, turnover))),
        Section(COLOUR, tuple(_colour_fields(row))),
        Section(AUDIO, tuple(_audio_fields(row, batch))),
        Section(TURNOVER, tuple(turnover_fields(turnover, batch.project_rate)) if turnover else ()),
        Section(QC, tuple(_qc_fields([row]))),
    ]


# --- more than one row ------------------------------------------------------------------


def _merge(described: Sequence[list[Section]]) -> list[Section]:
    """The fields the selection agrees on, with the rest reading `mixed` (section 12.3).

    Order comes from the first row, and a field only some rows have is `mixed` too: a
    selection where one clip has a CLF and the others do not disagrees about the CLF,
    and saying so is the whole point.
    """
    merged: list[Section] = []
    for position, first in enumerate(described[0]):
        others = [described[index][position] for index in range(1, len(described))]
        labels = list(dict.fromkeys(field.label for section in [first, *others] for field in section.fields))
        fields: list[Field] = []
        for label in labels:
            found = [_value_for(section, label) for section in [first, *others]]
            template = _field_for(first, label)
            value = found[0] if len(set(found)) == 1 and found[0] is not None else MIXED
            fields.append(
                Field(
                    label,
                    value,
                    is_path=template.is_path if template else False,
                    rule_id=template.rule_id if template else None,
                )
            )
        merged.append(Section(first.title, tuple(fields)))
    return merged


def _field_for(section: Section, label: str) -> Field | None:
    return next((field for field in section.fields if field.label == label), None)


def _value_for(section: Section, label: str) -> str | None:
    found = _field_for(section, label)
    return found.value if found else None


def describe(rows: Sequence[ShotRow], batch: Batch) -> list[Section]:
    """What the pane shows for a selection. Empty sections are dropped (section 12.2).

    A path is never merged into `mixed` usefully, but it is merged the same way as
    everything else on purpose: a selection of two rows whose media sits in different
    folders genuinely disagrees about the path, and inventing a third answer for paths
    would be a rule to remember rather than a rule to read.
    """
    if not rows:
        return []
    described = [describe_row(row, batch) for row in rows]
    sections = described[0] if len(described) == 1 else _merge(described)
    if len(rows) > 1:
        sections = [
            Section(QC, tuple(_qc_fields(rows))) if section.title == QC else section for section in sections
        ]
    return [section for section in sections if section.fields]


def describe_turnover(turnover: Turnover, rate: FrameRate) -> list[Section]:
    """A group header's selection: **the Turnover section alone** (section 12.3).

    Alone, so the turnover's own results go in it as fields rather than in a QC section
    of their own. Nothing is lost by that and two things are gained: the sentence in
    12.3 stays literally true, and the rows' results are not rolled up here, which they
    would only duplicate - the group header in the list already counts them, and the
    Issues dock lists every one.
    """
    fields = [
        *turnover_fields(turnover, rate),
        *(Field(result.rule_id, result.message, rule_id=result.rule_id) for result in turnover.qc),
    ]
    return [Section(TURNOVER, tuple(fields))]


def as_text(sections: Sequence[Section]) -> str:
    """The whole pane as `key: value` text, which is what Copy all puts on the clipboard.

    Section 12.1 asks for it because an editor chasing a media problem pastes the lot
    into a message rather than reading twelve values out loud.
    """
    lines: list[str] = []
    for section in sections:
        lines.append(f"[{section.title}]")
        lines.extend(f"{field.label}: {field.value}" for field in section.fields)
        lines.append("")
    return "\n".join(lines).strip()


def selection_summary(count: int) -> str:
    """`12 shots selected`, the count section 12.3 asks for above a merged pane."""
    return _plural(count, "shot") + " selected"


__all__ = [
    "MIXED",
    "NO_SELECTION",
    "SECTION_ORDER",
    "Field",
    "Section",
    "as_text",
    "describe",
    "describe_row",
    "describe_turnover",
    "format_date",
    "format_mtime",
    "format_rate",
    "format_size",
    "selection_summary",
    "turnover_fields",
    "turnover_for",
]
