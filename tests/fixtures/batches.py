"""Batches built by hand, for the tests that need a model rather than media.

The scan fixtures make real files and cost ffmpeg a second each; a list model only ever
sees the objects, so these build them directly. Everything is a plausible turnover: 4k
ProRes starting at `01:00:00:00`, a timeline starting at the same hour, two shots.
"""

from __future__ import annotations

from pathlib import Path

from proingest.core.models import (
    CDL,
    Batch,
    Deliverable,
    FrameRate,
    InOut,
    MediaInfo,
    QCResult,
    ShotRow,
    Turnover,
)
from tests.fixtures.names import identity_of

RATE_24 = FrameRate(24)
ONE_HOUR = 86400
"""`01:00:00:00` at 24, which is where both the media and the timeline start here."""


def media(**kwargs: object) -> MediaInfo:
    built = MediaInfo(
        path=Path("/turnover/MELT0001_pl01.mov"),
        codec="prores",
        pixel_format="yuv444p12le",
        width=3840,
        height=2160,
        rate=RATE_24,
        frame_count=240,
        start_frame=0,
        start_timecode=ONE_HOUR,
    )
    for key, value in kwargs.items():
        setattr(built, key, value)
    return built


def row(
    clip_name: str = "MELT0001_pl01",
    turnover_id: str = "turnover001",
    record_in: int = 0,
    **kwargs: object,
) -> ShotRow:
    """One scanned row, trimmed to 8-231 the way a turnover arrives.

    It names a source encoding because a real clip does, and since 2026-09-18 a plate
    without one is QC-046 as an error rather than a line of provenance.
    """
    built = ShotRow(
        turnover_id=turnover_id,
        clip_name=clip_name,
        identity=identity_of(clip_name),
        source_encoding="ACEScct",
        media=media(path=Path(f"/turnover/{clip_name}.mov")),
        record_in=record_in,
        record_out=record_in + 223,
        snapshot=InOut(8, 231),
        current=InOut(8, 231),
    )
    for key, value in kwargs.items():
        setattr(built, key, value)
    return built


def delivered(row_: ShotRow, status: str = "done", version: int = 1) -> ShotRow:
    """Give a row the four picture deliverables a plate plans, in one status."""
    row_.deliverables = [
        Deliverable(
            kind=kind,
            name=f"{row_.clip_name}_{kind}_v{version:02d}",
            path=Path("/delivery") / f"{row_.clip_name}_{kind}",
            version=version,
            status=status,  # type: ignore[arg-type]
        )
        for kind in ("raw_dir", "ref_mp4")
    ]
    return row_


def with_sides(row_: ShotRow) -> ShotRow:
    """Audio, which is the only file beside the media the tool still delivers."""
    row_.audio_path = Path("/turnover/MELT0001_pl01.wav")
    row_.audio_clip_count = 1
    return row_


def warn(row_: ShotRow, rule_id: str = "QC-030") -> ShotRow:
    row_.qc.append(QCResult(rule_id, "warning", "row", "handles are short"))
    return row_


def fail(row_: ShotRow, rule_id: str = "QC-012") -> ShotRow:
    row_.qc.append(QCResult(rule_id, "error", "row", "media not found"))
    return row_


def turnover(turnover_id: str = "turnover001", **kwargs: object) -> Turnover:
    built = Turnover(
        turnover_id=turnover_id,
        folder=Path(f"/source/{turnover_id}_02_23_2026_danielluckett"),
        edl_path=Path(f"/source/{turnover_id}/FINAL_v01.edl"),
        csv_path=Path(f"/source/{turnover_id}/metadata.csv"),
        timeline_start=ONE_HOUR,
    )
    for key, value in kwargs.items():
        setattr(built, key, value)
    return built


def batch(
    *rows: ShotRow,
    turnovers: list[Turnover] | None = None,
    name: str = "melt",
    delivery_root: Path | None = Path("/delivery"),
) -> Batch:
    """A batch holding the rows given, with one turnover unless told otherwise.

    `delivery_root` is a real folder for anything that plans or renders, and the
    unwritable placeholder for everything that only reads the model.
    """
    return Batch(
        name=name,
        delivery_root=delivery_root,
        turnovers=turnovers if turnovers is not None else [turnover()],
        rows=list(rows),
    )


def ingested(built: Batch, tmp_path: Path) -> Batch:
    """Give a batch the colour session a run needs, in place. QC-008 refuses one without.

    A CDL per row, because that is the whole of the grade since 2026-09-22 and QC-009
    checks for it; the EDL is a location and nothing reads it after an ingest, so it is
    a path rather than a file. `clf.ingest` is what does this from a real EDL - this is
    the same end state, built for the tests that are about the window rather than the
    session.
    """
    session = tmp_path / "session"
    session.mkdir(parents=True, exist_ok=True)
    for turnover_ in built.turnovers:
        turnover_.color_session_edl = session / "MELT_FINAL_v01.edl"
        # A real folder, because a run's pre-flight holds back a turnover whose folder
        # has gone (QC-069).
        turnover_.folder = tmp_path / "source" / turnover_.folder.name
        turnover_.folder.mkdir(parents=True, exist_ok=True)
    for row_ in built.rows:
        if row_.shot_code is None:
            continue
        row_.cdl = CDL(
            slope=(1.02, 0.99, 1.01),
            offset=(0.001, -0.002, 0.0),
            power=(0.98, 1.0, 1.02),
            saturation=1.05,
            sop_text=(
                "*ASC_SOP (1.020000 0.990000 1.010000)"
                "(0.001000 -0.002000 0.000000)(0.980000 1.000000 1.020000)"
            ),
            sat_text="*ASC_SAT 1.050000",
        )
        if row_.current is not None:
            row_.approved = row_.current
    return built
