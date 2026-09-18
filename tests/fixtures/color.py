"""A colour session's exports, built at test time rather than committed.

Same rule as the media fixtures: a cube typed out by hand is a second implementation of
a transform, and the point of a fixture here is to have OpenColorIO answer what it
would actually load. COLOR_AND_FORMAT section 1 specifies what the session exports: an
EDL carrying the CDL (`make_session`) and, for a shot that needed more than the wheels,
a grade-only cube out of the ACEScct session (`plate_clf`, `plate_cube`).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import PyOpenColorIO as ocio

from proingest.core import clf, color

CLF_FORMAT = "Academy/ASC Common LUT Format"

SOURCE_ENCODING = "ACEScct"
"""What a fixture clip is taken to be encoded in.

A real clip says this in its own metadata and the scan reads it (M4.6.4); a fixture has
to state it somewhere, and stating it here keeps it a fact about the fixture rather than
a constant of the tool's. ACEScct because that is what every test rendered through
before the encoding became a per clip fact, so the numbers in the render tests did not
move when it did.
"""

UNGRADED = clf.ShotColor(source_encoding=SOURCE_ENCODING)
"""The chain a row with no grade renders through: the source encoding to ACEScg."""

CLF_SOURCE = color.WORKING_SPACE
"""Where a session's cube starts and ends: the timeline space of the session it came
out of, which is ACEScct by the standard decided on 2026-09-18."""


def write_clf(path: Path, *transforms: ocio.Transform) -> Path:
    """Bake a chain into a CLF at `path`."""
    group = ocio.GroupTransform()
    for transform in transforms:
        group.appendTransform(transform)
    path.parent.mkdir(parents=True, exist_ok=True)
    baked = color.config().getProcessor(group).createGroupTransform()
    baked.write(formatName=CLF_FORMAT, config=color.config(), fileName=str(path))
    return path


GRADE = ocio.CDLTransform(slope=[1.4, 1.0, 0.7], offset=[0.0] * 3, power=[1.0] * 3, sat=1.1)
"""The grade in every fixture cube. It lifts red and drops blue hard enough that a plate
it was not applied to is obvious in one pixel."""


def plate_clf(path: Path) -> Path:
    """What Generate LUT writes out of an ACEScct session: the grade alone, log in, log out."""
    return write_clf(path, GRADE)


def display_clf(path: Path, size: int = 9) -> Path:
    """A cube with the ACES output transform baked into it, which is QC-039's failure.

    What Generate LUT writes when the viewing transform sits on the clip rather than the
    timeline. Sampled into a 3D LUT because that is what a cube is.
    """
    view = ocio.DisplayViewTransform(src=CLF_SOURCE, display=color.DISPLAY, view=color.VIEW)
    cpu = color.config().getProcessor(view).getDefaultCPUProcessor()
    lut = ocio.Lut3DTransform(gridSize=size, interpolation=color.INTERPOLATION)
    for red in range(size):
        for green in range(size):
            for blue in range(size):
                sample = [value / (size - 1) for value in (red, green, blue)]
                lut.setValue(red, green, blue, *cpu.applyRGB(sample))
    return write_clf(path, lut)


def make_session(folder: Path, shots: int = 1, frames: int = 4) -> Path:
    """A colour session package for the `media.make_turnover` fixture: an EDL with a CDL per event.

    A run needs one (QC-008), so the tests that are about anything else still have to
    have one. It is written to match the fixture turnover exactly: one event per shot at
    the media's own `01:00:00:00`, with the CDL that is the grade. No cube, because the
    standard package has none; a test about the override writes its own `plate_clf`.
    """
    folder.mkdir(parents=True, exist_ok=True)
    edl = folder / "MELT_FINAL_v01.edl"
    events = ["TITLE: MELT_FINAL_v01", "FCM: NON-DROP FRAME", ""]
    for index in range(1, shots + 1):
        shot = f"MELT{index:04d}"
        out_timecode = f"01:00:00:{frames:02d}"
        events += [
            f"{index:03d}  {shot} V     C        01:00:00:00 {out_timecode} 01:00:00:00 {out_timecode}",
            f"* FROM CLIP NAME: {shot}_pl01.exr",
            "*ASC_SOP (1.020000 0.990000 1.010000)(0.001000 -0.002000 0.000000)(0.980000 1.000000 1.020000)",
            "*ASC_SAT 1.050000",
        ]
    edl.write_text("\n".join(events) + "\n")
    return edl


def plate_cube(path: Path, size: int = 17) -> Path:
    """What Resolve's Generate LUT writes: the grade sampled onto a 3D `.cube` (OQ-54).

    The same grade as `plate_clf`, so a test can swap one for the other. Red varies fastest,
    which is the cube format's order, and the values are the processor's own, so the probe
    that judges a CLF judges this the same way.
    """
    steps = np.linspace(0.0, 1.0, size, dtype=np.float32)
    b, g, r = np.meshgrid(steps, steps, steps, indexing="ij")
    pixels = np.stack([r, g, b], axis=-1).reshape(1, -1, 3).astype(np.float32)
    color.apply(pixels, color.processor(GRADE))
    lines = [f"LUT_3D_SIZE {size}", "DOMAIN_MIN 0.0 0.0 0.0", "DOMAIN_MAX 1.0 1.0 1.0"]
    lines += [f"{px[0]:.6f} {px[1]:.6f} {px[2]:.6f}" for px in pixels[0]]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")
    return path
