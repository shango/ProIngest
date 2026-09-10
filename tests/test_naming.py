"""Golden tests for naming.

Examples come from docs/NAMING_SPEC.md section 3 and from the shooters' spec PDF.
The round-trip tests are what QC-151 relies on.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from proingest.core import naming
from proingest.core.naming import LensGridIdentity, ShotIdentity

PLATE = ShotIdentity(show="MELT", shot="0001", elem_type="pl", elem_index="01")
CLEAN = ShotIdentity(show="MELT", shot="0001", elem_type="cp", elem_index="01")
CHART = ShotIdentity(
    show="MELT", shot="0001", elem_type="pl", elem_index="01", aux="colorChart", aux_index="01"
)
BTS_STILL = ShotIdentity(
    show="MELT", shot="0001", elem_type="pl", elem_index="01", aux="BTS", aux_index="01"
)
LENS_GRID = LensGridIdentity(camera="SonyA7V", lens="Tamron20-40", mm="40")


class TestParseClipName:
    def test_plate(self) -> None:
        assert naming.parse_clip_name("MELT0001_pl01") == PLATE

    @pytest.mark.parametrize("elem_type", naming.ELEMENT_TYPES)
    def test_every_element_type(self, elem_type: str) -> None:
        parsed = naming.parse_clip_name(f"MELT0001_{elem_type}01")
        assert parsed is not None
        assert parsed.elem_type == elem_type

    @pytest.mark.parametrize("aux", naming.AUX_NAMES)
    def test_every_aux_name(self, aux: str) -> None:
        parsed = naming.parse_clip_name(f"MELT0001_pl01_{aux}_01")
        assert parsed is not None
        assert parsed.aux == aux
        assert parsed.aux_index == "01"

    def test_bts_is_an_aux_clip(self) -> None:
        assert naming.parse_clip_name("MELT0001_pl01_BTS_01") == BTS_STILL

    def test_derived_properties(self) -> None:
        assert PLATE.shot_code == "MELT0001"
        assert PLATE.elem == "pl01"
        assert PLATE.stem == "MELT0001_pl01"

    @pytest.mark.parametrize(
        "name",
        [
            "",
            "MELT0001",  # no element
            "melt0001_pl01",  # show must be upper case
            "MELT001_pl01",  # shot is exactly four digits
            "MELT00001_pl01",
            "MELT0001_xx01",  # unknown type
            "MELT0001_pl1",  # index is exactly two digits
            "MELT0001_pl01_extra",
            "MELT0001_pl01_colorChart",  # aux needs an index
            "MELT0001_pl01_bogus_01",
            "M0001_pl01",  # show is at least two characters
            "TOOLONGSHOW0001_pl01",
            " MELT0001_pl01",
            "MELT0001_pl01 ",
        ],
    )
    def test_rejects_invalid(self, name: str) -> None:
        assert naming.parse_clip_name(name) is None

    def test_configurable_show_pattern(self) -> None:
        assert naming.parse_clip_name("XY0001_pl01", show_pattern=r"[A-Z]{2}") is not None
        assert naming.parse_clip_name("MELT0001_pl01", show_pattern=r"[A-Z]{2}") is None


class TestParseShotCode:
    """A shot code the editor corrected has to split back into show and number."""

    def test_splits_show_and_number(self) -> None:
        assert naming.parse_shot_code("MELT0001") == ("MELT", "0001")

    def test_leading_zeros_survive(self) -> None:
        parsed = naming.parse_shot_code("AB0007")
        assert parsed is not None and parsed[1] == "0007"

    @pytest.mark.parametrize("code", ["MELT001", "melt0001", "MELT0001_pl01", "0001", ""])
    def test_rejects_anything_else(self, code: str) -> None:
        assert naming.parse_shot_code(code) is None

    def test_honours_the_configured_show_pattern(self) -> None:
        assert naming.parse_shot_code("MELT0001", show_pattern=r"[A-Z]{2}") is None


class TestParseLensGridName:
    def test_example_from_spec(self) -> None:
        assert naming.parse_lens_grid_name("SonyA7V_Tamron20-40_lensgrid_40mm") == LENS_GRID

    @pytest.mark.parametrize(
        "name", ["SonyA7V_lensgrid_40mm", "SonyA7V_Tamron20-40_lensgrid_40", "MELT0001_pl01"]
    )
    def test_rejects_invalid(self, name: str) -> None:
        assert naming.parse_lens_grid_name(name) is None


class TestBuildNames:
    """Every example in NAMING_SPEC.md section 3, verbatim."""

    def test_raw_frame(self) -> None:
        assert naming.raw_frame(PLATE, "4k", 1, 1001) == "MELT0001_pl01_raw_4k_v01.1001.exr"

    def test_frame_in_sequence_names_a_frame_from_its_folder(self) -> None:
        folder = naming.raw_sequence_dir(PLATE, "HD", 2)
        assert naming.frame_in_sequence(folder, 1234) == "MELT0001_pl01_raw_HD_v02.1234.exr"

    def test_raw_sequence_dir(self) -> None:
        assert naming.raw_sequence_dir(PLATE, "4k", 1) == "MELT0001_pl01_raw_4k_v01"

    def test_ref_mp4(self) -> None:
        assert naming.ref_mp4(PLATE, "HD", 1) == "MELT0001_pl01_ref_HD_v01.mp4"

    def test_audio(self) -> None:
        assert naming.audio_wav(PLATE, 1) == "MELT0001_pl01_audio_v01.wav"

    def test_hdri(self) -> None:
        assert naming.hdri_exr(PLATE, 1) == "MELT0001_pl01_HDRI_v01.exr"

    def test_camdata(self) -> None:
        assert naming.camdata(PLATE, 1, "rtf") == "MELT0001_pl01_camData_v01.rtf"
        assert naming.camdata(PLATE, 1, ".TXT") == "MELT0001_pl01_camData_v01.txt"

    def test_aux_still(self) -> None:
        assert naming.aux_still_exr(CHART, 1) == "MELT0001_pl01_colorChart_01_4k_v01.exr"

    def test_bts(self) -> None:
        assert naming.bts(BTS_STILL, 1, "png") == "MELT0001_pl01_BTS_01_v01.png"

    @pytest.mark.parametrize("ext", naming.BTS_EXTENSIONS)
    def test_bts_accepts_every_extension_the_pdf_allows(self, ext: str) -> None:
        assert naming.bts(BTS_STILL, 1, ext).endswith(f".{ext}")

    def test_lens_grid(self) -> None:
        expected = "SonyA7V_Tamron20-40_lensgrid_40mm_v01.png"
        assert naming.lens_grid_png(LENS_GRID, 1) == expected

    def test_stringout(self) -> None:
        built = naming.stringout_mp4(1, 2, 23, 2026, "Daniel Luckett", 1)
        assert built == "turnover001_02_23_2026_danielluckett_v01.mp4"

    def test_clean_plate_uses_its_own_element(self) -> None:
        assert naming.raw_sequence_dir(CLEAN, "HD", 3) == "MELT0001_cp01_raw_HD_v03"

    def test_version_is_two_digits(self) -> None:
        assert naming.ref_mp4(PLATE, "4k", 12).endswith("_v12.mp4")

    def test_frame_is_four_digits(self) -> None:
        assert naming.raw_frame(PLATE, "4k", 1, 1240).endswith(".1240.exr")

    def test_rejects_bad_extensions(self) -> None:
        with pytest.raises(ValueError):
            naming.camdata(PLATE, 1, "doc")
        with pytest.raises(ValueError):
            naming.bts(BTS_STILL, 1, "gif")

    def test_aux_still_requires_an_aux(self) -> None:
        with pytest.raises(ValueError):
            naming.aux_still_exr(PLATE, 1)

    def test_aux_still_rejects_bts(self) -> None:
        """BTS is an aux clip but is copied, not written as a 4k exr."""
        with pytest.raises(ValueError):
            naming.aux_still_exr(BTS_STILL, 1)


class TestNormalizeShooter:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("danielluckett", "danielluckett"),
            ("Daniel Luckett", "danielluckett"),
            ("daniel-luckett", "danielluckett"),
            ("Daniel O'Luckett", "danieloluckett"),
            ("  Daniel   Luckett  ", "danielluckett"),
        ],
    )
    def test_normalizes(self, raw: str, expected: str) -> None:
        assert naming.normalize_shooter(raw) == expected

    def test_empty_name_is_rejected(self) -> None:
        with pytest.raises(ValueError):
            naming.stringout_mp4(1, 2, 23, 2026, "!!!", 1)


class TestParseOutputName:
    """QC-151: every deliverable name must read back to what the planner intended."""

    @pytest.mark.parametrize(
        ("name", "kind"),
        [
            ("MELT0001_pl01_raw_4k_v01.1001.exr", "raw_frame"),
            ("MELT0001_pl01_raw_4k_v01", "raw_dir"),
            ("MELT0001_pl01_ref_HD_v01.mp4", "ref_mp4"),
            ("MELT0001_pl01_audio_v01.wav", "audio"),
            ("MELT0001_pl01_HDRI_v01.exr", "hdri"),
            ("MELT0001_pl01_camData_v01.rtf", "camdata"),
            ("MELT0001_pl01_colorChart_01_4k_v01.exr", "aux_still"),
            ("MELT0001_pl01_BTS_01_v01.png", "bts"),
            ("SonyA7V_Tamron20-40_lensgrid_40mm_v01.png", "lensgrid"),
            ("turnover001_02_23_2026_danielluckett_v01.mp4", "stringout"),
        ],
    )
    def test_each_example_parses_to_exactly_one_kind(self, name: str, kind: str) -> None:
        parsed = naming.parse_output_name(name)
        assert parsed is not None
        assert parsed.kind == kind
        assert parsed.version == 1

    @pytest.mark.parametrize(
        "name",
        [
            "MELT0001_pl01_raw_4k_v01.1001.exr",
            "MELT0001_pl01_raw_4k_v01",
            "MELT0001_pl01_ref_HD_v01.mp4",
            "MELT0001_pl01_audio_v01.wav",
            "MELT0001_pl01_HDRI_v01.exr",
            "MELT0001_pl01_camData_v01.rtf",
            "MELT0001_pl01_colorChart_01_4k_v01.exr",
            "MELT0001_pl01_BTS_01_v01.png",
            "SonyA7V_Tamron20-40_lensgrid_40mm_v01.png",
            "turnover001_02_23_2026_danielluckett_v01.mp4",
        ],
    )
    def test_patterns_are_mutually_exclusive(self, name: str) -> None:
        """Section 7 claims a match is unambiguous. Check that directly."""
        matched = [
            kind
            for kind, pattern in naming._output_patterns(naming.DEFAULT_SHOW_PATTERN)
            if pattern.match(name)
        ]
        assert len(matched) == 1, f"{name} matched {matched}"

    def test_raw_frame_fields(self) -> None:
        parsed = naming.parse_output_name("MELT0001_pl01_raw_4k_v01.1001.exr")
        assert parsed is not None
        assert (parsed.shot_code, parsed.elem, parsed.res, parsed.frame) == (
            "MELT0001",
            "pl01",
            "4k",
            1001,
        )

    @pytest.mark.parametrize(
        "name",
        [
            "MELT0001_pl01_raw_4k_v01.part",
            "MELT0001_pl01_ref_HD_v01.mp4.part",
            "MELT0001_pl01_raw_4k_v01.1001.exr.part",
            "notes.txt",
            "MELT0001_pl01_raw_4k.exr",  # no version
            "MELT0001_pl01_raw_8k_v01",  # unknown resolution
            "MELT0001_pl01_BTS_01_v01.gif",
        ],
    )
    def test_rejects_non_deliverables(self, name: str) -> None:
        assert naming.parse_output_name(name) is None


class TestRoundTrip:
    """Build then parse must recover the same shot, elem, kind, res and version."""

    @pytest.mark.parametrize("res", ["4k", "HD"])
    @pytest.mark.parametrize("version", [1, 7, 99])
    def test_raw_dir(self, res: str, version: int) -> None:
        built = naming.raw_sequence_dir(PLATE, res, version)  # type: ignore[arg-type]
        parsed = naming.parse_output_name(built)
        assert parsed is not None
        assert (parsed.kind, parsed.shot_code, parsed.elem, parsed.res, parsed.version) == (
            "raw_dir",
            PLATE.shot_code,
            PLATE.elem,
            res,
            version,
        )

    @pytest.mark.parametrize("elem_type", naming.ELEMENT_TYPES)
    def test_ref_mp4_for_every_element_type(self, elem_type: str) -> None:
        identity = ShotIdentity(show="MELT", shot="0042", elem_type=elem_type, elem_index="02")
        parsed = naming.parse_output_name(naming.ref_mp4(identity, "4k", 5))
        assert parsed is not None
        assert parsed.shot_code == "MELT0042"
        assert parsed.elem == f"{elem_type}02"
        assert parsed.version == 5

    def test_every_output_frame_of_a_sequence(self) -> None:
        duration = 240
        for offset in range(duration):
            frame = naming.FIRST_OUTPUT_FRAME + offset
            parsed = naming.parse_output_name(naming.raw_frame(PLATE, "4k", 1, frame))
            assert parsed is not None
            assert parsed.frame == frame

    @pytest.mark.parametrize("aux", naming.AUX_NAMES)
    def test_aux_still(self, aux: str) -> None:
        identity = ShotIdentity(
            show="MELT", shot="0001", elem_type="pl", elem_index="01", aux=aux, aux_index="03"
        )
        parsed = naming.parse_output_name(naming.aux_still_exr(identity, 2))
        assert parsed is not None
        assert (parsed.kind, parsed.aux, parsed.aux_index, parsed.version) == (
            "aux_still",
            aux,
            "03",
            2,
        )

    def test_stringout(self) -> None:
        built = naming.stringout_mp4(12, 12, 5, 2026, "Ada Lovelace", 3)
        parsed = naming.parse_output_name(built)
        assert parsed is not None
        assert (parsed.kind, parsed.version) == ("stringout", 3)


class TestNextVersion:
    def test_empty_destination_starts_at_one(self) -> None:
        assert naming.next_version([]) == 1

    def test_takes_max_plus_one(self) -> None:
        names = [
            "MELT0001_pl01_raw_4k_v01",
            "MELT0001_pl01_raw_4k_v03",
            "MELT0001_pl01_ref_HD_v02.mp4",
        ]
        assert naming.next_version(names) == 4

    def test_ignores_part_files_and_strays(self) -> None:
        """A .part leftover must never push the version forward."""
        names = ["MELT0001_pl01_raw_4k_v01", "MELT0001_pl01_raw_4k_v09.part", "readme.txt"]
        assert naming.next_version(names) == 2


class TestDeliveryLayout:
    def test_shot_dir(self) -> None:
        assert naming.shot_dir(Path("/d"), PLATE) == Path("/d/MELT/MELT0001")

    def test_turnovers_and_reports_sit_beside_shots(self) -> None:
        assert naming.turnovers_dir(Path("/d"), "MELT") == Path("/d/MELT/_turnovers")
        assert naming.reports_dir(Path("/d"), "MELT") == Path("/d/MELT/_reports")
