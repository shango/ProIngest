"""The colour pipeline: the pinned config, the two legs of the chain, and applying them.

COLOR_AND_FORMAT section 1. Every failure this guards against is a plausible looking
wrong image rather than a crash, which is why the anchors here are real numbers and not
just shapes: mid grey has to land on 0.18 and a highlight has to stay above 1.0.

Since 2026-09-28 the grade is the AMF's looks applied in ACES2065-1, so this module
supplies the leg into ACES2065-1, each look, and the leg out to ACEScg, and the one leg
chain is for a shot with no look.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import PyOpenColorIO as ocio
import pytest

from proingest.core import color, ffmpeg
from tests.fixtures import color as color_fixtures

DISPLAY, VIEW = color_fixtures.DISPLAY, color_fixtures.VIEW

SOURCE = "ACEScct"
"""The encoding these tests read their pixels as.

Named here rather than taken from a constant of the module's: since M4.6.1 there is no
default source encoding, because a clip's own metadata is what names one. ACEScct keeps
the anchors below where they were.
"""

ACESCCT_MID_GREY = 0.413588
"""The ACEScct encoding of 0.18 scene linear. `(log2(0.18) + 9.72) / 17.52`."""


def grey_frame(*values: float) -> np.ndarray:
    """One neutral pixel per value, as a `(1, n, 3)` float32 frame."""
    return np.array([[[v, v, v] for v in values]], dtype=np.float32)


class TestConfig:
    def test_the_pinned_config_loads(self) -> None:
        assert color.config().getName() == color.BUILTIN_CONFIG

    def test_it_is_an_aces_2_0_config(self) -> None:
        """The colour session is ACES 2.0 and the tool has to match it, not track latest."""
        assert "aces-v2.0" in color.BUILTIN_CONFIG

    def test_it_is_cached(self) -> None:
        assert color.config() is color.config()

    def test_it_carries_the_spaces_the_chain_names(self) -> None:
        for name in (color.PLATE_SPACE, SOURCE):
            assert color.config().getColorSpace(name) is not None

    def test_it_carries_camera_vendor_logs(self) -> None:
        """The studio config rather than the cg one, in case OQ-39 names one of these."""
        assert color.config().getColorSpace("ARRI LogC4") is not None

    def test_luts_are_interpolated_tetrahedrally(self) -> None:
        import PyOpenColorIO as ocio

        assert color.INTERPOLATION == ocio.INTERP_TETRAHEDRAL


class TestResolveEncoding:
    """A name the AMF's input transform resolved to, checked against the pinned config."""

    def test_a_colour_space_the_config_knows_resolves_to_itself(self) -> None:
        assert color.resolve_encoding("S-Log3 S-Gamut3.Cine") == "S-Log3 S-Gamut3.Cine"

    def test_it_comes_back_as_the_config_s_own_spelling(self) -> None:
        """So two clips that named the same space the two ways record one provenance."""
        assert color.resolve_encoding("acescg") == color.PLATE_SPACE

    def test_a_curve_without_a_gamut_is_not_a_colour_space(self) -> None:
        with pytest.raises(color.ColorError, match="not a colour space"):
            color.resolve_encoding("S-Log3")


class TestInputTransform:
    """The one leg chain, for a shot with no grade: an aux still."""

    def test_it_lands_in_the_plate_space_rather_than_a_working_space(self) -> None:
        """One leg, source to ACEScg, with no grade to stop in ACEScct for."""
        transform = color.input_transform(SOURCE)
        assert transform.getSrc() == SOURCE
        assert transform.getDst() == color.PLATE_SPACE

    def test_mid_grey_lands_on_scene_linear_018(self) -> None:
        pixels = grey_frame(ACESCCT_MID_GREY)
        color.apply(pixels, color.processor(color.input_transform(SOURCE)))
        assert pixels[0, 0] == pytest.approx([0.18, 0.18, 0.18], abs=1e-4)

    def test_a_highlight_stays_above_one(self) -> None:
        """The plate branch is unbounded. A clamp here is the failure resize.py exists for."""
        pixels = grey_frame(1.0)
        color.apply(pixels, color.processor(color.input_transform(SOURCE)))
        assert pixels[0, 0, 0] > 200.0

    def test_a_camera_log_lands_on_scene_linear_018_as_well(self) -> None:
        """The aux still's chain for a real shooter, anchored on Sony's own number.

        S-Log3 puts 18% grey at 10 bit code 420, which is the published value rather
        than one read back out of OCIO, so this says the table entry is the encoding it
        claims to be rather than that OCIO agrees with itself.
        """
        pixels = grey_frame(420 / 1023)
        color.apply(pixels, color.processor(color.input_transform("S-Log3 S-Gamut3.Cine")))
        assert pixels[0, 0] == pytest.approx([0.18, 0.18, 0.18], abs=1e-3)

    def test_it_is_not_its_own_inverse(self) -> None:
        """Applying it twice is the double conversion a graded plate must not get."""
        once, twice = grey_frame(ACESCCT_MID_GREY), grey_frame(ACESCCT_MID_GREY)
        cpu = color.processor(color.input_transform(SOURCE))
        color.apply(once, cpu)
        color.apply(twice, cpu)
        color.apply(twice, cpu)
        assert twice[0, 0, 0] != pytest.approx(once[0, 0, 0], abs=1e-3)

    def test_an_unknown_encoding_is_refused_by_name(self) -> None:
        """A string a shooter wrote, caught at the edge rather than mid render."""
        with pytest.raises(color.ColorError, match="Arri LogC9"):
            color.input_transform("Arri LogC9")


class TestTheLegsAroundTheLooks:
    """Into ACES2065-1, each look there, and out to ACEScg (user, 2026-09-28)."""

    def test_the_leg_in_ends_at_aces2065_1(self) -> None:
        transform = color.to_aces("S-Log3 S-Gamut3.Cine")
        assert (transform.getSrc(), transform.getDst()) == ("S-Log3 S-Gamut3.Cine", color.ACES)

    def test_the_two_legs_together_are_the_input_transform(self) -> None:
        pixels = grey_frame(ACESCCT_MID_GREY)
        color.apply(pixels, color.processor(color.to_aces(SOURCE), color.to_plate()))
        assert pixels[0, 0, 1] == pytest.approx(0.18, abs=1e-3)

    def test_the_leg_in_refuses_an_unknown_encoding_by_name(self) -> None:
        with pytest.raises(color.ColorError, match="Arri LogC9"):
            color.to_aces("Arri LogC9")

    def test_the_gamut_compress_is_a_look_the_config_has(self) -> None:
        look = color.look_transform("ACES 1.3 Reference Gamut Compression")
        assert (look.getSrc(), look.getDst()) == (color.ACES, color.ACES)

    def test_an_unknown_look_is_refused(self) -> None:
        with pytest.raises(color.ColorError, match="not a look"):
            color.look_transform("Film Emulation")

    def test_the_gamut_compress_leaves_a_neutral_alone(self) -> None:
        """It compresses saturation; grey has none, so an ungraded grey is untouched."""
        pixels = grey_frame(0.18)
        color.apply(pixels, color.processor(color.look_transform("ACES 1.3 Reference Gamut Compression")))
        assert pixels[0, 0, 0] == pytest.approx(0.18, abs=1e-4)

    def test_a_clf_is_read_as_it_is(self, tmp_path: Path) -> None:
        clf = color_fixtures.make_clf(tmp_path / "node.clf", gain=2.0)
        pixels = grey_frame(0.18)
        color.apply(pixels, color.processor(color.clf_transform(clf)))
        assert pixels[0, 0, 0] == pytest.approx(0.36, abs=1e-4)
        assert color.clf_transform(clf).getInterpolation() == color.INTERPOLATION


class TestTheAmfsCdl:
    """The CDL inside an AMF, when it names no CLF (user, 2026-10-05)."""

    def test_a_slope_scales_linear_light_in_its_working_space(self) -> None:
        """A uniform slope commutes with the gamut matrices, so it is a plain gain."""
        pixels = grey_frame(0.18)
        numbers = (2.0, 2.0, 2.0, 0.0, 0.0, 0.0, 1.0, 1.0, 1.0, 1.0)
        color.apply(pixels, color.processor(color.cdl_transform(numbers, color.PLATE_SPACE)))
        assert pixels[0, 0, 0] == pytest.approx(0.36, abs=1e-4)

    def test_it_does_not_clamp_values_above_one(self) -> None:
        pixels = grey_frame(4.0)
        numbers = (1.0, 1.0, 1.0, 0.0, 0.0, 0.0, 1.0, 1.0, 1.0, 1.0)
        color.apply(pixels, color.processor(color.cdl_transform(numbers, color.PLATE_SPACE)))
        assert pixels[0, 0, 0] == pytest.approx(4.0, abs=1e-3)


class TestProcessor:
    def test_a_chain_is_one_group(self) -> None:
        """The ungraded view branch: the input leg and the output transform together."""
        chained = grey_frame(ACESCCT_MID_GREY)
        color.apply(
            chained, color.processor(color.input_transform(SOURCE), color.output_transform(DISPLAY, VIEW))
        )
        assert chained[0, 0, 0] == pytest.approx(0.356, abs=0.01)

    def test_an_empty_chain_does_nothing(self) -> None:
        assert color.processor().isNoOp()


class TestApply:
    def test_it_transforms_the_caller_s_own_array(self) -> None:
        """In place: a 4k float32 frame is 95 MB and a copy would be thrown away."""
        pixels = grey_frame(ACESCCT_MID_GREY)
        before = pixels.copy()
        color.apply(pixels, color.processor(color.input_transform(SOURCE)))
        assert not np.array_equal(pixels, before)

    def test_alpha_is_refused(self) -> None:
        pixels = np.zeros((1, 1, 4), dtype=np.float32)
        with pytest.raises(color.ColorError, match="RGB"):
            color.apply(pixels, color.processor(color.input_transform(SOURCE)))

    def test_half_float_is_refused(self) -> None:
        pixels = np.zeros((1, 1, 3), dtype=np.float16)
        with pytest.raises(color.ColorError, match="float32"):
            color.apply(pixels, color.processor(color.input_transform(SOURCE)))  # type: ignore[arg-type]

    def test_a_non_contiguous_view_is_refused(self) -> None:
        """OCIO reads the buffer directly, so a strided view would transform the wrong bytes."""
        pixels = np.zeros((1, 4, 3), dtype=np.float32)[:, ::2]
        with pytest.raises(color.ColorError, match="contiguous"):
            color.apply(pixels, color.processor(color.input_transform(SOURCE)))


class TestOutputTransform:
    def test_the_view_is_one_the_pinned_config_carries(self) -> None:
        """OQ-29's open half. A view name that does not exist fails at the first bake."""
        assert VIEW in color.config().getViews(DISPLAY)
        assert VIEW in color.config().getViews("Gamma 2.2 Rec.709 - Display"), "turnover097's display"

    def test_it_starts_where_the_clf_lands(self) -> None:
        """ACEScg, not ACEScct: the CLF ends in linear, so the view branch starts there."""
        assert color.output_transform(DISPLAY, VIEW).getSrc() == color.PLATE_SPACE

    def test_white_comes_out_in_display_range(self) -> None:
        """222 in scene linear arrives at 1. This is the tone map QC-039 probes for."""
        pixels = grey_frame(1.0)
        color.apply(
            pixels, color.processor(color.input_transform(SOURCE), color.output_transform(DISPLAY, VIEW))
        )
        assert pixels[0, 0, 0] == pytest.approx(1.0, abs=0.05)

    def test_mid_grey_comes_out_where_aces_puts_it(self) -> None:
        """0.18 lands at 0.36, not at sRGB's 0.46: the ODT is a rendering, not a curve."""
        pixels = grey_frame(ACESCCT_MID_GREY)
        color.apply(
            pixels, color.processor(color.input_transform(SOURCE), color.output_transform(DISPLAY, VIEW))
        )
        assert pixels[0, 0, 0] == pytest.approx(0.356, abs=0.01)


class TestViewLut:
    """The view branch as one `.cube`, which is how an OCIO transform reaches ffmpeg."""

    def chain(self) -> tuple[ocio.Transform, ...]:
        """A view branch with no CLF in it: the input leg and the output transform."""
        return (color.input_transform(SOURCE), color.output_transform(DISPLAY, VIEW))

    def test_it_writes_a_cube_of_the_stated_size(self, tmp_path: Path) -> None:
        cube = color.view_lut(tmp_path / "MELT0001_view.cube", *self.chain(), size=17)
        lines = cube.read_text().splitlines()
        assert lines[0] == "LUT_3D_SIZE 17"
        assert len(lines) == 1 + 17**3

    def test_the_default_size_is_what_resolve_and_nuke_use(self) -> None:
        assert color.LUT_SIZE == 33

    def test_red_varies_fastest(self, tmp_path: Path) -> None:
        """The `.cube` format's own ordering, and the one way to get this silently wrong."""
        cube = color.view_lut(tmp_path / "identity.cube", size=33)
        lines = cube.read_text().splitlines()
        assert lines[1] == "0.000000 0.000000 0.000000"
        assert lines[2] == "0.031250 0.000000 0.000000"
        assert lines[1 + 33] == "0.000000 0.031250 0.000000"
        assert lines[1 + 33 * 33] == "0.000000 0.000000 0.031250"

    def test_it_reads_back_as_the_chain_it_baked(self, tmp_path: Path) -> None:
        """Written by us and read by OpenColorIO, which is the convention ffmpeg shares."""
        cube = color.view_lut(tmp_path / "MELT0001_view.cube", *self.chain())
        ramp = grey_frame(0.0, 0.2, ACESCCT_MID_GREY, 0.7, 1.0)
        baked = ramp.copy()
        color.apply(ramp, color.processor(*self.chain()))
        read_back = ocio.FileTransform(src=str(cube), interpolation=color.INTERPOLATION)
        color.apply(baked, color.processor(read_back))
        assert baked == pytest.approx(ramp, abs=0.005)

    def test_trilinear_is_the_worse_answer_the_constant_exists_to_avoid(self, tmp_path: Path) -> None:
        """Read the same cube the default way and mid grey lands several times further off.

        Measured under the ACES 2.0 view: 0.0005 tetrahedral, 0.0031 trilinear.
        """
        cube = color.view_lut(tmp_path / "MELT0001_view.cube", *self.chain())
        exact = grey_frame(ACESCCT_MID_GREY)
        color.apply(exact, color.processor(*self.chain()))
        error = {}
        for interpolation in (color.INTERPOLATION, ocio.INTERP_LINEAR):
            read = grey_frame(ACESCCT_MID_GREY)
            color.apply(read, color.processor(ocio.FileTransform(src=str(cube), interpolation=interpolation)))
            error[interpolation] = abs(float(read[0, 0, 0] - exact[0, 0, 0]))
        assert error[ocio.INTERP_LINEAR] > 4 * error[color.INTERPOLATION]

    def test_ffmpeg_reads_it_as_the_same_transform(self, tmp_path: Path) -> None:
        """The whole point of baking one, checked against the tool that will apply it.

        16 bit in and out, so the only error left is the cube's own interpolation of a
        curve it samples 33 times.
        """
        cube = color.view_lut(tmp_path / "MELT0001_view.cube", *self.chain())
        ramp = grey_frame(0.0, 0.2, ACESCCT_MID_GREY, 0.7, 1.0)
        expected = ramp.copy()
        color.apply(expected, color.processor(*self.chain()))

        source, result = tmp_path / "ramp.raw", tmp_path / "graded.raw"
        source.write_bytes((np.clip(ramp, 0.0, 1.0) * 65535).round().astype("<u2").tobytes())
        width = ramp.shape[1]
        completed = ffmpeg.run(
            [
                str(ffmpeg.resolve_tool("ffmpeg")),
                "-y",
                "-f",
                "rawvideo",
                "-pix_fmt",
                "rgb48le",
                "-s",
                f"{width}x1",
                "-i",
                str(source),
                "-vf",
                f"lut3d=file={cube}:interp=tetrahedral",
                "-f",
                "rawvideo",
                "-pix_fmt",
                "rgb48le",
                str(result),
            ]
        )
        assert completed.returncode == 0, completed.stderr
        got = np.frombuffer(result.read_bytes(), dtype="<u2").astype(np.float32) / 65535.0
        assert got.reshape(1, width, 3) == pytest.approx(np.clip(expected, 0.0, 1.0), abs=0.005)

    def test_a_part_file_is_not_left_behind(self, tmp_path: Path) -> None:
        """Renamed onto the destination, so ffmpeg cannot read a half written cube."""
        color.view_lut(tmp_path / "MELT0001_view.cube", *self.chain(), size=9)
        assert [path.name for path in tmp_path.iterdir()] == ["MELT0001_view.cube"]
