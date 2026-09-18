"""The colour session package: the final EDL, its CDL per event, and any cube beside it.

COLOR_AND_FORMAT section 1. Colour is decided before the tool runs. Ben's session exports
an updated final EDL, and this module is where it is read: the conform, the approved
In/Out, and the **ASC CDL on each event, which is the grade** (decided 2026-09-18,
OQ-46). `core/color.py` supplies the legs either side of it, into ACEScct and out to
ACEScg, and this module supplies the middle.

**"CLF" throughout this module means the per-shot grade file, which is optional and is a
`.cube` from Resolve's Generate LUT** (OQ-54). Out of the same ACEScct session that cube
is the clip's whole node graph, ACEScct in and out, and where one names a shot it takes
the CDL's place in the chain: it is how a grade that needed more than the wheels, a
curve or a second node, reaches the plate. The names stay because a rename across the
batch file's `clf_path`, the EXR header's `proingest/clf` and the QC log would be a
schema change for a word.

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
import logging
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

log = logging.getLogger(__name__)

GRADE_EXTENSIONS = (".cube", ".clf")
"""What a per-shot grade file may be. A `.cube` is what Resolve's Generate LUT writes
(OQ-54); a `.clf` is accepted in the same role for a session that has a way to make one.
OpenColorIO loads either through the same `FileTransform`, so nothing past the index
cares which. The file is optional: the CDL is the grade, and a cube overrides it."""

MATCH_FIELD = "FROM CLIP NAME"
"""The EDL field an event is matched on (OQ-30).

It is the contract the whole naming spec already rests on, so it is the one field that
is checkable against something the tool knows independently. Reel plus source timecode
is the fallback, because Resolve populates reel names differently depending on export
settings and a reel is not required to be unique.
"""

TONE_MAP_STEP_FLOOR = 0.07
"""QC-039's floor: how far apart the two probe samples must still be after the cube.

The probe pushes ACEScct `LOG_WHITE` and `LOG_NEAR_WHITE` through the cube alone and
measures the step between them, per channel, widest channel deciding. A grade-only cube
out of an ACEScct session is log in and log out, so the step is 0.2 for a neutral grade,
scales with the slope, and is untouched by an offset. A display rendering's whole job is
to close that gap: the ACES SDR video output transform leaves 0.02 to 0.04 of it out of
every encoding in play. 0.07 is a slope of 0.35, a far heavier contrast change than any
colourist means by a grade, and not far off twice the widest display rendering measured.

A step rather than the ratio QC-039 used until 2026-09-18 (OQ-47): a ratio was the right
measurement while a grade file ended in scene linear, where an offset in log becomes a
scale. In log space an offset moves both samples together, so a ratio would read a dark
grade as a tone map; a difference is the thing an offset cannot move.
"""

LOG_WHITE = 1.0
"""The probe's upper sample: the top of ACEScct, where a tone map is unmissable."""

LOG_NEAR_WHITE = 0.8
"""The probe's lower sample. Far enough down the curve to have leverage, far enough from
middle grey to still be about the top end. The step between the two is what is measured."""


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
    """A cube that OpenColorIO has accepted, with what the EXR header needs to say.

    `digest` is what identifies the grade: a CLF re-exported and redelivered gets a new
    one, so deliverables rendered from the old version stay findable afterwards. It is
    sha256 rather than the xxhash `qc.file_digest` uses on media, because this one
    leaves the tool and a facility with no OCIO install still has `shasum`.
    """

    path: Path
    digest: str
    transform: ocio.FileTransform
    is_grade_only: bool
    """It leaves the top of ACEScct open the way a grade does, rather than flattening it
    the way a display rendering does (QC-039, `_probe_grade_only`)."""


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

    clf_path: Path | None = None
    cdl: CDL | None = None

    def load(self) -> LoadedClf | None:
        """The cube, loaded hashed and probed, or None when the shot has none."""
        return load_clf(self.clf_path) if self.clf_path is not None else None

    def plate_transforms(self, clf: LoadedClf | None) -> list[ocio.Transform]:
        """The plate branch: into ACEScct, the grade, out to ACEScg. One leg with no grade.

        **The grade means something only in ACEScct** (OQ-46, decided 2026-09-18). It is
        the primaries of node one in a session whose timeline is ACEScct, so the tool gets
        the clip there from the encoding its metadata names and carries the result on to
        ACEScg. A cube from the same session is that grade with the clip's whole node
        graph in it, ACEScct in and out, and takes the CDL's place. Either leg applied in
        a different space is a plausible looking wrong image rather than an error, which
        is why this returns the transforms a chain contains rather than leaving the rule
        to a caller. COLOR_AND_FORMAT section 1 states the same thing as a table.
        """
        if self.source_encoding is None:
            raise ClfError(
                f"no source encoding: nothing turns these pixels into {color.WORKING_SPACE} "
                f"for the grade, or into {color.PLATE_SPACE}. QC-046 and QC-047 report this "
                "before a render"
            )
        grade: ocio.Transform | None
        if clf is not None:
            grade = clf.transform
        elif self.cdl is not None:
            grade = color.cdl_transform(self.cdl)
        else:
            grade = None
        if grade is None:
            return [color.input_transform(self.source_encoding)]
        return [color.to_working(self.source_encoding), grade, color.from_working()]

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
    where the difference is reported rather than here.
    """
    if row.source_encoding is None:
        return None
    try:
        return color.resolve_encoding(row.source_encoding)
    except color.ColorError:
        return None


def has_grade(row: ShotRow) -> bool:
    """Whether the session left this row a grade: a CDL on its event, or a cube naming it.

    One definition, because the ingest report, QC-008, QC-009 and QC-048 all ask it and
    the answer has to be the same one the chain gives.
    """
    return row.cdl is not None or row.clf_path is not None


DEFAULT_SHOT_COLOR = ShotColor()
"""No grade and no encoding: what a job carries until the planner fills it in.

A copy job carries this and ignores it, because bytes are bytes. Anything that renders
pixels is given a real one, and a row that cannot be given one is what QC-046 reports.
"""


@dataclass(frozen=True)
class ColorSession:
    """The package: one final EDL, and any cubes delivered beside it."""

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
        """The cube for a shot, or None when the session delivered none, which is usual."""
        found = self.clfs.get(shot_code, [])
        if len(found) > 1:
            names = ", ".join(path.name for path in found)
            raise AmbiguousClfError(f"{len(found)} grade files name {shot_code}: {names}")
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


SESSION_FOLDER = "_color"
"""The folder beside the turnovers that a session is looked for in (OQ-53).

`<source root>/_color/<turnover folder name>/` holds the final EDL and the CLFs Ben
exported for that turnover. Named like `_reports` and `_turnovers` in the delivery, so
it sorts to the top and cannot be mistaken for a turnover by anyone, including the
scan, which never looks at a sibling folder.
"""


def session_folders(turnover_folder: Path, color_session_folder: Path | None = None) -> list[Path]:
    """Where a turnover's session is looked for, most specific first (OQ-53).

    Under the folder Settings names when it names one, then in the `_color` folder
    beside the turnover; in both, a folder named exactly as the turnover folder is.
    The turnover's own name is the convention because it is the one string the
    editor, Ben and the tool already share.
    """
    roots = [color_session_folder] if color_session_folder else []
    roots.append(turnover_folder.parent / SESSION_FOLDER)
    return [root / turnover_folder.name for root in roots]


def find_session(turnover_folder: Path, color_session_folder: Path | None = None) -> Path | None:
    """The final EDL exported for this turnover, found by convention, or None.

    The first of `session_folders` that exists is the answer, and it has to hold exactly
    one `.edl`, at any depth: two is a folder nobody has tidied, and choosing between
    them is choosing a cut, so it is None and the editor points at the right one
    (`Ingest Colour Session`). The CLFs are not looked for here; `load_session` indexes
    them under the EDL's folder as it always has.
    """
    for folder in session_folders(turnover_folder, color_session_folder):
        if not folder.is_dir():
            continue
        edls = sorted(path for path in folder.rglob("*.edl") if path.is_file())
        if len(edls) == 1:
            return edls[0]
        log.info("%s holds %d .edl files, so no session was offered for it", folder, len(edls))
        return None
    return None


def load_session(
    edl_path: Path, rate: FrameRate, show_pattern: str = naming.DEFAULT_SHOW_PATTERN
) -> ColorSession:
    """Read the final EDL and index any cubes delivered with it.

    The editor points at the EDL (PRD section 6), so the package is whatever sits in
    the folder around it; cubes are found recursively because Resolve is as likely to
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
    """Rows the session left a grade for: a CDL on the event, or a cube (`has_grade`)."""

    overwritten: list[str] = field(default_factory=list)
    """Rows whose one-off trim the approved In/Out replaced. PRD section 6 step 4: the
    session's cut wins and the tool says so, rather than keeping a trim the AD never saw."""

    unmatched: list[str] = field(default_factory=list)
    ambiguous: list[str] = field(default_factory=list)
    """Rows whose shot code more than one cube names. Left to the CDL rather than
    resolved, because picking either one is picking a grade (`AmbiguousClfError`)."""

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
            ("more than one cube names the shot", self.ambiguous),
        )
        return [(label, sorted(names)) for label, names in lists if names]


def ingest(turnover: Turnover, rows: list[ShotRow], session: ColorSession) -> IngestReport:
    """Write what the colour session says onto a turnover and its rows. PRD section 6 step 4.

    **The session is read once, here, and never again.** What it said travels on the
    model afterwards - the approved In/Out, the CDL and any cube's path - so a batch
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
        clf_path=row.clf_path,
        cdl=row.cdl,
    )


def index_clfs(folder: Path, show_pattern: str = naming.DEFAULT_SHOW_PATTERN) -> dict[str, list[Path]]:
    """Every grade file under `folder`, `.cube` or `.clf`, by the shot code in its filename (OQ-33).

    A cube names its shot and that is the whole convention. Anything else in the
    filename is the session's business, and a file naming no shot at all is not an
    error here: it is simply not the cube for any row, and the row grades by its CDL.
    """
    pattern = re.compile(rf"(?P<code>{show_pattern}\d{{4}})")
    found: dict[str, list[Path]] = {}
    for path in sorted(p for p in folder.rglob("*") if p.suffix.lower() in GRADE_EXTENSIONS):
        match = pattern.search(path.stem)
        if match is not None:
            found.setdefault(match["code"], []).append(path)
    return found


def load_clf(path: Path) -> LoadedClf:
    """Load, hash and probe one cube.

    Loading and probing happen together because a cube that loads and has a display
    rendering in it is worse than one that does not load at all: the second stops a
    render and the first finishes one that looks right.
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
        is_grade_only=_probe_grade_only(cpu),
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


def _probe_grade_only(cpu: ocio.CPUProcessor) -> bool:
    """Whether a cube is a grade alone, or has a display rendering baked into it (QC-039).

    Probed rather than trusted, because the filename cannot say and the failure is
    invisible: a plate with a display rendering in it, under a header claiming linear
    ACEScg, looks completely normal until someone tries to comp it. What it catches is a
    tone map, which is what every output transform and film emulation ends with, and what
    it measures is how much **room is left at the top**: two samples near the top of
    ACEScct, and how far apart they still are. A tone map's whole job is to close that gap.

    Per channel, and the widest channel decides. A grade with per channel slopes leaves
    one channel with more range than the others, and one channel with room at the top is
    enough to say nothing flattened it.
    """
    samples = np.array([[[LOG_WHITE] * 3, [LOG_NEAR_WHITE] * 3]], dtype=np.float32)
    color.apply(samples, cpu)
    white, near = samples[0, 0], samples[0, 1]
    return bool(np.any(white - near >= TONE_MAP_STEP_FLOOR))
