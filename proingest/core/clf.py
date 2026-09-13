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
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
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

Every output transform tone maps the top end into display range, so a CLF with a
display rendering baked into it answers about 1.0 at white, where a scene linear one
answers what the log encoding's top is worth: 222 from ACEScct, 100 from DaVinci
Intermediate, 38 from S-Log3. A grade in the CLF scales that, so the margin is what is
left after the darkest grade anyone would deliver.

**The margin depends on the source encoding, and since 2026-09-12 that is per clip.**
The floor was calibrated when every CLF started at ACEScct and 2.0 sat clear of both
ends. It no longer does for every camera: C-Log3 white is worth 14.7, so four stops of
grade in the CLF answers 0.92 and this probe calls a valid CLF a display rendering.
Recorded as OQ-47 with the numbers, and not changed here, because it is QC-039's
definition rather than M4.6.2's chain.

What it does not catch either way is a transfer curve with no tone map in it, which is
not something an ACES session exports.
"""

LOG_WHITE = 1.0
"""The probe value: the top of the log encoding, where a tone map is unmissable.

Whichever log the CLF starts at. It was named for ACEScct, which was the only thing a
CLF could start at before 2026-09-12; the value is 1.0 for the same reason under every
camera log, which is that the top of the code range is where a display rendering is
forced to give itself away.
"""


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
class ShotColor:
    """One shot's colour, in the form that survives a pickle to a worker process.

    A render job is self contained (`planner.DeliverableJob`), so what a worker needs to
    know about colour travels on it. That rules out holding an `ocio` object or a
    `LoadedClf`: neither pickles, and a transform built in the parent could not cross a
    spawn boundary anyway. What crosses is a path, a colour space name and the CDL, and
    the worker calls `load` once per job to turn the path back into a transform.

    Loading per job rather than per shot costs a few kilobytes read four times and buys
    a digest taken at render time, which is the one that describes what was applied.

    The default is a shot with no grade and no encoding resolved for it, which is the
    honest starting point rather than a usable chain: a row with no CLF renders through
    the input transform alone, and that needs an encoding the clip's metadata names.
    """

    source_encoding: str | None = None
    """The colour space the input transform starts at, resolved from what the clip named.

    None where the clip's metadata named no encoding, or named one the input transform
    table could not resolve (QC-046, QC-047). That is renderable on a graded row, since
    the CLF is the whole chain there, and it is not renderable on any other.
    """

    source_encoding_origin: SourceEncodingOrigin | None = None
    """Which carrier named it, carried so the delivered EXR header can say.

    It describes the row's written name rather than the colour space above it, which is
    what the resolution was performed on. Set even where `source_encoding` is None, since
    a name that resolved to nothing still came from somewhere; `exr.provenance` writes it
    only beside an encoding, because an origin with nothing to originate says nothing.
    """

    clf_path: Path | None = None
    cdl: CDL | None = None

    def load(self) -> LoadedClf | None:
        """The CLF, loaded hashed and probed, or None when the shot has no grade."""
        return load_clf(self.clf_path) if self.clf_path is not None else None

    def plate_transforms(self, clf: LoadedClf | None) -> list[ocio.Transform]:
        """The plate branch: the CLF alone, or the source encoding to ACEScg where there is none.

        **The tool applies no input transform ahead of a CLF** (OQ-37, answered
        2026-09-12). The colourist starts each shot's CLF at whatever that clip is
        encoded in and ends it in linear ACEScg (QC-039), so the CLF is the entire
        transform and anything applied either side of it converts twice. That is a
        plausible looking wrong image rather than an error, which is why this returns
        the transforms a chain contains rather than leaving the rule to a caller.
        COLOR_AND_FORMAT section 1 states the same thing as a table.
        """
        if clf is not None:
            return [clf.transform]
        if self.source_encoding is None:
            raise ClfError(
                "no CLF and no source encoding: nothing turns these pixels into "
                f"{color.PLATE_SPACE}. QC-046 and QC-047 report this before a render"
            )
        return [color.input_transform(self.source_encoding)]

    def view_transforms(self, clf: LoadedClf | None) -> list[ocio.Transform]:
        """The view branch: the plate branch, then the ACES output transform to sRGB.

        The two branches share everything up to linear ACEScg, which is why this is the
        plate chain plus one leg rather than a chain of its own.
        """
        return [*self.plate_transforms(clf), color.output_transform()]


def resolved_encoding(row: ShotRow) -> str | None:
    """The colour space this row's clip named, or None when nothing resolves to one.

    One definition because two paths build a `ShotColor`: with a colour session and
    without one. None covers both a clip that named no encoding (QC-046) and one whose
    name the input transform table could not resolve (QC-047); the chain treats them
    identically, since neither gives it anything to convert with, and the rules are
    where the difference is reported. An unresolvable name is not raised here because a
    graded row renders correctly without it: the CLF is the whole chain.
    """
    if row.source_encoding is None:
        return None
    try:
        return color.resolve_encoding(row.source_encoding)
    except color.ColorError:
        return None


DEFAULT_SHOT_COLOR = ShotColor()
"""No grade and no encoding: what a job carries until the planner fills it in.

A copy job carries this and ignores it, because bytes are bytes. Anything that renders
pixels is given a real one, and a row that cannot be given one is what QC-046 reports.
"""


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
            if event.reel.casefold() == shot_code.casefold()
            and first <= event.source_in <= event.source_out <= last
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


@dataclass(frozen=True)
class IngestReport:
    """What ingesting one turnover's colour session did to its rows.

    Returned rather than logged because every list on it is something a person acts on:
    an unmatched row will not render, an overwritten trim is work the editor has just
    lost, and an ambiguous CLF is a redelivery somebody has to clean up. The rules
    report the same facts at run time (QC-008, QC-009); this reports them at the moment
    the editor can still do something about them.
    """

    edl_path: Path
    events: int
    matched: list[str] = field(default_factory=list)
    graded: list[str] = field(default_factory=list)
    overwritten: list[str] = field(default_factory=list)
    """Rows whose one-off trim the approved In/Out replaced. PRD section 6 step 4: the
    session's cut wins and the tool says so, rather than keeping a trim the AD never saw."""

    unmatched: list[str] = field(default_factory=list)
    ambiguous: list[str] = field(default_factory=list)
    """Rows whose shot code more than one CLF names. Left ungraded rather than resolved,
    because picking either one is picking a grade (`AmbiguousClfError`)."""

    @property
    def counts(self) -> str:
        """What the ingest did, in the one phrase every surface says it in."""
        return f"{len(self.matched)} rows matched, {len(self.graded)} with a CLF"

    def notices(self) -> list[tuple[str, list[str]]]:
        """The three lists a person acts on, labelled, and only where there is anything.

        The labels live here rather than in each caller because the CLI and the window
        both report an ingest and the editor compares what the two said.
        """
        lists = (
            ("no event", self.unmatched),
            ("trim overwritten by the approved cut", self.overwritten),
            ("more than one CLF names the shot", self.ambiguous),
        )
        return [(label, sorted(names)) for label, names in lists if names]


def ingest(turnover: Turnover, rows: list[ShotRow], session: ColorSession) -> IngestReport:
    """Write what the colour session says onto a turnover and its rows. PRD section 6 step 4.

    **The session is read once, here, and never again.** What it said travels on the
    model afterwards - the approved In/Out, the CDL and the CLF path - so a batch
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
        try:
            row.clf_path = session.clf_for(row.shot_code) if row.shot_code else None
        except AmbiguousClfError:
            row.clf_path = None
            report.ambiguous.append(row.clip_name)
        if row.clf_path is not None:
            report.graded.append(row.clip_name)
    return report


def shot_color(row: ShotRow) -> ShotColor:
    """What this row's deliverables are rendered through, read off the row alone.

    One definition, and the only one since the session is ingested rather than carried:
    a planned row and a reopened batch resolve their colour the same way, from the four
    fields ingest filled in. A row nothing was ingested for carries no CLF, which renders
    through the input transform alone and is QC-009.
    """
    return ShotColor(
        source_encoding=resolved_encoding(row),
        source_encoding_origin=row.source_encoding_origin,
        clf_path=row.clf_path,
        cdl=row.cdl,
    )


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
    white = np.array([[[LOG_WHITE, LOG_WHITE, LOG_WHITE]]], dtype=np.float32)
    color.apply(white, cpu)
    return bool(white.max() > SCENE_LINEAR_FLOOR)
