"""An identity from an old-style clip name, for tests only.

The shooters do not rename clips and identity arrives in the CSV (`metacsv`), so nothing
in the tool parses a clip name any more. The tests still describe a row by one, because
`MELT0001_pl01` says in one word what `ShotIdentity("MELT0001", "pl", "01")` says in
three, and this is the one place that reading lives.
"""

from __future__ import annotations

import re

from proingest.core import naming
from proingest.core.naming import ShotIdentity

_AUX = "|".join(naming.AUX_NAMES)
_TYPES = "|".join(naming.ELEMENT_TYPES)


def identity_of(name: str, show_pattern: str = naming.DEFAULT_SHOW_PATTERN) -> ShotIdentity | None:
    """`MELT0001_pl01` as its identity, `MELT0001_pl01_colorChart_01` as that still."""
    match = re.match(
        rf"^(?P<show>{show_pattern})(?P<shot>\d{{4}})"
        rf"_(?P<type>{_TYPES})(?P<idx>\d{{2}})"
        rf"(?:_(?P<aux>{_AUX})_(?P<auxidx>\d{{2}}))?$",
        name,
    )
    if match is None:
        return None
    code = f"{match['show']}{match['shot']}"
    if match["aux"] is not None:
        return ShotIdentity(shot_code=code, kind=match["aux"], index=match["auxidx"])
    return ShotIdentity(shot_code=code, kind=match["type"], index=match["idx"])
