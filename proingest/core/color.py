"""The colour transforms every deliverable is built from.

COLOR_AND_FORMAT section 1. Colour is decided before the tool runs: the colour session in
Resolve exports one AMF per clip, naming the input transform, the looks and the output
transform, and a CLF per corrector node of the grade (user, 2026-09-28). Nothing here
authors colour, and nothing here is a hand written curve or matrix. Every transform comes
from OpenColorIO's built-in ACES config, which travels inside the wheel, or is one of the
colourist's CLFs, which OCIO reads as they are.

The chain, in the AMF's own order, with this module supplying each leg:

    source encoding -> ACES2065-1 -> [the AMF's looks, in order] -> linear ACEScg  plate
                                                                 -> the AMF's display  view

**Every look is applied in ACES2065-1**, because that is where the AMF puts them: the
Reference Gamut Compress is a look the config defines in ACES2065-1, and each of Resolve's
CLFs takes ACES2065-1 in and gives it back, carrying its own trip into ACEScct and out
again around the node's LUT. So the tool converts into ACES2065-1 once, applies what the
AMF lists, and converts out once; there is no working space of its own to get wrong.

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


class ColorError(RuntimeError):
    """A colour space that does not exist, or pixels that cannot be transformed."""


BUILTIN_CONFIG = "studio-config-v4.0.0_aces-v2.0_ocio-v2.5"
"""The config, pinned rather than tracking latest (OQ-29).

ACES 2.0 because that is what the colour session runs (user, 2026-09-25; it was 1.3 until
then), and matching the session matters more than being current: a dependency bump must
not change what the references look like. Moving from the 1.3 config left the plate branch
bit for bit the same, measured on frame 30 of `C0148.MP4`; only the view changed.
The studio config rather than the cg one because it carries the camera vendor log
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

ACES = "ACES2065-1"
"""Where the AMF's looks are applied: the Reference Gamut Compress is defined there, and
every one of Resolve's CLFs takes it in and gives it back."""

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


def resolve_encoding(name: str) -> str:
    """A colour space name as the config's canonical one, aliases and casing included.

    Raises `ColorError` for a name the config does not know. The name comes from the
    config itself since 2026-09-28 (`amf.colour_space_for`), so this is a check that a
    saved batch still names something the pinned config has, not a lookup of what a
    shooter typed.
    """
    known = config().getColorSpace(" ".join(name.split()))
    if known is None:
        raise ColorError(f"{name!r} is not a colour space in {BUILTIN_CONFIG}")
    return str(known.getName())


def to_aces(source_encoding: str) -> ocio.ColorSpaceTransform:
    """The source encoding to ACES2065-1: the AMF's input transform, as the config has it."""
    check_encoding(source_encoding)
    return ocio.ColorSpaceTransform(src=source_encoding, dst=ACES)


def input_transform(source_encoding: str) -> ocio.ColorSpaceTransform:
    """The source encoding to linear ACEScg in one leg, for a chain with no look in it.

    An aux still, which is delivered ungraded by design, and a clip whose AMF lists no
    look. The same pixels as `to_aces` then `to_plate`, in one transform.
    """
    check_encoding(source_encoding)
    return ocio.ColorSpaceTransform(src=source_encoding, dst=PLATE_SPACE)


def to_plate() -> ocio.ColorSpaceTransform:
    """ACES2065-1 to linear ACEScg: the leg after the looks, the same for every shot."""
    return ocio.ColorSpaceTransform(src=ACES, dst=PLATE_SPACE)


def look_transform(name: str) -> ocio.LookTransform:
    """A look the config defines, applied in ACES2065-1 and staying there."""
    if config().getLook(name) is None:
        raise ColorError(f"{name!r} is not a look in {BUILTIN_CONFIG}")
    return ocio.LookTransform(src=ACES, dst=ACES, looks=name)


def clf_transform(path: Path) -> ocio.FileTransform:
    """One of the colourist's CLFs, as it is: ACES2065-1 in and out (Resolve's export)."""
    return ocio.FileTransform(src=str(path), interpolation=INTERPOLATION)


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


LUT_SIZE = 33
"""Samples per axis in the baked cube. 33 is what Resolve and Nuke default to.

The cube is written per shot and read once by ffmpeg, so the cost of a larger one is a
megabyte of text nobody keeps, and the cost of a smaller one is banding in a gradient
that only shows up on the delivered reference.
"""


def output_transform(display: str, view: str) -> ocio.DisplayViewTransform:
    """Linear ACEScg to the display and view the clip's AMF names: the view branch's tail.

    From the AMF since 2026-09-28 (user), so a reference is viewed the way the colour
    session was; turnover097's AMFs name Gamma 2.2 Rec.709 through the ACES 2.0 SDR
    100 nit rendering. The plates never see it.
    """
    return ocio.DisplayViewTransform(src=PLATE_SPACE, display=display, view=view)


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
