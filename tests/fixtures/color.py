"""A colour session's exports, built at test time rather than committed.

Same rule as the media fixtures: a CLF typed out by hand is a second implementation of
a transform, and the point of a fixture here is to have OpenColorIO answer what it
would actually load. COLOR_AND_FORMAT section 1 specifies what the session exports, and
`plate_clf` is a file shaped like it.
"""

from __future__ import annotations

from pathlib import Path

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
"""The chain a row with no CLF renders through: the source encoding to ACEScg, no grade."""

CLF_SOURCE = "ACEScct"
"""Where these fixture CLFs start, which the tool no longer needs to know.

A real session's CLF starts at whatever its clip is encoded in (OQ-37), and since the
tool applies the CLF alone, which log a fixture picks is free. ACEScct because the
numeric anchors in the colour tests are ACEScct code values.
"""


def write_clf(path: Path, *transforms: ocio.Transform) -> Path:
    """Bake a chain into a CLF at `path`."""
    group = ocio.GroupTransform()
    for transform in transforms:
        group.appendTransform(transform)
    path.parent.mkdir(parents=True, exist_ok=True)
    baked = color.config().getProcessor(group).createGroupTransform()
    baked.write(formatName=CLF_FORMAT, config=color.config(), fileName=str(path))
    return path


def plate_clf(path: Path) -> Path:
    """What the session is specified to export: source encoding in, a primary, ACEScg out.

    The grade lifts red and drops blue hard enough that a plate it was not applied to is
    obvious in one pixel.
    """
    return write_clf(
        path,
        ocio.CDLTransform(slope=[1.4, 1.0, 0.7], offset=[0.0] * 3, power=[1.0] * 3, sat=1.1),
        ocio.ColorSpaceTransform(src=CLF_SOURCE, dst=color.PLATE_SPACE),
    )


def display_clf(path: Path, size: int = 9) -> Path:
    """A CLF with the ACES output transform baked into it, which is QC-039's failure.

    Sampled into a 3D LUT because that is the only way such a CLF exists: the output
    transform uses ops CLF cannot express, so a session that exported one would have had
    to bake it, exactly as here.
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
    """A colour session package for the `media.make_turnover` fixture: an EDL and a CLF each.

    A run needs one (QC-008), so the tests that are about anything else still have to
    have one. It is written to match the fixture turnover exactly: one event per shot at
    the media's own `01:00:00:00`, and a CLF named after the shot the way OQ-33 expects.
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
        plate_clf(folder / f"{shot}_grade_v01.clf")
    edl.write_text("\n".join(events) + "\n")
    return edl
