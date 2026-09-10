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
CAMDATA_EXTENSIONS = ("txt", "rtf")
BTS_EXTENSIONS = ("png", "jpg", "jpeg")

FIRST_OUTPUT_FRAME = 1001
"""Output sequences always start here, whatever the source frame numbering is."""

Resolution = Literal["4k", "HD"]

_TYPES = "|".join(ELEMENT_TYPES)
_AUX = "|".join(AUX_NAMES)


@dataclass(frozen=True)
class ShotIdentity:
    """A parsed timeline clip name.

    Numeric parts stay strings so leading zeros survive the round trip.
    """

    show: str
    shot: str
    elem_type: str
    elem_index: str
    aux: str | None = None
    aux_index: str | None = None

    @property
    def shot_code(self) -> str:
        return f"{self.show}{self.shot}"

    @property
    def elem(self) -> str:
        return f"{self.elem_type}{self.elem_index}"

    @property
    def stem(self) -> str:
        """`MELT0001_pl01`, the prefix shared by every deliverable of this element."""
        return f"{self.shot_code}_{self.elem}"


@dataclass(frozen=True)
class LensGridIdentity:
    """A lens grid clip. Turnover level, not tied to a shot."""

    camera: str
    lens: str
    mm: str


def _clip_pattern(show_pattern: str) -> re.Pattern[str]:
    return re.compile(
        rf"^(?P<show>{show_pattern})(?P<shot>\d{{4}})"
        rf"_(?P<type>{_TYPES})(?P<idx>\d{{2}})"
        rf"(?:_(?P<aux>{_AUX}|BTS)_(?P<auxidx>\d{{2}}))?$"
    )


LENS_GRID_PATTERN = re.compile(
    r"^(?P<camera>[A-Za-z0-9]+)_(?P<lens>[A-Za-z0-9\-]+)_lensgrid_(?P<mm>\d+)mm$"
)


def parse_clip_name(name: str, show_pattern: str = DEFAULT_SHOW_PATTERN) -> ShotIdentity | None:
    """Parse a timeline clip name. Returns None when it does not match (caller raises QC-010)."""
    match = _clip_pattern(show_pattern).match(name)
    if match is None:
        return None
    return ShotIdentity(
        show=match["show"],
        shot=match["shot"],
        elem_type=match["type"],
        elem_index=match["idx"],
        aux=match["aux"],
        aux_index=match["auxidx"],
    )


def parse_shot_code(code: str, show_pattern: str = DEFAULT_SHOW_PATTERN) -> tuple[str, str] | None:
    """Split `MELT0001` into show and shot number.

    Used when the editor corrects a shot code (NAMING_SPEC section 6): the correction
    carries a new show and number, and every name is rebuilt from them.
    """
    match = re.match(rf"^(?P<show>{show_pattern})(?P<shot>\d{{4}})$", code)
    if match is None:
        return None
    return match["show"], match["shot"]


def parse_lens_grid_name(name: str) -> LensGridIdentity | None:
    """Parse a lens grid clip name, which uses a different pattern to shot clips."""
    match = LENS_GRID_PATTERN.match(name)
    if match is None:
        return None
    return LensGridIdentity(camera=match["camera"], lens=match["lens"], mm=match["mm"])


def normalize_shooter(name: str) -> str:
    """Reduce a shooter's name to what the stringout filename can carry.

    The stringout pattern only accepts lowercase alphanumerics, so `Daniel Luckett`
    and `daniel-luckett` both become `danielluckett`. The unnormalized value stays on
    the turnover for the tracker and the QC log. See OQ-15.
    """
    return re.sub(r"[^a-z0-9]", "", name.lower())


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


def hdri_exr(identity: ShotIdentity, version: int) -> str:
    return f"{identity.stem}_HDRI_{_ver(version)}.exr"


def camdata(identity: ShotIdentity, version: int, ext: str) -> str:
    ext = ext.lstrip(".").lower()
    if ext not in CAMDATA_EXTENSIONS:
        raise ValueError(f"camData extension must be one of {CAMDATA_EXTENSIONS}, got {ext!r}")
    return f"{identity.stem}_camData_{_ver(version)}.{ext}"


def aux_still_exr(identity: ShotIdentity, version: int) -> str:
    """Single-frame reference still (colorChart, mirrorBall, greyBall, sizeRef). Always 4k."""
    if identity.aux is None or identity.aux_index is None:
        raise ValueError(f"{identity.stem} carries no aux still")
    if identity.aux not in AUX_NAMES:
        raise ValueError(f"aux still must be one of {AUX_NAMES}, got {identity.aux!r}")
    return f"{identity.stem}_{identity.aux}_{identity.aux_index}_4k_{_ver(version)}.exr"


def bts(identity: ShotIdentity, version: int, ext: str) -> str:
    ext = ext.lstrip(".").lower()
    if ext not in BTS_EXTENSIONS:
        raise ValueError(f"BTS extension must be one of {BTS_EXTENSIONS}, got {ext!r}")
    if identity.aux_index is None:
        raise ValueError(f"{identity.stem} carries no BTS index")
    return f"{identity.stem}_BTS_{identity.aux_index}_{_ver(version)}.{ext}"


def lens_grid_png(identity: LensGridIdentity, version: int) -> str:
    return f"{identity.camera}_{identity.lens}_lensgrid_{identity.mm}mm_{_ver(version)}.png"


def stringout_mp4(turnover_number: int, month: int, day: int, year: int, shooter: str, version: int) -> str:
    """`turnover001_02_23_2026_danielluckett_v01.mp4`. Shooter is normalized here."""
    normalized = normalize_shooter(shooter)
    if not normalized:
        raise ValueError(f"shooter name {shooter!r} normalizes to an empty string")
    return (
        f"turnover{turnover_number:03d}_{month:02d}_{day:02d}_{year:04d}"
        f"_{normalized}_{_ver(version)}.mp4"
    )


# --- Delivery folder layout, NAMING_SPEC.md section 5. ---


def shot_dir(delivery_root: Path, identity: ShotIdentity) -> Path:
    return delivery_root / identity.show / identity.shot_code


def turnovers_dir(delivery_root: Path, show: str) -> Path:
    return delivery_root / show / "_turnovers"


def reports_dir(delivery_root: Path, show: str) -> Path:
    return delivery_root / show / "_reports"


# --- Reading output names back, NAMING_SPEC.md section 7. Drives QC-151 and versioning. ---

OutputKind = Literal[
    "raw_frame",
    "raw_dir",
    "ref_mp4",
    "audio",
    "hdri",
    "camdata",
    "aux_still",
    "bts",
    "lensgrid",
    "stringout",
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
    sc = rf"(?P<show>{show_pattern})(?P<shot>\d{{4}})_(?P<type>{_TYPES})(?P<idx>\d{{2}})"
    v = r"v(?P<ver>\d{2})"
    res = r"(?P<res>4k|HD)"
    camdata_ext = "|".join(CAMDATA_EXTENSIONS)
    bts_ext = "|".join(BTS_EXTENSIONS)
    return [
        ("raw_frame", re.compile(rf"^{sc}_raw_{res}_{v}\.(?P<frame>\d{{4}})\.exr$")),
        ("raw_dir", re.compile(rf"^{sc}_raw_{res}_{v}$")),
        ("ref_mp4", re.compile(rf"^{sc}_ref_{res}_{v}\.mp4$")),
        ("audio", re.compile(rf"^{sc}_audio_{v}\.wav$")),
        ("hdri", re.compile(rf"^{sc}_HDRI_{v}\.exr$")),
        ("camdata", re.compile(rf"^{sc}_camData_{v}\.(?P<ext>{camdata_ext})$")),
        ("aux_still", re.compile(rf"^{sc}_(?P<aux>{_AUX})_(?P<auxidx>\d{{2}})_4k_{v}\.exr$")),
        ("bts", re.compile(rf"^{sc}_BTS_(?P<auxidx>\d{{2}})_{v}\.(?P<ext>{bts_ext})$")),
        (
            "lensgrid",
            re.compile(
                rf"^(?P<camera>[A-Za-z0-9]+)_(?P<lens>[A-Za-z0-9\-]+)"
                rf"_lensgrid_(?P<mm>\d+)mm_{v}\.png$"
            ),
        ),
        (
            "stringout",
            re.compile(
                rf"^turnover(?P<tno>\d{{3}})_(?P<mm>\d{{2}})_(?P<dd>\d{{2}})"
                rf"_(?P<yyyy>\d{{4}})_(?P<shooter>[a-z0-9]+)_{v}\.mp4$"
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
