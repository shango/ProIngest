"""A colour session's exports, built at test time rather than committed.

COLOR_AND_FORMAT section 1 specifies what the session exports, and since 2026-09-28 (user)
that is one AMF per EDL event, naming the input transform, the looks and the output
transform, and a CLF per corrector node. `make_clf` and `make_amf` write both in the shape
turnover097's Resolve export has.
"""

from __future__ import annotations

from pathlib import Path

from proingest.core import clf, color

SOURCE_ENCODING = "ACEScct"
"""What a fixture clip is taken to be encoded in, as its AMF names it.

ACEScct because that is what every test rendered through before the encoding became a
per clip fact, so the numbers in the render tests did not move when it did.
"""

DISPLAY = "sRGB - Display"
VIEW = "ACES 2.0 - SDR 100 nits (Rec.709)"
"""The fixture AMFs' output transform: sRGB, which is what every view test was written
against before the display came from the AMF (2026-09-28)."""

URN = "urn:ampas:aces:transformId:v2.0:"
OUTPUT_ID = URN + "Output.Academy.Rec709-D65_100nit_in_Rec709-D65_sRGB-Piecewise.a2.v1"
GAMUT_COMPRESS_ID = URN + "Look.Academy.ReferenceGamutCompress.a2.v1"

UNGRADED = clf.ShotColor(source_encoding=SOURCE_ENCODING, display=DISPLAY, view=VIEW)
"""The chain a row with no look renders through: the source encoding to ACEScg."""


def input_id(space: str) -> str:
    """The AMF input transform ID the config lists for `space`: its `..._to_ACES` one."""
    listed = color.config().getColorSpace(space).getInterchangeAttribute("amf_transform_ids")
    return next(line for line in str(listed).splitlines() if "_to_ACES" in line)


def make_clf(path: Path, gain: float = 1.1) -> Path:
    """A CLF that takes ACES2065-1 in and gives it back, as Resolve's do: here a plain gain,
    so a test can predict what it does to a pixel."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"""<?xml version='1.0' encoding='UTF-8'?>
<ProcessList xmlns="urn:AMPAS:CLF:v3.0" id="urn:uuid:fixture" compCLFversion="3.0" name="LMT: {path.stem}">
 <InputDescriptor>Academy Color Encoding Specification (ACES2065-1)</InputDescriptor>
 <OutputDescriptor>Academy Color Encoding Specification (ACES2065-1)</OutputDescriptor>
 <Matrix inBitDepth="32f" outBitDepth="32f">
  <Array dim="3 3">{gain} 0 0
0 {gain} 0
0 0 {gain}
</Array>
 </Matrix>
</ProcessList>
""",
        encoding="utf-8",
    )
    return path


def make_amf(
    folder: Path,
    event: int,
    clip_file: str,
    *,
    source_encoding: str | None = SOURCE_ENCODING,
    clfs: list[str] | None = None,
    preset: str = "VFX Request",
    output_id: str = OUTPUT_ID,
) -> Path:
    """One AMF for EDL event `event` (1-based), named the way Resolve names it.

    `clfs` are file names in `folder`, which a test writes with `make_clf`; the md5 the AMF
    records is left out, which the reader allows.
    """
    folder.mkdir(parents=True, exist_ok=True)
    stem = Path(clip_file).stem
    path = folder / f"Test_turnover001_{preset.replace(' ', '')}_{stem}_{event - 1}_2026-09-28_180306Z.amf"
    source = (
        f'<aces:inputTransform applied="false"><aces:transformId>{input_id(source_encoding)}'
        "</aces:transformId></aces:inputTransform>"
        if source_encoding
        else ""
    )
    looks = "".join(
        f'<aces:lookTransform applied="false"><aces:file>{name}</aces:file></aces:lookTransform>'
        for name in clfs or []
    )
    path.write_text(
        f"""<?xml version="1.0" encoding="UTF-8"?>
<aces:acesMetadataFile version="2.0" xmlns:aces="urn:ampas:aces:amf:v2.0">
<aces:amfInfo>
<aces:description>Test, turnover001, {preset}, Exported by DaVinci Resolve</aces:description>
</aces:amfInfo>
<aces:clipId><aces:clipName>{stem}</aces:clipName><aces:file>{clip_file}</aces:file></aces:clipId>
<aces:pipeline>
{source}
<aces:lookTransform applied="false">
<aces:transformId>{GAMUT_COMPRESS_ID}</aces:transformId>
</aces:lookTransform>
<aces:workingLocation/>
{looks}
<aces:outputTransform applied="false"><aces:transformId>{output_id}</aces:transformId></aces:outputTransform>
</aces:pipeline>
</aces:acesMetadataFile>
""",
        encoding="utf-8",
    )
    return path
