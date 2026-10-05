"""`core/amf.py`: reading an AMF, and resolving its IDs through the pinned config.

The AMFs are written here, shaped exactly like turnover097's (Resolve 20, Dailies Request
preset, 2026-09-28), rather than copied from it: the folder is not committed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from proingest.core import amf

URN = "urn:ampas:aces:transformId:v2.0:"
SLOG3 = URN + "CSC.Sony.SLog3_SGamut3Cine_to_ACES.a2.v1"
RGC = URN + "Look.Academy.ReferenceGamutCompress.a2.v1"
GAMMA22 = URN + "Output.Academy.Rec709-D65_100nit_in_Rec709-D65_Gamma2pt2.a2.v1"
NAME = "Tool_Test2_turnover097_DailiesRequest_C4261_1_2026-09-28_180306Z.amf"


def written(
    folder: Path,
    *,
    name: str = NAME,
    clip: str = "<aces:file>C4261.MP4</aces:file>",
    source: str = (
        f'<aces:inputTransform applied="false"><aces:transformId>{SLOG3}</aces:transformId>'
        "</aces:inputTransform>"
    ),
    looks: str = "",
    description: str = "Tool Test2, turnover097, Dailies Request, Exported by DaVinci Resolve",
) -> Path:
    path = folder / name
    path.write_text(
        f"""<?xml version="1.0" encoding="UTF-8"?>
<aces:acesMetadataFile version="2.0" xmlns:aces="urn:ampas:aces:amf:v2.0">
    <aces:amfInfo><aces:description>{description}</aces:description></aces:amfInfo>
    <aces:clipId><aces:clipName>C4261</aces:clipName>{clip}</aces:clipId>
    <aces:pipeline>
        {source}
        <aces:lookTransform applied="false"><aces:transformId>{RGC}</aces:transformId></aces:lookTransform>
        <aces:workingLocation/>
        {looks}
        <aces:outputTransform applied="false">
            <aces:transformId>{GAMMA22}</aces:transformId>
        </aces:outputTransform>
    </aces:pipeline>
</aces:acesMetadataFile>
""",
        encoding="utf-8",
    )
    return path


CLF_LOOK = (
    '<aces:lookTransform applied="false"><aces:hash algorithm="md5">A4BC</aces:hash>'
    "<aces:file>C4261_1_ClipGraph_CorrectorNode_1.clf</aces:file></aces:lookTransform>"
)


class TestReading:
    def test_what_turnover097_s_amf_says(self, tmp_path: Path) -> None:
        read = amf.read(written(tmp_path, looks=CLF_LOOK))
        assert (read.index, read.preset, read.clip_file) == (1, "Dailies Request", "C4261.MP4")
        assert read.input_transform == SLOG3 and not read.input_applied
        assert [(look.transform_id, look.file, look.md5) for look in read.looks] == [
            (RGC, "", ""),
            ("", "C4261_1_ClipGraph_CorrectorNode_1.clf", "a4bc"),
        ]
        assert read.output_transform == GAMMA22

    def test_the_index_is_the_one_before_the_timestamp(self, tmp_path: Path) -> None:
        """`DALU0012_pl01_02_02_7`: the clip name is full of numbers, the index is the last."""
        name = "Tool_Test2_turnover097_DailiesRequest_DALU0012_pl01_02_02_7_2026-09-28_180306Z.amf"
        assert amf.read(written(tmp_path, name=name)).index == 7

    def test_a_name_with_no_index_says_so(self, tmp_path: Path) -> None:
        assert amf.read(written(tmp_path, name="C4261.amf")).index is None

    def test_an_hdri_amf_has_no_input_transform_and_names_a_sequence(self, tmp_path: Path) -> None:
        sequence = '<aces:sequence min="2" max="2" idx="#">DALU0012_pl01_##_HDRI.exr</aces:sequence>'
        read = amf.read(written(tmp_path, clip=sequence, source=""))
        assert read.input_transform == ""
        assert read.names("DALU0012_pl01_02_HDRI.exr")
        assert not read.names("DALU0012_pl01_03_HDRI.exr"), "outside its range"
        assert not read.names("C4261.MP4")

    def test_a_single_file_is_named_without_case(self, tmp_path: Path) -> None:
        read = amf.read(written(tmp_path))
        assert read.names("c4261.mp4") and not read.names("C4262.MP4")

    def test_an_embedded_cdl_is_carried_as_unsupported(self, tmp_path: Path) -> None:
        """Anything neither an ID nor a CLF: ignored with a warning (user, 2026-09-28)."""
        embedded = (
            '<aces:lookTransform applied="false">'
            '<cdl:ColorCorrection xmlns:cdl="urn:ASC:CDL:v1.01"/></aces:lookTransform>'
        )
        read = amf.read(written(tmp_path, looks=embedded))
        assert read.looks[-1].unsupported == "ColorCorrection"

    def test_an_applied_look_says_so(self, tmp_path: Path) -> None:
        baked = CLF_LOOK.replace('applied="false"', 'applied="true"')
        assert amf.read(written(tmp_path, looks=baked)).looks[-1].applied

    def test_the_vfx_preset_is_read_too(self, tmp_path: Path) -> None:
        read = amf.read(
            written(tmp_path, description="Show, turnover098, VFX Request, Exported by DaVinci Resolve")
        )
        assert read.preset == "VFX Request"

    @pytest.mark.parametrize("text", ["not xml at all", "<?xml version='1.0'?><ProcessList/>"])
    def test_a_file_that_is_not_an_amf_raises(self, tmp_path: Path, text: str) -> None:
        path = tmp_path / NAME
        path.write_text(text, encoding="utf-8")
        with pytest.raises(amf.AmfError):
            amf.read(path)


class TestResolvingThroughTheConfig:
    """The pinned config's `amf_transform_ids`, verified against turnover097 (2026-09-28)."""

    def test_the_sony_input_transform(self) -> None:
        assert amf.colour_space_for(SLOG3) == "S-Log3 S-Gamut3.Cine"

    def test_the_reference_gamut_compress(self) -> None:
        assert amf.look_for(RGC) == "ACES 1.3 Reference Gamut Compression"

    def test_the_output_transform_is_a_display_and_a_view(self) -> None:
        assert amf.display_view_for(GAMMA22) == (
            "Gamma 2.2 Rec.709 - Display",
            "ACES 2.0 - SDR 100 nits (Rec.709)",
        )

    @pytest.mark.parametrize("lookup", [amf.colour_space_for, amf.look_for, amf.display_view_for])
    def test_an_id_the_config_does_not_list_is_none(self, lookup: object) -> None:
        assert lookup(URN + "IDT.Unknown.Camera.a1.v1") is None  # type: ignore[operator]
