"""The colour session package: the final EDL, and the CLF that goes with each row.

COLOR_AND_FORMAT section 1. Colour is finished before the tool runs. Ben's session
exports an updated final EDL and one CLF per shot, and this module is where both are
read: the EDL for the conform, the approved In/Out and the CDL, and the CLF matched to
a row, loaded, hashed and probed. `core/color.py` supplies the transforms either side
of it and this module supplies the middle.

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

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import PyOpenColorIO as ocio

from proingest.core import color, frames, naming
from proingest.core.models import FrameRate, InOut, MediaInfo, ShotRow

CLF_EXTENSION = ".clf"

MATCH_FIELD = "FROM CLIP NAME"
"""The EDL field an event is matched on (OQ-30).

It is the contract the whole naming spec already rests on, so it is the one field that
is checkable against something the tool knows independently. Reel plus source timecode
is the fallback, because Resolve populates reel names differently depending on export
settings and a reel is not required to be unique.
"""

SCENE_LINEAR_FLOOR = 2.0
"""What a CLF's white has to exceed for the output to be scene linear (QC-039).

ACEScct 1.0 is 222 in scene linear, and every output transform tone maps the top end
into display range, so a CLF with a display rendering baked into it answers about 1.0.
An ungraded chain answers 222, four stops down answers 13.9 and six stops down 3.5, so
2.0 sits clear of a grade darker than anyone would deliver and clear of every display
render. What it does not catch is a transfer curve with no tone map in it, which is not
something an ACES session exports.
"""

ACESCCT_WHITE = 1.0
"""The probe value: the top of the log encoding, where a tone map is unmissable."""


class ColorSessionError(RuntimeError):
    """The colour session package cannot be read. Reported as QC-008."""


class ClfError(RuntimeError):
    """A CLF that will not load in OpenColorIO. Reported as QC-019."""


class AmbiguousClfError(ClfError):
    """More than one CLF names the same shot.

    An error rather than a choice: the session exports one CLF per shot, so two is a
    redelivery that was not cleaned up, and picking either one is picking a grade.
    """


@dataclass(frozen=True)
class CDL:
    """One event's ASC CDL, as numbers and as the lines it was written on.

    Both forms are delivered. The numbers go into the EXR header as attributes, and the
    text goes in verbatim because it is what another facility's tool reads and what a
    human compares against the session. Neither is ever applied: the CLF is.
    """

    slope: tuple[float, float, float]
    offset: tuple[float, float, float]
    power: tuple[float, float, float]
    saturation: float
    sop_text: str
    sat_text: str


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
class LoadedClf:
    """A CLF that OpenColorIO has accepted, with what the EXR header needs to say.

    `digest` is what identifies the grade: a CLF re-exported and redelivered gets a new
    one, so deliverables rendered from the old version stay findable afterwards. It is
    sha256 rather than the xxhash `qc.file_digest` uses on media, because this one
    leaves the tool and a facility with no OCIO install still has `shasum`.
    """

    path: Path
    digest: str
    transform: ocio.FileTransform
    is_scene_linear: bool


@dataclass(frozen=True)
class ColorSession:
    """The package: one final EDL, and the CLFs delivered beside it."""

    edl_path: Path
    events: list[ConformEvent]
    clfs: dict[str, list[Path]]

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

    def clf_for(self, shot_code: str) -> Path | None:
        """The CLF for a shot, or None when the session delivered none (QC-009)."""
        found = self.clfs.get(shot_code, [])
        if len(found) > 1:
            names = ", ".join(path.name for path in found)
            raise AmbiguousClfError(f"{len(found)} CLFs name {shot_code}: {names}")
        return found[0] if found else None

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
            if event.reel == shot_code and first <= event.source_in <= event.source_out <= last
        ]
        return matched[0] if len(matched) == 1 else None


def load_session(
    edl_path: Path, rate: FrameRate, show_pattern: str = naming.DEFAULT_SHOW_PATTERN
) -> ColorSession:
    """Read the final EDL and index the CLFs delivered with it.

    The editor points at the EDL (PRD section 6), so the package is whatever sits in
    the folder around it; CLFs are found recursively because Resolve is as likely to
    export them into a subfolder as beside it.
    """
    events = read_final_edl(edl_path, rate)
    clfs = index_clfs(edl_path.parent, show_pattern)
    return ColorSession(edl_path=edl_path, events=events, clfs=clfs)


def index_clfs(
    folder: Path, show_pattern: str = naming.DEFAULT_SHOW_PATTERN
) -> dict[str, list[Path]]:
    """Every CLF under `folder`, by the shot code in its filename (OQ-33).

    A CLF names its shot and that is the whole convention. Anything else in the
    filename is the session's business, and a file naming no shot at all is not an
    error here: it is simply not the CLF for any row, and the row that wanted one
    reports QC-009.
    """
    pattern = re.compile(rf"(?P<code>{show_pattern}\d{{4}})")
    found: dict[str, list[Path]] = {}
    for path in sorted(folder.rglob(f"*{CLF_EXTENSION}")):
        match = pattern.search(path.stem)
        if match is not None:
            found.setdefault(match["code"], []).append(path)
    return found


def load_clf(path: Path) -> LoadedClf:
    """Load, hash and probe one CLF.

    Loading and probing happen together because a CLF that loads and lands in the wrong
    place is worse than one that does not load at all: the second stops a render and the
    first finishes one that looks right.
    """
    if not path.is_file():
        raise ClfError(f"{path} does not exist")
    transform = ocio.FileTransform(src=str(path), interpolation=color.INTERPOLATION)
    try:
        cpu = color.processor(transform)
    except Exception as exc:
        raise ClfError(f"{path} will not load in OpenColorIO: {exc}") from exc
    return LoadedClf(
        path=path,
        digest=clf_digest(path),
        transform=transform,
        is_scene_linear=_probe_scene_linear(cpu),
    )


def clf_digest(path: Path) -> str:
    """sha256 of a CLF, and named apart from `qc.file_digest` because it is not the same.

    That one is xxhash over media, chosen for speed on gigabytes. This one is over a few
    kilobytes and leaves the tool in an EXR header, where a facility with no OCIO install
    still has `shasum`. Two digests under one name would agree on nothing and look like
    a corruption.
    """
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 16), b""):
            digest.update(block)
    return digest.hexdigest()


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
        text = path.read_text(errors="ignore")
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
            raise ColorSessionError(
                f"{path}: event {head['event']} states {len(found)} timecodes, not four"
            )
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


def _probe_scene_linear(cpu: ocio.CPUProcessor) -> bool:
    """Whether a CLF lands in scene linear, or has a display rendering in it (QC-039).

    Probed rather than trusted, because the filename cannot say and the failure is
    invisible: a display referred plate that claims to be linear looks completely normal
    until someone tries to comp it. What it catches is a tone map, which is what every
    output transform and film emulation ends with.
    """
    white = np.array([[[ACESCCT_WHITE, ACESCCT_WHITE, ACESCCT_WHITE]]], dtype=np.float32)
    color.apply(white, cpu)
    return bool(white.max() > SCENE_LINEAR_FLOOR)
