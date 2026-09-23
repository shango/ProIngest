"""The QC rule registry, phase A.

Rules here are pure functions of the model, so they re-run after every edit without
touching the filesystem. Rules that can only be discovered while scanning (media
missing, ambiguous, unreadable) are raised in `scan.py` instead, because they cannot
be recomputed from a saved batch, and the handful of pre-flight rules that must look
at the disk are grouped at the bottom of this module under `preflight`.

Severity comes from docs/QC_RULES.md and is not reinterpreted here. QC-060 and QC-061
are the planner's, which is where a version is decided.

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

import xxhash

from proingest.core import clf, color, exr, ffmpeg, media, naming
from proingest.core.models import (
    Batch,
    Deliverable,
    FrameRate,
    QCResult,
    Severity,
    ShotRow,
    Turnover,
)
from proingest.core.planner import DeliverableJob, effective_identity

SYNC_TOLERANCE_FRAMES = 1
"""How far audio may run from picture before it is called a sync problem.

Audio and picture rarely land on exactly the same frame boundary, so a single frame
of slack avoids flagging every clip. Anything beyond that will be audible.
"""

"""What a lens grid folder's name contains. OQ-20: it is a folder, never a clip."""

AUDIO_BIT_DEPTH = 16
"""What the delivered wav is. A source that is not this is extracted down to it."""

EXR_SUFFIX = ".exr"
WAV_SUFFIX = ".wav"

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
            expected_handle_frames=int(data.get("expected_handle_frames", cls.expected_handle_frames)),
            target_resolution=(
                (int(resolution[0]), int(resolution[1])) if resolution is not None else cls.target_resolution
            ),
            allow_non_4k=bool(data.get("allow_non_4k", cls.allow_non_4k)),
            sync_tolerance_frames=int(data.get("sync_tolerance_frames", cls.sync_tolerance_frames)),
        )


DEFAULT_SETTINGS = RuleSettings()

RULES_OVERRIDE_KEY = "rules"
"""Where `RuleSettings` lives inside `Batch.settings_overrides`."""

OWNED_ROW_RULES = frozenset(
    {
        "QC-011",
        "QC-018",
        "QC-020",
        "QC-021",
        "QC-023",
        "QC-026",
        "QC-027",
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
        "QC-045",
        "QC-046",
        "QC-047",
        "QC-055",
    }
)
"""Row rule IDs this module produces, cleared before it produces them again.

Results raised elsewhere, such as the scan's QC-012 or the planner's QC-060, are left
alone: a module owns only the IDs it raises.
"""


def is_picture_row(row: ShotRow) -> bool:
    """True for a row that delivers a moving picture rather than a reference still.

    A still carries no timeline range worth checking and is planned separately
    (`planner._aux_plan`), so the range, duration, handle and timecode rules do not
    apply to it.
    """
    return row.identity is not None and not row.identity.is_still


def delivers_aux_still(row: ShotRow) -> bool:
    """True for a row that delivers a reference still the tool converts on its own.

    The one picture with no grade in its chain by design (COLOR_AND_FORMAT section 1),
    so it is the one that cannot be delivered without a source encoding.
    """
    return row.identity is not None and row.identity.is_still


def is_plate(row: ShotRow) -> bool:
    """True for the main plate, which is the only clip type that owes audio."""
    return row.identity is not None and row.identity.kind == "pl"


# --- source format rules ----------------------------------------------------------

_DEPTH_PATTERN = re.compile(r"(\d+)(?:le|be)?$")

_EIGHT_BIT_NAMES = frozenset(
    {
        "rgb24",
        "bgr24",
        "rgba",
        "bgra",
        "argb",
        "abgr",
        "gray",
        # Packed and semi-planar names bake a layout number into the name, not a depth:
        # `nv12` is 8 bit 4:2:0, `uyvy422` is 8 bit 4:2:2, `rgb0` is 8 bit with a pad byte.
        "nv12",
        "nv21",
        "nv16",
        "nv24",
        "yuyv422",
        "uyvy422",
        "yvyu422",
        "rgb0",
        "bgr0",
        "0rgb",
        "0bgr",
    }
)


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
                "warning",
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


def check_color_tags(row: ShotRow) -> list[QCResult]:
    """QC-018, info: the matrix and range a container is decoded with, when it is not
    simply the BT.709 it says it is.

    The file's own matrix is used when it states one; otherwise BT.709, which is the
    user's provisional choice (D17), so every row that takes it says so. A sequence is
    RGB and has no matrix to choose.
    """
    media = row.media
    if media is None or media.is_sequence or media.color_space == "bt709":
        return []
    decoded = f"{ffmpeg.input_matrix(media.color_space)}, {ffmpeg.input_range(media.color_range)} range"
    if not media.color_space:
        said = "states no colour matrix, so it is decoded as BT.709 (provisional)"
    else:
        said = f"states the {media.color_space} matrix, so it is decoded with that"
    return [QCResult("QC-018", "info", "row", f"{media.path.name} {said}: {decoded}")]


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

    A source of another size is resampled to fit and letterboxed rather than stretched
    (F9), which is a delivery nobody asked for, so it is still an error unless the
    setting allows it.
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
    """QC-027 and QC-028: drop-frame timecode, and a source with none.

    Drop-frame is must-fix: no 24 fps frame count honours it, and it used to fall
    through to QC-028 as though the file had none (F24). No timecode at all is not
    fatal: the delivered EXRs simply carry no `timeCode` attribute. It is worth saying
    out loud because the vendor reading them back has no way to conform.
    """
    if row.media is None or not is_picture_row(row):
        return []
    if row.media.drop_frame:
        return [
            QCResult(
                "QC-027",
                "error",
                "row",
                f"{row.media.path.name} states drop-frame timecode, which a 24 fps delivery cannot carry",
            )
        ]
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


def check_approved(row: ShotRow) -> list[QCResult]:
    """QC-045: the row will be delivered at an In/Out the colour session did not approve.

    A warning where QC-035 is info, and the difference is what the comparison is
    against. QC-035 compares with the turnover snapshot, which records what the editor
    did; this compares with the cut Ben and the AD signed off, so the fact it carries is
    that **the delivered shot is not the shot that was approved**. Nothing else records
    that, which is the whole reason the rule exists.

    Silent until a session has been ingested, because `approved` is what an ingest
    writes and a row with none has nothing to deviate from (QC-008 is that state). An
    ingest writes `current` from `approved` as well, so this fires on the one-off trim
    made afterwards, which is a supported thing to do (PRD FR-5) and not an error.
    """
    approved, current = row.approved, row.current
    if approved is None or current is None or approved == current:
        return []
    return [
        QCResult(
            "QC-045",
            "warning",
            "row",
            f"delivered at {current.in_frame}-{current.out_frame}, but the colour session "
            f"approved {approved.in_frame}-{approved.out_frame}",
        )
    ]


# --- audio rules ------------------------------------------------------------------


def check_audio_presence(row: ShotRow) -> list[QCResult]:
    """QC-040 and QC-041: a plate with no audio, or with more than one candidate.

    Only the plate delivers audio (`planner.AUDIO_TYPES`), so only the plate is asked
    whether it has any. More than one audio file matching the clip's name is a warning
    on any row: the scan uses none of them rather than guess, and which one it should
    have been is a human question.
    """
    results: list[QCResult] = []
    # Audio inside the plate's own file is audio: it was delivered and reported
    # missing on every real plate (F20).
    embedded = row.media is not None and row.media.has_audio
    if is_plate(row) and row.audio_path is None and not embedded:
        results.append(QCResult("QC-040", "warning", "row", "plate has no associated audio clip"))
    if row.audio_clip_count > 1:
        results.append(
            QCResult(
                "QC-041",
                "warning",
                "row",
                f"{row.audio_clip_count} audio files match this clip's name, so none was used",
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
    range is the editor's own trim. The delivered wav is cut to the edited range, so
    audio longer than it is cut off, and audio shorter than it is padded with silence.
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
        (
            "the range was edited past the turnover's audio, so the delivered wav is padded with silence"
            if drift < 0
            else "the range was edited inside the turnover's; the delivered wav is cut to it"
        )
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


def _pulled_down(rate: FrameRate) -> FrameRate:
    """`rate` slowed by 1000/1001: 24000/1001 for 24. Exact, never a float comparison."""
    return FrameRate(rate.numerator * 1000, rate.denominator * 1001)


def check_source_rate(row: ShotRow, project_rate: FrameRate) -> list[QCResult]:
    """QC-026: media that states a rate must state the project rate, or its 1000/1001.

    **24000/1001 against 24 is the normal case and is silent** (user, 2026-09-23). The
    shooters set every clip to 24 in Resolve, which is a timeline property: Copy with trim
    does not rewrite the file, so every delivered file states 24000/1001 and is rendered
    at 24 frame for frame. Any other rate, 25 or 30, is an error and the row does not run.

    Frame math already follows the timeline, so an odd rate here does not corrupt
    the output. It does mean this particular file escaped the conform, so the file
    is flagged rather than quietly accepted.

    Media that states no rate at all, as a DPX sequence does, cannot disagree.
    """
    if row.media is None or row.media.stated_rate is None:
        return []
    if row.media.stated_rate in (project_rate, _pulled_down(project_rate)):
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


def check_aux_still(row: ShotRow) -> list[QCResult]:
    """QC-055: an aux still that is really a clip.

    `planner._aux_plan` delivers the In frame and nothing else, so a colour chart that
    arrived as a hundred frames loses ninety-nine of them silently without this. **That
    is now the normal case rather than an oddity**: in the real sample a reference still
    is one timeline frame inside a 49-frame file, so this fires on every one of them.
    """
    if row.identity is None or not row.identity.is_still:
        return []
    if row.media is None or row.media.frame_count <= 1:
        return []
    return [
        QCResult(
            "QC-055",
            "warning",
            "row",
            f"{row.identity.kind} still has {row.media.frame_count} frames; the In frame will be used",
        )
    ]


def check_source_encoding(row: ShotRow) -> list[QCResult]:
    """QC-046 and QC-047: the clip named no source encoding, or named one that does not resolve.

    **An error on every row the tool transforms**, which since 2026-09-18 is every plate
    as well as the aux still: the grade is applied in ACEScct and this name is what gets
    the clip there, so a wrong one grades the wrong pixels and a missing one renders
    nothing. Info on a BTS frame, which is copied byte for byte.

    QC-047 quotes what was written and says what it could not be resolved to, because
    the fix is somebody retyping a field rather than anything in the tool.
    """
    blocking = is_picture_row(row) or delivers_aux_still(row)
    if row.source_encoding is None:
        return [
            QCResult(
                "QC-046",
                "error" if blocking else "info",
                "row",
                "the clip's metadata names no source encoding",
            )
        ]
    try:
        color.resolve_encoding(row.source_encoding)
    except color.ColorError as exc:
        return [
            QCResult(
                "QC-047",
                "error" if blocking else "warning",
                "row",
                f"source encoding {exc}",
            )
        ]
    return []


def identity_key(row: ShotRow) -> str | None:
    """What a row's deliverables are named from: shot code, type and index (D6).

    None for a row that delivers nothing, which cannot collide with anything. A skipped
    row is one, so skipping the second of two is a way to resolve a duplicate.
    """
    if row.skipped or row.identity is None or row.shot_code is None:
        return None
    return f"{row.shot_code} {row.identity.kind}{row.identity.index}"


def check_duplicate_name(row: ShotRow, counts: dict[str, int]) -> list[QCResult]:
    """QC-011, must-fix: two rows with the same shot code, type and index (D6).

    Names are built from that identity, so two rows sharing one would plan the same
    files and the second render would overwrite the first. It used to key on the clip
    name, which a clip used twice legitimately repeats and two different clips never do
    (F2). `counts` comes from the batch because a row alone cannot know.
    """
    key = identity_key(row)
    if key is None or counts.get(key, 0) <= 1:
        return []
    others = counts[key] - 1
    also = "so is another row" if others == 1 else f"so are {others} other rows"
    return [
        QCResult(
            "QC-011",
            "error",
            "row",
            f"{row.clip_name} is {key}, and {also} in this batch; they would write the same files",
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
    results.extend(check_source_encoding(row))
    results.extend(check_color_tags(row))
    results.extend(check_source_format(row))
    results.extend(check_source_resolution(row, settings))
    results.extend(check_source_rate(row, project_rate))
    results.extend(check_timecode(row))
    results.extend(check_handles(row, settings))
    results.extend(check_range(row))
    results.extend(check_duration(row, settings))
    results.extend(check_edits(row))
    results.extend(check_approved(row))
    results.extend(check_audio_presence(row))
    results.extend(check_audio_sync(row, project_rate, settings))
    results.extend(check_audio_format(row))
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
    """How often each identity appears (`identity_key`), which is all QC-011 needs."""
    counts: dict[str, int] = {}
    for row in batch.rows:
        key = identity_key(row)
        if key is not None:
            counts[key] = counts.get(key, 0) + 1
    return counts


def apply_duplicate_rule(batch: Batch, counts: dict[str, int]) -> None:
    """QC-011 alone, across the batch: what one row's edit can change about the others."""
    for row in batch.rows:
        row.qc = [result for result in row.qc if result.rule_id != "QC-011"]
        row.qc.extend(check_duplicate_name(row, counts))


def apply_batch_rules(batch: Batch, settings: RuleSettings = DEFAULT_SETTINGS) -> None:
    """Re-run every model-derived rule across a batch, after a settings change."""
    counts = clip_name_counts(batch)
    for row in batch.rows:
        apply_row_rules(row, batch.project_rate, settings, counts)


# --- pre-flight: the rules that have to look at the disk ---------------------------

OWNED_PREFLIGHT_RULES = frozenset(
    {
        "QC-008",
        "QC-069",
        "QC-009",
        "QC-022",
        "QC-048",
        "QC-062",
        "QC-063",
    }
)
"""Rule IDs `preflight` produces, cleared before a re-run.

QC-022 is here rather than with the model rules only because the decoder set comes
from asking ffmpeg. The rule itself is pure; `check_source_codec` takes the set.
"""


def check_color_session(turnover: Turnover, rows: list[ShotRow]) -> list[QCResult]:
    """QC-008: the turnover has no colour session behind it, so nothing final can be rendered.

    **Turnover scope rather than batch scope, and that is the point of it**: turnovers
    arrive on different days and the grade for one is signed off while the next is still
    being shot, so one turnover can be waiting on colour while another renders
    (`Turnover.color_session_edl`).

    Two ways to be in that state and they read differently to the person fixing it: an
    ingest that never happened, and a session that ingested but delivered no CLF for
    anything in this turnover. The second is the one worth separating from QC-009: a
    single row with no CLF is a matching problem, and no row with one is a package that
    was never exported.

    **The package's own files are not checked here and that is deliberate.** An ingest
    writes what the session said onto the rows, so nothing reads the EDL again and a
    package archived after a delivery costs a re-ingest rather than a render. The one
    file a render still needs is the CLF itself, and QC-009 is what checks that, per row,
    where the answer differs per row.
    """
    edl = turnover.color_session_edl
    if edl is None:
        return [
            QCResult(
                "QC-008",
                "error",
                "turnover",
                "no colour session has been ingested; nothing final can be rendered "
                "until the session's final EDL is ingested for this turnover",
            )
        ]
    if not any(clf.has_grade(row) for row in rows):
        return [
            QCResult(
                "QC-008",
                "error",
                "turnover",
                f"{edl.name} was ingested but carried no CDL for any row in this turnover",
            )
        ]
    return []


def check_clf(row: ShotRow, has_session: bool) -> list[QCResult]:
    """QC-009: this row has no usable grade, and an ungraded plate is the wrong pixels.

    Silent until a session has been ingested for the turnover, because with none the
    whole turnover is QC-008 and repeating it per row would bury it, and silent on an
    aux still and a BTS frame, which are delivered ungraded by design and owe no grade
    (`is_picture_row`). Two states report the same way because they cost the same thing:
    the session left this shot neither a CDL nor a cube (OQ-33), and the cube it left is
    no longer on the disk.
    """
    if not has_session or not is_picture_row(row):
        return []
    if not clf.has_grade(row):
        return [
            QCResult(
                "QC-009",
                "error",
                "row",
                "the colour session left no CDL for this shot; it would render ungraded",
            )
        ]
    return []


def check_color_chain(row: ShotRow) -> list[QCResult]:
    """QC-048: which colour chain this row is about to be rendered through.

    **Not a check and deliberately not one** (OQ-46). It says what the tool did, so a
    delivery that turns out to have been graded in the wrong space, or through a cube
    nobody remembers exporting, is identifiable afterwards rather than re-derived from a
    setting nobody wrote down.

    Here rather than with the model rules because the chain is resolved by the planner,
    which runs immediately before a render: a row's chain is a fact about the run that
    is about to happen, not about the batch as it was scanned.
    """
    encoding = clf.resolved_encoding(row)
    if delivers_aux_still(row):
        chain = (
            f"{encoding} to {color.PLATE_SPACE}, never graded"
            if encoding
            else "nothing: no source encoding resolved"
        )
        return [QCResult("QC-048", "info", "row", f"aux still rendered through {chain}")]
    if encoding is None:
        return [QCResult("QC-048", "info", "row", "no source encoding: nothing to render through")]
    legs = f"{encoding} to {color.WORKING_SPACE}, {{grade}}, {color.WORKING_SPACE} to {color.PLATE_SPACE}"
    if row.cdl is not None:
        grade = "the CDL"
    else:
        return [
            QCResult(
                "QC-048",
                "info",
                "row",
                f"no grade: rendered through the input transform alone, {encoding} to {color.PLATE_SPACE}",
            )
        ]
    return [QCResult("QC-048", "info", "row", f"rendered through {legs.format(grade=grade)}")]


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
        return [QCResult("QC-062", "error", "batch", f"nothing on the path to {delivery_root} exists")]
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
        try:
            if candidate.exists():
                return candidate
        except OSError:
            # `exists` swallows a missing path but not a mount that refuses to answer.
            continue
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
    try:
        free = shutil.disk_usage(root).free
    except OSError as exc:
        # A mount that will not say is a warning, not a crash out of pre-flight.
        return [QCResult("QC-063", "warning", "batch", f"free space at {root} could not be read: {exc}")]
    if free >= needed:
        return []
    return [
        QCResult(
            "QC-063",
            "error",
            "batch",
            f"{free // 1_000_000} MB free at {batch.delivery_root} but the run is estimated at "
            f"{needed // 1_000_000} MB",
        )
    ]


def must_fix(batch: Batch) -> list[tuple[str, QCResult]]:
    """Every error in the batch that stops a run, with where it is (D8, D9).

    **Any must-fix anywhere stops the whole run**: the editor fixes the folder, re-scans
    and runs, and nothing renders past a problem nobody has looked at. A skipped row's
    errors do not count, because a skipped row renders nothing. Where is the batch, a
    turnover's folder name, or a row's clip name. Phase B (QC-1xx) is not here: it is
    about what a run wrote, and fails the row rather than refusing the next run.
    """
    found: list[tuple[str, QCResult]] = [("batch", r) for r in batch.qc if r.severity == "error"]
    for turnover in batch.turnovers:
        found.extend((turnover.folder.name, r) for r in turnover.qc if r.severity == "error")
    for row in batch.rows:
        if row.skipped:
            continue
        found.extend((row.clip_name, r) for r in row.qc if r.severity == "error" and not _phase_b(r))
    return found


def blocking_results(batch: Batch) -> list[QCResult]:
    """`must_fix` without the where. The window and `proingest run` both ask here, so the
    two cannot come to different answers about whether a batch may go."""
    return [result for _, result in must_fix(batch)]


def _phase_b(result: QCResult) -> bool:
    return result.rule_id.startswith("QC-1")


def check_turnover_folder(turnover: Turnover) -> list[QCResult]:
    """QC-069: the turnover's folder is not where the batch last found it (D16).

    An error, so the turnover cannot run: its sources are in that folder. Fixed by
    right-clicking the turnover and choosing its new location, which rescans it there.
    """
    if turnover.folder.is_dir():
        return []
    return [
        QCResult(
            "QC-069",
            "error",
            "turnover",
            f"{turnover.folder} is not there any more; right-click the turnover and choose "
            f"New Folder Location",
        )
    ]


def check_folders(batch: Batch) -> None:
    """QC-069 on every turnover, alone. What opening a batch runs; `preflight` runs it too."""
    for turnover in batch.turnovers:
        turnover.qc = [result for result in turnover.qc if result.rule_id != "QC-069"]
        turnover.qc.extend(check_turnover_folder(turnover))


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
    graded: set[str] = set()
    for turnover in batch.turnovers:
        turnover.qc = [result for result in turnover.qc if result.rule_id not in OWNED_PREFLIGHT_RULES]
        turnover.qc.extend(check_color_session(turnover, batch.rows_for(turnover.turnover_id)))
        turnover.qc.extend(check_turnover_folder(turnover))
        if turnover.color_session_edl is not None:
            graded.add(turnover.turnover_id)
    for row in batch.rows:
        row.qc = [result for result in row.qc if result.rule_id not in OWNED_PREFLIGHT_RULES]
        row.qc.extend(check_source_codec(row, decoders))
        row.qc.extend(check_clf(row, row.turnover_id in graded))
        row.qc.extend(check_color_chain(row))


# --- phase B: verifying what was written ------------------------------------------

RENDER_FAILED = "QC-100"
"""The render did not complete. Every other QC-1xx is NA when this one fires.

It is also the exception to phase B's keep-the-file rule: a render failure leaves
nothing at all, so there is no file to mark and nothing to inspect.
"""

DIGEST_CHUNK = 1 << 20

EXR_COMPRESSION = "DWAA_COMPRESSION"
"""What COLOR_AND_FORMAT section 3 pins, and what `exr.write_frame` writes."""

EXR_PIXEL_TYPE = "float16"
"""Half float (OQ-13), as `numpy` spells it back from the header."""

EXR_CHANNEL_SETS = (("R", "G", "B"), ("R", "G", "B", "A"))

SMALL_FRAME_RATIO = 0.10
"""QC-107: a frame under this share of the sequence median is probably black."""

WAV_BIT_DEPTH = 16
WAV_CODEC = "pcm_s16le"


def file_digest(path: Path) -> str:
    """xxhash64 of a file, read in chunks so a 4k frame never lands in memory twice."""
    digest = xxhash.xxh64()
    with path.open("rb") as handle:
        while block := handle.read(DIGEST_CHUNK):
            digest.update(block)
    return digest.hexdigest()


def _failure(rule_id: str, message: str, severity: Severity = "error") -> QCResult:
    return QCResult(rule_id, severity, "deliverable", message)


def run_phase_b(job: DeliverableJob, deliverable: Deliverable) -> list[QCResult]:
    """Verify one deliverable against the job that planned it, after the rename.

    The job is the expectation and the file on disk is the claim, which is why this
    takes both: everything phase B checks (frame count, target size, rate, the source
    to compare a copy against) is on the job, and the checksums the writer recorded
    are on the deliverable.

    ARCHITECTURE.md calls this `qc.run_phase_b(job)`; it takes the deliverable too
    because QC-106 and QC-120 compare against what the writer recorded, which a job
    cannot know.

    Nothing here raises. A check that cannot be made because the file will not open is
    reported as the failure it is, so one unreadable deliverable cannot stop a run.
    """
    if deliverable.status == "failed":
        # QC-100 already said the render did not complete; there is no file to check.
        return []
    verifier = {
        "raw_dir": _verify_sequence,
        "aux_still": _verify_still,
        "ref_mp4": _verify_reference,
        "audio": _verify_audio,
    }.get(job.kind)
    if verifier is None:
        return [_failure(RENDER_FAILED, f"{job.name}: no phase B checks for a {job.kind} job")]
    if not job.destination.exists():
        return [_failure(RENDER_FAILED, f"{job.name}: nothing was written to {job.destination}")]
    return verifier(job, deliverable)


# --- QC-101 to QC-107: a delivered EXR sequence -----------------------------------


def _verify_sequence(job: DeliverableJob, deliverable: Deliverable) -> list[QCResult]:
    """Every check the delivered sequence owes, in rule ID order.

    The frames are listed once and every later check reads that list, because this
    runs on a network mount and a second listing of a 240 frame folder costs real
    time for an answer already in hand.
    """
    results: list[QCResult] = []
    paths = sorted(job.destination.glob(f"*{EXR_SUFFIX}"))

    if len(paths) != job.frame_count:
        results.append(_failure("QC-101", f"{job.name} holds {len(paths)} frames, not {job.frame_count}"))
    results.extend(_check_numbering(job, paths))
    results.extend(_check_frame_headers(job, paths))
    results.extend(_check_frame_digests(deliverable, paths))
    results.extend(_check_frame_sizes(paths))
    return results


def _check_numbering(job: DeliverableJob, paths: list[Path]) -> list[QCResult]:
    """QC-102: 1001 first, no gaps, nothing extra.

    The frame number is read back out of each filename rather than assumed from the
    position in the sorted list, so a missing frame shows up as the gap it is instead
    of shifting every later frame's identity.
    """
    found = [naming.parse_output_name(path.name, job.show_pattern) for path in paths]
    numbers = [parsed.frame for parsed in found if parsed is not None and parsed.frame is not None]
    unparsed = [path.name for path, parsed in zip(paths, found, strict=True) if parsed is None]
    expected = list(job.output_frames())
    if not expected:
        return [_failure("QC-102", f"{job.name} planned no frames but {len(paths)} were delivered")]
    if unparsed:
        return [_failure("QC-102", f"{job.name} holds files that are not delivery frames: {unparsed[0]}")]
    if numbers == expected:
        return []
    missing = sorted(set(expected) - set(numbers))
    extra = sorted(set(numbers) - set(expected))
    detail = f"missing {missing[:5]}" if missing else f"unexpected {extra[:5]}"
    return [
        _failure(
            "QC-102",
            f"{job.name} should run {expected[0]} to {expected[-1]} with no gaps: {detail}",
        )
    ]


def _check_frame_headers(job: DeliverableJob, paths: list[Path]) -> list[QCResult]:
    """QC-103, QC-104 and QC-105: every frame opens and says what it should.

    One result per rule rather than one per frame: a sequence whose every frame is the
    wrong compression is one defect, and 240 identical rows would bury the rest of the
    report. The first offender is named, which is what someone opening a file needs.
    """
    results: list[QCResult] = []
    unreadable: tuple[Path, str] | None = None
    bad_window: Path | None = None
    bad_format: tuple[Path, str] | None = None

    for path in paths:
        try:
            header = exr.read_header(path)
        except (exr.ExrError, OSError) as error:
            unreadable = unreadable or (path, str(error))
            continue
        if bad_window is None and (
            not header.windows_match or (job.target_size is not None and header.resolution != job.target_size)
        ):
            bad_window = path
        if bad_format is None:
            bad_format = _frame_format_fault(path, header)

    if unreadable is not None:
        results.append(_failure("QC-103", f"{unreadable[0].name} did not open: {unreadable[1]}"))
    if bad_window is not None:
        results.append(
            _failure(
                "QC-104",
                f"{bad_window.name} does not have both windows at {job.target_size}",
            )
        )
    if bad_format is not None:
        results.append(_failure("QC-105", f"{bad_format[0].name} {bad_format[1]}"))
    return results


def _frame_format_fault(path: Path, header: exr.ExrHeader) -> tuple[Path, str] | None:
    """QC-105's complaint about one frame, or None when it is what the spec pins."""
    if header.compression != EXR_COMPRESSION:
        return path, f"is {header.compression}, not {EXR_COMPRESSION}"
    if header.channels not in EXR_CHANNEL_SETS:
        return path, f"has channels {header.channels}, not R,G,B or R,G,B,A"
    if header.pixel_type != EXR_PIXEL_TYPE:
        return path, f"is {header.pixel_type}, not {EXR_PIXEL_TYPE}"
    return None


def _check_frame_digests(deliverable: Deliverable, paths: list[Path]) -> list[QCResult]:
    """QC-106: every frame still hashes to what the writer recorded.

    DWAA is lossy, so a frame does not read back byte-identical to the pixels that
    went in; the encoder is deterministic, so the written file's digest is stable.
    This catches a frame changed or truncated between the write and the rename.
    """
    recorded = deliverable.frame_checksums
    if not recorded:
        return []
    if len(recorded) != len(paths):
        return [
            _failure(
                "QC-106",
                f"{len(paths)} frames on disk against {len(recorded)} checksums recorded",
            )
        ]
    for path, expected in zip(paths, recorded, strict=True):
        if file_digest(path) != expected:
            return [_failure("QC-106", f"{path.name} does not match the checksum recorded for it")]
    return []


def _check_frame_sizes(paths: list[Path]) -> list[QCResult]:
    """QC-107: a frame far smaller than its neighbours, which usually means black.

    A warning, not an error: a genuinely dark frame at the head of a shot is legal and
    common. The median is the comparison because a handful of black frames would drag
    a mean down far enough to hide themselves.
    """
    if len(paths) < 3:
        return []
    sizes = [path.stat().st_size for path in paths]
    middle = sorted(sizes)[len(sizes) // 2]
    small = [path.name for path, size in zip(paths, sizes, strict=True) if size < middle * SMALL_FRAME_RATIO]
    if not small:
        return []
    shown = ", ".join(small[:3])
    more = f" and {len(small) - 3} more" if len(small) > 3 else ""
    return [
        _failure(
            "QC-107",
            f"{len(small)} frames are under {int(SMALL_FRAME_RATIO * 100)}% of the median "
            f"size and may be black: {shown}{more}",
            severity="warning",
        )
    ]


def _verify_still(job: DeliverableJob, deliverable: Deliverable) -> list[QCResult]:
    """An aux still is one EXR, so it owes the header checks and nothing about counts.

    QC_RULES scopes QC-103 to QC-105 at "exr seq". A still is written by the same
    function into the same format, and a mirror ball delivered as ZIP RGBA float would
    be the same defect, so the same three rules are applied to it.
    """
    results = _check_frame_headers(job, [job.destination])
    if deliverable.checksum and file_digest(job.destination) != deliverable.checksum:
        results.append(_failure("QC-106", f"{job.name} does not match the checksum recorded for it"))
    return results


# --- QC-110 to QC-115: a delivered reference mp4 ----------------------------------


def _verify_reference(job: DeliverableJob, deliverable: Deliverable) -> list[QCResult]:
    """The reference has to be playable, complete, the right size and in sync."""
    try:
        probed = ffmpeg.probe_raw(job.destination)
    except (ffmpeg.FFprobeError, ffmpeg.FFmpegNotFound) as error:
        return [_failure("QC-110", f"{job.name} did not open: {error}")]

    streams = probed.get("streams", [])
    video = [stream for stream in streams if stream.get("codec_type") == "video"]
    audio = [stream for stream in streams if stream.get("codec_type") == "audio"]
    if len(video) != 1:
        return [_failure("QC-110", f"{job.name} has {len(video)} video streams, not one")]

    results: list[QCResult] = []
    results.extend(_check_reference_frames(job))
    results.extend(_check_reference_video(job, video[0]))
    results.extend(_check_reference_audio(job, audio))
    results.extend(_check_faststart(job))
    return results


def _check_reference_frames(job: DeliverableJob) -> list[QCResult]:
    """QC-111: the frame count by decode, not by the container's own index.

    The render already compared the index; this decodes, because an index can say 240
    over a file that stops at 12 and the delivered reference is what the vendor plays.
    """
    try:
        counted = ffmpeg.count_frames(job.destination)
    except (ffmpeg.FFprobeError, ffmpeg.FFmpegNotFound) as error:
        return [_failure("QC-111", f"{job.name} could not be counted: {error}")]
    if counted == job.frame_count:
        return []
    return [_failure("QC-111", f"{job.name} decodes {counted} frames, not {job.frame_count}")]


def _check_reference_video(job: DeliverableJob, stream: dict[str, Any]) -> list[QCResult]:
    """QC-112 and QC-113: the size and the rate the vendor will conform against."""
    results: list[QCResult] = []
    size = (int(stream.get("width", 0)), int(stream.get("height", 0)))
    if job.target_size is not None and size != job.target_size:
        results.append(_failure("QC-112", f"{job.name} is {size[0]}x{size[1]}, not {job.target_size}"))
    if job.rate is not None:
        stated = str(stream.get("r_frame_rate", ""))
        expected = f"{job.rate.numerator}/{job.rate.denominator}"
        if stated != expected:
            results.append(_failure("QC-113", f"{job.name} plays at {stated}, not {expected}"))
    return results


def _check_reference_audio(job: DeliverableJob, audio: list[dict[str, Any]]) -> list[QCResult]:
    """QC-114: an audio stream exactly when the row had audio to mux.

    Both directions are defects. A missing stream is a silent reference; an unexpected
    one means the encode picked up sound from somewhere the plan did not know about.
    """
    wanted = job.audio_source is not None
    if wanted == bool(audio):
        return []
    complaint = "has no audio stream" if wanted else "has an audio stream nothing planned"
    return [_failure("QC-114", f"{job.name} {complaint}", severity="warning")]


def _check_faststart(job: DeliverableJob) -> list[QCResult]:
    """QC-115: the moov atom ahead of the media data, so the file streams.

    Read from the box headers rather than trusting the `-movflags +faststart` that
    asked for it: the flag is a request, and a file that fell back to a trailing moov
    still plays locally and stalls over a Drive link, which is exactly where these go.
    """
    try:
        order = _top_level_boxes(job.destination)
    except OSError as error:
        return [_failure("QC-115", f"{job.name} could not be read: {error}")]
    if "moov" not in order:
        return [_failure("QC-115", f"{job.name} has no moov atom")]
    if "mdat" in order and order.index("mdat") < order.index("moov"):
        return [_failure("QC-115", f"{job.name} has its moov atom after the media data")]
    return []


def _top_level_boxes(path: Path, limit: int = 32) -> list[str]:
    """The names of an mp4's top level boxes, in file order.

    Only the 8 or 16 byte header of each box is read, so this costs a few seeks
    whatever the file weighs.
    """
    names: list[str] = []
    with path.open("rb") as handle:
        while len(names) < limit:
            header = handle.read(8)
            if len(header) < 8:
                break
            size = int.from_bytes(header[:4], "big")
            name = header[4:8].decode("ascii", errors="replace")
            names.append(name)
            if size == 1:
                # A 64 bit size lives in the eight bytes after the name.
                extended = handle.read(8)
                if len(extended) < 8:
                    break
                size = int.from_bytes(extended, "big")
                handle.seek(size - 16, 1)
            elif size == 0:
                break  # Runs to the end of the file, so there is nothing after it.
            else:
                handle.seek(size - 8, 1)
    return names


# --- QC-120, QC-121 and QC-130: audio and byte copies -----------------------------


def _verify_audio(job: DeliverableJob, deliverable: Deliverable) -> list[QCResult]:
    """QC-120 and QC-121: the delivered wav against the source it came from."""
    results: list[QCResult] = []
    if job.in_frame is not None and job.rate is not None:
        # Cut to the picture (user, 2026-09-23), so it is compared to the picture.
        results.extend(_check_trimmed_duration(job))
    elif job.source.suffix.lower() == WAV_SUFFIX:
        # A row with no range: its wav is delivered as a byte copy, so the digest is
        # the whole check.
        if file_digest(job.destination) != file_digest(job.source):
            results.append(_failure("QC-120", f"{job.name} does not match {job.source.name}"))
    else:
        results.extend(_check_extracted_duration(job))

    try:
        probed = ffmpeg.probe_raw(job.destination)
    except (ffmpeg.FFprobeError, ffmpeg.FFmpegNotFound) as error:
        return [*results, _failure("QC-121", f"{job.name} did not open: {error}")]
    for stream in probed.get("streams", []):
        if stream.get("codec_type") != "audio":
            continue
        depth = int(stream.get("bits_per_raw_sample") or stream.get("bits_per_sample") or 0)
        if stream.get("codec_name") != WAV_CODEC or depth != WAV_BIT_DEPTH:
            results.append(
                _failure(
                    "QC-121",
                    f"{job.name} is {stream.get('codec_name')} at {depth} bit, not "
                    f"{WAV_CODEC} at {WAV_BIT_DEPTH} bit",
                    severity="warning" if job.source.suffix.lower() == WAV_SUFFIX else "error",
                )
            )
        return results
    return [*results, _failure("QC-121", f"{job.name} has no audio stream")]


def _check_trimmed_duration(job: DeliverableJob) -> list[QCResult]:
    """QC-120 for a wav cut to the picture: exactly the plate's length at its rate.

    Integer throughout: frames times sample rate over the frame rate. One sample either
    way is rounding at the cut, not drift.
    """
    assert job.rate is not None
    try:
        written = media.probe_audio(job.destination)
    except (ffmpeg.FFprobeError, ffmpeg.FFmpegNotFound) as error:
        return [_failure("QC-120", f"{job.name} could not be read: {error}")]
    wanted = job.frame_count * written.sample_rate * job.rate.denominator // job.rate.numerator
    if abs(written.duration_samples - wanted) <= 1:
        return []
    return [
        _failure(
            "QC-120",
            f"{job.name} holds {written.duration_samples} samples; the plate's "
            f"{job.frame_count} frames want {wanted}",
        )
    ]


def _check_extracted_duration(job: DeliverableJob) -> list[QCResult]:
    """QC-120 for audio pulled out of a container, where no byte copy happened.

    Sample rate and channel count are preserved by the extraction, so the sample count
    is directly comparable and a resample would show up here as the drift it is.
    """
    try:
        source = media.probe_audio(job.source)
        written = media.probe_audio(job.destination)
    except (ffmpeg.FFprobeError, ffmpeg.FFmpegNotFound) as error:
        return [_failure("QC-120", f"{job.name} could not be compared to its source: {error}")]
    if source.duration_samples == written.duration_samples:
        return []
    return [
        _failure(
            "QC-120",
            f"{job.name} holds {written.duration_samples} samples against the source's "
            f"{source.duration_samples}",
        )
    ]


# --- QC-150 and QC-151: the row and the batch -------------------------------------

DELIVERABLE_RULES: tuple[str, ...] = (
    "QC-100",
    "QC-101",
    "QC-102",
    "QC-103",
    "QC-104",
    "QC-105",
    "QC-106",
    "QC-107",
    "QC-110",
    "QC-111",
    "QC-112",
    "QC-113",
    "QC-114",
    "QC-115",
    "QC-120",
    "QC-121",
)
"""Every deliverable-scoped phase B rule, in the order the QC log columns them.

The QC log's Deliverables sheet is one column per rule, so the list has to exist
somewhere whole rather than being inferred from whichever rules happened to fire: a
rule that fired nowhere still owes a column of PASS. It lives here because rule IDs
are this module's to know, and `tests/test_qc.py` checks it against the IDs the module
actually raises so a new rule cannot be added without a column appearing.

QC-140 and QC-141 are retired and QC-150 and QC-151 are row and batch scoped, so none
of them belongs here.
"""

DELIVERABLE_RULES_BY_KIND: dict[str, tuple[str, ...]] = {
    "raw_dir": ("QC-101", "QC-102", "QC-103", "QC-104", "QC-105", "QC-106", "QC-107"),
    "aux_still": ("QC-103", "QC-104", "QC-105", "QC-106"),
    "ref_mp4": ("QC-110", "QC-111", "QC-112", "QC-113", "QC-114", "QC-115"),
    "audio": ("QC-120", "QC-121"),
}
"""Which rules each kind of deliverable owes, from the scope column of QC_RULES.md.

This is what makes NA mean something in the log: an mp4 has no opinion about EXR
compression, so QC-105 against a reference reads NA rather than a PASS it never
earned. QC-100 is not here because every kind owes it.
"""


def deliverable_rule_state(deliverable: Deliverable, rule_id: str) -> str:
    """PASS, FAIL or NA for one rule against one deliverable, for the QC log.

    A deliverable that never rendered fails QC-100 and is NA for everything else,
    because there is no file any other rule could have looked at.
    """
    failed = {result.rule_id for result in deliverable.qc}
    if rule_id in failed:
        return "FAIL"
    if deliverable.status == "failed":
        return "FAIL" if rule_id == RENDER_FAILED else "NA"
    if rule_id == RENDER_FAILED:
        return "PASS"
    return "PASS" if rule_id in DELIVERABLE_RULES_BY_KIND.get(deliverable.kind, ()) else "NA"


OWNED_PHASE_B_ROW_RULES = frozenset({"QC-150"})
OWNED_PHASE_B_BATCH_RULES = frozenset({"QC-151"})


def check_row_complete(row: ShotRow) -> list[QCResult]:
    """QC-150: every deliverable this row planned exists and passed its own checks."""
    if not row.deliverables:
        return []
    unfinished = [item.name for item in row.deliverables if item.status != "done"]
    failed = [item.name for item in row.deliverables if any(result.severity == "error" for result in item.qc)]
    broken = sorted(set(unfinished) | set(failed))
    if not broken:
        return []
    shown = ", ".join(broken[:3])
    more = f" and {len(broken) - 3} more" if len(broken) > 3 else ""
    return [QCResult("QC-150", "error", "row", f"{len(broken)} deliverables are not done: {shown}{more}")]


def check_names_reparse(batch: Batch, show_pattern: str = naming.DEFAULT_SHOW_PATTERN) -> list[QCResult]:
    """QC-151: every delivered filename reads back as the thing that was planned.

    The naming spec is the contract with the vendor, and the parser is the only thing
    that can say a name honours it. Comparing the parse against the plan rather than
    merely checking that it parses is what catches a name that is well formed and
    wrong: the right shape with the wrong shot code, resolution or version.
    """
    results: list[QCResult] = []
    for row in batch.rows:
        identity = effective_identity(row, show_pattern)
        for item in row.deliverables:
            if item.status != "done":
                continue
            parsed = naming.parse_output_name(item.name, show_pattern)
            fault = _name_fault(item, parsed) or _identity_fault(parsed, identity)
            if fault is not None:
                results.append(QCResult("QC-151", "error", "batch", f"{item.name}: {fault}"))
    return results


def _name_fault(item: Deliverable, parsed: naming.ParsedOutput | None) -> str | None:
    """What a delivered name says that the plan does not, or None when they agree."""
    if parsed is None:
        return "does not parse as a delivery name"
    if parsed.kind != item.kind:
        return f"reads as a {parsed.kind}, but a {item.kind} was planned"
    if parsed.version != item.version:
        return f"reads as v{parsed.version:02d}, but v{item.version:02d} was planned"
    if item.res is not None and parsed.res is not None and parsed.res != item.res:
        return f"reads as {parsed.res}, but {item.res} was planned"
    return None


def _identity_fault(parsed: naming.ParsedOutput | None, identity: naming.ShotIdentity | None) -> str | None:
    """What a delivered name says about who the clip is that the row does not (F22).

    The shape was checked and the shot was not: a well formed name for the wrong shot or
    element passed.
    """
    if parsed is None or identity is None:
        return None
    if parsed.shot_code != identity.shot_code:
        return f"reads as {parsed.shot_code}, but the row is {identity.shot_code}"
    if identity.is_still:
        if (parsed.aux, parsed.aux_index) != (identity.kind, identity.index):
            said, row_is = f"{parsed.aux} {parsed.aux_index}", f"{identity.kind} {identity.index}"
            return f"reads as {said}, but the row is {row_is}"
    elif parsed.elem != identity.elem:
        return f"reads as {parsed.elem}, but the row is {identity.elem}"
    return None


def reset_row(row: ShotRow) -> bool:
    """The editor fixed what failed: its outputs run again at the same version (D11).

    Every failed deliverable goes back to planned with its results cleared, and QC-150
    goes with them until the next run says again whether the row landed. False when the
    row had nothing failed, so there was nothing to reset.
    """
    failed = [item for item in row.deliverables if item.status == "failed"]
    for item in failed:
        item.status = "planned"
        item.qc = []
    row.qc = [result for result in row.qc if result.rule_id != "QC-150"]
    return bool(failed)


def apply_phase_b(batch: Batch, show_pattern: str = naming.DEFAULT_SHOW_PATTERN) -> None:
    """Re-run QC-150 and QC-151 across a batch, after a run or on reopening one."""
    batch.qc = [result for result in batch.qc if result.rule_id not in OWNED_PHASE_B_BATCH_RULES]
    batch.qc.extend(check_names_reparse(batch, show_pattern))
    for row in batch.rows:
        row.qc = [result for result in row.qc if result.rule_id not in OWNED_PHASE_B_ROW_RULES]
        row.qc.extend(check_row_complete(row))
