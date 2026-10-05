"""Ben's per-clip AMF: which input transform, which looks, which output transform.

COLOR_AND_FORMAT section 1. Since 2026-09-28 (user) the colour of a turnover is carried
by one ACES Metadata File per EDL event, exported from Ben's Resolve session, and the CLF
files each one names. The EDL is the cut and the CSV is the identity; neither carries
colour any more. An AMF is Academy S-2019-001 XML:

    clipId            the file the clip is, or the sequence pattern of an EXR sequence
    inputTransform    a transform ID: the camera encoding to ACES2065-1
    lookTransform...  in order: a transform ID (the Reference Gamut Compress) or a CLF
    outputTransform   a transform ID: ACES to the display the session was viewed on

**The IDs are resolved through the pinned config and nothing else.** The config lists,
per colour space, look and view transform, the AMF transform IDs it implements
(`interchange: amf_transform_ids`), so the answer is the config's own and there is no
table here to go stale. An ID the config does not list resolves to None, and the rule
that reads it says so (QC-047 for an input, QC-077 for a look, QC-079 for an output).

**Which event an AMF belongs to is in its file name**: Resolve's export appends the
timeline item's index, the event's place among the EDL's video events from 0
(`clf.ConformEvent.position`). In turnover097 that was the event number less one for all
fifteen files (verified 2026-09-28), but only because it had no audio-only events:
turnover134's EDL numbers three of its own (002, 010, 018) and its 21 AMFs count video
clips only (verified 2026-10-05). The AMF carries no timecode, so that index is the only
thing that tells two uses of one clip apart; the clip it names is checked as well.

Parsed with `xml.etree`, matching on local names, because the namespace carries the AMF
version and a v1 file names its elements the same way.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from proingest.core import color

SUFFIX = ".amf"

_INDEX = re.compile(r"_(\d+)_\d{4}-\d{2}-\d{2}_\d{6}Z$")
"""The timeline index Resolve writes before the export's timestamp:
`..._C4261_1_2026-09-28_180306Z.amf` is index 1, the second video event."""

_PRESET = re.compile(r",\s*([^,]*Request)\s*,", re.IGNORECASE)
"""The export preset in `amfInfo/description`: `Tool Test2, turnover097, Dailies Request,
Exported by DaVinci Resolve`."""

DAILIES_PRESET = "Dailies Request"


class AmfError(RuntimeError):
    """An AMF that is not XML, or not an AMF. Reported as QC-075."""


@dataclass(frozen=True)
class AmfCdl:
    """An ASC CDL written inside the AMF, and the working space it is applied in."""

    slope: tuple[float, float, float]
    offset: tuple[float, float, float]
    power: tuple[float, float, float]
    saturation: float
    working: str
    """`toCdlWorkingSpace`'s transform ID, empty when the AMF states none."""


@dataclass(frozen=True)
class AmfLook:
    """One `lookTransform`, in pipeline order. Exactly one of the four is set."""

    transform_id: str = ""
    """A look named by ID, which the config resolves: the Reference Gamut Compress."""

    file: str = ""
    """A CLF beside the AMF, by file name: one corrector node of the grade."""

    cdl: AmfCdl | None = None
    """An embedded CDL: the grade only when the AMF names no CLF (QC-082, user 2026-10-05)."""

    unsupported: str = ""
    """What the look was when it is none of these. Ignored, QC-077."""

    md5: str = ""
    """The checksum the AMF records for `file`, empty when it records none."""

    applied: bool = False
    """Already baked into the media, so not applied again."""


@dataclass(frozen=True)
class Amf:
    """One AMF as written, before anything is resolved."""

    path: Path
    index: int | None
    """The timeline index from the file name, or None when the name carries none."""

    preset: str
    """`Dailies Request`, `VFX Request` or empty, from the description."""

    clip_file: str
    """The file the clip is, or an EXR sequence's pattern (`DALU0012_pl01_##_HDRI.exr`)."""

    sequence_range: tuple[int, int] | None
    """A sequence pattern's first and last frame, None for a single file."""

    input_transform: str
    input_applied: bool
    looks: tuple[AmfLook, ...]
    output_transform: str

    def names(self, file_name: str) -> bool:
        """Whether this AMF is about `file_name`, compared without case.

        A sequence pattern names every file its `#` run can stand for inside its range;
        `DALU0012_pl01_##_HDRI.exr` over 2..2 names `DALU0012_pl01_02_HDRI.exr`.
        """
        if self.sequence_range is None:
            return self.clip_file.casefold() == file_name.casefold()
        match = re.fullmatch(_pattern(self.clip_file), file_name, re.IGNORECASE)
        return match is not None and self.sequence_range[0] <= int(match.group(1)) <= self.sequence_range[1]


def _pattern(sequence: str) -> str:
    head, run, tail = re.split(r"(#+)", sequence, maxsplit=1)
    return f"{re.escape(head)}(\\d{{{len(run)}}}){re.escape(tail)}"


def read(path: Path) -> Amf:
    """Parse one AMF. Raises `AmfError` for a file that is not one."""
    try:
        root = ET.parse(path).getroot()
    except (ET.ParseError, OSError) as exc:
        raise AmfError(f"{path.name} is not readable XML: {exc}") from exc
    if _local(root.tag) != "acesMetadataFile":
        raise AmfError(f"{path.name} is not an ACES Metadata File")
    clip = _child(root, "clipId")
    pipeline = _child(root, "pipeline")
    if pipeline is None:
        raise AmfError(f"{path.name} has no pipeline")
    clip_file, sequence_range = _clip(clip)
    source = _child(pipeline, "inputTransform")
    output = _child(pipeline, "outputTransform")
    return Amf(
        path=path,
        index=_index_of(path),
        preset=_preset(root),
        clip_file=clip_file,
        sequence_range=sequence_range,
        input_transform=_text(source, "transformId"),
        input_applied=_applied(source),
        looks=tuple(_look(item) for item in pipeline if _local(item.tag) == "lookTransform"),
        output_transform=_text(output, "transformId"),
    )


def _index_of(path: Path) -> int | None:
    match = _INDEX.search(path.stem)
    return int(match.group(1)) if match else None


def _preset(root: ET.Element) -> str:
    match = _PRESET.search(_text(_child(root, "amfInfo"), "description"))
    return match.group(1).strip() if match else ""


def _clip(clip: ET.Element | None) -> tuple[str, tuple[int, int] | None]:
    if clip is None:
        return "", None
    sequence = _child(clip, "sequence")
    if sequence is not None and sequence.text:
        first, last = sequence.get("min"), sequence.get("max")
        span = (int(first), int(last)) if first and last and first.isdigit() and last.isdigit() else None
        return sequence.text.strip(), span
    return _text(clip, "file"), None


def _look(item: ET.Element) -> AmfLook:
    applied = _applied(item)
    transform_id = _text(item, "transformId")
    if transform_id:
        return AmfLook(transform_id=transform_id, applied=applied)
    file = _text(item, "file")
    if file:
        return AmfLook(file=file, md5=_text(item, "hash").lower(), applied=applied)
    cdl = _cdl(item)
    if cdl is not None:
        return AmfLook(cdl=cdl, applied=applied)
    inner = [_local(child.tag) for child in item]
    return AmfLook(unsupported=", ".join(inner) or "an empty look", applied=applied)


def _cdl(item: ET.Element) -> AmfCdl | None:
    """`cdl:ASC_SOP` and `cdl:ASC_SAT` under the look, as Resolve writes them, or None."""
    sop = _child(item, "ASC_SOP")
    if sop is None:
        return None
    try:
        slope, offset, power = (_three(_text(sop, name)) for name in ("Slope", "Offset", "Power"))
        saturation = float(_text(_child(item, "ASC_SAT"), "Saturation") or 1)
    except ValueError:
        return None
    working = _text(_child(_child(item, "cdlWorkingSpace"), "toCdlWorkingSpace"), "transformId")
    return AmfCdl(slope, offset, power, saturation, working)


def _three(text: str) -> tuple[float, float, float]:
    first, second, third = (float(value) for value in text.split())
    return first, second, third


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _child(element: ET.Element | None, name: str) -> ET.Element | None:
    if element is None:
        return None
    return next((child for child in element if _local(child.tag) == name), None)


def _text(element: ET.Element | None, name: str) -> str:
    child = _child(element, name)
    return (child.text or "").strip() if child is not None else ""


def _applied(element: ET.Element | None) -> bool:
    return element is not None and (element.get("applied") or "").strip().lower() == "true"


# --- The config's own answer for an ID. ---


@dataclass(frozen=True)
class _Index:
    colour_spaces: dict[str, str]
    looks: dict[str, str]
    view_transforms: dict[str, str]


@lru_cache(maxsize=1)
def _index() -> _Index:
    """Every AMF transform ID the pinned config lists, to what lists it. Built once."""
    config = color.config()

    def ids(item: object) -> list[str]:
        text = item.getInterchangeAttribute("amf_transform_ids")  # type: ignore[attr-defined]
        return [line.strip() for line in str(text or "").splitlines() if line.strip()]

    spaces = {urn: space.getName() for space in config.getColorSpaces() for urn in ids(space)}
    looks = {urn: look.getName() for look in config.getLooks() for urn in ids(look)}
    views = {urn: view.getName() for view in config.getViewTransforms() for urn in ids(view)}
    return _Index(spaces, looks, views)


def colour_space_for(transform_id: str) -> str | None:
    """The config colour space an input transform ID converts from, or None."""
    return _index().colour_spaces.get(transform_id)


def look_for(transform_id: str) -> str | None:
    """The config look a look transform ID is, or None."""
    return _index().looks.get(transform_id)


def display_view_for(transform_id: str) -> tuple[str, str] | None:
    """The config display and view an output transform ID renders to, or None.

    The config lists an ACES 2.0 output ID twice: on the display colour space it encodes
    for and on the view transform that tone maps to it. The display is the one whose
    colour space that is, and the view is the view on that display built from that view
    transform, so both halves come from the config rather than from reading the ID.
    """
    index = _index()
    display = index.colour_spaces.get(transform_id)
    view_transform = index.view_transforms.get(transform_id)
    config = color.config()
    if display is None or view_transform is None or display not in config.getDisplays():
        return None
    for view in config.getViews(display):
        if config.getDisplayViewTransformName(display, view) == view_transform:
            return display, view
    return None
