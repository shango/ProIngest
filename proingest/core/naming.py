"""Clip name parsing and deliverable naming.

Every output name in ProIngest is produced here. Nothing else formats a filename.

The templates in docs/NAMING_SPEC.md section 3 are a two-way contract: the build_*
functions write them and parse_output_name reads them back. QC-151 depends on that
round trip, so the two directions are tested against the same example table.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

DEFAULT_SHOW_PATTERN = r"[A-Z]{2,6}"
"""Show prefix. Configurable in Settings; the same value drives both directions."""

ELEMENT_TYPES = ("pl", "cp", "el", "wit", "re")
AUX_NAMES = ("colorChart", "mirrorBall", "greyBall", "sizeRef")

CLIP_TYPES = ELEMENT_TYPES + AUX_NAMES
"""Every value `Shot Type` may carry, plates and reference stills alike.

NAMING_SPEC section 1: a reference still is a peer of a plate here, not something
hanging off one. `Shot Type` is the whole of the tool's scope (user, 2026-09-22), so a
value outside this tuple is a clip the tool does not deliver.
"""

SHOT_TYPE_ALIASES = {"cl": "cp"}
"""Spellings the shooters use that are not the spelling the deliverable carries.

`cl` for a clean plate is the user's own habit and `cp` is what their spec sheet says
everywhere (OQ-72). Accepting both costs one row and writing `cp` keeps one spelling
in the delivered names.
"""

HDRI_KIND = "HDRI"
"""An HDRI's `Shot Type`. Not in `CLIP_TYPES`: `core/metacsv.py` reads it on its own (QC-080).

The tool delivers the HDRI EXR byte for byte, and the stringout shows Ben's pre-render of
its timeline event (user, 2026-10-07)."""

LDRI_KIND = "LDRI"
"""An LDRI's `Shot Type` (user, 2026-10-08): an HDRI whose file is a JPG or PNG. Treated as
an HDRI throughout (`ShotIdentity.is_hdri` is true of both, and so is `qc.is_hdri`), except
that its file is delivered byte for byte under its own extension and the stringout shows it,
or its pre-render, as it is, with no grade."""

LDRI_EXTENSIONS = (".jpg", ".jpeg", ".png")
"""What an LDRI's file is, and so what its delivered copy ends with."""

HDRI_SHOT_TYPE = re.compile(r"(?P<kind>hdri|ldri)(?P<index>\d{1,2})?", re.IGNORECASE)
"""`HDRI` or `LDRI`, as the CSV writes it, with or without an index (`HDRI2` is 02)."""


def hdri_kind(shot_type: str) -> str | None:
    """`HDRI_KIND` or `LDRI_KIND` for a `Shot Type` that is one, else None."""
    match = HDRI_SHOT_TYPE.fullmatch(shot_type.strip())
    if match is None:
        return None
    return LDRI_KIND if match["kind"].casefold() == LDRI_KIND.casefold() else HDRI_KIND


STYLE_FRAME_KIND = "styleFrame"
"""A style frame's `Shot Type` (QC-085, user 2026-10-07): a pre-graded PNG or JPG held on the
timeline before its shot's plate. Not in `CLIP_TYPES` and never delivered: the stringout
shows it as it is, for the event's length."""

HDRI_ELEMENT = "pl01"
"""Every HDRI and LDRI is named under the plate: `[SHOTCODE]_pl01_HDRI_v01.exr` in the shooters'
spec, `BACH0002_pl01_HDRI_01_v01.exr` in the tracker."""

_SHOT_TYPE_INDEX = {name.casefold(): name for name in CLIP_TYPES}
_SHOT_TYPE_PATTERN = re.compile(r"^(?P<kind>[A-Za-z]+)(?P<index>\d{1,2})?$")

FIRST_OUTPUT_FRAME = 1001
"""Output sequences always start here, whatever the source frame numbering is."""

Resolution = Literal["4k", "HD"]

_TYPES = "|".join(ELEMENT_TYPES)
_AUX = "|".join(AUX_NAMES)


@dataclass(frozen=True)
class ShotIdentity:
    """Who a clip is: the shot it belongs to and what kind of clip it is.

    **Assembled from two CSV fields rather than parsed out of a filename** (NAMING_SPEC
    section 1, settled 2026-09-21): `Shot` gives `shot_code` and `Shot Type` gives
    `kind` and `index`.

    `kind` is drawn from `CLIP_TYPES`, which holds plates and reference stills **in one
    tuple**. That is the shape of the change rather than a detail of it: the old model
    hung a still off an element, and in the CSV `colorChart` is a peer of `pl01`. A
    still therefore has no element, which is why `stem` refuses to build one for it.

    `index` stays a string so a leading zero survives the round trip.
    """

    shot_code: str
    kind: str
    index: str

    @property
    def show(self) -> str:
        """`MELT` out of `MELT0001`, which is the delivery's top folder.

        Taken off the shot code rather than carried, because a shot code is letters then
        four digits by grammar (NAMING_SPEC section 1) and carrying it would be a second
        place for the two to disagree.
        """
        return self.shot_code.rstrip("0123456789")

    @property
    def is_still(self) -> bool:
        """A reference still: one 4k EXR, never graded, keyed to the shot code."""
        return self.kind in AUX_NAMES

    @property
    def is_hdri(self) -> bool:
        """An HDRI or an LDRI: its file is delivered as it is, keyed to the shot's plate."""
        return self.kind in (HDRI_KIND, LDRI_KIND)

    @property
    def is_ldri(self) -> bool:
        """An LDRI: an HDRI whose file is a JPG or PNG (user, 2026-10-08)."""
        return self.kind == LDRI_KIND

    @property
    def is_style_frame(self) -> bool:
        """A style frame: shown on the stringout, never delivered."""
        return self.kind == STYLE_FRAME_KIND

    @property
    def elem(self) -> str:
        """`pl01`, what a plate's deliverables are named for."""
        return f"{self.kind}{self.index}"

    @property
    def stem(self) -> str:
        """`MELT0001_pl01`, the prefix shared by every deliverable of this element.

        Refuses for a still rather than returning `MELT0001_colorChart01`, which is a
        name nothing writes: a still's deliverable is `MELT0001_colorChart_01_4k_v01.exr`,
        with an underscore before the index and no element segment. Raising here is the
        difference between a still that cannot be named and one named plausibly wrong.
        """
        if self.is_still:
            raise ValueError(f"{self.shot_code} {self.kind} is a reference still and has no element stem")
        if self.is_hdri:
            raise ValueError(f"{self.shot_code} {self.kind} is an HDRI and has no element stem")
        if self.is_style_frame:
            raise ValueError(f"{self.shot_code} {self.kind} is a style frame and has no element stem")
        return f"{self.shot_code}_{self.elem}"


def parse_shot_type(written: str) -> tuple[str, str] | None:
    """A `Shot Type` value as (kind, index), or None when it names nothing we deliver.

    Case insensitive, because the shooters do not keep the camel case. Safe rather than
    lenient: the nine codes are distinct casefolded, so nothing is ambiguous.

    **A bare code means index `01`.** Three of the five rows in the real sample are bare
    (`colorChart`, `mirrorBall`, `greyBall`), so this carries weight rather than being a
    kindness. `cl` is accepted and comes back `cp` (OQ-72).

    What comes back is always the spelling in NAMING_SPEC section 1, never the shooter's,
    so two deliverables cannot differ by capitalisation alone.
    """
    match = _SHOT_TYPE_PATTERN.match(written.strip())
    if match is None:
        return None
    key = match["kind"].casefold()
    kind = _SHOT_TYPE_INDEX.get(SHOT_TYPE_ALIASES.get(key, key))
    if kind is None:
        return None
    return kind, (match["index"] or "1").zfill(2)


def parse_shot_code(code: str, show_pattern: str = DEFAULT_SHOW_PATTERN) -> tuple[str, str] | None:
    """Split `MELT0001` into show and shot number.

    Used when the editor corrects a shot code (NAMING_SPEC section 6): the correction
    carries a new show and number, and every name is rebuilt from them.
    """
    match = re.match(rf"^(?P<show>{show_pattern})(?P<shot>\d{{4}})$", code)
    if match is None:
        return None
    return match["show"], match["shot"]


def _ver(version: int) -> str:
    return f"v{version:02d}"


# --- Output names. One function per row of NAMING_SPEC.md section 3. ---


def raw_sequence_dir(identity: ShotIdentity, res: Resolution, version: int) -> str:
    return f"{identity.stem}_raw_{res}_{_ver(version)}"


def raw_frame(identity: ShotIdentity, res: Resolution, version: int, frame: int) -> str:
    return frame_in_sequence(raw_sequence_dir(identity, res, version), frame)


def frame_in_sequence(sequence_dir: str, frame: int) -> str:
    """One frame inside a raw EXR folder. The folder name is the frame's stem.

    Kept apart from `raw_frame` so a planned job, which knows only the folder it is
    writing into, can still name its frames here rather than formatting them itself.
    """
    return f"{sequence_dir}.{frame:04d}.exr"


def ref_mp4(identity: ShotIdentity, res: Resolution, version: int) -> str:
    return f"{identity.stem}_ref_{res}_{_ver(version)}.mp4"


def audio_wav(identity: ShotIdentity, version: int) -> str:
    return f"{identity.stem}_audio_{_ver(version)}.wav"


def aux_still_exr(identity: ShotIdentity, version: int) -> str:
    """Single-frame reference still (colorChart, mirrorBall, greyBall, sizeRef). Always 4k.

    **Keyed to the shot code, with no element segment** (shooters' spec, 2026-09-21):
    `MELT0001_colorChart_01_4k_v01.exr`, not `MELT0001_pl01_colorChart_01_...`.
    """
    if not identity.is_still:
        raise ValueError(f"aux still must be one of {AUX_NAMES}, got {identity.kind!r}")
    return f"{identity.shot_code}_{identity.kind}_{identity.index}_4k_{_ver(version)}.exr"


def hdri_exr(identity: ShotIdentity, version: int) -> str:
    """`SECA0009_pl01_HDRI_01_v01.exr`: the HDRI, copied byte for byte (user, 2026-10-07)."""
    if identity.kind != HDRI_KIND:
        raise ValueError(f"an HDRI must have kind {HDRI_KIND!r}, got {identity.kind!r}")
    return f"{hdri_label(identity)}_{_ver(version)}.exr"


def ldri_image(identity: ShotIdentity, version: int, suffix: str) -> str:
    """`SECA0009_pl01_LDRI_01_v01.jpg`: the LDRI, copied byte for byte under the extension it
    came with (user, 2026-10-08)."""
    if not identity.is_ldri:
        raise ValueError(f"an LDRI must have kind {LDRI_KIND!r}, got {identity.kind!r}")
    if suffix.lower() not in LDRI_EXTENSIONS:
        raise ValueError(f"an LDRI must be one of {LDRI_EXTENSIONS}, got {suffix!r}")
    return f"{hdri_label(identity)}_{_ver(version)}{suffix.lower()}"


def hdri_label(identity: ShotIdentity) -> str:
    """`SECA0009_pl01_HDRI_01` or `SECA0009_pl01_LDRI_01`: the name without its version."""
    return f"{identity.shot_code}_{HDRI_ELEMENT}_{identity.kind}_{identity.index}"


# --- The turnover stringout, NAMING_SPEC.md section 5 (OQ-38, reopened 2026-09-25). ---

STRINGOUT_SUFFIX = ".mp4"

_STRINGOUT = re.compile(
    r"^turnover(?P<number>\d{3,})_(?P<month>\d{2})_(?P<day>\d{2})_(?P<year>\d{2}|\d{4})_"
    r"(?P<shooter>.+)_SO_v(?P<ver>\d{2})\.mp4$"
)


def stringout_stem(number: int, month: int, day: int, year: int, shooter: str, version: int) -> str:
    """`turnover121_09_23_26_danielluckett_SO_v01`: the file's name without `.mp4`, which
    is also what the stringout burns in at the top of every frame (Ben's `burn-ins.png`).

    Dated as the turnover folder is, not as the render (user, 2026-09-25), and always
    two digits each for month, day and year (user, 2026-10-05).
    """
    return f"turnover{number:03d}_{month:02d}_{day:02d}_{year % 100:02d}_{shooter}_SO_{_ver(version)}"


def stringout_mp4(number: int, month: int, day: int, year: int, shooter: str, version: int) -> str:
    return stringout_stem(number, month, day, year, shooter, version) + STRINGOUT_SUFFIX


def stringout_version(name: str, number: int, month: int, day: int, year: int, shooter: str) -> int | None:
    """The version of an existing stringout of this turnover, or None for any other file."""
    match = _STRINGOUT.match(name)
    if match is None:
        return None
    said = tuple(int(match[key]) for key in ("number", "month", "day", "year"))
    # A stringout written before 2026-10-05 carries a four digit year; it is still a version.
    same = said[:3] == (number, month, day) and said[3] % 100 == year % 100 and match["shooter"] == shooter
    return int(match["ver"]) if same else None


def shot_label(identity: ShotIdentity) -> str:
    """What the stringout burns in at bottom right: `TIME1001_pl01`, or a still's
    `SECA0002_colorChart_01`, the way its own file names it, or `SECA0009 styleFrame`
    (user, 2026-10-07)."""
    if identity.is_still:
        return f"{identity.shot_code}_{identity.kind}_{identity.index}"
    if identity.is_hdri:
        return hdri_label(identity)
    if identity.is_style_frame:
        return f"{identity.shot_code} {STYLE_FRAME_KIND}"
    return identity.stem


def take_label(label: str, take: str) -> str:
    """`SECA0009_pl01 Take 02`: the burn-in with its take, when the CSV's `Take` is above 1.
    Take 1, a blank or anything not a number leaves the label as it is (user, 2026-10-07)."""
    written = take.strip()
    if not written.isdigit() or int(written) <= 1:
        return label
    return f"{label} Take {int(written):02d}"


# --- Delivery folder layout, NAMING_SPEC.md section 5. ---


def shot_dir(delivery_root: Path, identity: ShotIdentity) -> Path:
    return delivery_root / identity.show / identity.shot_code


def reports_dir(delivery_root: Path, show: str) -> Path:
    return delivery_root / show / "_reports"


USER_FOLDERS = ("User_Generated", "User_Uploads")
"""Two empty folders at the top of the delivery root for the user's own files (user,
2026-10-06). The tool makes them and never reads, writes or removes anything inside."""


def user_dirs(delivery_root: Path) -> list[Path]:
    return [delivery_root / name for name in USER_FOLDERS]


# --- Reading output names back, NAMING_SPEC.md section 7. Drives QC-151 and versioning. ---

OutputKind = Literal[
    "raw_frame",
    "raw_dir",
    "ref_mp4",
    "audio",
    "aux_still",
    "hdri",
]


@dataclass(frozen=True)
class ParsedOutput:
    """What an output filename decomposes into. Compared against the plan for QC-151."""

    kind: OutputKind
    version: int
    shot_code: str | None = None
    elem: str | None = None
    res: Resolution | None = None
    frame: int | None = None
    aux: str | None = None
    aux_index: str | None = None
    ext: str | None = None


def _output_patterns(show_pattern: str) -> list[tuple[OutputKind, re.Pattern[str]]]:
    """One anchored pattern per kind. Mutually exclusive on the literal kind segment."""
    shot = rf"(?P<show>{show_pattern})(?P<shot>\d{{4}})"
    sc = rf"{shot}_(?P<type>{_TYPES})(?P<idx>\d{{2}})"
    v = r"v(?P<ver>\d{2})"
    res = r"(?P<res>4k|HD)"
    return [
        ("raw_frame", re.compile(rf"^{sc}_raw_{res}_{v}\.(?P<frame>\d{{4}})\.exr$")),
        ("raw_dir", re.compile(rf"^{sc}_raw_{res}_{v}$")),
        ("ref_mp4", re.compile(rf"^{sc}_ref_{res}_{v}\.mp4$")),
        ("audio", re.compile(rf"^{sc}_audio_{v}\.wav$")),
        ("aux_still", re.compile(rf"^{shot}_(?P<aux>{_AUX})_(?P<auxidx>\d{{2}})_4k_{v}\.exr$")),
        ("hdri", re.compile(rf"^{shot}_{HDRI_ELEMENT}_(?P<aux>{HDRI_KIND})_(?P<auxidx>\d{{2}})_{v}\.exr$")),
        (
            "hdri",
            re.compile(
                rf"^{shot}_{HDRI_ELEMENT}_(?P<aux>{LDRI_KIND})_(?P<auxidx>\d{{2}})_{v}\.(?P<ext>jpe?g|png)$"
            ),
        ),
    ]


def parse_output_name(name: str, show_pattern: str = DEFAULT_SHOW_PATTERN) -> ParsedOutput | None:
    """Read a deliverable filename back into its parts.

    Returns None for anything this tool did not write, which is what keeps a stray
    file from inflating the version number and why a `.part` name can never match.
    """
    for kind, pattern in _output_patterns(show_pattern):
        match = pattern.match(name)
        if match is None:
            continue
        groups = match.groupdict()
        shot_code = f"{groups['show']}{groups['shot']}" if "show" in groups else None
        elem = f"{groups['type']}{groups['idx']}" if "type" in groups else None
        frame = groups.get("frame")
        raw_res = groups.get("res")
        return ParsedOutput(
            kind=kind,
            version=int(groups["ver"]),
            shot_code=shot_code,
            elem=elem,
            res=("4k" if raw_res == "4k" else "HD") if raw_res else None,
            frame=int(frame) if frame else None,
            aux=groups.get("aux"),
            aux_index=groups.get("auxidx"),
            ext=groups.get("ext"),
        )
    return None


def next_version(existing_names: list[str], show_pattern: str = DEFAULT_SHOW_PATTERN) -> int:
    """Highest version present plus one, or 1 when none.

    Names that do not parse are ignored, so `.part` leftovers and unrelated files
    cannot push the version forward. NAMING_SPEC.md section 4.
    """
    versions = [
        parsed.version
        for parsed in (parse_output_name(name, show_pattern) for name in existing_names)
        if parsed is not None
    ]
    return max(versions, default=0) + 1
