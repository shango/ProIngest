"""The turnover stringout: Ben's final EDL, every event in timeline order, as one HD mp4.

OQ-38, reopened 2026-09-25: Ben renders one in Resolve and the tool renders one with
ffmpeg. The user's decisions, all in OQ-38:

- **The cut is the final saved EDL in the turnover**, event for event, gaps included.
- **Each event is cut from its delivered EXRs** (user, 2026-10-07): the HD EXR sequence, or
  a reference still's 4k EXR, so the stringout shows what the vendor works from. **Everything
  in the stringout is graded** (user, 2026-10-07): a plate's EXR has its grade in it already
  and gets its clip's output transform alone; a still's EXR, delivered ungraded, gets its
  clip's looks in ACEScg first. Each is read with OpenEXR, transformed and fitted to HD into
  a lossless intermediate the segment is cut from. The HD EXR's frame 1001 is the HD
  reference's first frame, so every offset is the same either way. **The one exception is an
  HDRI**, cut from its pre-render (below). ffmpeg's own EXR decoder is not used: it left the last rows of a
  small DWAA frame black (measured on ffmpeg 6.1.1, 2026-10-07).
- **An event with no delivered EXR** falls back to its HD reference, then **the source
  through its AMF** (a skipped or failed shot; a clip with no AMF, such as one the CSV gives
  no `Shot Type`, stays as it is), and black when not even that is known.
- **Burn-ins copy Ben's frame** (`burn-ins.png`): the stringout's own name top centre,
  `Frame:` bottom left, `Primary Effect:` (the CSV's `Scene`) bottom centre, and the
  shot and element bottom right. White, Open Sans, no box. No camera timecode: the
  counter is the delivered frame number, 1001 on the frame the plate starts with.
- **A reference clip plays** (user, 2026-10-07): a chart, ball or size ref is a video on the
  timeline, so its event plays its cut at full speed, graded, from the source (its delivery is
  one EXR frame, which cannot play). It was held for a second until then.
- **Any held frame plays for one second** (user, 2026-09-29): a frame hold or a one frame cut,
  a reference clip's from its delivered EXR. **Except a held HDRI, which keeps the EDL's
  length** (user, 2026-09-30). Taken from the source, it is **coloured through its AMF**
  (input transform, CLF nodes, output transform) the way Resolve shows it.
- **An HDRI on the timeline is a frame hold on the HDRI EXR with a pan** (user, 2026-10-07),
  which no EDL carries. Ben renders the event, pan included, beside the EXR under its name as
  a video (`xxxx_001.mp4` beside `xxxx_001.exr`), in sRGB Linear and ungraded. **The event
  is cut from that pre-render**, from its first frame for the event's length, and **coloured
  through the HDRI's AMF**, its own encoding taking the input transform's place. With no
  pre-render (QC-083) the EXR is held for the event's length, graded the same way, read as
  linear Rec.709 like its pre-render.
- **An LDRI is an HDRI whose file is a JPG or PNG** (user, 2026-10-08): its event is cut
  from its pre-render the same way, but **shown as it is, with no grade**, since a JPG or PNG
  is display referred already. With no pre-render the image is held as it is for the event's
  length, as a style frame is.
- **A style frame is held as it is** (user, 2026-10-07): a pre-graded PNG or JPG, `Shot Type`
  `styleFrame`, cut before its shot's plate. It keeps the EDL's length, takes no grade and
  no `Frame:` counter, and is never delivered (QC-085). Its file missing is black.
- **Only a plate has sound**, from its delivered wav; every other segment carries silence of
  the same length.
- **A plate carries its shot's cp top left and wit top right** (user, 2026-09-29), each at
  quarter size flush in its corner (Resolve's zoom 0.25 at X -720/+720, Y 405 on 1920x1080).
  The first cp and the first wit of the shot in EDL order, from their delivered EXRs (or HD
  references), playing from their own cut In at the plate's first frame. Each is gone when
  it runs out or at the plate's Out, whichever is first. No delivered reference, no inset.
  Each carries its own element (`cp01`) a little smaller, bottom left inside it.

Each segment is encoded on its own and the segments are joined by stream copy, which
is safe because every one is encoded with the reference's settings and the same
streams. The join goes to a `.part` beside the destination, is checked (QC-142), and
only then takes its name.
"""

from __future__ import annotations

import logging
import multiprocessing
import shutil
import tempfile
from collections.abc import Callable, Iterable
from concurrent.futures import FIRST_EXCEPTION, ProcessPoolExecutor, ThreadPoolExecutor, as_completed, wait
from concurrent.futures.process import BrokenProcessPool
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Literal

import numpy as np
import numpy.typing as npt
import PyOpenColorIO as ocio

from proingest.core import clf, color, ffmpeg, frames, logsetup, media, naming, qc, resize, scan
from proingest.core import exr as exr_module
from proingest.core.models import (
    DEFAULT_WORKERS,
    Batch,
    Deliverable,
    InOut,
    MediaInfo,
    QCResult,
    ShotRow,
    Turnover,
)
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

STILL_LENGTH = 24
"""A reference still's time on the stringout: one second at 24, whatever the EDL cut."""

INSET_SIZE = (480, 270)
"""Resolve's zoom 0.25 on the 1920x1080 stringout."""

INSET_FONT_SIZE = 32
"""The inset's own label: "slightly smaller" than the frame's burn-ins (user, 2026-09-29)."""
INSET_LABEL_X = "10"
INSET_LABEL_Y = "h-text_h-10"

INSET_CORNERS: dict[str, tuple[int, int]] = {"cp": (0, 0), "wit": (SIZE[0] - INSET_SIZE[0], 0)}
"""Which shot type is inset over a plate, and where its top left corner goes."""

STRINGOUT_RULES = ("QC-142", "QC-143", "QC-144")
"""What a build owns on its turnover, replaced each time it runs."""

SegmentKind = Literal["reference", "source", "black"]


class StringoutError(RuntimeError):
    """A stringout that cannot be planned or did not come out right. Reported as QC-142."""


@dataclass(frozen=True)
class ExrView:
    """A delivered EXR, a sequence's folder or a still's file, and the chain it is seen
    through, ending in its clip's AMF output transform. Made into a picture at render time."""

    source: Path
    color: clf.ShotColor


@dataclass(frozen=True)
class PictureInPicture:
    """An inset over a plate and the element it is (`cp01`), burned in on it."""

    picture: ffmpeg.Inset
    label: str
    exr: ExrView | None = None


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

    identity: naming.ShotIdentity | None = None
    color: clf.ShotColor | None = None
    """A held frame's AMF colour, baked into a LUT for its source segment."""

    insets: tuple[PictureInPicture, ...] = ()
    """A plate's cp and wit, laid over it (`INSET_CORNERS`)."""

    exr: ExrView | None = None
    """The delivered EXR this segment is cut from; `path` becomes its picture at render."""

    wav: Path | None = None
    """A plate's delivered sound, from the frame the delivery starts on."""

    prerender: bool = False
    """An HDRI's pre-render (QC-083): linear, so its cube goes behind a shaper, and the
    event it stands for, so it is no stand-in (QC-143)."""

    style_frame: bool = False
    """A style frame (QC-085): held as it is, with no counter, and no stand-in either."""


@dataclass
class Plan:
    stem: str
    destination: Path
    version: int
    timecode: str
    segments: list[Segment] = field(default_factory=list)
    display: str = ffmpeg.DEFAULT_DISPLAY
    """What the joined file is labelled for: the display the turnover's AMFs name, which is
    what its references were rendered for (2026-09-28). The first graded row's, since one
    colour session views every clip on one display."""

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
        display=next(
            (row.grade.display for row in rows if row.grade is not None and row.grade.display),
            ffmpeg.DEFAULT_DISPLAY,
        ),
    )
    cursor = events[0].record_in
    for event in events:
        if event.record_in > cursor:
            result.segments.append(Segment(kind="black", length=event.record_in - cursor, gap=True))
        result.segments.append(_segment(event, session, rows, show_pattern))
        cursor = max(cursor, event.record_out + 1)
    result.segments = _with_insets(result.segments)
    return result


def _with_insets(segments: list[Segment]) -> list[Segment]:
    """Each plate with its shot's first cp and first wit in EDL order laid over it."""
    first: dict[tuple[str, str], Segment] = {}
    for segment in segments:
        if segment.identity is not None:
            first.setdefault((segment.identity.shot_code, segment.identity.kind), segment)
    placed = []
    for segment in segments:
        if segment.identity is not None and segment.identity.kind == "pl":
            code = segment.identity.shot_code
            found = (
                _inset(first.get((code, kind)), segment.length, corner)
                for kind, corner in INSET_CORNERS.items()
            )
            segment = replace(segment, insets=tuple(inset for inset in found if inset is not None))
        placed.append(segment)
    return placed


def _inset(source: Segment | None, length: int, corner: tuple[int, int]) -> PictureInPicture | None:
    """`source`'s delivered reference from its cut In, for as long as it has or `length`."""
    if source is None or source.kind != "reference" or source.path is None or source.identity is None:
        return None
    frames_held = 1 if source.freeze else source.length
    picture = ffmpeg.Inset(source.path, source.start, min(frames_held, length), *corner, INSET_SIZE)
    return PictureInPicture(picture, source.identity.elem, source.exr)


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
    hdri = next((row for row in claimed if qc.is_hdri(row) and row.hdri_render is not None), None)
    if hdri is not None:
        return _prerender(event, hdri, length, show_pattern)
    style = next((row for row in claimed if qc.is_style_frame(row)), None)
    if style is not None:
        return _style_frame(event, style, length, show_pattern)
    known = next((row for row in claimed if row.media is not None), None)
    cut = _cut(event, known.media) if known is not None and known.media is not None else None
    if known is None or cut is None:
        name = event.clip_stem or event.reel or f"event {event.event_id}"
        held = event.freeze or length == 1
        return Segment(
            kind="black",
            length=STILL_LENGTH if held else length,
            event_id=event.event_id,
            freeze=held,
            label=name,
        )

    exr = next((row for row in claimed if _exr(row, cut, event) is not None), None)
    delivering = exr or next((row for row in claimed if _reference(row, cut) is not None), None)
    row = delivering or next((row for row in claimed if row.approved == cut), known)
    identity = effective_identity(row, show_pattern)
    named = naming.shot_label(identity) if identity is not None else Path(row.clip_name).stem
    label = naming.take_label(named, row.take)
    held = _held(event, cut)
    # A held HDRI keeps the EDL's length (user, 2026-09-30); every other held frame is a second.
    shown = STILL_LENGTH if held and not qc.is_hdri(row) else length
    if exr is not None and exr.delivered_range is not None:
        view = _exr(exr, cut, event)
        assert view is not None
        still = identity is not None and identity.is_still
        offset = 0 if still else cut.in_frame - exr.delivered_range.in_frame
        return Segment(
            kind="reference",
            length=shown,
            event_id=event.event_id,
            first_frame=naming.FIRST_OUTPUT_FRAME + offset,
            freeze=held,
            label=label,
            effect=exr.scene,
            path=view.source,
            start=offset,
            identity=identity,
            exr=view,
            wav=_landed(exr, "audio") if qc.is_plate(exr) else None,
        )
    if delivering is not None and delivering.delivered_range is not None:
        offset = cut.in_frame - delivering.delivered_range.in_frame
        return Segment(
            kind="reference",
            length=shown,
            event_id=event.event_id,
            first_frame=naming.FIRST_OUTPUT_FRAME + offset,
            freeze=held,
            label=label,
            effect=delivering.scene,
            path=_reference(delivering, cut),
            start=offset,
            audio=qc.is_plate(delivering),
            identity=identity,
        )
    still_hdri = _hdri_exr(row) if qc.is_hdri(row) else None
    if still_hdri is not None:
        return Segment(
            kind="reference",
            length=shown,
            event_id=event.event_id,
            freeze=True,  # one image, held for the event's length
            label=label,
            effect=row.scene,
            path=still_hdri.source,
            identity=identity,
            exr=still_hdri,
        )
    base = row.current.in_frame if row.current is not None else cut.in_frame
    return Segment(
        kind="source",
        length=shown,
        event_id=event.event_id,
        first_frame=naming.FIRST_OUTPUT_FRAME + cut.in_frame - base,
        freeze=held,
        label=label,
        effect=row.scene,
        path=known.media.path if known.media is not None else None,
        start=cut.in_frame,
        media=known.media,
        identity=identity,
        # Graded through its AMF (user, 2026-10-07: "everything in the stringout should be graded").
        color=None if qc.is_hdri(row) else clf.shot_color(row),
    )


def _hdri_exr(row: ShotRow) -> ExrView | None:
    """An HDRI with no pre-render (QC-083): its EXR, read as linear Rec.709 like its
    pre-render, through its AMF's grade. None when the AMF names no output transform."""
    shot = replace(clf.shot_color(row), source_encoding=color.HDRI_RENDER_ENCODING)
    if row.media is None or row.media.path.suffix.lower() != ".exr" or not (shot.display and shot.view):
        return None
    return ExrView(row.media.path, shot)


def _prerender(event: clf.ConformEvent, row: ShotRow, length: int, show_pattern: str) -> Segment:
    """An HDRI's event, cut from Ben's pre-render of it: from its first frame for the
    event's length (user, 2026-10-07), through the HDRI's grade."""
    render = row.hdri_render
    assert render is not None
    identity = effective_identity(row, show_pattern)
    return Segment(
        kind="source",
        length=length,
        event_id=event.event_id,
        label=naming.take_label(
            naming.shot_label(identity) if identity is not None else Path(row.clip_name).stem, row.take
        ),
        effect=row.scene,
        path=render.path,
        start=render.start_frame,
        media=render,
        identity=identity,
        color=_prerender_color(row),
        prerender=True,
    )


def _prerender_color(row: ShotRow) -> clf.ShotColor | None:
    """None, the pre-render as it is, for an LDRI (user, 2026-10-08) or when it is on the
    timeline and its AMF carries no grade (QC-009); otherwise the HDRI's grade over linear
    Rec.709 (QC-083)."""
    if qc.is_ldri(row) or (qc.is_hdri_prerender(row) and not clf.has_grade(row)):
        return None
    return replace(clf.shot_color(row), source_encoding=color.HDRI_RENDER_ENCODING)


def _style_frame(event: clf.ConformEvent, row: ShotRow, length: int, show_pattern: str) -> Segment:
    """A style frame's event: its still held as it is for the event's length, or black
    when the file is not there (user, 2026-10-07)."""
    identity = effective_identity(row, show_pattern)
    media = row.media
    return Segment(
        kind="black" if media is None else "source",
        length=length,
        event_id=event.event_id,
        freeze=True,
        label=naming.shot_label(identity) if identity is not None else Path(row.clip_name).stem,
        effect=row.scene,
        path=None if media is None else media.path,
        start=0 if media is None else media.start_frame,
        media=media,
        identity=identity,
        style_frame=True,
    )


def _cut(event: clf.ConformEvent, source: MediaInfo) -> InOut:
    """The event's frames in its file. **Never None: a file that is there plays** (user,
    2026-09-29). A file with no timecode is counted from 00:00:00:00, which is where Resolve
    starts one and what the EDL's source In counts from (turnover097's events 008 and 015
    cut from 00:00:00:00), as a delivery is since 2026-10-07. A single image with no
    timecode has only its one frame."""
    if source.start_timecode is None and not source.is_sequence and source.frame_count <= 1:
        return InOut(source.start_frame, source.start_frame)
    return clf.approved_in_out(event, source)


def _held(event: clf.ConformEvent, cut: InOut) -> bool:
    """One frame on screen: a frame hold, or a one frame cut. Each plays for `STILL_LENGTH`
    on the stringout (user, 2026-09-29). A reference clip plays its cut (user, 2026-10-07)."""
    return event.freeze or cut.duration == 1


def _exr(row: ShotRow, cut: InOut, event: clf.ConformEvent) -> ExrView | None:
    """The row's delivered EXR and the chain it is seen through: its HD sequence when that
    holds the cut, which is graded already, or a reference clip's one frame, which takes its
    clip's looks, when the event holds one frame. None without an output transform to see it
    through, or for a reference clip that plays, which leaves the event to its source."""
    shot = clf.shot_color(row)
    if row.skipped or row.identity is None or row.delivered_range is None or not (shot.display and shot.view):
        return None
    if row.identity.is_still:
        path = _landed(row, "aux_still") if _held(event, cut) else None
        chain = replace(shot, source_encoding=color.PLATE_SPACE)
    else:
        held = row.delivered_range
        inside = held.in_frame <= cut.in_frame and cut.out_frame <= held.out_frame
        path = _landed(row, "raw_dir", "HD") if inside else None
        chain = clf.ShotColor(source_encoding=color.PLATE_SPACE, display=shot.display, view=shot.view)
    return ExrView(path, chain) if path is not None else None


def _landed(row: ShotRow, kind: str, res: str | None = None) -> Path | None:
    """A deliverable of the row that landed and is still there."""
    for item in row.deliverables:
        if (
            item.kind == kind
            and (res is None or item.res == res)
            and item.status in ("done", "exists")
            and item.path.exists()
        ):
            return item.path
    return None


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
    progress: Progress | None = None,
    workers: int = DEFAULT_WORKERS,
) -> Deliverable | None:
    """Plan, render and check one turnover's stringout, and record the outcome on it.

    Never raises: a stringout that could not be made is QC-142 on the turnover, which
    does not block a run (it is phase B), and the delivery it describes is unaffected.
    """
    turnover.qc = [result for result in turnover.qc if result.rule_id not in STRINGOUT_RULES]
    try:
        made = plan(batch, turnover, delivery_root, show_pattern)
        deliverable = render(made, progress, workers)
    except (StringoutError, ffmpeg.FFmpegError, ffmpeg.FFprobeError, OSError) as exc:
        turnover.qc.append(QCResult("QC-142", "error", "turnover", f"the stringout was not written: {exc}"))
        return None
    turnover.stringout = deliverable
    events = [s for s in made.segments if not s.gap and not s.prerender]
    black = [f"{s.event_id} ({s.label})" for s in events if s.kind == "black"]
    stand_ins = [
        f"{s.event_id} ({s.label})"
        for s in events
        if s.exr is None and s.kind != "black" and not s.style_frame
    ]
    if black:
        turnover.qc.append(
            QCResult(
                "QC-144",
                "warning",
                "turnover",
                f"{deliverable.name}: events {', '.join(black)} have nothing to show and are black",
            )
        )
    if stand_ins:
        turnover.qc.append(
            QCResult(
                "QC-143",
                "info",
                "turnover",
                f"{deliverable.name}: events {', '.join(stand_ins)} have no delivered EXR and are "
                f"cut from their HD reference, or the source through its AMF's grade (as it is "
                f"when it has none)",
            )
        )
    return deliverable


Progress = Callable[[int, int], None]
"""Frames done so far and the total, called from the thread building it. Both count the
frames converted from the delivered EXRs (`_make_views`) and then the frames encoded."""


def render(made: Plan, progress: Progress | None = None, workers: int = DEFAULT_WORKERS) -> Deliverable:
    """Convert the EXRs, encode every segment, join them, check the join, and name it."""
    folder = made.destination.parent
    folder.mkdir(parents=True, exist_ok=True)
    # The pictures and segments on this machine's own disk, not beside the stringout: the
    # delivery root is a Google Drive mount, and turnover135's six pictures alone were
    # about 9 GB to write there and delete (2026-10-08). Only the joined file is written
    # in the destination folder, under a temporary name, as every deliverable is.
    parts = Path(tempfile.mkdtemp(prefix=f"{made.stem}.", suffix=".parts"))
    temp = made.destination.with_name(made.destination.name + ".part")
    try:
        wanted = _views_wanted(made, parts)
        converted = sum(len(files) for _, files in wanted.values())
        total = converted + made.total
        views = _make_views(wanted, workers, lambda done: progress(done, total) if progress else None)
        encoded = _encode_all(
            made, views, parts, workers, lambda done: progress(converted + done, total) if progress else None
        )
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


def _encode_all(
    made: Plan, views: dict[ExrView, Path], parts: Path, workers: int, progress: Callable[[int], None]
) -> list[Path]:
    """Every segment encoded, `workers` at a time, in the timeline's order for the join.

    Threads rather than processes: each segment is one ffmpeg run that the thread only
    waits on, and the burn-in, the insets and the cube are written under the segment's
    own index. Several at once because one ffmpeg spends much of a segment in its
    single threaded filters (2026-10-08, turnover135: the 21 events were most of what was
    left once the pictures were fast). Progress is reported here, on the calling thread,
    as each finishes.
    """
    encoded: list[Path | None] = [None] * len(made.segments)
    done = 0
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {
            pool.submit(_encode, made, _seen(segment, views), parts, index): index
            for index, segment in enumerate(made.segments)
        }
        for future in as_completed(futures):
            index = futures[future]
            encoded[index] = future.result()
            done += made.segments[index].length
            progress(done)
    return [path for path in encoded if path is not None]


def _seen(segment: Segment, views: dict[ExrView, Path]) -> Segment:
    """The segment cut from its EXRs' pictures, each made once however often it is used."""
    insets = tuple(
        replace(inset, picture=replace(inset.picture, path=views[inset.exr]))
        if inset.exr is not None
        else inset
        for inset in segment.insets
    )
    path = views[segment.exr] if segment.exr is not None else segment.path
    return replace(segment, path=path, insets=insets)


def _views_wanted(made: Plan, parts: Path) -> dict[ExrView, tuple[Path, list[Path]]]:
    """Every delivered EXR the stringout shows, plates and insets, once each in order of
    first use, with the lossless file it becomes and its frames. One listing each."""
    wanted: dict[ExrView, tuple[Path, list[Path]]] = {}
    for segment in made.segments:
        for exr in (segment.exr, *(inset.exr for inset in segment.insets)):
            if exr is not None and exr not in wanted:
                files = sorted(exr.source.glob("*.exr")) if exr.source.is_dir() else [exr.source]
                wanted[exr] = (parts / f"view{len(wanted):03d}.mkv", files)
    return wanted


def _make_views(
    wanted: dict[ExrView, tuple[Path, list[Path]]], workers: int, progress: Callable[[int], None]
) -> dict[ExrView, Path]:
    """Every EXR made into its picture, **several at once** (user, 2026-10-07: "convert
    the plates in parallel"). Measured on turnover135 before: about 3 minutes per 240
    frame plate, one after another, nearly all of the stringout's time.

    In spawned processes, as the render's are, for the same reason: the macOS target
    spawns, so the tests meet its pickling rules. Each counts its frames into a shared
    counter that is read every second, so the stringout line's bar and time left move
    while the long part runs. One picture, or one worker, is made in this process: a
    spawned interpreter costs a second or two to start and buys nothing then.
    """
    if not wanted:
        return {}
    if len(wanted) == 1 or workers <= 1:
        done = [0]

        def tick() -> None:
            done[0] += 1
            progress(done[0])

        for exr, (destination, files) in wanted.items():
            _write_view(exr, files, destination, tick)
        return {exr: destination for exr, (destination, _) in wanted.items()}

    context = multiprocessing.get_context("spawn")
    counter = context.Value("q", 0)
    log_queue: Any = context.Queue()
    listener = logsetup.start_listener(log_queue)
    initargs = (counter, log_queue, logging.getLogger().getEffectiveLevel(), ffmpeg.current_override())
    try:
        with ProcessPoolExecutor(
            max_workers=min(workers, len(wanted)),
            mp_context=context,
            initializer=_view_worker_init,
            initargs=initargs,
        ) as pool:
            futures = [
                pool.submit(_pooled_view, exr, files, destination)
                for exr, (destination, files) in wanted.items()
            ]
            pending = set(futures)
            while pending:
                finished, pending = wait(pending, timeout=1.0, return_when=FIRST_EXCEPTION)
                progress(int(counter.value))
                for future in finished:
                    future.result()  # a picture that failed fails the stringout (QC-142)
    except BrokenProcessPool as exc:
        raise StringoutError(f"a process converting the EXRs died: {exc}") from exc
    finally:
        listener.stop()
    return {exr: destination for exr, (destination, _) in wanted.items()}


_COUNTER: Any = None
"""This worker's frame counter, shared with the parent. Handed over at process creation,
the only way a `multiprocessing.Value` crosses a spawn."""


def _view_worker_init(counter: Any, log_queue: Any, log_level: int, ffmpeg_override: Path | None) -> None:
    """A spawned worker knows nothing the parent was told: the counter, where its log
    records go (every ffmpeg command is logged, FR-13), and which ffmpeg to run."""
    global _COUNTER
    _COUNTER = counter
    logsetup.install_worker_handler(log_queue, log_level)
    ffmpeg.set_override(ffmpeg_override)


def _pooled_view(exr: ExrView, files: list[Path], destination: Path) -> None:
    _write_view(exr, files, destination, _count_frame)


def _count_frame() -> None:
    with _COUNTER.get_lock():
        _COUNTER.value += 1


def _write_view(exr: ExrView, files: list[Path], destination: Path, tick: Callable[[], None]) -> None:
    """One EXR seen through its output transform and fitted to HD, as a lossless file,
    with `tick` called as each frame is handed to ffmpeg."""
    chain = exr.color.view_transforms()  # refuses a picture with no encoding (QC-046)
    assert exr.color.source_encoding is not None
    cpu = color.baked_processor(exr.color.source_encoding, *chain)

    def shown() -> Iterable[npt.NDArray[np.float32]]:
        for path in files:
            yield _shown(path, cpu)
            tick()

    ffmpeg.write_frames(shown(), SIZE, destination, RATE)


def _shown(path: Path, cpu: ocio.CPUProcessor) -> npt.NDArray[np.float32]:
    """One delivered EXR frame as display values 0..1 on the HD canvas."""
    pixels = np.ascontiguousarray(exr_module.read_pixels(path)[..., :3], dtype=np.float32)
    height, width = pixels.shape[:2]
    if (width, height) != SIZE:
        fitted = resize.fit_inside((width, height), SIZE)
        pixels = np.ascontiguousarray(resize.lanczos_resize(pixels, *fitted), dtype=np.float32)
    color.apply(pixels, cpu)
    return resize.letterbox(np.clip(pixels, 0.0, 1.0), SIZE)


def _quoted(path: Path) -> str:
    """A path inside the concat list's single quotes."""
    return str(path).replace("'", "'\\''")


def _encode(made: Plan, segment: Segment, parts: Path, index: int) -> Path:
    destination = parts / f"{index:04d}.mp4"
    overlay = _burn_ins(made.stem, segment, parts / f"{index:04d}")
    if segment.kind == "reference" and segment.path is not None:
        size, has_audio = _probe(segment.path)
        sound = segment.wav is not None or (segment.audio and has_audio)
        fitted = _fit(size)
        command = ffmpeg.encode_command(
            str(segment.path),
            destination,
            segment.start,
            segment.start + (0 if segment.freeze else segment.length - 1),
            is_sequence=False,
            rate=RATE,
            audio=(segment.wav or segment.path) if sound else None,
            audio_skip=segment.start / 24 if sound else 0.0,
            target_size=fitted if fitted != size else None,
            color_space="bt709",
            color_range="tv",
            canvas=SIZE if fitted != SIZE else None,
            hold=segment.length if segment.freeze else 0,
            overlay=overlay,
            silence=not sound,
            audio_format=ffmpeg.STRINGOUT_AUDIO,
            display=made.display,
            insets=_labelled(segment, parts / f"{index:04d}"),
        )
    elif segment.kind == "source" and segment.path is not None and segment.media is not None:
        source = segment.media
        fitted = _fit(source.resolution)
        last = segment.start + (0 if segment.freeze else segment.length - 1)
        if segment.prerender:
            # A pre-render a frame or two short holds its last frame rather than failing the join.
            last = min(last, source.max_available_out)
        held = segment.freeze or last - segment.start + 1 < segment.length
        lut = _still_lut(segment, parts / f"{index:04d}{LUT_SUFFIX}")
        shaper = parts / f"{index:04d}_shaper{LUT_SUFFIX}"
        command = ffmpeg.encode_command(
            media.printf_pattern_for(segment.path) if source.is_sequence else str(segment.path),
            destination,
            segment.start,
            last,
            is_sequence=source.is_sequence,
            rate=RATE,
            target_size=fitted if fitted != source.resolution else None,
            color_space=source.color_space,
            color_range=source.color_range,
            lut=lut,
            shaper=color.shaper_lut(shaper) if lut is not None and segment.prerender else None,
            canvas=SIZE if fitted != SIZE else None,
            hold=segment.length if held else 0,
            overlay=overlay,
            silence=True,
            audio_format=ffmpeg.STRINGOUT_AUDIO,
            display=made.display,
            insets=_labelled(segment, parts / f"{index:04d}"),
        )
    else:
        command = ffmpeg.black_command(destination, SIZE, RATE, segment.length, overlay, display=made.display)
    _run(command, f"event {segment.event_id or 'gap'}")
    return destination


LUT_SUFFIX = ".cube"


def _still_lut(segment: Segment, destination: Path) -> Path | None:
    """A source segment's AMF colour as the LUT it is encoded through, as a reference's is;
    None, and the source as it is, when its AMF resolves to no chain."""
    if segment.color is None:
        return None
    try:
        return color.view_lut(destination, *segment.color.view_transforms(), shaped=segment.prerender)
    except (clf.ClfError, color.ColorError, ocio.Exception, OSError) as exc:
        log.warning("event %s (%s) is ungraded on the stringout: %s", segment.event_id, segment.label, exc)
        return None


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


def _labelled(segment: Segment, base: Path) -> list[ffmpeg.Inset]:
    """Each inset with its element burned in on it, read from a file like the rest."""
    insets = []
    for position, inset in enumerate(segment.insets):
        textfile = base.with_name(f"{base.name}_inset{position}.txt")
        textfile.write_text(ffmpeg.drawtext_literal(inset.label), encoding="utf-8")
        label = ffmpeg.drawtext_filter(textfile, FONT, INSET_FONT_SIZE, INSET_LABEL_X, INSET_LABEL_Y)
        insets.append(replace(inset.picture, filters=(label,)))
    return insets


def _burn_ins(stem: str, segment: Segment, base: Path) -> list[str]:
    """Ben's four burn-ins, each read from a file, or only the name over a gap."""
    texts = [(ffmpeg.drawtext_literal(stem), CENTRE_X, TOP_Y)]
    if not segment.gap:
        counter = (
            f"Frame: {segment.first_frame}"
            if segment.freeze
            else f"Frame: %{{eif:n+{segment.first_frame}:d}}"
        )
        if not segment.style_frame:  # a style frame has no delivered frame to count
            texts.append((counter, LEFT_X, BOTTOM_Y))
        texts += [
            (ffmpeg.drawtext_literal(f"Primary Effect: {segment.effect}"), CENTRE_X, BOTTOM_Y),
            (ffmpeg.drawtext_literal(segment.label), RIGHT_X, BOTTOM_Y),
        ]
    filters = []
    for position, (text, x, y) in enumerate(texts):
        textfile = base.with_name(f"{base.name}_{position}.txt")
        textfile.write_text(text, encoding="utf-8")
        filters.append(ffmpeg.drawtext_filter(textfile, FONT, FONT_SIZE, x, y))
    return filters
