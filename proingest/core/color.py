"""The colour transforms every deliverable is built from.

COLOR_AND_FORMAT section 1. Colour is finished before the tool runs: a colour session
in Resolve exports one CLF per shot and the tool applies it. Nothing here authors
colour, and nothing here is a hand written curve or matrix. Every transform comes from
OpenColorIO's built-in ACES config, which travels inside the wheel, so no config files
ship and there is nothing for an installer to get wrong.

The chain, with this module supplying every leg except the CLF:

    studio standard log -> ACEScct -> [the shot's CLF] -> linear ACEScg   the plate branch
                                                      -> sRGB display    the view branch

`input_transform` is the first leg, `plate_transform` the plate branch's last and
`output_transform` the view branch's. The CLF in the middle is loaded rather than built
(`core/clf.py`), which is why this module composes transforms and hands back a processor
instead of owning the whole chain. It also means the caller decides whether the plate
branch's last leg is needed at all: a CLF is specified to end in linear ACEScg itself
(QC-039), so applying `plate_transform` after one would convert twice.

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

    Takes ACEScg because that is where the CLF lands, which is the same reason
    `plate_transform` is not applied after a CLF.
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

