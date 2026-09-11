"""The QC rule registry, phase A.

Rules here are pure functions of the model, so they re-run after every edit without
touching the filesystem. Rules that can only be discovered while scanning (media
missing, ambiguous, unreadable) are raised in `scan.py` instead, because they cannot
be recomputed from a saved batch, and the handful of pre-flight rules that must look
at the disk are grouped at the bottom of this module under `preflight`.

Severity comes from docs/QC_RULES.md and is not reinterpreted here. Three phase A
rules are deliberately not implemented yet and each is recorded in PROGRESS.md
section 9: QC-024 needs decoded pixels rather than a header, QC-053 needs the camData
parser that lands with the exports, and QC-061 needs a Force re-render setting that
does not exist.

Rules are scoped by what the row actually is. An aux still and a BTS frame are single
frames with no timeline range, so the duration, handle and timecode rules skip them:
firing QC-033 on every colour chart in a turnover would bury the warnings that matter.
`is_picture_row` is the one place that decision is made.
"""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any

from proingest.core import exr, ffmpeg
from proingest.core.models import Batch, FrameRate, QCResult, Severity, ShotRow, Turnover

SYNC_TOLERANCE_FRAMES = 1
"""How far audio may run from picture before it is called a sync problem.

Audio and picture rarely land on exactly the same frame boundary, so a single frame
of slack avoids flagging every clip. Anything beyond that will be audible.
"""

LENS_GRID_FRAGMENT = "lensgrid"
"""What a lens grid folder's name contains. OQ-20: it is a folder, never a clip."""

AUDIO_BIT_DEPTH = 16
"""What the delivered wav is. A source that is not this is extracted down to it."""

PICTURE_DELIVERABLES_PER_ROW = 4
"""Raw and reference at both resolutions. `planner.PICTURE_DELIVERABLES`, for QC-063."""


@dataclass(frozen=True)
class RuleSettings:
    """The thresholds the rules compare against. FR-12's Rules section, in one place.

    Nothing here is hardcoded at the point of use, so the Settings page in M5 edits
    this object and every rule follows. Defaults are the ones stated in
    docs/QC_RULES.md, except `expected_handle_frames`, which no doc states (OQ-28).
    """

    min_duration_frames: int = 120
    max_duration_frames: int = 240
    expected_handle_frames: int = 8
    target_resolution: tuple[int, int] = (3840, 2160)
    allow_non_4k: bool = False
    sync_tolerance_frames: int = SYNC_TOLERANCE_FRAMES

    def to_dict(self) -> dict[str, Any]:
        return {
            "min_duration_frames": self.min_duration_frames,
            "max_duration_frames": self.max_duration_frames,
            "expected_handle_frames": self.expected_handle_frames,
            "target_resolution": list(self.target_resolution),
            "allow_non_4k": self.allow_non_4k,
            "sync_tolerance_frames": self.sync_tolerance_frames,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RuleSettings:
        """Build from an overrides dict, taking the default for anything absent.

        An unknown key is an error rather than a shrug: a typo in a settings file
        that silently changed nothing is the failure mode this exists to avoid.
        """
        known = {f.name for f in fields(cls)}
        unknown = sorted(set(data) - known)
        if unknown:
            raise ValueError(f"unknown rule settings: {', '.join(unknown)}")
        resolution = data.get("target_resolution")
        return cls(
            min_duration_frames=int(data.get("min_duration_frames", cls.min_duration_frames)),
            max_duration_frames=int(data.get("max_duration_frames", cls.max_duration_frames)),
            expected_handle_frames=int(
                data.get("expected_handle_frames", cls.expected_handle_frames)
            ),
            target_resolution=(
                (int(resolution[0]), int(resolution[1]))
                if resolution is not None
                else cls.target_resolution
            ),
            allow_non_4k=bool(data.get("allow_non_4k", cls.allow_non_4k)),
            sync_tolerance_frames=int(
                data.get("sync_tolerance_frames", cls.sync_tolerance_frames)
            ),
        )


DEFAULT_SETTINGS = RuleSettings()

RULES_OVERRIDE_KEY = "rules"
"""Where `RuleSettings` lives inside `Batch.settings_overrides`."""

OWNED_ROW_RULES = frozenset(
    {
        "QC-011",
        "QC-020",
        "QC-021",
        "QC-023",
        "QC-026",
        "QC-028",
        "QC-030",
        "QC-031",
        "QC-032",
        "QC-033",
        "QC-034",
        "QC-035",
        "QC-036",
        "QC-040",
        "QC-041",
        "QC-043",
        "QC-044",
        "QC-050",
        "QC-051",
        "QC-055",
    }
)
"""Row rule IDs this module produces, cleared before it produces them again.

Results raised elsewhere, such as the scan's QC-012 or the planner's QC-060, are left
alone: a module owns only the IDs it raises.
"""


def is_picture_row(row: ShotRow) -> bool:
    """True for a row that delivers a moving picture, rather than a still or a BTS.

    An aux still and a BTS frame carry no timeline range worth checking and are
    planned separately (`planner._aux_plan`), so the range, duration, handle and
    timecode rules do not apply to them.
    """
    return row.identity is not None and row.identity.aux is None


def is_plate(row: ShotRow) -> bool:
    """True for the main plate, which is the only element that owes audio and side files."""
    return row.identity is not None and row.identity.aux is None and row.identity.elem_type == "pl"


# --- turnover rules ---------------------------------------------------------------


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


# --- source format rules ----------------------------------------------------------

_DEPTH_PATTERN = re.compile(r"(\d+)(?:le|be)?$")

_EIGHT_BIT_NAMES = frozenset({"rgb24", "bgr24", "rgba", "bgra", "argb", "abgr", "gray"})


def _is_float_format(pixel_format: str) -> bool:
    """A float pixel format carries linear data without damage, whatever its depth."""
    return "f32" in pixel_format or "f16" in pixel_format


def bit_depth(pixel_format: str) -> int:
    """Bits per component of an ffmpeg pixel format name.

    ffmpeg spells depth as a suffix on the planar name (`yuv422p10le`) and bakes it
    into the packed names (`rgb24` is three 8 bit components, `rgb48le` is three 16
    bit ones). Anything with no depth to read is 8, which is ffmpeg's own default for
    the unsuffixed names.
    """
    if _is_float_format(pixel_format):
        return 32
    if pixel_format in _EIGHT_BIT_NAMES:
        return 8
    match = _DEPTH_PATTERN.search(pixel_format)
    if match is None:
        return 8
    value = int(match[1])
    if pixel_format.startswith(("rgb", "bgr", "gbr")) and value in (24, 30, 36, 48, 64):
        # A packed RGB name states the total across components, not the depth of one.
        return value // (4 if value == 64 else 3)
    return value


def check_source_format(row: ShotRow) -> list[QCResult]:
    """QC-020 and QC-021: whether the source can carry a linear plate.

    COLOR_AND_FORMAT section 2 is the list. Float formats and EXR are what the
    pipeline wants; an integer or chroma-subsampled container still decodes, so it is
    a warning about precision rather than a refusal; 8 bit or 4:2:0 cannot be a
    legitimate linear plate at all.
    """
    if row.media is None:
        return []
    pixel_format = row.media.pixel_format
    if _is_float_format(pixel_format):
        return []
    depth = bit_depth(pixel_format)
    if "420" in pixel_format or depth <= 8:
        return [
            QCResult(
                "QC-020",
                "error",
                "row",
                f"{row.media.path.name} is {pixel_format} ({depth} bit); 8 bit and 4:2:0 "
                f"sources cannot carry a linear plate",
            )
        ]
    return [
        QCResult(
            "QC-021",
            "warning",
            "row",
            f"{row.media.path.name} is {pixel_format}, an integer container; linear "
            f"shadow precision is at risk",
        )
    ]


def check_source_codec(row: ShotRow, decoders: frozenset[str]) -> list[QCResult]:
    """QC-022: the source codec must be one this ffmpeg can decode.

    The decoder set is passed in rather than looked up, so the rule stays pure and
    re-runs from a saved batch. `preflight` is what asks ffmpeg for it.
    """
    if row.media is None or not decoders:
        return []
    if row.media.codec in decoders:
        return []
    return [
        QCResult(
            "QC-022",
            "error",
            "row",
            f"{row.media.path.name} is {row.media.codec}, which this ffmpeg cannot decode",
        )
    ]


def check_source_resolution(row: ShotRow, settings: RuleSettings) -> list[QCResult]:
    """QC-023: the source must be the target resolution.

    `render._fit` resamples whatever it is given to the target size, so a source of
    the wrong shape would be squashed rather than letterboxed. This is the check that
    stops that happening, which is why it is an error unless the setting allows it.
    """
    if row.media is None or not is_picture_row(row):
        return []
    if row.media.resolution == settings.target_resolution:
        return []
    width, height = settings.target_resolution
    severity: Severity = "warning" if settings.allow_non_4k else "error"
    return [
        QCResult(
            "QC-023",
            severity,
            "row",
            f"{row.media.path.name} is {row.media.width}x{row.media.height}, not {width}x{height}",
        )
    ]


def check_timecode(row: ShotRow) -> list[QCResult]:
    """QC-028: a source with no embedded timecode.

    Not fatal: the delivered EXRs simply carry no `timeCode` attribute. It is worth
    saying out loud because the vendor reading them back has no way to conform.
    """
    if row.media is None or not is_picture_row(row):
        return []
    if row.media.start_timecode is not None:
        return []
    return [QCResult("QC-028", "warning", "row", f"{row.media.path.name} has no embedded timecode")]


# --- range rules ------------------------------------------------------------------


def check_range(row: ShotRow) -> list[QCResult]:
    """QC-031 and QC-032: an In/Out the media cannot satisfy.

    QC-029 says the same thing about the range the turnover arrived with. These two
    are about the range the editor has chosen since, so both can be true at once and
    each names a different culprit.
    """
    if row.media is None or row.current is None:
        return []
    if row.current.in_frame > row.current.out_frame:
        return [
            QCResult(
                "QC-032",
                "error",
                "row",
                f"In {row.current.in_frame} is after Out {row.current.out_frame}",
            )
        ]
    first, last = row.media.start_frame, row.media.max_available_out
    if row.current.in_frame < first or row.current.out_frame > last:
        return [
            QCResult(
                "QC-031",
                "error",
                "row",
                f"In/Out {row.current.in_frame}-{row.current.out_frame} falls outside the "
                f"{first}-{last} the media holds",
            )
        ]
    return []


def check_handles(row: ShotRow, settings: RuleSettings) -> list[QCResult]:
    """QC-030: too little room left to extend the cut.

    Handles are already inside the timeline range (PRD FR-5), so this is about the
    frames beyond it: what is left if the editor needs to pull Out later.
    """
    if row.media is None or row.current is None or not is_picture_row(row):
        return []
    before = row.current.in_frame - row.media.start_frame
    after = row.media.max_available_out - row.current.out_frame
    want = settings.expected_handle_frames
    short = [
        f"{count} {side}" for count, side in ((before, "before In"), (after, "after Out")) if count < want
    ]
    if not short:
        return []
    return [
        QCResult(
            "QC-030",
            "warning",
            "row",
            f"{' and '.join(short)}, fewer than the {want} handle frames expected",
        )
    ]


def check_duration(row: ShotRow, settings: RuleSettings) -> list[QCResult]:
    """QC-033 and QC-034: a cut outside the expected shot length."""
    if row.current is None or not is_picture_row(row):
        return []
    duration = row.current.duration
    if duration < settings.min_duration_frames:
        return [
            QCResult(
                "QC-033",
                "warning",
                "row",
                f"{duration} frames is below the {settings.min_duration_frames} frame minimum",
            )
        ]
    if duration > settings.max_duration_frames:
        return [
            QCResult(
                "QC-034",
                "warning",
                "row",
                f"{duration} frames is above the {settings.max_duration_frames} frame maximum",
            )
        ]
    return []


def check_edits(row: ShotRow) -> list[QCResult]:
    """QC-035 and QC-036: what the editor changed, recorded rather than judged.

    Both are info. They exist so the QC log can show the turnover's values beside the
    delivered ones and the shooter can be told which shots moved.
    """
    results: list[QCResult] = []
    if row.was_edited and row.snapshot is not None and row.current is not None:
        results.append(
            QCResult(
                "QC-035",
                "info",
                "row",
                f"In/Out edited from {row.snapshot.in_frame}-{row.snapshot.out_frame} to "
                f"{row.current.in_frame}-{row.current.out_frame}",
            )
        )
    if row.shot_code_override and row.identity and row.shot_code_override != row.identity.shot_code:
        results.append(
            QCResult(
                "QC-036",
                "info",
                "row",
                f"shot code edited from {row.identity.shot_code} to {row.shot_code_override}",
            )
        )
    return results


# --- audio rules ------------------------------------------------------------------


def check_audio_presence(row: ShotRow) -> list[QCResult]:
    """QC-040 and QC-041: a plate with no audio, or with more than one candidate.

    Only the plate delivers audio (`planner.AUDIO_TYPES`), so only the plate is asked
    about it. More than one overlapping clip is a warning because the association
    picked the first, and which one it should have been is a human question.
    """
    results: list[QCResult] = []
    if is_plate(row) and row.audio_path is None:
        results.append(QCResult("QC-040", "warning", "row", "plate has no associated audio clip"))
    if row.audio_clip_count > 1:
        results.append(
            QCResult(
                "QC-041",
                "warning",
                "row",
                f"{row.audio_clip_count} audio clips overlap this clip; the first was used",
            )
        )
    return results


def check_audio_format(row: ShotRow) -> list[QCResult]:
    """QC-044: audio that is not already 16 bit PCM.

    The extraction writes 16 bit either way, so this reports a conversion rather than
    a failure. A source that states no depth at all says nothing and is left alone.
    """
    if row.audio is None or row.audio.bit_depth in (0, AUDIO_BIT_DEPTH):
        return []
    return [
        QCResult(
            "QC-044",
            "warning",
            "row",
            f"{row.audio.path.name} is {row.audio.bit_depth} bit; it will be extracted as "
            f"{AUDIO_BIT_DEPTH} bit PCM",
        )
    ]


def check_audio_sync(
    row: ShotRow, project_rate: FrameRate, settings: RuleSettings = DEFAULT_SETTINGS
) -> list[QCResult]:
    """QC-043: audio that will not line up with picture.

    Audio format is left flexible on purpose. What matters is whether it syncs, so
    the check is a duration comparison against the chosen In/Out range, in frames,
    in both directions. Audio recorded against a different rate shows up here as
    drift even when every file claims to be correct.

    OQ-27 makes the reading firm. A wav runs cut point to cut point, so a mismatch
    against the *snapshot* means a malformed turnover, while one against an edited
    range is the editor's own trim: the wav is a byte copy and is never retrimmed.
    The message says which, because the two need different phone calls.
    """
    if row.audio is None or row.current is None:
        return []
    audio_frames = row.audio.duration_in_frames(project_rate)
    drift = audio_frames - row.current.duration
    if abs(drift) <= settings.sync_tolerance_frames:
        return []
    direction = "longer" if drift > 0 else "shorter"
    cause = (
        "the range was edited away from the turnover's and the wav is delivered untrimmed"
        if row.was_edited
        else "the turnover is malformed: a wav should run cut point to cut point"
    )
    return [
        QCResult(
            "QC-043",
            "warning",
            "row",
            f"audio is {abs(drift)} frames {direction} than the {row.current.duration} frame "
            f"picture range and will not sync ({row.audio.path.name}); {cause}",
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


# --- side file rules --------------------------------------------------------------


def check_side_files(row: ShotRow) -> list[QCResult]:
    """QC-050 and QC-051: a plate missing its HDRI or its camera data.

    The shooters' sheet marks both Required per plate. OQ-18 keeps them warnings: a
    missing one chases the shooter, it does not stop the delivery.
    """
    if not is_plate(row):
        return []
    results: list[QCResult] = []
    if row.side_files.hdri is None:
        results.append(QCResult("QC-050", "warning", "row", "plate has no HDRI side file"))
    if row.side_files.camdata is None:
        results.append(QCResult("QC-051", "warning", "row", "plate has no camData side file"))
    return results


def check_aux_still(row: ShotRow) -> list[QCResult]:
    """QC-055: an aux still that is really a clip.

    `planner._aux_plan` delivers the first frame and nothing else, so a colour chart
    that arrived as a hundred frames loses ninety-nine of them silently without this.
    BTS is excluded: it is a still by definition and never carries a frame count.
    """
    if row.identity is None or row.identity.aux is None or row.identity.aux == "BTS":
        return []
    if row.media is None or row.media.frame_count <= 1:
        return []
    return [
        QCResult(
            "QC-055",
            "warning",
            "row",
            f"{row.identity.aux} still has {row.media.frame_count} frames; the first will be used",
        )
    ]


def check_duplicate_name(row: ShotRow, counts: dict[str, int]) -> list[QCResult]:
    """QC-011: the same clip name twice in one batch.

    Names are what every deliverable is built from, so two rows sharing one would
    plan two sets of identical filenames and the second render would overwrite the
    first. `counts` comes from the batch because a row alone cannot know.
    """
    if counts.get(row.clip_name, 0) <= 1:
        return []
    return [
        QCResult(
            "QC-011",
            "warning",
            "row",
            f"{row.clip_name!r} appears {counts[row.clip_name]} times in this batch",
        )
    ]


# --- registry ---------------------------------------------------------------------


def run_row_rules(
    row: ShotRow,
    project_rate: FrameRate,
    settings: RuleSettings = DEFAULT_SETTINGS,
    name_counts: dict[str, int] | None = None,
) -> list[QCResult]:
    """Every row rule that is a pure function of the model, in rule ID order."""
    results: list[QCResult] = []
    results.extend(check_duplicate_name(row, name_counts or {}))
    results.extend(check_source_format(row))
    results.extend(check_source_resolution(row, settings))
    results.extend(check_source_rate(row, project_rate))
    results.extend(check_timecode(row))
    results.extend(check_handles(row, settings))
    results.extend(check_range(row))
    results.extend(check_duration(row, settings))
    results.extend(check_edits(row))
    results.extend(check_audio_presence(row))
    results.extend(check_audio_sync(row, project_rate, settings))
    results.extend(check_audio_format(row))
    results.extend(check_side_files(row))
    results.extend(check_aux_still(row))
    return results


def apply_row_rules(
    row: ShotRow,
    project_rate: FrameRate,
    settings: RuleSettings = DEFAULT_SETTINGS,
    name_counts: dict[str, int] | None = None,
) -> None:
    """Re-run the row rules in place, replacing any previous results from them."""
    row.qc = [result for result in row.qc if result.rule_id not in OWNED_ROW_RULES]
    row.qc.extend(run_row_rules(row, project_rate, settings, name_counts))


def settings_for(batch: Batch) -> RuleSettings:
    """The rule settings a saved batch carries, or the defaults when it carries none."""
    overrides = batch.settings_overrides.get(RULES_OVERRIDE_KEY) or {}
    return RuleSettings.from_dict(overrides)


def clip_name_counts(batch: Batch) -> dict[str, int]:
    """How often each clip name appears, which is all QC-011 needs."""
    counts: dict[str, int] = {}
    for row in batch.rows:
        counts[row.clip_name] = counts.get(row.clip_name, 0) + 1
    return counts


def apply_batch_rules(batch: Batch, settings: RuleSettings = DEFAULT_SETTINGS) -> None:
    """Re-run every model-derived rule across a batch, after a settings change."""
    counts = clip_name_counts(batch)
    for row in batch.rows:
        apply_row_rules(row, batch.project_rate, settings, counts)


# --- pre-flight: the rules that have to look at the disk ---------------------------

OWNED_PREFLIGHT_RULES = frozenset({"QC-022", "QC-052", "QC-054", "QC-057", "QC-062", "QC-063"})
"""Rule IDs `preflight` produces, cleared before a re-run.

QC-022 is here rather than with the model rules only because the decoder set comes
from asking ffmpeg. The rule itself is pure; `check_source_codec` takes the set.
"""


def check_hdri_header(row: ShotRow) -> list[QCResult]:
    """QC-052: an HDRI that does not open as an EXR.

    The copy is a byte copy, so a corrupt HDRI would be delivered intact and unusable.
    Reading the header is cheap and is the only way to know before delivery.
    """
    path = row.side_files.hdri
    if path is None:
        return []
    try:
        exr.read_header(path)
    except (exr.ExrError, OSError) as error:
        return [QCResult("QC-052", "warning", "row", f"{path.name} failed to open as an EXR: {error}")]
    return []


def find_lens_grid_folder(folder: Path) -> Path | None:
    """The lens grid folder in a turnover, or None. OQ-20: it is a folder, not a clip."""
    if not folder.is_dir():
        return None
    for candidate in sorted(folder.rglob("*")):
        if candidate.is_dir() and LENS_GRID_FRAGMENT in candidate.name.lower():
            return candidate
    return None


def check_lens_grid(turnover: Turnover) -> list[QCResult]:
    """QC-054 and QC-057: whether the turnover brought a lens grid.

    Exactly one of the two always fires. Absent chases the shooter, because the
    studio's sheet marks it Required; present is raised because v01 does not deliver
    it and the editor has to move and rename it by hand (OQ-20).
    """
    found = find_lens_grid_folder(turnover.folder)
    if found is None:
        return [
            QCResult(
                "QC-054",
                "warning",
                "turnover",
                "no lens grid folder in the turnover; the studio's sheet marks it required",
            )
        ]
    return [
        QCResult(
            "QC-057",
            "info",
            "turnover",
            f"lens grid folder {found.name!r} is present; v01 does not deliver it, so move and "
            f"rename it by hand per NAMING_SPEC section 3",
        )
    ]


def check_destination_writable(delivery_root: Path | None) -> list[QCResult]:
    """QC-062: the delivery root has to accept a file.

    The root itself need not exist: the run creates the show and shot folders under
    it, so what matters is the nearest ancestor that does exist. Existence is not
    enough on a network mount, which is where this always is, so the check writes and
    removes a probe file rather than trusting the permission bits.
    """
    if delivery_root is None:
        return [QCResult("QC-062", "error", "batch", "no delivery root is set")]
    existing = _nearest_existing(delivery_root)
    if existing is None:
        return [
            QCResult("QC-062", "error", "batch", f"nothing on the path to {delivery_root} exists")
        ]
    if not existing.is_dir():
        return [QCResult("QC-062", "error", "batch", f"{existing} is not a directory")]
    probe = existing / ".proingest-write-probe"
    try:
        probe.touch()
        probe.unlink()
    except OSError as error:
        return [QCResult("QC-062", "error", "batch", f"{existing} is not writable: {error}")]
    return []


def _nearest_existing(path: Path) -> Path | None:
    """The deepest part of `path` that is already on disk, or None."""
    for candidate in (path, *path.parents):
        if candidate.exists():
            return candidate
    return None


def estimate_output_bytes(batch: Batch) -> int:
    """A rough total for what a run will write, for QC-063 only.

    Each row is charged its source's own bytes per frame once per picture deliverable,
    which over-counts the two HD outputs and the compressed references and under-counts
    nothing. A free space warning wants to be pessimistic.
    """
    total = 0
    for row in batch.rows:
        if row.media is None or not row.media.frame_count:
            continue
        per_frame = row.media.size / row.media.frame_count
        duration = row.current.duration if row.current else row.media.frame_count
        total += round(per_frame * duration) * PICTURE_DELIVERABLES_PER_ROW
    return total


def check_free_space(batch: Batch) -> list[QCResult]:
    """QC-063: less free space at the delivery root than the run is likely to need.

    Measured against the nearest existing ancestor, for the same reason QC-062 is:
    the root is usually about to be created and is on the same volume either way.
    """
    if batch.delivery_root is None:
        return []
    root = _nearest_existing(batch.delivery_root)
    if root is None or not root.is_dir():
        return []
    needed = estimate_output_bytes(batch)
    free = shutil.disk_usage(root).free
    if free >= needed:
        return []
    return [
        QCResult(
            "QC-063",
            "warning",
            "batch",
            f"{free // 1_000_000} MB free at {batch.delivery_root} but the run is estimated at "
            f"{needed // 1_000_000} MB",
        )
    ]


def decoders_available() -> frozenset[str]:
    """What this ffmpeg can decode, or nothing when it cannot be asked.

    A build that will not answer must not fail every row in the batch, so QC-022
    falls silent rather than firing on everything.
    """
    try:
        return ffmpeg.available_decoders()
    except (ffmpeg.FFmpegNotFound, ffmpeg.FFmpegError, OSError):
        return frozenset()


def preflight(batch: Batch, decoders: frozenset[str] | None = None) -> None:
    """Run the rules that touch the disk, in place, just before a render.

    Separate from `apply_batch_rules` because these cost stat calls on a network
    mount and their answers change without the model changing. The model rules run
    after every edit; these run when a run is about to start.
    """
    if decoders is None:
        decoders = decoders_available()
    batch.qc = [result for result in batch.qc if result.rule_id not in OWNED_PREFLIGHT_RULES]
    batch.qc.extend(check_destination_writable(batch.delivery_root))
    batch.qc.extend(check_free_space(batch))
    for turnover in batch.turnovers:
        turnover.qc = [
            result for result in turnover.qc if result.rule_id not in OWNED_PREFLIGHT_RULES
        ]
        turnover.qc.extend(check_lens_grid(turnover))
    for row in batch.rows:
        row.qc = [result for result in row.qc if result.rule_id not in OWNED_PREFLIGHT_RULES]
        row.qc.extend(check_source_codec(row, decoders))
        row.qc.extend(check_hdri_header(row))


