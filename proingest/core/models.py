"""Data model for a batch.

Plain dataclasses with explicit dict conversion. Core stays dependency-light and
`mypy --strict` clean, and the JSON shape is visible in one place rather than
inferred from a library's behaviour.

Everything here is JSON round-trippable: `to_dict` and `from_dict` are inverses, and
that is asserted in the tests. The batch file is schema versioned, so changing a
field name is a migration, not an edit.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from proingest.core import frames
from proingest.core.naming import ShotIdentity

SCHEMA_VERSION = 1

Severity = Literal["error", "warning", "info"]
Scope = Literal["batch", "turnover", "row", "deliverable"]
DeliverableStatus = Literal["planned", "rendering", "done", "failed", "exists", "skipped"]


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
            if abs(value - (whole * 1000 / 1001)) < 1e-4:
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
            is_sequence=bool(data["is_sequence"]),
            has_audio=bool(data["has_audio"]),
            audio_channels=int(data["audio_channels"]),
            audio_sample_rate=int(data["audio_sample_rate"]),
            audio_bit_depth=int(data["audio_bit_depth"]),
            size=int(data["size"]),
            mtime=float(data["mtime"]),
            stated_rate=(
                FrameRate.from_dict(data["stated_rate"]) if data.get("stated_rate") else None
            ),
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
        return round(self.duration_samples * rate.as_float() / self.sample_rate)

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


@dataclass
class SideFiles:
    """Files found next to the media, matched by shot code and element id."""

    hdri: Path | None = None
    camdata: Path | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "hdri": str(self.hdri) if self.hdri else None,
            "camdata": str(self.camdata) if self.camdata else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SideFiles:
        return cls(hdri=_as_path(data.get("hdri")), camdata=_as_path(data.get("camdata")))


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

    side_files: SideFiles = field(default_factory=SideFiles)
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
            "side_files": self.side_files.to_dict(),
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
            side_files=SideFiles.from_dict(data.get("side_files", {})),
            notes=str(data.get("notes", "")),
            skipped=bool(data.get("skipped", False)),
            skip_reason=data.get("skip_reason"),
            deliverables=[Deliverable.from_dict(item) for item in data.get("deliverables", [])],
            qc=[QCResult.from_dict(item) for item in data.get("qc", [])],
        )


def _identity_to_dict(identity: ShotIdentity | None) -> dict[str, Any] | None:
    if identity is None:
        return None
    return {
        "show": identity.show,
        "shot": identity.shot,
        "elem_type": identity.elem_type,
        "elem_index": identity.elem_index,
        "aux": identity.aux,
        "aux_index": identity.aux_index,
    }


def _identity_from_dict(data: dict[str, Any] | None) -> ShotIdentity | None:
    if data is None:
        return None
    return ShotIdentity(
        show=str(data["show"]),
        shot=str(data["shot"]),
        elem_type=str(data["elem_type"]),
        elem_index=str(data["elem_index"]),
        aux=data.get("aux"),
        aux_index=data.get("aux_index"),
    )


@dataclass
class Turnover:
    """One turnover folder and the fields the stringout name needs (FR-9).

    Number, date and shooter are prefilled from the folder name when it matches the
    `turnover###_MM_DD_YYYY_name` pattern, and entered by hand otherwise (QC-005).
    """

    turnover_id: str
    folder: Path
    timeline_path: Path | None = None
    number: int | None = None
    month: int | None = None
    day: int | None = None
    year: int | None = None
    shooter: str = ""
    qc: list[QCResult] = field(default_factory=list)

    @property
    def has_stringout_fields(self) -> bool:
        return all(v is not None for v in (self.number, self.month, self.day, self.year)) and bool(
            self.shooter
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "turnover_id": self.turnover_id,
            "folder": str(self.folder),
            "timeline_path": str(self.timeline_path) if self.timeline_path else None,
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
            number=data.get("number"),
            month=data.get("month"),
            day=data.get("day"),
            year=data.get("year"),
            shooter=str(data.get("shooter", "")),
            qc=[QCResult.from_dict(item) for item in data.get("qc", [])],
        )


@dataclass
class Batch:
    """Everything needed to reopen a session. Serialized as `.pibatch` (FR-11)."""

    name: str = "untitled"
    schema_version: int = SCHEMA_VERSION
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
            name=str(data.get("name", "untitled")),
            schema_version=version,
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
