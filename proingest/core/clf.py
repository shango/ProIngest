"""Ben's final EDL: the conform, and the CDL on each event, which is the grade.

COLOR_AND_FORMAT section 1. Colour is decided before the tool runs. Ben's session exports
an updated final EDL, and this module is where it is read: the conform, the approved
In/Out, and the **ASC CDL on each event, which is the grade** (decided 2026-09-18,
OQ-46). `core/color.py` supplies the legs either side of it, into ACEScct and out to
ACEScg, and this module supplies the middle.

**There are no per-shot grade files** (user, 2026-09-22). The CDL on the event is the
whole grade, and nothing beside the EDL is read: no `.cube`, no `.clf`, anywhere. What
went with them is QC-019, QC-039 and the probe that asked whether a cube had a display
rendering baked into it. The module keeps its name because it is still the module that
reads the session.

**The EDL is parsed here rather than through `core/timeline.py`.** That module reads the
shooters' timeline through otio, which is the right tool for a conform and the wrong one
here: otio's CMX3600 adapter hands back the CDL as numbers and drops the event id and the
verbatim `*ASC_SOP` / `*ASC_SAT` lines, and a delivered EXR is specified to carry that
original text (COLOR_AND_FORMAT, EXR metadata). An event line is a fixed format, so
reading it directly costs less than reconstructing what the adapter threw away, and
timecode still goes through `frames.timecode_to_frames`, which refuses drop-frame.

**Which field identifies a row is one constant, `MATCH_FIELD`** (OQ-30, OQ-33). Every
failure in this module looks entirely plausible on screen: a row paired with a
neighbour's event takes the wrong approved In/Out, and a row paired with a neighbour's
CLF ships the wrong grade under the right filename. Nothing here guesses at the nearest
candidate. It matches or it reports nothing matched, and QC-009 is what fires.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

import PyOpenColorIO as ocio

from proingest.core import color, frames, naming
from proingest.core.models import (
    CDL,
    FrameRate,
    InOut,
    MediaInfo,
    ShotRow,
    SourceEncodingOrigin,
    Turnover,
)

log = logging.getLogger(__name__)

MATCH_FIELD = "FROM CLIP NAME"
"""The EDL field an event is matched on (OQ-30).

It is the contract the whole naming spec already rests on, so it is the one field that
is checkable against something the tool knows independently. Reel plus source timecode
is the fallback, because Resolve populates reel names differently depending on export
settings and a reel is not required to be unique.
"""


class ColorSessionError(RuntimeError):
    """The colour session package cannot be read. Reported as QC-008."""


class ClfError(RuntimeError):
    """A chain that cannot be built, most often because nothing resolved the encoding."""


@dataclass(frozen=True)
class ConformEvent:
    """One event of the colour session's final EDL.

    Source and record values are frames at the EDL's rate, and both ranges are
    inclusive: an EDL's own out timecode is the first frame after the cut and it is
    converted on the way in, so nothing downstream has to remember which convention
    this came from.
    """

    event_id: str
    reel: str
    clip_name: str
    source_in: int
    source_out: int
    record_in: int
    record_out: int
    cdl: CDL | None = None

    @property
    def duration(self) -> int:
        return frames.duration(self.source_in, self.source_out)

    @property
    def clip_stem(self) -> str:
        """`FROM CLIP NAME` without its extension, which is what a clip name is."""
        return Path(self.clip_name).stem


@dataclass(frozen=True)
class ShotColor:
    """One shot's colour, in the form that survives a pickle to a worker process.

    A render job is self contained (`planner.DeliverableJob`), so what a worker needs to
    know about colour travels on it. That rules out holding an `ocio` object: it does not
    pickle, and a transform built in the parent could not cross a spawn boundary anyway.
    What crosses is a colour space name and the CDL, which are both plain data.

    The default is a shot with no grade and no encoding resolved for it, which is the
    honest starting point rather than a usable chain: every chain starts at the encoding
    the clip's metadata names, and a shot with no grade renders through that leg alone.
    """

    source_encoding: str | None = None
    """The colour space the input transform starts at, resolved from what the clip named.

    None where the clip's metadata named no encoding, or named one the input transform
    table could not resolve (QC-046, QC-047). Nothing renders without it: the grade is
    applied in ACEScct and this is what gets the clip there.
    """

    source_encoding_origin: SourceEncodingOrigin | None = None
    """Which carrier named it, carried so the delivered EXR header can say.

    It describes the row's written name rather than the colour space above it, which is
    what the resolution was performed on. Set even where `source_encoding` is None, since
    a name that resolved to nothing still came from somewhere; `exr.provenance` writes it
    only beside an encoding, because an origin with nothing to originate says nothing.
    """

    cdl: CDL | None = None

    def plate_transforms(self) -> list[ocio.Transform]:
        """The plate branch: into ACEScct, the CDL, out to ACEScg. One leg with no grade.

        **The grade means something only in ACEScct** (OQ-46, decided 2026-09-18). It is
        the primaries of node one in a session whose timeline is ACEScct, so the tool gets
        the clip there from the encoding its metadata names and carries the result on to
        ACEScg. Either leg applied in a different space is a plausible looking wrong image
        rather than an error, which is why this returns the transforms a chain contains
        rather than leaving the rule to a caller. COLOR_AND_FORMAT section 1 states the
        same thing as a table.
        """
        if self.source_encoding is None:
            raise ClfError(
                f"no source encoding: nothing turns these pixels into {color.WORKING_SPACE} "
                f"for the grade, or into {color.PLATE_SPACE}. QC-046 and QC-047 report this "
                "before a render"
            )
        if self.cdl is None:
            return [color.input_transform(self.source_encoding)]
        return [color.to_working(self.source_encoding), color.cdl_transform(self.cdl), color.from_working()]

    def view_transforms(self) -> list[ocio.Transform]:
        """The view branch: the plate branch, then the ACES output transform to sRGB.

        The two branches share everything up to linear ACEScg, which is why this is the
        plate chain plus one leg rather than a chain of its own.
        """
        return [*self.plate_transforms(), color.output_transform()]


def resolved_encoding(row: ShotRow) -> str | None:
    """The colour space this row's clip named, or None when nothing resolves to one.

    One definition because two paths build a `ShotColor`: with a colour session and
    without one. None covers both a clip that named no encoding (QC-046) and one whose
    name the input transform table could not resolve (QC-047); the chain treats them
    identically, since neither gives it anything to convert with, and the rules are
    where the difference is reported rather than here.
    """
    if row.source_encoding is None:
        return None
    try:
        return color.resolve_encoding(row.source_encoding)
    except color.ColorError:
        return None


def has_grade(row: ShotRow) -> bool:
    """Whether the session left this row a grade: a CDL on its event.

    One definition, because the ingest report, QC-008, QC-009 and QC-048 all ask it and
    the answer has to be the same one the chain gives. Since 2026-09-22 that is the CDL
    and nothing else, there being no per-shot grade files.
    """
    return row.cdl is not None


DEFAULT_SHOT_COLOR = ShotColor()
"""No grade and no encoding: what a job carries until the planner fills it in.

A copy job carries this and ignores it, because bytes are bytes. Anything that renders
pixels is given a real one, and a row that cannot be given one is what QC-046 reports.
"""


@dataclass(frozen=True)
class ColorSession:
    """One final EDL, read once. It is the whole of what Ben's session hands over."""

    edl_path: Path
    events: list[ConformEvent]

    def event_for(self, row: ShotRow) -> ConformEvent | None:
        """The event that conforms this row, or None when nothing matches it.

        `MATCH_FIELD` first, compared without the extension and without case, because a
        case difference between a Resolve export and a macOS filesystem is not a
        disagreement about which shot this is. Reel plus source timecode is the
        fallback, and it has to agree on both.
        """
        for event in self.events:
            if event.clip_stem.casefold() == row.clip_name.casefold():
                return event
        return self._event_by_reel(row)

    def _event_by_reel(self, row: ShotRow) -> ConformEvent | None:
        """Reel plus source timecode, which is OQ-30's fallback.

        The reel has to be the row's shot code and the event's source range has to sit
        inside the media's own timecode. Either alone is too weak: reels repeat across
        a turnover, and the same timecode turns up on every reel that was not jam
        synced.
        """
        shot_code, media = row.shot_code, row.media
        if shot_code is None or media is None or media.start_timecode is None:
            return None
        first = media.start_timecode
        last = first + media.frame_count - 1
        matched = [
            event
            for event in self.events
            if event.reel.casefold() == shot_code.casefold()
            and first <= event.source_in <= event.source_out <= last
        ]
        return matched[0] if len(matched) == 1 else None


def load_session(
    edl_path: Path, rate: FrameRate, show_pattern: str = naming.DEFAULT_SHOW_PATTERN
) -> ColorSession:
    """Read the final EDL. It is the whole session as far as this tool is concerned."""
    return ColorSession(edl_path=edl_path, events=read_final_edl(edl_path, rate))


@dataclass(frozen=True)
class IngestReport:
    """What ingesting one turnover's colour session did to its rows.

    Returned rather than logged because every list on it is something a person acts on:
    an unmatched row will not render and an overwritten trim is work the editor has just
    lost. The rules report the same facts at run time (QC-008, QC-009); this reports them
    at the moment the editor can still do something about them.
    """

    edl_path: Path
    events: int
    matched: list[str] = field(default_factory=list)
    graded: list[str] = field(default_factory=list)
    """Rows the session left a grade for: a CDL on the event (`has_grade`)."""

    overwritten: list[str] = field(default_factory=list)
    """Rows whose one-off trim the approved In/Out replaced. PRD section 6 step 4: the
    session's cut wins and the tool says so, rather than keeping a trim the AD never saw."""

    unmatched: list[str] = field(default_factory=list)

    @property
    def counts(self) -> str:
        """What the ingest did, in the one phrase every surface says it in."""
        return f"{len(self.matched)} rows matched, {len(self.graded)} graded"

    def notices(self) -> list[tuple[str, list[str]]]:
        """The three lists a person acts on, labelled, and only where there is anything.

        The labels live here rather than in each caller because the CLI and the window
        both report an ingest and the editor compares what the two said.
        """
        lists = (
            ("no event", self.unmatched),
            ("trim overwritten by the approved cut", self.overwritten),
        )
        return [(label, sorted(names)) for label, names in lists if names]


def ingest(turnover: Turnover, rows: list[ShotRow], session: ColorSession) -> IngestReport:
    """Write what the colour session says onto a turnover and its rows. PRD section 6 step 4.

    **The session is read once, here, and never again.** What it said travels on the
    model afterwards - the approved In/Out and the CDL - so a batch
    reopened after the package has been archived plans the same grade, and the planner
    needs no session at all. The turnover keeps the EDL's location as the record of
    where the answers came from.

    **The approved cut wins over a trim already made.** Ben and the AD trimmed in the
    session and that is the cut that was signed off, so `current` is written from
    `approved` and the rows that lost a trim are named in the report (FR-5). A trim made
    *after* an ingest is the supported one-off, and QC-045 is what reports it.

    A row the session says nothing about keeps everything it had. Nothing here guesses:
    an unmatched row is reported, not conformed to its neighbour's event.
    """
    report = IngestReport(edl_path=session.edl_path, events=len(session.events))
    turnover.color_session_edl = session.edl_path
    for row in rows:
        event = session.event_for(row)
        if event is not None:
            report.matched.append(row.clip_name)
            approved = approved_in_out(event, row.media) if row.media else None
            row.cdl = event.cdl
            if approved is not None:
                if row.current is not None and row.current != approved:
                    report.overwritten.append(row.clip_name)
                row.approved = approved
                row.current = approved
        else:
            report.unmatched.append(row.clip_name)
        if has_grade(row):
            report.graded.append(row.clip_name)
    return report


def shot_color(row: ShotRow) -> ShotColor:
    """What this row's deliverables are rendered through, read off the row alone.

    One definition, and the only one since the session is ingested rather than carried:
    a planned row and a reopened batch resolve their colour the same way, from the four
    fields ingest filled in. A row nothing was ingested for carries no grade, which
    renders through the input transform alone and is QC-009.
    """
    return ShotColor(
        source_encoding=resolved_encoding(row),
        source_encoding_origin=row.source_encoding_origin,
        cdl=row.cdl,
    )


def approved_in_out(event: ConformEvent, media: MediaInfo) -> InOut | None:
    """The event's source range as frame indices into this media.

    None when the media states no start timecode, because then an EDL's source timecode
    says nothing about which frames it means. The caller reports that; guessing an
    origin here would silently conform every row to the wrong frames.
    """
    if media.start_timecode is None:
        return None
    start = media.start_frame + (event.source_in - media.start_timecode)
    return InOut(start, start + event.duration - 1)


def read_final_edl(path: Path, rate: FrameRate) -> list[ConformEvent]:
    """Parse the colour session's final EDL into events, in file order.

    Video events only: an audio only event conforms nothing, and an EDL that carries
    both has the picture event for the same cut anyway.
    """
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError as exc:
        raise ColorSessionError(f"could not read {path}: {exc}") from exc

    events: list[ConformEvent] = []
    pending: _Event | None = None
    for line in text.splitlines():
        head = _EVENT_HEAD.match(line)
        if head is not None:
            if pending is not None:
                events.append(pending.build(path, rate))
            pending = _Event(head) if _is_video(head["channel"]) else None
            continue
        if pending is not None:
            pending.comment(line)
    if pending is not None:
        events.append(pending.build(path, rate))

    if not events:
        raise ColorSessionError(f"{path} carries no video events")
    return events


_EVENT_HEAD = re.compile(
    r"^(?P<event>\d{3,})\s+(?P<reel>\S+)\s+(?P<channel>\S+)\s+(?P<edit>[A-Z]+)\b(?P<rest>.*)$"
)
_TIMECODE = re.compile(r"\d{1,2}:\d{2}:\d{2}[:;]\d{2}")
_FROM_CLIP = re.compile(r"^\*\s*FROM CLIP NAME:\s*(?P<name>.+?)\s*$", re.IGNORECASE)
_ASC_SOP = re.compile(r"^\*\s*ASC_SOP\b", re.IGNORECASE)
_ASC_SAT = re.compile(r"^\*\s*ASC_SAT\s+(?P<value>\S+)", re.IGNORECASE)
_TRIPLE = re.compile(r"\(\s*(?P<a>\S+)\s+(?P<b>\S+)\s+(?P<c>\S+)\s*\)")


def _is_video(channel: str) -> bool:
    """`V`, or `B` and `AA/V` which carry picture and audio together."""
    return "V" in channel.upper() or channel.upper() == "B"


class _Event:
    """One event under construction: the head line, then the comments under it."""

    def __init__(self, head: re.Match[str]) -> None:
        self.head = head
        self.clip_name = ""
        self.sop_text = ""
        self.sat_text = ""

    def comment(self, line: str) -> None:
        from_clip = _FROM_CLIP.match(line)
        if from_clip is not None:
            self.clip_name = from_clip["name"]
        elif _ASC_SOP.match(line):
            self.sop_text = line.strip()
        elif _ASC_SAT.match(line):
            self.sat_text = line.strip()

    def build(self, path: Path, rate: FrameRate) -> ConformEvent:
        head = self.head
        found = _TIMECODE.findall(head["rest"])
        if len(found) < 4:
            raise ColorSessionError(f"{path}: event {head['event']} states {len(found)} timecodes, not four")
        try:
            times = [frames.timecode_to_frames(value, rate.as_float()) for value in found[-4:]]
        except ValueError as exc:
            raise ColorSessionError(f"{path}: event {head['event']} has {exc}") from exc
        source_in, source_out, record_in, record_out = times
        return ConformEvent(
            event_id=head["event"],
            reel=head["reel"],
            clip_name=self.clip_name,
            source_in=source_in,
            source_out=source_out - 1,
            record_in=record_in,
            record_out=record_out - 1,
            cdl=_parse_cdl(self.sop_text, self.sat_text),
        )


def _parse_cdl(sop_text: str, sat_text: str) -> CDL | None:
    """The CDL off an event's comment lines, or None when it carries neither.

    A partial CDL is None rather than a default: slope 1 offset 0 power 1 is a real
    grade that says do nothing, so standing in for a missing line would record a
    neutral grade the colourist never wrote.
    """
    if not sop_text or not sat_text:
        return None
    triples = list(_TRIPLE.finditer(sop_text))
    saturation = _ASC_SAT.match(sat_text)
    if len(triples) != 3 or saturation is None:
        return None
    try:
        slope, offset, power = (_triple(match) for match in triples)
        return CDL(
            slope=slope,
            offset=offset,
            power=power,
            saturation=float(saturation["value"]),
            sop_text=sop_text,
            sat_text=sat_text,
        )
    except ValueError:
        return None


def _triple(match: re.Match[str]) -> tuple[float, float, float]:
    return float(match["a"]), float(match["b"]), float(match["c"])
