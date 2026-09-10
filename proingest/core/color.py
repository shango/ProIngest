"""What colour the incoming pixels are, and what each deliverable does about it.

This is the answer to OQ-17, and it is a setting rather than a constant because the
answer is known to change.

Today the shooters deliver everything with the sRGB curve already baked in, the EXRs
included: the files are display referred, not scene referred. Later the EXRs become
scene linear sRGB. Only the source changes; the deliverables are defined the same way
in both cases, which is why one value drives every decision here.

The consequence that matters is the reference encode. A display encode has to end up
in display sRGB. From a scene linear source that means applying the linear to sRGB
transfer; from a source that already carries the curve it means applying nothing at
all. Getting that backwards does not fail loudly, it just produces washed out or
crushed references, so the rule lives in one place and is read, never re-derived.

Primaries do not change either way: sRGB and Rec.709 share them.
"""

from __future__ import annotations

from typing import Literal

SourceColorSpace = Literal["srgb_display", "scene_linear_srgb"]

SRGB_DISPLAY: SourceColorSpace = "srgb_display"
"""Display referred: the sRGB curve is baked in. What the shooters deliver today."""

SCENE_LINEAR_SRGB: SourceColorSpace = "scene_linear_srgb"
"""Scene referred, sRGB primaries. What the EXRs are expected to become."""

DEFAULT_SOURCE_COLORSPACE: SourceColorSpace = SRGB_DISPLAY
"""v01 default. Editable in Settings, so a turnover that arrives linear needs no build."""

_EXR_ATTRIBUTE_VALUES: dict[SourceColorSpace, str] = {
    SRGB_DISPLAY: "sRGB_display",
    SCENE_LINEAR_SRGB: "scene_linear_sRGB",
}

LINEAR_TO_SRGB_FILTER = "zscale=transferin=linear:transfer=iec61966-2-1"
"""COLOR_AND_FORMAT section 1. Only ever applied to a scene linear source."""


def exr_attribute(space: SourceColorSpace) -> str:
    """What a written EXR states in `proingest/colorspace`.

    Raw output is never transformed, so this records what the pixels are, not a
    conversion that happened.
    """
    return _EXR_ATTRIBUTE_VALUES[space]


def display_transform(space: SourceColorSpace) -> str | None:
    """The ffmpeg filter that brings a source to display sRGB, or None when it is there.

    Reference mp4s and the stringout are display encodes and are the only outputs
    that use this. Both are tagged `bt709` primaries and matrix with an
    `iec61966-2-1` transfer whichever branch this takes, because both end up in the
    same place; only the work needed to get there differs.
    """
    return LINEAR_TO_SRGB_FILTER if space == SCENE_LINEAR_SRGB else None
