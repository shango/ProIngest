"""What the Settings page offers, worked out without a widget in sight.

PRD FR-12 is the section list and UI_SPEC section 9 is the shape: a section list on the
left, a form on the right, Apply and Cancel at the bottom. This module turns the two
settings objects into `Section`s of `Field`s and back again; `ui/settings_dialog.py`
draws the answer and owns every widget.

Apart for the reason `ui/metadata.py` is: **the field list is the part that gets argued
about**, and an argument about which settings a tool should have is easier against a
list than against a layout. It also makes the page's contents assertable without a
window, which is how a section that quietly lost a field gets caught.

**A field is here only if something already reads it**, with one stated exception: the
Colour section's ingest folder is read by the chooser in M5.7.3 and is remembered from
now, because the alternative is a Colour section that is entirely read only and a page
reopened one chunk later for one line. **Every section is live as of M5.12**, Output
last: the two settings it carries are applied inside a worker process, so they had to
travel there before the section could mean anything. `Section.enabled` stays, because
listing a section that has nothing behind it yet and saying what it waits on is the rule
the page was built to - the same one the toolbar was built to in M5.1.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from proingest.core import color, exr, ffmpeg, logsetup, naming, qc
from proingest.core.settings import AppSettings
from proingest.ui import paths

Kind = Literal["int", "text", "bool", "resolution", "lines", "folder", "readonly", "choice"]
"""What a field is edited with. `lines` is a `key = value` per line block, which is how
a small mapping is edited without a table widget and two buttons to maintain, and
`choice` is a fixed list where a typo would otherwise mean an unreadable setting."""


@dataclass(frozen=True)
class Field:
    """One row of the form.

    `key` is where the value lives in the flat dict this module hands back and forth,
    prefixed by which object owns it: `app.` for the per user settings and `rules.` for
    the thresholds a batch carries. The prefix is what stops the two ever being written
    to the wrong place.
    """

    key: str
    label: str
    kind: Kind
    help: str = ""
    minimum: int = 0
    maximum: int = 0
    options: tuple[str, ...] = ()
    """The choices, for a `choice` field. Empty for every other kind."""


@dataclass(frozen=True)
class Section:
    """One entry in the left list, and the form it shows.

    `note` is shown above the fields. On a disabled section it is the whole content and
    says what the section is waiting on, so a page with nothing behind it yet reads as a
    plan rather than as a bug.
    """

    title: str
    fields: tuple[Field, ...] = ()
    enabled: bool = True
    note: str = ""


GENERAL = "General"
RULES = "Rules"
COLOUR = "Colour"
NAMING = "Naming"
OUTPUT = "Output"
ADVANCED = "Advanced"


def sections() -> tuple[Section, ...]:
    """Every section of the page, in the order PRD FR-12 lists them.

    A function rather than a constant because the Colour section reads the pinned
    config's own names, and a constant would fix them at import time and then disagree
    with the library after a version bump - which is precisely the thing OQ-29 pinned
    the config to prevent.
    """
    return (
        Section(
            GENERAL,
            (
                Field(
                    "app.workers",
                    "Render processes",
                    "int",
                    "How many deliverables are written at once. More is faster until the "
                    "disk or the mount is the limit.",
                    minimum=1,
                    maximum=32,
                ),
                Field(
                    "app.path_map",
                    "Media path map",
                    "lines",
                    "One rewrite per line, as from = to. A timeline exported on Windows "
                    "carries paths that mean nothing here (FR-2). Leave it empty unless a "
                    "turnover needs it: the scan already searches the source root by "
                    "filename, which needs no configuration.",
                ),
            ),
        ),
        Section(
            RULES,
            (
                Field(
                    "rules.min_duration_frames",
                    "Shortest shot",
                    "int",
                    "Frames. Shorter than this is QC-033.",
                    minimum=1,
                    maximum=100_000,
                ),
                Field(
                    "rules.max_duration_frames",
                    "Longest shot",
                    "int",
                    "Frames. Longer than this is QC-034.",
                    minimum=1,
                    maximum=100_000,
                ),
                Field(
                    "rules.expected_handle_frames",
                    "Expected handles",
                    "int",
                    "Frames either side of the cut. Fewer is QC-030.",
                    minimum=0,
                    maximum=1_000,
                ),
                Field(
                    "rules.target_resolution",
                    "Expected resolution",
                    "resolution",
                    "What a source is expected to arrive at, as width x height.",
                ),
                Field(
                    "rules.allow_non_4k",
                    "Allow other resolutions",
                    "bool",
                    "Downgrades QC-023 from an error to a warning. Letterboxing a source "
                    "that is not 16:9 is not built, so such a row is still resampled.",
                ),
                Field(
                    "rules.sync_tolerance_frames",
                    "Audio sync tolerance",
                    "int",
                    "Frames audio may run from picture before QC-043.",
                    minimum=0,
                    maximum=1_000,
                ),
            ),
            note=(
                "Thresholds the checks compare against. Applying them re-checks the open "
                "batch, and the batch keeps its own copy: changing these later does not "
                "re-judge a delivery that has already shipped."
            ),
        ),
        Section(
            COLOUR,
            (
                Field(
                    "app.color_session_folder",
                    "Ingest opens at",
                    "folder",
                    "Where the colour session chooser starts. Which session a "
                    "turnover was ingested from is kept on the turnover, not here.",
                ),
                Field(
                    "readonly.config",
                    "ACES config",
                    "readonly",
                    "Pinned rather than tracking the latest, so a dependency bump cannot "
                    "change what a reference looks like (OQ-29).",
                ),
                Field(
                    "readonly.working_space",
                    "Working space",
                    "readonly",
                    "Where the colour session's CDL is applied: the timeline colour space "
                    "the session is set to, by standard. The tool converts each clip into "
                    "it from the encoding its metadata names, applies the CDL, and carries "
                    "the result to ACEScg. A session set to anything else grades wrong "
                    "without an error, so this is a standard rather than a setting.",
                ),
                Field(
                    "readonly.output_transform",
                    "Output transform",
                    "readonly",
                    "What a reference mp4 is viewed through. The plates never see it.",
                ),
                Field(
                    "readonly.input_transforms",
                    "Input transform table",
                    "readonly",
                    "What a shooter may write, and the colour space each resolves to. "
                    "Every colour space the config knows also resolves to itself, so only "
                    "the short names need a row. Read only until an override can travel "
                    "to a worker; adding a camera is adding a row in core/color.py.",
                ),
            ),
            note=(
                "There is no source encoding setting and no mode: each clip's own metadata "
                "names what it is encoded in, and the house wide gamut is one more entry in "
                "the table rather than something to switch into."
            ),
        ),
        Section(
            NAMING,
            (
                Field(
                    "app.show_pattern",
                    "Show prefix pattern",
                    "text",
                    "The regular expression every clip name is parsed with and every "
                    "delivered name is built from. Empty means the default.",
                ),
            ),
        ),
        Section(
            OUTPUT,
            (
                Field(
                    "app.reference_crf",
                    "Reference quality",
                    "int",
                    "The x264 rate factor a reference mp4 is encoded at. Lower is better "
                    "and bigger; 0 is lossless and 51 is the worst the encoder will do. "
                    f"The spec is {ffmpeg.REFERENCE_CRF}, at preset {ffmpeg.REFERENCE_PRESET}, "
                    "and the preset is not editable.",
                    minimum=0,
                    maximum=51,
                ),
                Field(
                    "app.exr_compression_level",
                    "EXR compression level",
                    "int",
                    "How hard DWAA compresses a delivered plate. Higher is smaller and "
                    f"lossier; the spec is {exr.DWA_COMPRESSION_LEVEL}. DWAA is lossy at "
                    "every level, so this moves how lossy rather than whether.",
                    minimum=0,
                    maximum=200,
                ),
            ),
            note=(
                "What the two delivered picture formats cost. Both are applied inside a "
                "render's worker processes, so a change reaches the next run rather than "
                "one already going, and both are pinned by the spec: moving either is a "
                "decision about a delivery, not a preference."
            ),
        ),
        Section(
            ADVANCED,
            (
                Field(
                    "app.log_level",
                    "Log level",
                    "choice",
                    "How much reaches the Log tab and the log file. Info includes every "
                    "ffmpeg command the tool runs, which is what makes a render "
                    "reproducible. A level changed while a run is going applies from the "
                    "next run: a worker process is told the level when it starts.",
                    options=logsetup.LEVEL_NAMES,
                ),
                Field(
                    "app.ffmpeg_path",
                    "ffmpeg override",
                    "folder",
                    "The folder holding ffmpeg and ffprobe, or one of the binaries "
                    "itself. Empty uses the bundled pair, then whatever is on PATH. A "
                    "path that is not there is an error rather than a silent fallback: "
                    "an override that was ignored is a render done with the wrong build.",
                ),
                Field(
                    "readonly.log_file",
                    "Log file",
                    "readonly",
                    "The complete record. The Log tab shows its tail.",
                ),
            ),
            note=(
                "Where the log goes and which ffmpeg writes the deliverables. Both take "
                "effect as soon as they are applied, and both reach a render's worker "
                "processes when the next run starts them."
            ),
        ),
    )


def readonly_values() -> dict[str, str]:
    """The Colour section's four read-only lines, read from core rather than copied."""
    table = "\n".join(f"{written} = {space}" for written, space in sorted(color.INPUT_TRANSFORMS.items()))
    return {
        "readonly.config": color.BUILTIN_CONFIG,
        "readonly.working_space": color.WORKING_SPACE,
        "readonly.output_transform": f"{color.VIEW} on {color.DISPLAY}",
        "readonly.input_transforms": table,
        "readonly.log_file": str(paths.log_dir() / logsetup.LOG_FILENAME),
    }


def to_values(app: AppSettings, rules: qc.RuleSettings) -> dict[str, Any]:
    """The two settings objects as the flat dict the form edits."""
    values: dict[str, Any] = {
        "app.workers": app.workers,
        "app.path_map": dict(app.path_map),
        "app.show_pattern": app.show_pattern,
        "app.color_session_folder": app.color_session_folder,
        "app.log_level": app.log_level,
        "app.ffmpeg_path": app.ffmpeg_path,
        "app.reference_crf": app.reference_crf,
        "app.exr_compression_level": app.exr_compression_level,
        "rules.target_resolution": tuple(rules.target_resolution),
        "rules.allow_non_4k": rules.allow_non_4k,
    }
    for name in (
        "min_duration_frames",
        "max_duration_frames",
        "expected_handle_frames",
        "sync_tolerance_frames",
    ):
        values[f"rules.{name}"] = getattr(rules, name)
    values.update(readonly_values())
    return values


def apply_values(
    app: AppSettings, values: dict[str, Any], rules: qc.RuleSettings | None = None
) -> qc.RuleSettings:
    """Write the form back: the app settings in place, the thresholds as a new object.

    In place for one and not the other because that is what each is. `AppSettings` is
    one long-lived object the window holds and saves; `RuleSettings` is frozen and is
    handed to whatever re-runs the checks, so a changed one is a new one.

    Anything the form could not parse is absent from `values` rather than present and
    wrong, so every read here takes what is already set when a key is missing: `app` for
    its own fields and `rules` for the thresholds, which is why the thresholds the page
    opened with have to be passed back in. A field that would not parse therefore changes
    nothing, which is the same answer the shot list gives a value it will not accept
    (UI_SPEC section 5).
    """
    current = rules if rules is not None else qc.RuleSettings()
    app.workers = int(values.get("app.workers", app.workers))
    app.path_map = dict(values.get("app.path_map", app.path_map))
    app.show_pattern = str(values.get("app.show_pattern", app.show_pattern))
    app.color_session_folder = str(values.get("app.color_session_folder", app.color_session_folder))
    app.log_level = logsetup.name_of(logsetup.level_of(str(values.get("app.log_level", app.log_level))))
    app.ffmpeg_path = str(values.get("app.ffmpeg_path", app.ffmpeg_path))
    app.reference_crf = int(values.get("app.reference_crf", app.reference_crf))
    app.exr_compression_level = int(values.get("app.exr_compression_level", app.exr_compression_level))
    applied = qc.RuleSettings(
        min_duration_frames=int(values.get("rules.min_duration_frames", current.min_duration_frames)),
        max_duration_frames=int(values.get("rules.max_duration_frames", current.max_duration_frames)),
        expected_handle_frames=int(
            values.get("rules.expected_handle_frames", current.expected_handle_frames)
        ),
        target_resolution=_pair(values.get("rules.target_resolution", current.target_resolution)),
        allow_non_4k=bool(values.get("rules.allow_non_4k", current.allow_non_4k)),
        sync_tolerance_frames=int(values.get("rules.sync_tolerance_frames", current.sync_tolerance_frames)),
    )
    app.rules = applied.to_dict()
    return applied


def _pair(value: Any) -> tuple[int, int]:
    width, height = value
    return (int(width), int(height))


def show_pattern_of(app: AppSettings) -> str:
    """The pattern to parse and build names with, with empty meaning the default.

    One definition because four callers want it: the scan, the planner, the phase B name
    check and the CLF index all take a pattern, and a settings file that stored a copy of
    today's default would keep it after the default moved.
    """
    return app.show_pattern or naming.DEFAULT_SHOW_PATTERN


def apply_to_process(app: AppSettings) -> None:
    """Put the four settings that change behaviour into force for this process.

    The two Advanced ones and the two Output ones. Apart from `apply_values`, which only
    writes the objects: these change what the rest of the tool does, and doing that
    inside a function whose job is to read a form would mean a test of the form had side
    effects on the interpreter running it.

    Called at startup and again after every Apply. A render's worker processes are told
    all four when they start (`core/render.execute`), so a change reaches the next run
    rather than the one in flight.
    """
    logsetup.set_level(logsetup.level_of(app.log_level))
    ffmpeg.set_override(Path(app.ffmpeg_path) if app.ffmpeg_path else None)
    ffmpeg.set_reference_crf(app.reference_crf)
    exr.set_compression_level(app.exr_compression_level)
