"""The colour transforms every deliverable is built from.

COLOR_AND_FORMAT section 1. Colour is finished before the tool runs: a colour session
in Resolve exports one CLF per shot and the tool applies it. Nothing here authors
colour, and nothing here is a hand written curve or matrix. Every transform comes from
OpenColorIO's built-in ACES config, which travels inside the wheel, so no config files
ship and there is nothing for an installer to get wrong.

The chain, with this module supplying its two ends:

    studio standard log -> ACEScct -> [the shot's CLF] -> linear ACEScg

`input_transform` is the first leg, `plate_transform` the last. The CLF in the middle
is loaded rather than built (M4.5.2), which is why this module composes transforms and
hands back a processor instead of owning the whole chain. It also means the caller
decides whether the last leg is needed at all: a CLF is specified to end in linear
ACEScg itself (QC-039), so applying `plate_transform` after one would convert twice.

Building a processor is expensive and applying it is not, so the two are separate
calls. Build one per shot, apply it per frame.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

import numpy as np
import numpy.typing as npt
import PyOpenColorIO as ocio


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

WORKING_SPACE = "ACEScct"
"""The colour session's timeline space, and therefore where every CLF starts."""

PLATE_SPACE = "ACEScg"
"""Scene linear, AP1 primaries. What a delivered EXR is."""

DEFAULT_SOURCE_ENCODING = WORKING_SPACE
"""The one log encoding every shooter delivers in, whatever they shot on (OQ-39).

One encoding on every file means one input transform forever: no per shot IDT, no
exposure index question, and no mapping of Resolve's transform names onto OpenColorIO's,
which do not agree. This is a Settings value rather than a constant because which
encoding is not settled, and it is one string either way. ACEScct is the default and
makes the input transform identity, which is why it is the one to push for.
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


def input_transform(source_encoding: str = DEFAULT_SOURCE_ENCODING) -> ocio.ColorSpaceTransform:
    """The studio standard log encoding to ACEScct, where the CLF begins.

    Identity when the studio standard is ACEScct itself, in which case the decode leads
    straight into the grade with nothing between them that could be silently wrong.
    """
    check_encoding(source_encoding)
    return ocio.ColorSpaceTransform(src=source_encoding, dst=WORKING_SPACE)


def plate_transform() -> ocio.ColorSpaceTransform:
    """ACEScct to linear ACEScg: the tail of the plate branch.

    Only for a chain that does not already land in ACEScg. The CLF is specified to end
    there itself, so a graded plate must not have this applied after it.
    """
    return ocio.ColorSpaceTransform(src=WORKING_SPACE, dst=PLATE_SPACE)


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


# --------------------------------------------------------------------------------------
# Superseded: M3's display referred reference encode.
#
# This is the 2026-09-10 premise, where sources carried a baked sRGB curve and a
# reference was encoded with no transform at all. Nothing above it is related to it.
# `render.py` and `exr.py` still read it, and M4.5.4 is where they stop: the reference
# becomes an ffmpeg `lut3d` from the viewing LUT and the EXR header states ACEScg. This
# block and its tests go in that chunk, together, and not before.
# --------------------------------------------------------------------------------------

SourceColorSpace = Literal["srgb_display", "scene_linear_srgb"]

SRGB_DISPLAY: SourceColorSpace = "srgb_display"
"""Display referred: the sRGB curve is baked in."""

SCENE_LINEAR_SRGB: SourceColorSpace = "scene_linear_srgb"
"""Scene referred, sRGB primaries."""

DEFAULT_SOURCE_COLORSPACE: SourceColorSpace = SRGB_DISPLAY

_EXR_ATTRIBUTE_VALUES: dict[SourceColorSpace, str] = {
    SRGB_DISPLAY: "sRGB_display",
    SCENE_LINEAR_SRGB: "scene_linear_sRGB",
}

LINEAR_TO_SRGB_FILTER = "zscale=transferin=linear:transfer=iec61966-2-1"


def exr_attribute(space: SourceColorSpace) -> str:
    """What a written EXR states in `proingest/colorspace`."""
    return _EXR_ATTRIBUTE_VALUES[space]


def display_transform(space: SourceColorSpace) -> str | None:
    """The ffmpeg filter that brings a source to display sRGB, or None when it is there."""
    return LINEAR_TO_SRGB_FILTER if space == SCENE_LINEAR_SRGB else None
