"""A colour session's exports, built at test time rather than committed.

Same rule as the media fixtures: a CLF typed out by hand is a second implementation of
a transform, and the point of a fixture here is to have OpenColorIO answer what it
would actually load. COLOR_AND_FORMAT section 1 specifies what the session exports, and
`plate_clf` is a file shaped like it.
"""

from __future__ import annotations

from pathlib import Path

import PyOpenColorIO as ocio

from proingest.core import color

CLF_FORMAT = "Academy/ASC Common LUT Format"

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
        ocio.CDLTransform(
            slope=[1.4, 1.0, 0.7], offset=[0.0] * 3, power=[1.0] * 3, sat=1.1
        ),
        ocio.ColorSpaceTransform(src=CLF_SOURCE, dst=color.PLATE_SPACE),
    )
