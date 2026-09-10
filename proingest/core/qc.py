"""The QC rule registry.

Rules here are pure functions of the model, so they re-run after every edit without
touching the filesystem. Rules that can only be discovered while scanning (media
missing, ambiguous, unreadable) are raised in `scan.py` instead, because they cannot
be recomputed from a saved batch.

The full phase A and phase B registries arrive with M4. What is implemented now are
the rules that guard the frame rate contract and audio sync, because everything
downstream computes on the assumption that they hold.

Severity comes from docs/QC_RULES.md and is not reinterpreted here.
"""

from __future__ import annotations

from proingest.core.models import Batch, FrameRate, QCResult, ShotRow, Turnover

SYNC_TOLERANCE_FRAMES = 1
"""How far audio may run from picture before it is called a sync problem.

Audio and picture rarely land on exactly the same frame boundary, so a single frame
of slack avoids flagging every clip. Anything beyond that will be audible.
"""


def check_timeline_rate(
    turnover: Turnover, timeline_rate: FrameRate, project_rate: FrameRate
) -> list[QCResult]:
    """QC-025: the timeline's rate must be the project rate.

    Everything is set to the project rate in Resolve before export, so a timeline
    that says otherwise means the conform did not take.
    """
    if timeline_rate == project_rate:
        return []
    return [
        QCResult(
            "QC-025",
            "error",
            "turnover",
            f"timeline is {timeline_rate} fps but the project is {project_rate} fps; "
            f"every clip should have been conformed in Resolve before export",
        )
    ]


def check_source_rate(row: ShotRow, project_rate: FrameRate) -> list[QCResult]:
    """QC-026: media that states a rate must state the project rate.

    Frame math already follows the timeline, so an odd rate here does not corrupt
    the output. It does mean this particular file escaped the conform, so the file
    is flagged rather than quietly accepted.

    Media that states no rate at all, as a DPX sequence does, cannot disagree.
    """
    if row.media is None or row.media.stated_rate is None:
        return []
    if row.media.stated_rate == project_rate:
        return []
    return [
        QCResult(
            "QC-026",
            "error",
            "row",
            f"{row.media.path.name} reports {row.media.stated_rate} fps but the project is "
            f"{project_rate} fps; the file was not conformed with the rest of the turnover",
        )
    ]


def check_audio_sync(row: ShotRow, project_rate: FrameRate) -> list[QCResult]:
    """QC-043: audio that will not line up with picture.

    Audio format is left flexible on purpose. What matters is whether it syncs, so
    the check is a duration comparison against the chosen In/Out range, in frames,
    in both directions. Audio recorded against a different rate shows up here as
    drift even when every file claims to be correct.
    """
    if row.audio is None or row.current is None:
        return []
    audio_frames = row.audio.duration_in_frames(project_rate)
    drift = audio_frames - row.current.duration
    if abs(drift) <= SYNC_TOLERANCE_FRAMES:
        return []
    direction = "longer" if drift > 0 else "shorter"
    return [
        QCResult(
            "QC-043",
            "warning",
            "row",
            f"audio is {abs(drift)} frames {direction} than the {row.current.duration} frame "
            f"picture range and will not sync ({row.audio.path.name})",
        )
    ]


def run_row_rules(row: ShotRow, project_rate: FrameRate) -> list[QCResult]:
    """Every row rule that is a pure function of the model."""
    results: list[QCResult] = []
    results.extend(check_source_rate(row, project_rate))
    results.extend(check_audio_sync(row, project_rate))
    return results


def apply_row_rules(row: ShotRow, project_rate: FrameRate) -> None:
    """Re-run the row rules in place, replacing any previous results from them.

    Results raised elsewhere, such as the scan's QC-012, are left alone: this owns
    only the rule IDs it produces.
    """
    owned = {"QC-026", "QC-043"}
    row.qc = [result for result in row.qc if result.rule_id not in owned]
    row.qc.extend(run_row_rules(row, project_rate))


def apply_batch_rules(batch: Batch) -> None:
    """Re-run every model-derived rule across a batch, after a settings change."""
    for row in batch.rows:
        apply_row_rules(row, batch.project_rate)
