"""Antialiased Lanczos resampling, for the EXR path only.

docs/COLOR_AND_FORMAT.md section 4 asks for `scale=1920:1080:flags=lanczos`, and a
container source gets exactly that from ffmpeg. An EXR source never goes through
ffmpeg (section 7), so the same filter is implemented here over numpy.

OQ-7 offered `scipy.ndimage.zoom` as the default. It is a cubic spline interpolation
with no antialiasing: at 2:1 it samples the source instead of integrating it, so fine
texture aliases rather than averaging, and it would add a large dependency to a 300 MB
installer budget. The kernel below widens with the scale factor, which is what turns a
reduction into an average, and it needs nothing beyond numpy.

Ringing is not clamped. Lanczos undershoot at a hard edge can push a scene linear
value below zero, and half float carries that fine; clamping would be a colour
decision, and this tool does not make those on raw output.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

import numpy as np
import numpy.typing as npt

LANCZOS_RADIUS = 3
"""Lanczos-3, the same lobe count ffmpeg's `flags=lanczos` uses by default."""


def _kernel(distance: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
    """Lanczos: a sinc windowed by a wider sinc, zero beyond the radius."""
    inside = np.abs(distance) < LANCZOS_RADIUS
    return np.where(inside, np.sinc(distance) * np.sinc(distance / LANCZOS_RADIUS), 0.0)


@lru_cache(maxsize=8)
def _plan(source: int, target: int) -> tuple[npt.NDArray[np.intp], npt.NDArray[np.float32]]:
    """Which source samples feed each target sample, and with what weight.

    Cached because every frame of a sequence resamples between the same two sizes.
    Sample positions are pixel centres, so the mapping stays symmetric end to end.
    """
    scale = min(target / source, 1.0)
    support = LANCZOS_RADIUS / scale
    centres = (np.arange(target) + 0.5) * source / target - 0.5

    span = int(np.ceil(support)) * 2 + 1
    first = np.ceil(centres - support).astype(np.intp)
    indices = first[:, None] + np.arange(span)[None, :]

    weights = _kernel((indices - centres[:, None]) * scale)
    # Clamping after weighting is a replicated edge, which is what swscale does.
    np.clip(indices, 0, source - 1, out=indices)
    normalized = (weights / weights.sum(axis=1, keepdims=True)).astype(np.float32)

    indices.flags.writeable = False
    normalized.flags.writeable = False
    return indices, normalized


def _resample_axis(image: npt.NDArray[np.float32], target: int, axis: int) -> npt.NDArray[np.float32]:
    """Resample one axis.

    Accumulating one tap at a time keeps peak memory at a couple of frames. Gathering
    every tap at once would need the frame times the kernel span, which at 4k is
    hundreds of megabytes for no gain.
    """
    if image.shape[axis] == target:
        return image

    indices, weights = _plan(image.shape[axis], target)
    shape = [1] * image.ndim
    shape[axis] = target

    result = np.zeros(
        tuple(target if index == axis else size for index, size in enumerate(image.shape)),
        dtype=np.float32,
    )
    for tap in range(indices.shape[1]):
        result += weights[:, tap].reshape(shape) * np.take(image, indices[:, tap], axis=axis)
    return result


def lanczos_resize(image: npt.NDArray[Any], width: int, height: int) -> npt.NDArray[np.float32]:
    """Resample an `(h, w, channels)` image to exactly `height` by `width`.

    Rows go first: when the target is smaller, that leaves less data for the second
    pass to move.
    """
    if image.ndim != 3:
        raise ValueError(f"expected an (h, w, channels) image, got shape {image.shape}")
    working = np.asarray(image, dtype=np.float32)
    working = _resample_axis(working, height, 0)
    return _resample_axis(working, width, 1)
