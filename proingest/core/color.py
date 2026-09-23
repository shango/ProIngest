"""The colour transforms every deliverable is built from.

COLOR_AND_FORMAT section 1. Colour is decided before the tool runs: a colour session in
Resolve exports one final EDL whose events carry the ASC CDL, and the tool applies that
CDL in the session's working space, ACEScct. Nothing here authors colour, and nothing
here is a hand written curve or matrix. Every transform comes from OpenColorIO's
built-in ACES config, which travels inside the wheel, so no config files ship and there
is nothing for an installer to get wrong.

The chain, with this module supplying every leg except the grade:

    source encoding -> ACEScct -> [the shot's CDL, or its cube] -> linear ACEScg   plate
                                                                -> sRGB display    view

**The tool converts on both sides of the grade** (decided 2026-09-18, OQ-46). The grade is
the primaries the colourist set in node one of a colour managed session whose timeline
is ACEScct, so it means something only in ACEScct: `to_working` gets the clip there from
whatever its metadata says it is encoded in, and `from_working` carries the graded
result to ACEScg. A `.cube` from Generate LUT out of that same session is the same
grade with the whole node graph in it, ACEScct in and out, and stands in the same slot
(`core/clf.py`). `input_transform` is the one leg chain for a shot with no grade at all:
an aux still, which is delivered ungraded by design.

Building a processor is expensive and applying it is not, so the two are separate
calls. Build one per shot, apply it per frame. The view branch is built once per shot
too, but as a `.cube`: `view_lut` bakes it because ffmpeg is what applies it.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import numpy as np
import numpy.typing as npt
import PyOpenColorIO as ocio

from proingest.core.models import CDL


class ColorError(RuntimeError):
    """A colour space that does not exist, or pixels that cannot be transformed."""


BUILTIN_CONFIG = "studio-config-v2.2.0_aces-v1.3_ocio-v2.4"
"""The config, pinned rather than tracking latest (OQ-29).

ACES 1.3 because that is what the colour session runs, and matching the session matters
more than being current: a dependency bump must not change what the references look
like. The studio config rather than the cg one because it carries the camera vendor log
encodings, which is what OQ-39 may yet name, and the full set of view transforms M4.5.3
bakes into the viewing LUT.
"""

PLATE_SPACE = "ACEScg"
"""Scene linear, AP1 primaries. What a delivered EXR is, and where every CLF ends."""

# There is no default source encoding, and that is deliberate. A constant lived here
# until M4.6.1, standing in for the clip metadata nothing read yet. The encoding is a
# per clip fact (COLOR_AND_FORMAT section 1), a turnover may mix encodings freely, and a
# batch-wide value would be wrong for every clip it was not guessed for.
# `ShotRow.source_encoding` carries what the clip itself names, and a row that names
# nothing is QC-046 rather than a row converted through a guess.

WORKING_SPACE = "ACEScct"
"""The colour session's timeline colour space, which is where the CDL is applied.

A constant and not a setting, because it is the standard the colourist's session is
set to (decided 2026-09-18) and a value here that disagreed with the session would
replay the grade in the wrong space without an error: a CDL applied in ACEScc instead
of ACEScct is wrong in the shadows and looks like a grade. ACEScct rather than ACEScc
because it is Resolve's default for an ACES managed project and what a colourist
grades in, its toe behaving like camera log under the wheels. Shown read only on the
Settings page beside the config, and written into every delivered EXR's header.
"""

INPUT_TRANSFORMS: dict[str, str] = {
    "c-log3": "CanonLog3 CinemaGamut D55",
    "bm film": "BMDFilm WideGamut Gen5",
    "davinci wide gamut": "DaVinci Intermediate WideGamut",
}
"""What a shooter writes, to one colour space in the pinned config. COLOR_AND_FORMAT
section 1.

Keys are casefolded with their whitespace collapsed, which `resolve_encoding` does to
both sides before it looks. That is still an exact lookup: a Resolve export and a
shooter's typing differ in case and spacing far more often than they disagree about
which camera shot the clip.

**A table, not a search.** No prefix matching and no nearest miss: a name that is not an
entry and not a colour space the config knows is QC-047, because a near miss converts a
picture plausibly and wrongly. **Adding a camera is adding a row**, which is why "more
may be added" costs nothing.

**Only the names the config does not already know need a row.** Every colour space in
the pinned config resolves to itself, aliases and casing included, so a clip that names
`S-Log3 S-Gamut3.Cine` or `DaVinci Intermediate WideGamut` needs nothing here. The
`davinci wide gamut` row is what the house template's shorter name lands on.

**`S-Log3` is deliberately absent.** It names four colour spaces in this config, since a
curve does not choose a gamut, and a row picking one of them would be picking a gamut on
the shooter's behalf. It resolves to nothing and QC-047 names the four candidates.
"""

INTERPOLATION = ocio.INTERP_TETRAHEDRAL
"""Read from here, never re-derived, wherever a LUT is loaded or baked.

The default in several tools is trilinear, it is visibly worse on saturated colour, and
it is a one word difference that nobody notices being wrong.
"""


@lru_cache(maxsize=1)
def config() -> ocio.Config:
    """The pinned ACES config. Cached: reading it back is not free and it never varies."""
    return ocio.Config.CreateFromBuiltinConfig(BUILTIN_CONFIG)


def check_encoding(name: str) -> None:
    """Raise unless `name` is a colour space the pinned config knows.

    Worth doing at the edge rather than at the first frame, because a source encoding
    is a setting a human typed and OCIO's own failure for an unknown space arrives deep
    inside a render.
    """
    if config().getColorSpace(name) is None:
        raise ColorError(f"{name!r} is not a colour space in {BUILTIN_CONFIG}")


def resolve_encoding(written: str) -> str:
    """What a clip's metadata names, as one colour space in the pinned config (QC-047).

    Three ways in, in order: the config's own name for it, including aliases and any
    casing, then a row of `INPUT_TRANSFORMS`, then nothing. What comes back is the
    config's canonical name, so a clip that said `acescg` and one that said `ACEScg`
    record the same provenance in their headers.

    Raises rather than reaching for the nearest entry. The failure this prevents is a
    mis-converted colour chart: it is the one picture the tool transforms on its own
    authority, it is delivered precisely to be matched against, and a wrong one still
    looks exactly like a chart.
    """
    key = " ".join(written.split()).casefold()
    if not key:
        raise ColorError("the clip names no source encoding")
    known = config().getColorSpace(key)
    if known is not None:
        return str(known.getName())
    mapped = INPUT_TRANSFORMS.get(key)
    if mapped is not None:
        return mapped
    raise ColorError(f"{written!r} {_unresolved_reason(key)}")


def _unresolved_reason(key: str) -> str:
    """Why a name did not resolve, for QC-047's message. Never used to match.

    A name that appears inside several colour space names is a curve without a gamut,
    which is the common case and the one worth naming the candidates for: "S-Log3" is
    four colour spaces here. The search is for the sentence only - resolving to any of
    them would be the nearest miss this module refuses to make.
    """
    contains = [name for name in config().getColorSpaceNames() if key in " ".join(name.split()).casefold()]
    if len(contains) > 1:
        return f"names {len(contains)} colour spaces in {BUILTIN_CONFIG}: {', '.join(contains)}"
    return f"is not a colour space in {BUILTIN_CONFIG} and is not in the input transform table"


def input_transform(source_encoding: str) -> ocio.ColorSpaceTransform:
    """The source encoding to linear ACEScg, in one leg. COLOR_AND_FORMAT section 1.

    **Only for a chain with no grade in it**: an aux still, which is delivered ungraded by
    design, and a row the colour session has no CDL and no cube for. A graded chain goes
    through `to_working` and `from_working` instead, because the grade sits between them.
    """
    check_encoding(source_encoding)
    return ocio.ColorSpaceTransform(src=source_encoding, dst=PLATE_SPACE)


def to_working(source_encoding: str) -> ocio.ColorSpaceTransform:
    """The source encoding to ACEScct: the leg ahead of the grade, from the clip's metadata.

    This is where the input transform table earns its keep on a plate: a clip that
    names the wrong camera lands in ACEScct wrong and the CDL grades the wrong pixels,
    so QC-046 and QC-047 block a graded plate as they block an aux still.
    """
    check_encoding(source_encoding)
    return ocio.ColorSpaceTransform(src=source_encoding, dst=WORKING_SPACE)


def from_working() -> ocio.ColorSpaceTransform:
    """ACEScct to linear ACEScg: the leg after the grade, the same for every shot."""
    return ocio.ColorSpaceTransform(src=WORKING_SPACE, dst=PLATE_SPACE)


def cdl_transform(cdl: CDL) -> ocio.CDLTransform:
    """The ASC CDL off the EDL's `*ASC_SOP` and `*ASC_SAT` lines, as one OCIO transform.

    OpenColorIO's default style, which does not clamp between the SOP and the
    saturation. The ASC specification clamps there to 0..1, but Resolve's node graph is
    32 bit float and clamps nothing, and a clamp in ACEScct would discard the values
    above 1.0 and the negative values that out of gamut colours legitimately take.
    Whether this matches what the session showed is what the stringout comparison is for
    (OQ-55).
    """
    return ocio.CDLTransform(
        slope=list(cdl.slope), offset=list(cdl.offset), power=list(cdl.power), sat=cdl.saturation
    )


def processor(*transforms: ocio.Transform) -> ocio.CPUProcessor:
    """One CPU processor for the whole chain, as a single `GroupTransform`.

    A group rather than a transform applied per stage: OCIO optimises across the group,
    and a stage applied on its own would round trip through float for nothing.
    """
    group = ocio.GroupTransform()
    for transform in transforms:
        group.appendTransform(transform)
    return config().getProcessor(group).getDefaultCPUProcessor()


def apply(pixels: npt.NDArray[np.float32], cpu: ocio.CPUProcessor) -> None:
    """Transform one `(h, w, 3)` float32 RGB frame in place.

    In place because a 4k float32 frame is 95 MB and the plate branch holds one at a
    time by design. The shape, the dtype and the contiguity are all what
    `ffmpeg.decode_frames` yields; anything else is a caller error rather than
    something to quietly copy around, because a silent copy would transform a frame
    the caller then throws away.
    """
    if pixels.ndim != 3 or pixels.shape[2] != 3:
        raise ColorError(f"expected an (h, w, 3) RGB image, got shape {pixels.shape}")
    if pixels.dtype != np.float32:
        raise ColorError(f"expected float32 pixels, got {pixels.dtype}")
    if not pixels.flags["C_CONTIGUOUS"]:
        raise ColorError("expected a C contiguous array; OCIO reads the buffer directly")
    height, width, _ = pixels.shape
    cpu.apply(ocio.PackedImageDesc(pixels, width, height, ocio.CHANNEL_ORDERING_RGB))


DISPLAY = "sRGB - Display"
"""What a reference mp4 is viewed on, and therefore what the view branch ends at."""

VIEW = "ACES 1.0 - SDR Video"
"""Which ACES 1.3 output transform, which is the half of OQ-29 the config did not settle.

The pinned config offers four views on `sRGB - Display`, and the other three are not
candidates: two are a D60 simulation and an un-tone-mapped debug view, and `Raw` is no
transform at all. This one is the standard SDR video rendering, which is what the colour
session is looking at while the grade is decided.
"""

LUT_SIZE = 33
"""Samples per axis in the baked cube. 33 is what Resolve and Nuke default to.

The cube is written per shot and read once by ffmpeg, so the cost of a larger one is a
megabyte of text nobody keeps, and the cost of a smaller one is banding in a gradient
that only shows up on the delivered reference.
"""


def output_transform() -> ocio.DisplayViewTransform:
    """Linear ACEScg to sRGB display: the tail of the view branch (OQ-29).

    Takes ACEScg because that is where the CLF lands, which is the same reason nothing
    of this module's is applied ahead of one.
    """
    return ocio.DisplayViewTransform(src=PLATE_SPACE, display=DISPLAY, view=VIEW)


def view_lut(destination: Path, *transforms: ocio.Transform, size: int = LUT_SIZE) -> Path:
    """Bake a chain into one Resolve `.cube`. COLOR_AND_FORMAT section 1.

    **This is how an OCIO transform reaches ffmpeg**, which has no OCIO filter and does
    have `lut3d`. It is what keeps a reference encode a single pass with no frames pulled
    through Python, and it is only ever the view branch: a 3D LUT needs a bounded input
    domain, which the log encoding gives and scene linear does not.

    No shaper LUT, because the domain is already log: the input runs 0..1 across the
    source encoding and the samples land where the code values are, which is the whole
    reason the view branch stays in log until the output transform.

    Written to a temporary name in the same folder and renamed, so a cancelled bake
    cannot leave a short file that ffmpeg would read as a LUT.
    """
    grid = _identity_grid(size)
    apply(grid, processor(*transforms))
    lines = [f"LUT_3D_SIZE {size}"]
    lines += [f"{r:.6f} {g:.6f} {b:.6f}" for r, g, b in grid[0]]
    temp = destination.with_name(f".{destination.name}.part")
    temp.write_text("\n".join(lines) + "\n")
    temp.replace(destination)
    return destination


def _identity_grid(size: int) -> npt.NDArray[np.float32]:
    """The cube's sample points as one `(1, size ** 3, 3)` frame, red varying fastest.

    Red fastest is the `.cube` format's own ordering, so the array is written out in
    the order it is sampled in. One frame shaped row rather than a real image because
    `apply` transforms a frame, and the LUT is a frame of every colour that matters.
    """
    axis = np.linspace(0.0, 1.0, size, dtype=np.float32)
    grid = np.empty((1, size**3, 3), dtype=np.float32)
    grid[0, :, 0] = np.tile(axis, size * size)
    grid[0, :, 1] = np.tile(np.repeat(axis, size), size)
    grid[0, :, 2] = np.repeat(axis, size * size)
    return grid
