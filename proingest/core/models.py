"""Data model for a batch.

Plain dataclasses with explicit dict conversion. Core stays dependency-light and
`mypy --strict` clean, and the JSON shape is visible in one place rather than
inferred from a library's behaviour.

Everything here is JSON round-trippable: `to_dict` and `from_dict` are inverses, and
that is asserted in the tests. The batch file is schema versioned, so changing a
field name is a migration, not an edit.
"""

from __future__ import annotations

from dataclasses import MISSING, asdict, dataclass, field, fields
from fractions import Fraction
from pathlib import Path
from typing import Any, Literal

from proingest.core import frames
from proingest.core.naming import ShotIdentity

SCHEMA_VERSION = 1

DEFAULT_WORKERS = 4
"""Capped rather than one per core on purpose.

Each worker may run its own ffmpeg, and ffmpeg is already multi-threaded, so more
workers than this mostly buys contention. It is a parameter because the right number
depends on the machine and on whether the source is on a network mount; measuring it
against a real turnover is M8.
"""

Severity = Literal["error", "warning", "info"]
Scope = Literal["batch", "turnover", "row", "deliverable"]
DeliverableStatus = Literal["planned", "rendering", "done", "failed", "exists", "skipped"]

SourceEncodingOrigin = Literal["clip metadata", "container tag"]
"""Which carrier named a row's source encoding. COLOR_AND_FORMAT, EXR metadata.

The two the scan reads, in the order it reads them (OQ-44). It is written into the
delivered EXR header and the QC log because the encoding is the fact that matters and
the origin is how a wrong one is traced back to whoever wrote it: a name from the clip
metadata was typed into the session, one from a container tag travelled in the file and
may predate it. An override typed by an editor would be a third value rather than a second
mechanism; nothing sets one today.
"""


def _as_path(value: Any) -> Path | None:
    return Path(value) if value else None


@dataclass(frozen=True)
class FrameRate:
    """An exact frame rate. 24 is 24/1; NTSC 23.976 is 24000/1001.

    Kept rational so equality is exact. QC-025 and QC-026 compare these directly
    rather than comparing floats with a tolerance.
    """

    numerator: int
    denominator: int = 1

    def __post_init__(self) -> None:
        if self.numerator <= 0 or self.denominator <= 0:
            raise ValueError(f"frame rate must be positive, got {self.numerator}/{self.denominator}")

    @classmethod
    def from_float(cls, value: float) -> FrameRate:
        """Recognise the NTSC rates exactly; treat everything else as a whole number."""
        for whole in (24, 30, 60, 120):
            # 1e-3 rather than tighter: 119.88 is 1.2e-4 off 120000/1001, and the nearest
            # whole number is 0.12 away, so nothing else can fall inside it.
            if abs(value - (whole * 1000 / 1001)) < 1e-3:
                return cls(whole * 1000, 1001)
        if abs(value - round(value)) < 1e-6:
            return cls(round(value))
        raise ValueError(f"unsupported frame rate {value}")

    def as_float(self) -> float:
        return self.numerator / self.denominator

    def nominal(self) -> int:
        """The integer rate timecode counts at."""
        return frames.nominal_rate(self.as_float())

    def __str__(self) -> str:
        return str(self.numerator) if self.denominator == 1 else f"{self.numerator}/{self.denominator}"

    def to_dict(self) -> dict[str, int]:
        return {"numerator": self.numerator, "denominator": self.denominator}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FrameRate:
        return cls(numerator=int(data["numerator"]), denominator=int(data["denominator"]))


@dataclass(frozen=True)
class QCResult:
    """One rule outcome. `rule_id` is the stable ID from docs/QC_RULES.md."""

    rule_id: str
    severity: Severity
    scope: Scope
    message: str

    def to_dict(self) -> dict[str, str]:
        return {
            "rule_id": self.rule_id,
            "severity": self.severity,
            "scope": self.scope,
            "message": self.message,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> QCResult:
        return cls(
            rule_id=str(data["rule_id"]),
            severity=data["severity"],
            scope=data["scope"],
            message=str(data["message"]),
        )


@dataclass
class MediaInfo:
    """One ffprobe result. Cached in the batch keyed by path, size and mtime (FR-3)."""

    path: Path
    codec: str
    pixel_format: str
    width: int
    height: int
    rate: FrameRate
    """Effective rate: what the timeline conforms this media to, and what frame math uses."""

    frame_count: int
    start_frame: int = 0
    start_timecode: int | None = None
    is_sequence: bool = False
    has_audio: bool = False
    audio_channels: int = 0
    audio_sample_rate: int = 0
    audio_bit_depth: int = 0
    size: int = 0
    mtime: float = 0.0
    tags: dict[str, str] = field(default_factory=dict)
    """The container's own metadata tags, format and stream merged.

    Kept because the source encoding may be written into the file itself rather than
    into the timeline (OQ-44), and the scan is where both are in front of the tool at
    once. Nothing else reads it, and it is not a colour tag: COLOR_AND_FORMAT section 2
    is explicit that a container's colour tags are overridden rather than trusted, and
    that what is trusted is a named field a person filled in. Additive, so the schema
    version does not move.
    """

    stated_rate: FrameRate | None = None
    """What the media itself claims, when it can claim anything.

    An EXR sequence states this in its header and a container in its stream; a
    sequence of stills states nothing, so this is None. Kept apart from `rate`
    because shooters conform every clip to the project rate in Resolve, which makes
    the timeline authoritative and can leave stale camera metadata behind. QC-026
    compares this against the project rate; nothing computes with it.
    """

    @property
    def rate_matches_timeline(self) -> bool:
        """False only when the media states a rate and it disagrees (QC-026)."""
        return self.stated_rate is None or self.stated_rate == self.rate

    @property
    def max_available_out(self) -> int:
        return frames.max_available_out(self.start_frame, self.frame_count)

    @property
    def resolution(self) -> tuple[int, int]:
        return self.width, self.height

    def cache_key(self) -> str:
        """Path plus size plus mtime. A re-exported file invalidates itself."""
        return f"{self.path}|{self.size}|{self.mtime}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "codec": self.codec,
            "pixel_format": self.pixel_format,
            "width": self.width,
            "height": self.height,
            "rate": self.rate.to_dict(),
            "frame_count": self.frame_count,
            "start_frame": self.start_frame,
            "start_timecode": self.start_timecode,
            "tags": dict(self.tags),
            "is_sequence": self.is_sequence,
            "has_audio": self.has_audio,
            "audio_channels": self.audio_channels,
            "audio_sample_rate": self.audio_sample_rate,
            "audio_bit_depth": self.audio_bit_depth,
            "size": self.size,
            "mtime": self.mtime,
            "stated_rate": self.stated_rate.to_dict() if self.stated_rate else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MediaInfo:
        return cls(
            path=Path(data["path"]),
            codec=str(data["codec"]),
            pixel_format=str(data["pixel_format"]),
            width=int(data["width"]),
            height=int(data["height"]),
            rate=FrameRate.from_dict(data["rate"]),
            frame_count=int(data["frame_count"]),
            start_frame=int(data["start_frame"]),
            start_timecode=data["start_timecode"],
            tags={str(key): str(value) for key, value in (data.get("tags") or {}).items()},
            is_sequence=bool(data["is_sequence"]),
            has_audio=bool(data["has_audio"]),
            audio_channels=int(data["audio_channels"]),
            audio_sample_rate=int(data["audio_sample_rate"]),
            audio_bit_depth=int(data["audio_bit_depth"]),
            size=int(data["size"]),
            mtime=float(data["mtime"]),
            stated_rate=(FrameRate.from_dict(data["stated_rate"]) if data.get("stated_rate") else None),
        )


@dataclass
class AudioInfo:
    """One audio file, probed only for what sync checking needs.

    Format is deliberately not constrained here: what matters is whether the audio
    lines up with the picture. Duration is kept in samples so the comparison stays
    integer and no float drift creeps in.
    """

    path: Path
    duration_samples: int
    sample_rate: int
    channels: int = 0
    bit_depth: int = 0

    def duration_in_frames(self, rate: FrameRate) -> int:
        """Length in project frames, rounded to the nearest whole frame."""
        if self.sample_rate <= 0:
            return 0
        return round(Fraction(self.duration_samples * rate.numerator, self.sample_rate * rate.denominator))

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "duration_samples": self.duration_samples,
            "sample_rate": self.sample_rate,
            "channels": self.channels,
            "bit_depth": self.bit_depth,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AudioInfo:
        return cls(
            path=Path(data["path"]),
            duration_samples=int(data["duration_samples"]),
            sample_rate=int(data["sample_rate"]),
            channels=int(data.get("channels", 0)),
            bit_depth=int(data.get("bit_depth", 0)),
        )


@dataclass(frozen=True)
class InOut:
    """An inclusive source frame range."""

    in_frame: int
    out_frame: int

    @property
    def duration(self) -> int:
        return frames.duration(self.in_frame, self.out_frame)

    def to_dict(self) -> dict[str, int]:
        return {"in_frame": self.in_frame, "out_frame": self.out_frame}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> InOut:
        return cls(in_frame=int(data["in_frame"]), out_frame=int(data["out_frame"]))


@dataclass(frozen=True)
class CDL:
    """One event's ASC CDL, as numbers and as the lines it was written on.

    Both forms are delivered. The numbers go into the EXR header as attributes, and the
    text goes in verbatim because it is what another facility's tool reads and what a
    human compares against the session. Neither is ever applied: the CLF is.

    It lives here rather than in `core/clf.py`, where it was written, because since the
    colour session is ingested onto the rows it has to survive a save: a batch reopened
    a month later writes the same EXR header without the EDL still being on the disk.
    """

    slope: tuple[float, float, float]
    offset: tuple[float, float, float]
    power: tuple[float, float, float]
    saturation: float
    sop_text: str
    sat_text: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "slope": list(self.slope),
            "offset": list(self.offset),
            "power": list(self.power),
            "saturation": self.saturation,
            "sop_text": self.sop_text,
            "sat_text": self.sat_text,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CDL:
        return cls(
            slope=_triple(data["slope"]),
            offset=_triple(data["offset"]),
            power=_triple(data["power"]),
            saturation=float(data["saturation"]),
            sop_text=str(data["sop_text"]),
            sat_text=str(data["sat_text"]),
        )


def _triple(values: Any) -> tuple[float, float, float]:
    a, b, c = values
    return (float(a), float(b), float(c))


@dataclass
class Deliverable:
    """One planned or written output. Populated by the planner in M2.

    Present now so the batch file's schema is stable: FR-11 requires per-deliverable
    state to survive a crash, and the loader reconciles it against the filesystem.
    """

    kind: str
    name: str
    path: Path
    version: int
    res: str | None = None
    status: DeliverableStatus = "planned"
    checksum: str | None = None
    frame_checksums: list[str] = field(default_factory=list)
    """xxhash64 per written frame, in output frame order, for QC-106.

    A sequence has no single checksum, and QC-106 checks every frame, so the writer
    records them all here. `checksum` stays the whole-file digest a single file gets.
    Additive, so the schema version does not move: an older batch simply has none.
    """

    frame_count: int = 0
    size: int = 0
    qc: list[QCResult] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "name": self.name,
            "path": str(self.path),
            "version": self.version,
            "res": self.res,
            "status": self.status,
            "checksum": self.checksum,
            "frame_checksums": list(self.frame_checksums),
            "frame_count": self.frame_count,
            "size": self.size,
            "qc": [result.to_dict() for result in self.qc],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Deliverable:
        return cls(
            kind=str(data["kind"]),
            name=str(data["name"]),
            path=Path(data["path"]),
            version=int(data["version"]),
            res=data.get("res"),
            status=data.get("status", "planned"),
            checksum=data.get("checksum"),
            frame_checksums=[str(value) for value in data.get("frame_checksums", [])],
            frame_count=int(data.get("frame_count", 0)),
            size=int(data.get("size", 0)),
            qc=[QCResult.from_dict(item) for item in data.get("qc", [])],
        )


@dataclass
class ShotRow:
    """One row of the shot list. FR-4.

    `snapshot` is the In/Out the turnover arrived with and is immutable after scan;
    `current` is what the editor has since chosen. The difference is QC-035 and a
    column in the QC log.
    """

    turnover_id: str
    clip_name: str
    track: str = "V1"
    identity: ShotIdentity | None = None
    shot_code_override: str | None = None
    media: MediaInfo | None = None
    record_in: int = 0
    record_out: int = 0
    snapshot: InOut | None = None
    current: InOut | None = None
    audio_path: Path | None = None
    audio: AudioInfo | None = None
    audio_clip_count: int = 0
    """How many timeline audio clips overlapped this one. More than one is QC-041.

    Recorded at scan because the timeline is gone by the time the rules run. Additive,
    so the schema version does not move: an older batch simply reports none.
    """

    source_encoding: str | None = None
    """The log encoding this clip's own metadata names, verbatim, or None when it names none.

    **A per clip fact, which is why it lives on the row** (COLOR_AND_FORMAT section 1): a
    turnover may mix encodings freely and nothing batch wide can stand in for this. What
    is stored is the string a shooter wrote, not a colour space: `core/color.py` maps it
    onto one, and QC-047 is what a string that maps onto nothing reports. Additive, so
    the schema version does not move and an older batch simply names no encoding.
    """

    source_encoding_origin: SourceEncodingOrigin | None = None
    """Which carrier named it, or None when nothing named one.

    Set wherever `source_encoding` is set, so the two never disagree. Additive, so the
    schema version does not move and an older batch names no origin for an encoding it
    does name, which reads as unknown rather than as either carrier.
    """

    approved: InOut | None = None
    """The In/Out the colour session's final EDL approved, or None until one is ingested.

    A third range beside `snapshot` and `current`, and the three answer three different
    questions: what the turnover delivered, what will be rendered, and what Ben and the
    AD signed off (COLOR_AND_FORMAT section 1). Ingest writes `current` from it, so the
    two agree until the editor makes a one-off trim, and QC-045 is the gap between them.
    Additive, so the schema version does not move and a batch saved before this has
    nothing approved, which is the state a batch with no colour session is in anyway.
    """

    cdl: CDL | None = None
    """The CDL on this row's conform event, recorded and never applied.

    It reaches the EXR header as the readable version of the grade (COLOR_AND_FORMAT,
    EXR metadata). On the row rather than fetched from the EDL at render time so that a
    reopened batch writes the same header without the session package still being on the
    disk. Where it and `clf_path` disagree the CLF is what is in the pixels.
    """

    clf_path: Path | None = None
    """The CLF the colour session delivered for this shot, or None when it delivered none.

    Recorded on the row because it is what the QC log's CLF column names and what a
    reader compares a delivered EXR header against. The grade itself never lives here:
    the transform is loaded in the worker that applies it. Additive, so the schema
    version does not move and an older batch simply reports no CLF.
    """

    notes: str = ""
    skipped: bool = False
    skip_reason: str | None = None
    deliverables: list[Deliverable] = field(default_factory=list)
    qc: list[QCResult] = field(default_factory=list)

    @property
    def shot_code(self) -> str | None:
        """The corrected shot code when the editor changed it, else the parsed one."""
        if self.shot_code_override:
            return self.shot_code_override
        return self.identity.shot_code if self.identity else None

    @property
    def duration(self) -> int | None:
        return self.current.duration if self.current else None

    @property
    def max_available_out(self) -> int | None:
        return self.media.max_available_out if self.media else None

    @property
    def was_edited(self) -> bool:
        """True when the editor moved In or Out away from the turnover snapshot (QC-035)."""
        return self.snapshot is not None and self.current is not None and self.snapshot != self.current

    def edit_context(
        self,
        project_rate: FrameRate,
        timeline_start: int = 0,
        mode: frames.TimecodeMode = "source",
    ) -> frames.EditContext:
        """What this row's In and Out need to become timecode, and back again.

        One definition because two things read it: the list renders a frame as timecode
        with it (UI_SPEC section 2) and a typed timecode becomes a frame through it
        (section 5). Building it in two places is how a display and its editor come to
        disagree about which frame an hour is.

        `timeline_start` belongs to the turnover rather than the row, because it is a
        fact about one timeline, so it is passed in. The record anchor is the clip's
        record start paired with **the snapshot's** In: that pairing is where the
        turnover put this clip, and it does not move when the editor trims, which is
        what keeps the mapping linear rather than sliding with every edit.
        """
        media, snapshot = self.media, self.snapshot
        rate = media.rate if media else project_rate
        source_start = media.start_frame if media else 0
        return frames.EditContext(
            fps=rate.as_float(),
            source_start=source_start,
            source_start_timecode=media.start_timecode if media and media.start_timecode else 0,
            record_start_timecode=timeline_start + self.record_in,
            record_start_source_frame=snapshot.in_frame if snapshot else source_start,
            mode=mode,
        )

    def errors(self) -> list[QCResult]:
        return [result for result in self.qc if result.severity == "error"]

    def warnings(self) -> list[QCResult]:
        return [result for result in self.qc if result.severity == "warning"]

    def to_dict(self) -> dict[str, Any]:
        return {
            "turnover_id": self.turnover_id,
            "clip_name": self.clip_name,
            "track": self.track,
            "identity": _identity_to_dict(self.identity),
            "shot_code_override": self.shot_code_override,
            "media": self.media.to_dict() if self.media else None,
            "record_in": self.record_in,
            "record_out": self.record_out,
            "snapshot": self.snapshot.to_dict() if self.snapshot else None,
            "current": self.current.to_dict() if self.current else None,
            "audio_path": str(self.audio_path) if self.audio_path else None,
            "audio": self.audio.to_dict() if self.audio else None,
            "audio_clip_count": self.audio_clip_count,
            "source_encoding": self.source_encoding,
            "source_encoding_origin": self.source_encoding_origin,
            "approved": self.approved.to_dict() if self.approved else None,
            "cdl": self.cdl.to_dict() if self.cdl else None,
            "clf_path": str(self.clf_path) if self.clf_path else None,
            "notes": self.notes,
            "skipped": self.skipped,
            "skip_reason": self.skip_reason,
            "deliverables": [item.to_dict() for item in self.deliverables],
            "qc": [result.to_dict() for result in self.qc],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ShotRow:
        media = data.get("media")
        snapshot = data.get("snapshot")
        current = data.get("current")
        return cls(
            turnover_id=str(data["turnover_id"]),
            clip_name=str(data["clip_name"]),
            track=str(data.get("track", "V1")),
            identity=_identity_from_dict(data.get("identity")),
            shot_code_override=data.get("shot_code_override"),
            media=MediaInfo.from_dict(media) if media else None,
            record_in=int(data.get("record_in", 0)),
            record_out=int(data.get("record_out", 0)),
            snapshot=InOut.from_dict(snapshot) if snapshot else None,
            current=InOut.from_dict(current) if current else None,
            audio_path=_as_path(data.get("audio_path")),
            audio=AudioInfo.from_dict(data["audio"]) if data.get("audio") else None,
            audio_clip_count=int(data.get("audio_clip_count", 0)),
            source_encoding=data.get("source_encoding"),
            source_encoding_origin=data.get("source_encoding_origin"),
            approved=InOut.from_dict(data["approved"]) if data.get("approved") else None,
            cdl=CDL.from_dict(data["cdl"]) if data.get("cdl") else None,
            clf_path=_as_path(data.get("clf_path")),
            notes=str(data.get("notes", "")),
            skipped=bool(data.get("skipped", False)),
            skip_reason=data.get("skip_reason"),
            deliverables=[Deliverable.from_dict(item) for item in data.get("deliverables", [])],
            qc=[QCResult.from_dict(item) for item in data.get("qc", [])],
        )


def _identity_to_dict(identity: ShotIdentity | None) -> dict[str, Any] | None:
    return None if identity is None else asdict(identity)


def _identity_from_dict(data: dict[str, Any] | None) -> ShotIdentity | None:
    """Field by field off the dataclass, so a field added to `ShotIdentity` round trips.

    Required fields are read with `[]` so a missing one is the KeyError `batchfile.load`
    reports; optional ones default the way the class does.
    """
    if data is None:
        return None
    values: dict[str, Any] = {
        f.name: str(data[f.name]) if f.default is MISSING else data.get(f.name) for f in fields(ShotIdentity)
    }
    return ShotIdentity(**values)


@dataclass
class Turnover:
    """One turnover folder and the fields that identify it.

    Number, date and shooter are prefilled from the folder name when it matches the
    `turnover###_MM_DD_YYYY_name` pattern, and entered by hand otherwise (QC-005). They
    name the turnover in the window and the headless listing; nothing builds a filename
    out of them any more, because the tool no longer delivers the stringout (2026-09-22).
    """

    turnover_id: str
    folder: Path
    timeline_path: Path | None = None
    timeline_start: int = 0
    """The timeline's own start, in frames. `01:00:00:00` at 24 is 86400.

    Record timecode is only meaningful against it: `ShotRow.record_in` is measured from
    the timeline's zero, and an edit that starts at an hour is the normal case, so a row
    shown without this reads an hour early. Kept on the turnover because it is a fact
    about one timeline and a batch holds several. Additive, so the schema version does
    not move and a batch saved before this reads back as zero, which is what a timeline
    starting at zero would say anyway.
    """

    color_session_edl: Path | None = None
    """The final EDL of the colour session ingested for this turnover, or None.

    **Per turnover rather than per batch** (QC-008), because turnovers arrive on
    different days and the grade for one is finished while the next is still being shot:
    one turnover can be waiting on colour while another renders. **On the batch rather
    than in the app settings**, for the reason UI_SPEC section 13 gives for the two
    roots: it is a record of what this work was rendered from, not a preference, so
    reopening a `.pibatch` restores it and a second batch does not disturb it.

    It is the location only. What the session said is on the rows, in `approved`, `cdl`
    and `clf_path`, so a batch reopened after the package has been archived still
    renders the grade it was ingested with. Additive, so the schema version does not
    move and a batch saved before this has ingested nothing.
    """

    number: int | None = None
    month: int | None = None
    day: int | None = None
    year: int | None = None
    shooter: str = ""
    qc: list[QCResult] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "turnover_id": self.turnover_id,
            "folder": str(self.folder),
            "timeline_path": str(self.timeline_path) if self.timeline_path else None,
            "timeline_start": self.timeline_start,
            "color_session_edl": str(self.color_session_edl) if self.color_session_edl else None,
            "number": self.number,
            "month": self.month,
            "day": self.day,
            "year": self.year,
            "shooter": self.shooter,
            "qc": [result.to_dict() for result in self.qc],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Turnover:
        return cls(
            turnover_id=str(data["turnover_id"]),
            folder=Path(data["folder"]),
            timeline_path=_as_path(data.get("timeline_path")),
            timeline_start=int(data.get("timeline_start", 0)),
            color_session_edl=_as_path(data.get("color_session_edl")),
            number=data.get("number"),
            month=data.get("month"),
            day=data.get("day"),
            year=data.get("year"),
            shooter=str(data.get("shooter", "")),
            qc=[QCResult.from_dict(item) for item in data.get("qc", [])],
        )


DEFAULT_BATCH_NAME = "untitled"
"""What a batch is called before anything has named it. The UI replaces it with the
file's own stem on the first save, so a batch cannot reach the exports unnamed."""


@dataclass
class Batch:
    """Everything needed to reopen a session. Serialized as `.pibatch` (FR-11)."""

    name: str = DEFAULT_BATCH_NAME
    schema_version: int = SCHEMA_VERSION
    source_root: Path | None = None
    """The folder turnovers are added from (UI_SPEC section 13). The `Add Turnover`
    chooser opens here and the folder picked beneath it is what gets scanned.

    Remembered on the batch rather than in the app settings, so a second batch on
    another drive does not move the first one's starting point. Additive, so the schema
    version does not move: a batch saved before this reads back as None, which is the
    same state a batch that has never added a turnover is in. It is a starting point and
    not a fence: adding a turnover from outside it is allowed and moves it.
    """

    delivery_root: Path | None = None
    project_rate: FrameRate = field(default_factory=lambda: FrameRate(24))
    turnovers: list[Turnover] = field(default_factory=list)
    rows: list[ShotRow] = field(default_factory=list)
    probe_cache: dict[str, MediaInfo] = field(default_factory=dict)
    settings_overrides: dict[str, Any] = field(default_factory=dict)
    qc: list[QCResult] = field(default_factory=list)

    def rows_for(self, turnover_id: str) -> list[ShotRow]:
        """Rows in timeline order. Sorting is fixed within a turnover (UI_SPEC section 2)."""
        return [row for row in self.rows if row.turnover_id == turnover_id]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "name": self.name,
            "source_root": str(self.source_root) if self.source_root else None,
            "delivery_root": str(self.delivery_root) if self.delivery_root else None,
            "project_rate": self.project_rate.to_dict(),
            "turnovers": [item.to_dict() for item in self.turnovers],
            "rows": [row.to_dict() for row in self.rows],
            "probe_cache": {key: value.to_dict() for key, value in self.probe_cache.items()},
            "settings_overrides": self.settings_overrides,
            "qc": [result.to_dict() for result in self.qc],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Batch:
        version = int(data.get("schema_version", SCHEMA_VERSION))
        if version != SCHEMA_VERSION:
            raise ValueError(f"batch schema version {version} is not supported (expected {SCHEMA_VERSION})")
        return cls(
            name=str(data.get("name", DEFAULT_BATCH_NAME)),
            schema_version=version,
            source_root=_as_path(data.get("source_root")),
            delivery_root=_as_path(data.get("delivery_root")),
            project_rate=FrameRate.from_dict(data["project_rate"]),
            turnovers=[Turnover.from_dict(item) for item in data.get("turnovers", [])],
            rows=[ShotRow.from_dict(item) for item in data.get("rows", [])],
            probe_cache={
                key: MediaInfo.from_dict(value) for key, value in data.get("probe_cache", {}).items()
            },
            settings_overrides=dict(data.get("settings_overrides", {})),
            qc=[QCResult.from_dict(item) for item in data.get("qc", [])],
        )
