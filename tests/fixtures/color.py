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
    """What the session is specified to export: ACEScct in, a primary, linear ACEScg out.

    The grade lifts red and drops blue hard enough that a plate it was not applied to is
    obvious in one pixel.
    """
    return write_clf(
        path,
        ocio.CDLTransform(
            slope=[1.4, 1.0, 0.7], offset=[0.0] * 3, power=[1.0] * 3, sat=1.1
        ),
        ocio.ColorSpaceTransform(src=color.WORKING_SPACE, dst=color.PLATE_SPACE),
    )
