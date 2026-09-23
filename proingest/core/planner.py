"""What each shot row owes, and where it goes.

The type table in docs/NAMING_SPEC.md section 2 decides which deliverables a row
produces, section 3 names them, and section 5 places them under the delivery root.
Nothing here writes a file: a plan is a list of jobs a worker process can execute.

Version is resolved here rather than at scan time, because the answer depends on what is
in the delivery folder at the moment the run starts. All deliverables of one shot in one
run share a version (section 4), so a shot never ends up with a partial version set.

Job kinds use the same vocabulary `naming.parse_output_name` reads back, so QC-151 is a
direct comparison between what was planned and what the written filename says.
"""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Literal

from proingest.core import clf, frames, naming
from proingest.core.models import (
    Batch,
    Deliverable,
    FrameRate,
    InOut,
    MediaInfo,
    QCResult,
    ShotRow,
)
from proingest.core.naming import Resolution, ShotIdentity

TEMP_SUFFIX = ".part"
"""FR-7: every job writes to `<final>.part`, file or folder alike, and renames on success."""

RESOLUTIONS: dict[Resolution, tuple[int, int]] = {"4k": (3840, 2160), "HD": (1920, 1080)}
"""Exact target sizes, docs/COLOR_AND_FORMAT.md section 4. Never derived from the source."""

JobKind = Literal["raw_dir", "ref_mp4", "audio", "aux_still"]

PICTURE_DELIVERABLES: tuple[tuple[JobKind, Resolution], ...] = (
    ("raw_dir", "4k"),
    ("raw_dir", "HD"),
    ("ref_mp4", "4k"),
    ("ref_mp4", "HD"),
)
"""The four every element type owes. NAMING_SPEC section 2."""

TYPE_TABLE: dict[str, tuple[tuple[JobKind, Resolution], ...]] = {
    elem_type: PICTURE_DELIVERABLES for elem_type in naming.ELEMENT_TYPES
}
"""Type table, picture half. Audio is the only difference between the rows of the table,
and it also depends on there being audio at all, so it is added separately."""

AUDIO_TYPES = ("pl",)
"""Only the main plate delivers audio."""

OWNED_RULES = frozenset({"QC-060"})
"""Rule IDs this module raises. Cleared before it raises them again, as qc.py does."""


@dataclass(frozen=True)
class DeliverableJob:
    """One output to produce.

    Self-contained on purpose: a job is handed to a worker process, so it carries the
    paths and the frame range that worker needs rather than a reference to the batch.
    """

    kind: JobKind
    source: Path
    destination: Path
    version: int
    shot_code: str
    elem: str
    res: Resolution | None = None
    in_frame: int | None = None
    out_frame: int | None = None
    source_is_sequence: bool = False
    audio_source: Path | None = None
    """The audio to mux into a reference mp4, when the row has any."""

    source_size: tuple[int, int] | None = None
    """The media's own resolution, which is what sizes the raw decode."""

    rate: FrameRate | None = None
    """The effective rate, so a worker converts timecode without reopening the source."""

    source_start_frame: int = 0
    """First frame index of the media: the first sequence number, or 0 for a container."""

    source_start_timecode: int | None = None
    """Start timecode of `source_start_frame`, or None when the media states none (QC-028).

    These three are the last things a worker would otherwise have to reprobe. A job is
    self contained on purpose, and reprobing in the worker would also mean the render
    could disagree with the scan about the source.
    """

    shot_color: clf.ShotColor = clf.DEFAULT_SHOT_COLOR
    """The chain this deliverable is rendered through. COLOR_AND_FORMAT section 1.

    On the job for the same reason the source facts are: a worker is handed a job and
    nothing else. It holds a CLF path rather than a transform because a job crosses a
    spawn boundary and an OCIO object does not pickle.

    A copy job carries the default and ignores it; bytes are bytes. So does an **aux
    still**, deliberately: the aux names are `colorChart`, `mirrorBall`, `greyBall` and
    `sizeRef`, and a grade applied to a colour chart destroys the one thing the chart is
    delivered for. It still gets the input transform, so it lands in ACEScg like every
    other EXR the tool writes, but never the shot's grade.
    """

    @property
    def name(self) -> str:
        return self.destination.name

    @property
    def temp(self) -> Path:
        """Where the job actually writes. Renamed onto `destination` once it verifies."""
        return self.destination.with_name(self.destination.name + TEMP_SUFFIX)

    @property
    def target_size(self) -> tuple[int, int] | None:
        return RESOLUTIONS[self.res] if self.res else None

    @property
    def frame_count(self) -> int:
        """Frames this job writes. Zero for a copy, which has no frame range."""
        if self.in_frame is None or self.out_frame is None:
            return 0
        return frames.duration(self.in_frame, self.out_frame)

    def source_frame(self, output_frame: int) -> int:
        """The source frame an output frame comes from. COLOR_AND_FORMAT section 6."""
        if self.in_frame is None:
            raise ValueError(f"{self.name} has no frame range")
        return frames.source_frame_for(self.in_frame, output_frame)

    def timecode_for(self, output_frame: int) -> int | None:
        """The source timecode an output frame carries, or None when there is none."""
        if self.source_start_timecode is None:
            return None
        return frames.timecode_frames_for(
            self.source_frame(output_frame), self.source_start_frame, self.source_start_timecode
        )

    def output_frames(self) -> range:
        """The output frame numbers this job writes, 1001 first."""
        return range(naming.FIRST_OUTPUT_FRAME, naming.FIRST_OUTPUT_FRAME + self.frame_count)

    def frame_path(self, output_frame: int, temp: bool = False) -> Path:
        """One frame inside a raw EXR sequence folder."""
        if self.kind != "raw_dir":
            raise ValueError(f"{self.name} is not a sequence")
        directory = self.temp if temp else self.destination
        return directory / naming.frame_in_sequence(self.destination.name, output_frame)

    def to_deliverable(self) -> Deliverable:
        """The batch file's record of this job, before anything has been rendered."""
        return Deliverable(
            kind=self.kind,
            name=self.name,
            path=self.destination,
            version=self.version,
            res=self.res,
            frame_count=self.frame_count,
        )


@dataclass
class RowPlan:
    """What one row owes, plus anything planning it uncovered."""

    jobs: list[DeliverableJob] = field(default_factory=list)
    qc: list[QCResult] = field(default_factory=list)


@dataclass(frozen=True)
class _Shot:
    """Everything the job builders need from one row, narrowed and resolved once."""

    identity: ShotIdentity
    media: MediaInfo
    current: InOut
    directory: Path
    version: int
    audio: Path | None
    color: clf.ShotColor


def effective_identity(row: ShotRow, show_pattern: str = naming.DEFAULT_SHOW_PATTERN) -> ShotIdentity | None:
    """The identity every name for this row is built from.

    A shot code the editor corrected replaces the one the CSV gave (NAMING_SPEC section
    6); the clip type and its index always come from `Shot Type`, which the editor does
    not correct here. Returns None when the row never had an identity, or when the
    correction does not parse either, because then no name can be built at all.
    """
    if row.identity is None:
        return None
    if not row.shot_code_override:
        return row.identity
    if naming.parse_shot_code(row.shot_code_override, show_pattern) is None:
        return None
    return replace(row.identity, shot_code=row.shot_code_override)


def plannable_identity(row: ShotRow, show_pattern: str = naming.DEFAULT_SHOW_PATTERN) -> ShotIdentity | None:
    """The identity to plan this row under, or None when the row owes nothing.

    A row is not planned when the editor skipped it, when it carries an error, which
    FR-6 says blocks the row but not the batch, or when it has no media and no chosen
    range, because then there is nothing to read.
    """
    if row.skipped or row.errors() or row.media is None or row.current is None:
        return None
    return effective_identity(row, show_pattern)


def resolve_version(directory: Path, show_pattern: str = naming.DEFAULT_SHOW_PATTERN) -> int:
    """The highest version already delivered here, plus one. NAMING_SPEC section 4.

    Only names this tool writes are counted, so a stray file cannot inflate the version
    and a `.part` leftover can never be mistaken for a finished delivery.
    """
    if not directory.is_dir():
        return 1
    return naming.next_version([entry.name for entry in directory.iterdir()], show_pattern)


def plan_row(
    row: ShotRow,
    delivery_root: Path,
    version: int,
    show_pattern: str = naming.DEFAULT_SHOW_PATTERN,
    shot_color: clf.ShotColor = clf.DEFAULT_SHOT_COLOR,
) -> RowPlan:
    """The deliverables one row owes at `version`. Pure: it touches no filesystem."""
    identity = plannable_identity(row, show_pattern)
    media, current = row.media, row.current
    if identity is None or media is None or current is None:
        return RowPlan()

    shot = _Shot(
        identity=identity,
        media=media,
        current=current,
        directory=naming.shot_dir(delivery_root, identity),
        version=version,
        audio=_audio_source(row),
        color=shot_color,
    )
    if identity.is_still:
        return _aux_plan(shot)

    plan = RowPlan(jobs=[_picture_job(shot, kind, res) for kind, res in TYPE_TABLE[identity.kind]])
    audio = _audio_job(shot)
    if audio is not None:
        plan.jobs.append(audio)
    return plan


def plan_batch(
    batch: Batch,
    delivery_root: Path | None = None,
    show_pattern: str = naming.DEFAULT_SHOW_PATTERN,
    skip_turnovers: Collection[str] = (),
) -> list[DeliverableJob]:
    """Plan every row of a batch and record the plan on the rows.

    One version is resolved per shot, from a single listing of that shot's delivery
    folder, and every row of that shot uses it, so the elements of one shot cannot
    disagree about their version.

    This replaces each row's deliverable list, which is why it runs immediately before a
    run rather than when a batch is opened: the state recorded against a row belongs to
    the version that produced it, not to the one about to be written.

    **The colour session is not a parameter here.** It is ingested onto the rows before
    a run (`clf.ingest`, PRD section 6 step 4), so every row already carries the CLF, the
    CDL and the approved In/Out it was matched with and planning reads them off the model
    like every other field. A batch nothing has been ingested into plans ungraded: the
    deliverables are the same files in the same places, and the difference is whether the
    CLF is in them. QC-008 is what refuses a **run** in that state, and it is a rule about
    the turnover rather than something the planner decides.

    `skip_turnovers` is what that refusal does here: a turnover whose pre-flight found an
    error plans nothing, and the turnovers beside it still deliver (`qc.blocked_turnovers`).
    It is passed in rather than read off the turnovers' QC lists, so planning does not
    depend on a rule pass having run that it cannot see.
    """
    skipped = frozenset(skip_turnovers)
    root = delivery_root or batch.delivery_root
    if root is None:
        raise ValueError("no delivery root: pass one, or set batch.delivery_root")

    versions: dict[str, int] = {}
    jobs: list[DeliverableJob] = []
    for row in batch.rows:
        identity = plannable_identity(row, show_pattern)
        if identity is None or row.turnover_id in skipped:
            _record(row, RowPlan())
            continue

        code = identity.shot_code
        if code not in versions:
            versions[code] = resolve_version(naming.shot_dir(root, identity), show_pattern)
        version = versions[code]

        plan = plan_row(row, root, version, show_pattern, clf.shot_color(row))
        if version > 1:
            plan.qc.append(
                QCResult(
                    "QC-060",
                    "warning",
                    "row",
                    f"{code} already has deliverables at v{version - 1:02d}; this run writes v{version:02d}",
                )
            )
        _record(row, plan)
        jobs.extend(plan.jobs)
    return jobs


def _record(row: ShotRow, plan: RowPlan) -> None:
    """Attach a plan to its row, replacing the results this module owns."""
    row.deliverables = [job.to_deliverable() for job in plan.jobs]
    row.qc = [result for result in row.qc if result.rule_id not in OWNED_RULES]
    row.qc.extend(plan.qc)


def _picture_job(shot: _Shot, kind: JobKind, res: Resolution) -> DeliverableJob:
    """A raw EXR sequence or a reference mp4. Both read the same source range."""
    name = (
        naming.raw_sequence_dir(shot.identity, res, shot.version)
        if kind == "raw_dir"
        else naming.ref_mp4(shot.identity, res, shot.version)
    )
    return DeliverableJob(
        kind=kind,
        source=shot.media.path,
        destination=shot.directory / name,
        version=shot.version,
        shot_code=shot.identity.shot_code,
        elem=shot.identity.elem,
        res=res,
        in_frame=shot.current.in_frame,
        out_frame=shot.current.out_frame,
        source_is_sequence=shot.media.is_sequence,
        audio_source=shot.audio if kind == "ref_mp4" else None,
        source_size=shot.media.resolution,
        rate=shot.media.rate,
        source_start_frame=shot.media.start_frame,
        source_start_timecode=shot.media.start_timecode,
        shot_color=shot.color,
    )


def _audio_source(row: ShotRow) -> Path | None:
    """The audio to deliver: the associated clip, or the picture's own track.

    COLOR_AND_FORMAT section 3 accepts both. A clip on the timeline's audio track wins,
    because that is the one the editor synced.
    """
    if row.audio_path is not None:
        return row.audio_path
    if row.media is not None and row.media.has_audio:
        return row.media.path
    return None


def _audio_job(shot: _Shot) -> DeliverableJob | None:
    """The wav a plate owes, when it has audio at all.

    A plate with none is QC-040, raised by the rule registry rather than here, because a
    missing deliverable is a fact about the row and not about the plan.
    """
    if shot.identity.kind not in AUDIO_TYPES or shot.audio is None:
        return None
    return DeliverableJob(
        kind="audio",
        source=shot.audio,
        destination=shot.directory / naming.audio_wav(shot.identity, shot.version),
        version=shot.version,
        shot_code=shot.identity.shot_code,
        elem=shot.identity.elem,
    )


def _aux_plan(shot: _Shot) -> RowPlan:
    """A reference still delivers one 4k EXR and nothing else. NAMING_SPEC section 2.

    Only the clip's In frame is used, which is what QC-055 reports when the clip holds
    more than one. That is now the normal case rather than an oddity: in the real sample
    a reference still is one timeline frame inside a 49-frame file.
    """
    first = shot.current.in_frame
    return RowPlan(
        jobs=[
            DeliverableJob(
                kind="aux_still",
                source=shot.media.path,
                destination=shot.directory / naming.aux_still_exr(shot.identity, shot.version),
                version=shot.version,
                shot_code=shot.identity.shot_code,
                elem=shot.identity.elem,
                res="4k",
                in_frame=first,
                out_frame=first,
                source_is_sequence=shot.media.is_sequence,
                source_size=shot.media.resolution,
                rate=shot.media.rate,
                source_start_frame=shot.media.start_frame,
                source_start_timecode=shot.media.start_timecode,
                shot_color=clf.ShotColor(
                    source_encoding=shot.color.source_encoding,
                    source_encoding_origin=shot.color.source_encoding_origin,
                ),
            )
        ]
    )
