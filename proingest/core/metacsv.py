"""Ben's metadata CSV: the only carrier of identity.

Resolve writes it from the Media Pool and it sits in the turnover folder beside the
media and the EDL (docs/WORKFLOW.md). One thing reaches the tool through this file and
through nothing else: **which shot and which clip type each file is** (`Shot` and
`Shot Type`). The EDL carries the cut and each clip's AMF carries its colour; since
2026-09-28 (user) the CSV's colour columns are not read.

Three properties of the real file drive the whole module, all measured in
docs/SAMPLE_TURNOVER_199.md sections 7 and 8:

**`Shot Type` appears twice.** Position 12 is Resolve's built-in field, position 44 is
a custom field the shooters created with the same name. `csv.DictReader` silently keeps
the last duplicate, which is why this module uses `csv.reader` and arbitrates the
collision by hand (QC-065). The built-in is a *framing* field whose intended values are
`Wide` and the like, so a shooter using it as designed puts `Wide` in one and `pl01` in
the other, and picking by position would be picking by luck.

**Columns are dynamic.** Resolve writes a column only when some clip has a value for it,
so an absent column is the ordinary way a field is empty rather than a malformed file.
Nothing here requires a column except `File Name`, which is the key.

**Every duration, frame count and path in it is stale.** In the real sample `Frames`
reads 516 / 168 / 312 / 420 / 360 against delivered files of 280 / 49 / 49 / 49 / 248,
and `Clip Directory` points at the pre-consolidation originals. Resolve exported them
before Copy with trim and did not revisit them. **So this module reads identity and
nothing else**: ffprobe is the authority on every media fact, and a reader
that helpfully returned `Frames` would be handing out numbers that are wrong by up to
eight times.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field, replace
from pathlib import Path

from proingest.core import naming
from proingest.core.models import QCResult

FILE_NAME_COLUMN = "File Name"
SHOT_COLUMN = "Shot"
SHOT_TYPE_COLUMN = "Shot Type"
SCENE_COLUMN = "Scene"
TAKE_COLUMN = "Take"
"""The clip's take, burned into the stringout after its label when above 1 (user, 2026-10-07)."""
START_TC_COLUMN = "Start TC"
"""Where the clip starts as Resolve has it, which the EDL's source timecodes count from.
After media management it can differ from the file's own (QC-084, user 2026-10-07)."""
"""Burned into the stringout as its Primary Effect, as Ben's Resolve template does (2026-09-25)."""

CSV_SUFFIX = ".csv"


class MetaCsvError(Exception):
    """The file is not a metadata CSV this tool can read at all (QC-002)."""


@dataclass(frozen=True)
class MetaRow:
    """One clip, as the CSV describes it.

    `kind` and `index` are None on a row that named a `Shot Type` nothing resolves to;
    the row still exists, carrying QC-010, because a half-filled row is the one a person
    can fix and a row that vanished is one nobody knows to look at.
    """

    file_name: str
    shot: str
    shot_type: str
    kind: str | None
    index: str | None
    scene: str = ""
    qc: tuple[QCResult, ...] = ()
    start_tc: str = ""
    take: str = ""
    hdri: bool = False
    """An HDRI (QC-080): the tool copies its EXR as it is and runs no row rule on it, and
    the stringout shows Ben's pre-render of its timeline event (user, 2026-10-07)."""


@dataclass
class MetaCsv:
    """What one metadata CSV says."""

    path: Path
    rows: list[MetaRow] = field(default_factory=list)
    """Rows carrying a `Shot Type`, resolved or not. These become shot rows."""

    ignored: list[str] = field(default_factory=list)
    """`File Name` of every clip with no `Shot Type` at all. The scan counts these into
    QC-064 at turnover scope: ignoring such a clip is the intended behaviour, and a whole
    turnover ignored is what wants saying out loud."""

    qc: list[QCResult] = field(default_factory=list)
    """Turnover-scope findings about the file itself."""


def _decode(raw: bytes) -> str:
    """Resolve writes UTF-16 with a BOM. Accept UTF-8 too rather than insist."""
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16")
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise MetaCsvError(f"not UTF-16 or UTF-8: {exc}") from exc


def _columns(header: list[str], name: str) -> list[int]:
    """Every position carrying this column name, in file order.

    A list rather than an index because of `Shot Type`, and by the same argument for
    every other column: nothing guarantees the shooters' custom field set collides only
    where we have already seen it collide.
    """
    return [i for i, column in enumerate(header) if column.strip().casefold() == name.casefold()]


def _value(row: list[str], positions: list[int]) -> str:
    """The first non-empty value across these positions."""
    for i in positions:
        if i < len(row) and row[i].strip():
            return row[i].strip()
    return ""


def _resolve_shot_type(
    row: list[str], positions: list[int], file_name: str
) -> tuple[str, str | None, str | None, list[QCResult]]:
    """Arbitrate the duplicate `Shot Type` column (QC-065).

    Take the column that resolves to a known clip type; where both resolve, prefer the
    **later** one, because Resolve writes its own fields before the custom set and the
    built-in is the framing field. Warn only when both resolve and disagree: one
    resolving and one not is the normal shape of a shooter using both fields as intended.
    """
    written = [(i, row[i].strip()) for i in positions if i < len(row) and row[i].strip()]
    resolved = [
        (i, value, parsed) for i, value in written for parsed in [naming.parse_shot_type(value)] if parsed
    ]

    if not resolved:
        return (written[-1][1] if written else ""), None, None, []

    _, value, (kind, index) = resolved[-1]
    qc: list[QCResult] = []
    distinct = {parsed for _, _, parsed in resolved}
    if len(distinct) > 1:
        names = ", ".join(sorted(f"{v!r}" for _, v, _ in resolved))
        qc.append(
            QCResult(
                "QC-065",
                "error",
                "row",
                f"{file_name} carries {len(resolved)} Shot Type columns that resolve differently "
                f"({names}); using {value!r} from the last of them, which is the shooters' custom field",
            )
        )
    return value, kind, index, qc


def _shot(typed: str, show_pattern: str) -> str:
    """The `Shot` value, upper cased when that is the only way it reads as a shot code.

    `test0002` under the default pattern is a typo of `TEST0002`, not another shot (F27).
    Only when the typed value does not parse and the upper case one does, so a custom
    pattern written in lower case keeps working.
    """
    if naming.parse_shot_code(typed, show_pattern) is None and naming.parse_shot_code(
        typed.upper(), show_pattern
    ):
        return typed.upper()
    return typed


def _row_qc(file_name: str, shot: str, shot_type: str, kind: str | None, show_pattern: str) -> list[QCResult]:
    """QC-010: the half-filled row.

    A row with no `Shot Type` never gets here - it is ignored and counted by QC-064. What
    this catches is a row that says it is a deliverable and then cannot be named: a
    `Shot Type` nothing resolves to, or a blank or malformed `Shot`.
    """
    if kind is None:
        return [
            QCResult(
                "QC-010",
                "error",
                "row",
                f"{file_name} has Shot Type {shot_type!r}, which is not a clip type the tool "
                f"delivers ({', '.join(naming.CLIP_TYPES)})",
            )
        ]
    if not shot:
        return [QCResult("QC-010", "error", "row", f"{file_name} has Shot Type {shot_type!r} but no Shot")]
    if naming.parse_shot_code(shot, show_pattern) is None:
        return [
            QCResult(
                "QC-010",
                "error",
                "row",
                f"{file_name} has Shot {shot!r}, which is not a shot code matching {show_pattern}NNNN",
            )
        ]
    return []


def read(path: Path, show_pattern: str = naming.DEFAULT_SHOW_PATTERN) -> MetaCsv:
    """Read one metadata CSV.

    Raises `MetaCsvError` only when the file is not readable as this kind of CSV at all,
    which the scan turns into QC-002. Everything a person could fix comes back as QC on
    the row or on the turnover, because a turnover that refuses to open tells the editor
    less than one that opens and says what is wrong with it.
    """
    try:
        text = _decode(path.read_bytes())
    except OSError as exc:
        raise MetaCsvError(str(exc)) from exc

    records = [row for row in csv.reader(io.StringIO(text)) if any(cell.strip() for cell in row)]
    if not records:
        raise MetaCsvError("the file is empty")

    header = records[0]
    name_positions = _columns(header, FILE_NAME_COLUMN)
    if not name_positions:
        raise MetaCsvError(f"no {FILE_NAME_COLUMN!r} column, so no row can be matched to a file")

    shot_positions = _columns(header, SHOT_COLUMN)
    type_positions = _columns(header, SHOT_TYPE_COLUMN)
    scene_positions = _columns(header, SCENE_COLUMN)
    start_positions = _columns(header, START_TC_COLUMN)
    take_positions = _columns(header, TAKE_COLUMN)

    result = MetaCsv(path=path)
    for record in records[1:]:
        file_name = _value(record, name_positions)
        if not file_name:
            continue
        shot_type, kind, index, type_qc = _resolve_shot_type(record, type_positions, file_name)
        if not shot_type:
            result.ignored.append(file_name)
            continue
        shot = _shot(_value(record, shot_positions), show_pattern)
        scene = _value(record, scene_positions)
        if _HDRI.fullmatch(shot_type.strip()):
            named = naming.parse_shot_code(shot, show_pattern) is not None
            hdri = _hdri(file_name, shot, shot_type, scene, named)
            result.rows.append(replace(hdri, take=_value(record, take_positions)))
            continue
        if _STYLE_FRAME.fullmatch(shot_type.strip()):
            named = naming.parse_shot_code(shot, show_pattern) is not None
            result.rows.append(_style_frame(file_name, shot, shot_type, scene, named))
            continue
        result.rows.append(
            MetaRow(
                file_name=file_name,
                shot=shot,
                shot_type=shot_type,
                kind=kind,
                index=index,
                scene=scene,
                start_tc=_value(record, start_positions),
                take=_value(record, take_positions),
                qc=tuple(type_qc + _row_qc(file_name, shot, shot_type, kind, show_pattern)),
            )
        )
    return result


_HDRI = re.compile(r"hdri(?P<index>\d{1,2})?", re.IGNORECASE)
"""`HDRI`, as turnover097's CSV writes it, with or without an index."""


def _hdri(file_name: str, shot: str, shot_type: str, scene: str, named: bool) -> MetaRow:
    """An HDRI row (user, 2026-10-07): its EXR is delivered as it is, with no checks, and
    the stringout shows the pre-render of its timeline event. One whose `Shot` is no shot
    code has nowhere to be delivered, and only the stringout shows it."""
    note = QCResult(
        "QC-080",
        "info",
        "row",
        f"{file_name} is an HDRI: the tool delivers it as it is, with no checks, and the "
        "stringout shows its pre-render",
    )
    match = _HDRI.fullmatch(shot_type.strip())
    index = ((match["index"] if match else None) or "1").zfill(2)
    kind = naming.HDRI_KIND if named else None
    return MetaRow(file_name, shot, shot_type, kind, index if named else None, scene, (note,), hdri=True)


_STYLE_FRAME = re.compile(r"styleframe(?P<index>\d{1,2})?", re.IGNORECASE)


def _style_frame(file_name: str, shot: str, shot_type: str, scene: str, named: bool) -> MetaRow:
    """A style frame row (QC-085, user 2026-10-07): a pre-graded still the stringout holds
    before its shot's plate, as it is. Nothing is delivered and no check runs on it."""
    note = QCResult(
        "QC-085",
        "info",
        "row",
        f"{file_name} is a style frame: the stringout shows it as it is, and nothing is delivered",
    )
    match = _STYLE_FRAME.fullmatch(shot_type.strip())
    index = ((match["index"] if match else None) or "1").zfill(2)
    kind = naming.STYLE_FRAME_KIND if named else None
    return MetaRow(file_name, shot, shot_type, kind, index if named else None, scene, (note,))


def find(folder: Path) -> list[Path]:
    """Every CSV directly in the turnover folder.

    Not recursive, and the caller decides what more than one means: the handover is one
    folder holding the media, one EDL and one CSV (OQ-74), so a second CSV is a question
    rather than something to pick between.
    """
    return sorted(p for p in folder.iterdir() if p.is_file() and p.suffix.lower() == CSV_SUFFIX)
