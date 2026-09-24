"""The ALE beside Ben's EDL: which clip each EDL event is.

Ben's EDL names no clips: every event is reel `AX` with no `FROM CLIP NAME`. Matching an
event to a file by timecode works when cameras record time of day (Turnover199), and fails
when they do not: the iPhone files in Turnover121 all start within the first minute, so
most events fall inside several of them and the scan could only refuse (QC-067).

**The ALE is one row per timeline event, in timeline order** (verified 2026-09-23: 11 rows
for Turnover121's 11 events and 5 for Turnover199's 5, each row's `Name` a file whose own
timecode holds that event's source range). So its row order names the EDL's events.

**Only `Name` and the row order are read.** Its `Start` and `End` describe the clip, not the
cut, and `Start` is stale camera metadata (`docs/SAMPLE_TURNOVER_199.md`), so nothing here
reads a timecode. Tab separated, in three sections: `Heading`, then `Column` and one line
of names, then `Data` and a line per event.
"""

from __future__ import annotations

from pathlib import Path

ALE_SUFFIX = ".ale"
NAME_COLUMN = "Name"


class AleError(Exception):
    """The file is not an ALE this tool can read (QC-071)."""


def find(folder: Path) -> list[Path]:
    """Every ALE directly in the turnover folder, in any case."""
    return sorted(p for p in folder.iterdir() if p.is_file() and p.suffix.lower() == ALE_SUFFIX)


def read_names(path: Path) -> list[str]:
    """Each data row's `Name`, in file order, which is timeline order."""
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise AleError(f"could not read {path.name}: {exc}") from exc
    text = (
        raw.decode("utf-16")
        if raw.startswith((b"\xff\xfe", b"\xfe\xff"))
        else raw.decode("utf-8-sig", "replace")
    )

    lines = text.splitlines()
    headers = _section(lines, "Column")
    if not headers:
        raise AleError(f"{path.name} has no Column section")
    columns = [name.strip().casefold() for name in headers[0].split("\t")]
    if NAME_COLUMN.casefold() not in columns:
        raise AleError(f"{path.name} has no {NAME_COLUMN!r} column")
    position = columns.index(NAME_COLUMN.casefold())

    names: list[str] = []
    for line in _section(lines, "Data"):
        cells = line.split("\t")
        name = cells[position].strip() if position < len(cells) else ""
        if not name:
            raise AleError(f"{path.name} has a data row with no {NAME_COLUMN}")
        names.append(name)
    return names


def _section(lines: list[str], title: str) -> list[str]:
    """The non-empty lines after a section title, up to the next title."""
    titles = {"heading", "column", "data"}
    found: list[str] = []
    inside = False
    for line in lines:
        if line.strip().casefold() in titles:
            inside = line.strip().casefold() == title.casefold()
            continue
        if inside and line.strip():
            found.append(line)
    return found
