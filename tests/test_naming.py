"""Golden tests for naming.

Examples come from docs/NAMING_SPEC.md section 3 and from the shooters' spec PDF.
The round-trip tests are what QC-151 relies on.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from proingest.core import naming
from proingest.core.naming import ShotIdentity

PLATE = ShotIdentity(shot_code="MELT0001", kind="pl", index="01")
CLEAN = ShotIdentity(shot_code="MELT0001", kind="cp", index="01")
CHART = ShotIdentity(shot_code="MELT0001", kind="colorChart", index="01")


class TestShotIdentity:
    def test_derived_properties(self) -> None:
        assert PLATE.shot_code == "MELT0001"
        assert PLATE.show == "MELT"
        assert PLATE.elem == "pl01"
        assert PLATE.stem == "MELT0001_pl01"
        assert not PLATE.is_still

    def test_a_still_has_no_element_stem(self) -> None:
        """`MELT0001_colorChart01` is a name nothing writes, so it is refused rather
        than returned: a still that cannot be named beats one named plausibly wrong."""
        assert CHART.is_still
        assert CHART.show == "MELT"
        with pytest.raises(ValueError, match="reference still"):
            _ = CHART.stem


class TestParseShotType:
    """The `Shot Type` vocabulary (NAMING_SPEC section 1, the reading rules)."""

    @pytest.mark.parametrize(
        ("written", "expected"),
        [
            ("pl01", ("pl", "01")),
            ("cp02", ("cp", "02")),
            ("el01", ("el", "01")),
            ("wit01", ("wit", "01")),
            ("re01", ("re", "01")),
            ("colorChart", ("colorChart", "01")),
            ("mirrorBall", ("mirrorBall", "01")),
            ("greyBall", ("greyBall", "01")),
            ("sizeRef", ("sizeRef", "01")),
        ],
    )
    def test_every_clip_type(self, written: str, expected: tuple[str, str]) -> None:
        assert naming.parse_shot_type(written) == expected

    @pytest.mark.parametrize("written", ["PL01", "pL01", "COLORCHART", "colorchart", "SIZEREF"])
    def test_case_insensitive(self, written: str) -> None:
        """The shooters do not keep the camel case, so nothing may depend on it."""
        assert naming.parse_shot_type(written) is not None

    def test_output_spelling_is_the_specs_not_the_shooters(self) -> None:
        assert naming.parse_shot_type("colorchart") == ("colorChart", "01")

    @pytest.mark.parametrize("written", ["pl", "cp", "colorChart", "greyBall"])
    def test_a_bare_code_means_01(self, written: str) -> None:
        """Load bearing: three of the five real sample rows are bare."""
        assert naming.parse_shot_type(written) is not None
        assert naming.parse_shot_type(written)[1] == "01"  # type: ignore[index]

    def test_one_digit_index_is_padded(self) -> None:
        assert naming.parse_shot_type("pl2") == ("pl", "02")

    @pytest.mark.parametrize("written", ["cl", "CL", "cl01"])
    def test_clean_plate_is_accepted_as_cl_and_written_cp(self, written: str) -> None:
        """OQ-72: the user types `cl`, their own spec sheet says `cp` everywhere."""
        assert naming.parse_shot_type(written) == ("cp", "01")

    @pytest.mark.parametrize(
        "written",
        ["", "   ", "Wide", "Close Up", "Banana", "BTS", "lensgrid", "pl001", "pl_01", "01"],
    )
    def test_anything_else_resolves_to_nothing(self, written: str) -> None:
        """Including `BTS` and `lensgrid`, which are no longer deliverables, and `Wide`,
        which is what Resolve's built-in framing field is for."""
        assert naming.parse_shot_type(written) is None

    def test_the_codes_are_distinct_casefolded(self) -> None:
        """Why ignoring case is safe rather than lenient."""
        folded = [name.casefold() for name in naming.CLIP_TYPES]
        assert len(set(folded)) == len(folded)

    def test_aliases_do_not_collide_with_a_real_code(self) -> None:
        assert not set(naming.SHOT_TYPE_ALIASES) & {name.casefold() for name in naming.CLIP_TYPES}


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

    def test_aux_still(self) -> None:
        assert naming.aux_still_exr(CHART, 1) == "MELT0001_colorChart_01_4k_v01.exr"

    def test_clean_plate_uses_its_own_element(self) -> None:
        assert naming.raw_sequence_dir(CLEAN, "HD", 3) == "MELT0001_cp01_raw_HD_v03"

    def test_version_is_two_digits(self) -> None:
        assert naming.ref_mp4(PLATE, "4k", 12).endswith("_v12.mp4")

    def test_frame_is_four_digits(self) -> None:
        assert naming.raw_frame(PLATE, "4k", 1, 1240).endswith(".1240.exr")

    def test_aux_still_requires_an_aux(self) -> None:
        with pytest.raises(ValueError):
            naming.aux_still_exr(PLATE, 1)


class TestParseOutputName:
    """QC-151: every deliverable name must read back to what the planner intended."""

    @pytest.mark.parametrize(
        ("name", "kind"),
        [
            ("MELT0001_pl01_raw_4k_v01.1001.exr", "raw_frame"),
            ("MELT0001_pl01_raw_4k_v01", "raw_dir"),
            ("MELT0001_pl01_ref_HD_v01.mp4", "ref_mp4"),
            ("MELT0001_pl01_audio_v01.wav", "audio"),
            ("MELT0001_colorChart_01_4k_v01.exr", "aux_still"),
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
            "MELT0001_colorChart_01_4k_v01.exr",
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
        identity = ShotIdentity(shot_code="MELT0042", kind=elem_type, index="02")
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
        identity = ShotIdentity(shot_code="MELT0001", kind=aux, index="03")
        parsed = naming.parse_output_name(naming.aux_still_exr(identity, 2))
        assert parsed is not None
        assert (parsed.kind, parsed.aux, parsed.aux_index, parsed.version) == (
            "aux_still",
            aux,
            "03",
            2,
        )


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

    def test_reports_sit_beside_shots(self) -> None:
        assert naming.reports_dir(Path("/d"), "MELT") == Path("/d/MELT/_reports")
