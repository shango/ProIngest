"""The turnover stringout: Ben's final EDL, every event in timeline order, as one HD mp4.

OQ-38, reopened 2026-09-25: Ben renders one in Resolve and the tool renders one with
ffmpeg. The user's decisions, all in OQ-38:

- **The cut is the final saved EDL in the turnover**, event for event, gaps included.
- **Each event is cut from its delivered HD reference** when there is one, so the pixels
  are the vendor's references exactly and there is no second colour path to drift.
- **An event with no reference** (a still, a skipped or failed shot, a clip the CSV gives
  no `Shot Type`) is **the ungraded source**, and black when not even that is known.
- **Burn-ins copy Ben's frame** (`burn-ins.png`): the stringout's own name top centre,
  `Frame:` bottom left, `Primary Effect:` (the CSV's `Scene`) bottom centre, and the
  shot and element bottom right. White, Open Sans, no box. No camera timecode: the
  counter is the delivered frame number, 1001 on the frame the plate starts with.
- **Only a plate has sound**; every other segment carries silence of the same length.

Each segment is encoded on its own and the segments are joined by stream copy, which
is safe because every one is encoded with the reference's settings and the same
streams. The join goes to a `.part` beside the destination, is checked (QC-142), and
only then takes its name.
"""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from proingest.core import clf, ffmpeg, frames, media, naming, qc, scan
from proingest.core.models import Batch, Deliverable, InOut, MediaInfo, QCResult, ShotRow, Turnover
from proingest.core.planner import effective_identity

log = logging.getLogger(__name__)

SIZE = (1920, 1080)
"""The size of the HD references it is cut from."""

RATE = "24/1"

FONT = Path(__file__).resolve().parent.parent / "resources" / "fonts" / "OpenSans-Regular.ttf"
"""Bundled rather than found: a system font means a platform path (CLAUDE.md), and a
fontconfig lookup inside a static ffmpeg is not something to find out about on a Mac."""

# Measured off Ben's frame, scaled to 1920x1080 (2026-09-25).
FONT_SIZE = 42
TOP_Y = "11"
BOTTOM_Y = "892"
LEFT_X = "184"
RIGHT_X = "w-150-text_w"
CENTRE_X = "(w-text_w)/2"

STRINGOUT_RULES = ("QC-142", "QC-143")
"""What a build owns on its turnover, replaced each time it runs."""

SegmentKind = Literal["reference", "source", "black"]


class StringoutError(RuntimeError):
    """A stringout that cannot be planned or did not come out right. Reported as QC-142."""


@dataclass(frozen=True)
class Segment:
    """One stretch of the timeline: an event, or the gap before one."""

    kind: SegmentKind
    length: int
    """Frames on the timeline, which is the record length, a freeze's included."""

    event_id: str = ""
    first_frame: int = naming.FIRST_OUTPUT_FRAME
    """The `Frame:` number on the segment's first frame."""

    freeze: bool = False
    label: str = ""
    effect: str = ""
    path: Path | None = None
    """The reference mp4, or the source media's file (a sequence's first frame)."""

    start: int = 0
    """The first frame taken: from the reference's head, or the media's own frame index."""

    audio: bool = False
    """A plate's reference: its sound comes with it."""

    media: MediaInfo | None = None
    gap: bool = False
    """No event here: black, with only the name burned in."""


@dataclass
class Plan:
    stem: str
    destination: Path
    version: int
    timecode: str
    segments: list[Segment] = field(default_factory=list)

    @property
    def total(self) -> int:
        return sum(segment.length for segment in self.segments)


def plan(
    batch: Batch,
    turnover: Turnover,
    delivery_root: Path,
    show_pattern: str = naming.DEFAULT_SHOW_PATTERN,
) -> Plan:
    """Every event of the turnover's EDL as a segment. Raises StringoutError when there
    is no name to give it or no EDL to cut."""
    fields = (turnover.number, turnover.month, turnover.day, turnover.year)
    if None in fields or not turnover.shooter:
        raise StringoutError(
            f"{turnover.folder.name} gives no turnover number, date and shooter, so the stringout has no name"
        )
    number, month, day, year = (int(value) for value in fields if value is not None)
    try:
        session = scan.read_session(turnover, batch.project_rate, show_pattern)
    except clf.ColorSessionError as exc:
        raise StringoutError(str(exc)) from exc
    events = sorted(session.events, key=lambda event: event.record_in)
    if not events:
        raise StringoutError(f"{turnover.folder.name}'s EDL cuts nothing")

    rows = batch.rows_for(turnover.turnover_id)
    show = next((row.identity.show for row in rows if row.identity), None)
    if show is None:
        raise StringoutError(
            f"no row of {turnover.folder.name} has a shot code, so there is no show to file under"
        )
    folder = naming.reports_dir(delivery_root, show)
    version = _next_version(folder, number, month, day, year, turnover.shooter)
    stem = naming.stringout_stem(number, month, day, year, turnover.shooter, version)

    result = Plan(
        stem=stem,
        destination=folder / (stem + naming.STRINGOUT_SUFFIX),
        version=version,
        timecode=frames.frames_to_timecode(events[0].record_in, batch.project_rate.as_float()),
    )
    cursor = events[0].record_in
    for event in events:
        if event.record_in > cursor:
            result.segments.append(Segment(kind="black", length=event.record_in - cursor, gap=True))
        result.segments.append(_segment(event, session, rows, show_pattern))
        cursor = max(cursor, event.record_out + 1)
    return result


def _next_version(folder: Path, number: int, month: int, day: int, year: int, shooter: str) -> int:
    """One past the highest stringout of this turnover already there. One listing."""
    if not folder.is_dir():
        return 1
    found = [naming.stringout_version(p.name, number, month, day, year, shooter) for p in folder.iterdir()]
    return max((version for version in found if version is not None), default=0) + 1


def _segment(
    event: clf.ConformEvent, session: clf.ColorSession, rows: list[ShotRow], show_pattern: str
) -> Segment:
    length = frames.duration(event.record_in, event.record_out)
    claimed = [row for row in rows if event in session.candidates(row)]
    known = next((row for row in claimed if row.media is not None), None)
    cut = clf.approved_in_out(event, known.media) if known is not None and known.media is not None else None
    if known is None or cut is None:
        name = event.clip_stem or event.reel or f"event {event.event_id}"
        return Segment(kind="black", length=length, event_id=event.event_id, freeze=event.freeze, label=name)

    delivering = next((row for row in claimed if _reference(row, cut) is not None), None)
    row = delivering or next((row for row in claimed if row.approved == cut), known)
    identity = effective_identity(row, show_pattern)
    label = naming.shot_label(identity) if identity is not None else Path(row.clip_name).stem
    if delivering is not None and delivering.delivered_range is not None:
        offset = cut.in_frame - delivering.delivered_range.in_frame
        return Segment(
            kind="reference",
            length=length,
            event_id=event.event_id,
            first_frame=naming.FIRST_OUTPUT_FRAME + offset,
            freeze=event.freeze,
            label=label,
            effect=delivering.scene,
            path=_reference(delivering, cut),
            start=offset,
            audio=qc.is_plate(delivering),
        )
    base = row.current.in_frame if row.current is not None else cut.in_frame
    return Segment(
        kind="source",
        length=length,
        event_id=event.event_id,
        first_frame=naming.FIRST_OUTPUT_FRAME + cut.in_frame - base,
        freeze=event.freeze,
        label=label,
        effect=row.scene,
        path=known.media.path if known.media is not None else None,
        start=cut.in_frame,
        media=known.media,
    )


def _reference(row: ShotRow, cut: InOut) -> Path | None:
    """The row's HD reference, when it landed, is still there, and holds the cut."""
    if row.skipped or row.identity is None or row.delivered_range is None:
        return None
    held = row.delivered_range
    if cut.in_frame < held.in_frame or cut.out_frame > held.out_frame:
        return None
    for item in row.deliverables:
        if (
            item.kind == "ref_mp4"
            and item.res == "HD"
            and item.status in ("done", "exists")
            and item.path.is_file()
        ):
            return item.path
    return None


def build(
    batch: Batch,
    turnover: Turnover,
    delivery_root: Path,
    show_pattern: str = naming.DEFAULT_SHOW_PATTERN,
) -> Deliverable | None:
    """Plan, render and check one turnover's stringout, and record the outcome on it.

    Never raises: a stringout that could not be made is QC-142 on the turnover, which
    does not block a run (it is phase B), and the delivery it describes is unaffected.
    """
    turnover.qc = [result for result in turnover.qc if result.rule_id not in STRINGOUT_RULES]
    try:
        made = plan(batch, turnover, delivery_root, show_pattern)
        deliverable = render(made)
    except (StringoutError, ffmpeg.FFmpegError, ffmpeg.FFprobeError, OSError) as exc:
        turnover.qc.append(QCResult("QC-142", "error", "turnover", f"the stringout was not written: {exc}"))
        return None
    turnover.stringout = deliverable
    stand_ins = [f"{s.event_id} ({s.label})" for s in made.segments if s.kind != "reference" and not s.gap]
    if stand_ins:
        turnover.qc.append(
            QCResult(
                "QC-143",
                "info",
                "turnover",
                f"{deliverable.name}: events {', '.join(stand_ins)} have no delivered reference and "
                f"are the ungraded source, or black where no source is known",
            )
        )
    return deliverable


def render(made: Plan) -> Deliverable:
    """Encode every segment, join them, check the join, and give it its name."""
    folder = made.destination.parent
    folder.mkdir(parents=True, exist_ok=True)
    parts = folder / f".{made.stem}.parts"
    temp = made.destination.with_name(made.destination.name + ".part")
    shutil.rmtree(parts, ignore_errors=True)
    parts.mkdir()
    try:
        encoded = [_encode(made, segment, parts, index) for index, segment in enumerate(made.segments)]
        listing = parts / "segments.txt"
        listing.write_text("".join(f"file '{_quoted(path)}'\n" for path in encoded), encoding="utf-8")
        _run(ffmpeg.concat_command(listing, temp, made.timecode), temp.name)
        problems = qc.check_stringout(temp, made.total, SIZE, RATE)
        if problems:
            raise StringoutError("; ".join(problems))
        temp.replace(made.destination)
    finally:
        shutil.rmtree(parts, ignore_errors=True)
        temp.unlink(missing_ok=True)
    return Deliverable(
        kind="stringout",
        name=made.destination.name,
        path=made.destination,
        version=made.version,
        status="done",
        frame_count=made.total,
        size=made.destination.stat().st_size,
    )


def _quoted(path: Path) -> str:
    """A path inside the concat list's single quotes."""
    return str(path).replace("'", "'\\''")


def _encode(made: Plan, segment: Segment, parts: Path, index: int) -> Path:
    destination = parts / f"{index:04d}.mp4"
    overlay = _burn_ins(made.stem, segment, parts / f"{index:04d}")
    if segment.kind == "reference" and segment.path is not None:
        size, has_audio = _probe(segment.path)
        sound = segment.audio and has_audio
        fitted = _fit(size)
        command = ffmpeg.encode_command(
            str(segment.path),
            destination,
            segment.start,
            segment.start + (0 if segment.freeze else segment.length - 1),
            is_sequence=False,
            rate=RATE,
            audio=segment.path if sound else None,
            audio_skip=segment.start / 24 if sound else 0.0,
            target_size=fitted if fitted != size else None,
            color_space="bt709",
            color_range="tv",
            canvas=SIZE if fitted != SIZE else None,
            hold=segment.length if segment.freeze else 0,
            overlay=overlay,
            silence=not sound,
            audio_format=ffmpeg.STRINGOUT_AUDIO,
        )
    elif segment.kind == "source" and segment.path is not None and segment.media is not None:
        source = segment.media
        fitted = _fit(source.resolution)
        command = ffmpeg.encode_command(
            media.printf_pattern_for(segment.path) if source.is_sequence else str(segment.path),
            destination,
            segment.start,
            segment.start + (0 if segment.freeze else segment.length - 1),
            is_sequence=source.is_sequence,
            rate=RATE,
            target_size=fitted if fitted != source.resolution else None,
            color_space=source.color_space,
            color_range=source.color_range,
            canvas=SIZE if fitted != SIZE else None,
            hold=segment.length if segment.freeze else 0,
            overlay=overlay,
            silence=True,
            audio_format=ffmpeg.STRINGOUT_AUDIO,
        )
    else:
        command = ffmpeg.black_command(destination, SIZE, RATE, segment.length, overlay)
    _run(command, f"event {segment.event_id or 'gap'}")
    return destination


def _run(command: list[str], what: str) -> None:
    result = ffmpeg.run(command, timeout=ffmpeg.DECODE_TIMEOUT)
    if result.returncode != 0:
        raise StringoutError(f"{what}: {result.stderr.strip()[-500:]}")


def _probe(path: Path) -> tuple[tuple[int, int], bool]:
    """A reference's picture size, and whether it carries sound. One ffprobe."""
    streams = ffmpeg.probe_raw(path).get("streams", [])
    video: dict[str, Any] = next((s for s in streams if s.get("codec_type") == "video"), {})
    size = (int(video.get("width", SIZE[0])), int(video.get("height", SIZE[1])))
    return size, any(stream.get("codec_type") == "audio" for stream in streams)


def _fit(size: tuple[int, int]) -> tuple[int, int]:
    """The source's shape inside 1920x1080, even sized, as a reference is fitted."""
    width, height = size
    scale = min(SIZE[0] / width, SIZE[1] / height)
    return (int(width * scale) // 2 * 2, int(height * scale) // 2 * 2)


def _burn_ins(stem: str, segment: Segment, base: Path) -> list[str]:
    """Ben's four burn-ins, each read from a file, or only the name over a gap."""
    texts = [(ffmpeg.drawtext_literal(stem), CENTRE_X, TOP_Y)]
    if not segment.gap:
        counter = (
            f"Frame: {segment.first_frame}"
            if segment.freeze
            else f"Frame: %{{eif:n+{segment.first_frame}:d}}"
        )
        texts += [
            (counter, LEFT_X, BOTTOM_Y),
            (ffmpeg.drawtext_literal(f"Primary Effect: {segment.effect}"), CENTRE_X, BOTTOM_Y),
            (ffmpeg.drawtext_literal(segment.label), RIGHT_X, BOTTOM_Y),
        ]
    filters = []
    for position, (text, x, y) in enumerate(texts):
        textfile = base.with_name(f"{base.name}_{position}.txt")
        textfile.write_text(text, encoding="utf-8")
        filters.append(ffmpeg.drawtext_filter(textfile, FONT, FONT_SIZE, x, y))
    return filters
