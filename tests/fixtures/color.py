"""A colour session's exports, built at test time rather than committed.

COLOR_AND_FORMAT section 1 specifies what the session exports, and since 2026-09-22 it
is one thing: an EDL carrying the CDL per event (`make_session`). There are no per-shot
grade files, so there is nothing else here to build.
"""

from __future__ import annotations

from pathlib import Path

from proingest.core import clf

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


def make_session(folder: Path, shots: int = 1, frames: int = 4) -> Path:
    """A colour session package for the `media.make_turnover` fixture: an EDL with a CDL per event.

    A run needs one (QC-008), so the tests that are about anything else still have to
    have one. It is written to match the fixture turnover exactly: one event per shot at
    the media's own `01:00:00:00`, with the CDL that is the grade.
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
