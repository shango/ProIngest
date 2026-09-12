"""The colour pipeline: the pinned config, the two legs of the chain, and applying them.

COLOR_AND_FORMAT section 1. Every failure this guards against is a plausible looking
wrong image rather than a crash, which is why the anchors here are real numbers and not
just shapes: mid grey has to land on 0.18 and a highlight has to stay above 1.0.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import PyOpenColorIO as ocio
import pytest

from proingest.core import color, ffmpeg

ACESCCT_MID_GREY = 0.413588
"""The ACEScct encoding of 0.18 scene linear. `(log2(0.18) + 9.72) / 17.52`."""


def grey_frame(*values: float) -> np.ndarray:
    """One neutral pixel per value, as a `(1, n, 3)` float32 frame."""
    return np.array([[[v, v, v] for v in values]], dtype=np.float32)


class TestConfig:
    def test_the_pinned_config_loads(self) -> None:
        assert color.config().getName() == color.BUILTIN_CONFIG

    def test_it_is_an_aces_1_3_config(self) -> None:
        """The colour session is ACES 1.3 and the tool has to match it, not track latest."""
        assert "aces-v1.3" in color.BUILTIN_CONFIG

    def test_it_is_cached(self) -> None:
        assert color.config() is color.config()

    def test_it_carries_the_spaces_the_chain_names(self) -> None:
        for name in (color.WORKING_SPACE, color.PLATE_SPACE, color.DEFAULT_SOURCE_ENCODING):
            assert color.config().getColorSpace(name) is not None

    def test_it_carries_camera_vendor_logs(self) -> None:
        """The studio config rather than the cg one, in case OQ-39 names one of these."""
        assert color.config().getColorSpace("ARRI LogC4") is not None

    def test_luts_are_interpolated_tetrahedrally(self) -> None:
        import PyOpenColorIO as ocio

        assert color.INTERPOLATION == ocio.INTERP_TETRAHEDRAL


class TestInputTransform:
    def test_the_default_encoding_is_identity(self) -> None:
        """OQ-39's default: ACEScct in means nothing happens between decode and grade."""
        assert color.DEFAULT_SOURCE_ENCODING == color.WORKING_SPACE
        assert color.processor(color.input_transform()).isNoOp()

    def test_a_vendor_log_costs_one_real_transform(self) -> None:
        assert not color.processor(color.input_transform("ARRI LogC4")).isNoOp()

    def test_an_unknown_encoding_is_refused_by_name(self) -> None:
        """A setting a human typed, caught at the edge rather than mid render."""
        with pytest.raises(color.ColorError, match="Arri LogC9"):
            color.input_transform("Arri LogC9")


class TestPlateTransform:
    def test_mid_grey_lands_on_scene_linear_018(self) -> None:
        pixels = grey_frame(ACESCCT_MID_GREY)
        color.apply(pixels, color.processor(color.plate_transform()))
        assert pixels[0, 0] == pytest.approx([0.18, 0.18, 0.18], abs=1e-4)

    def test_a_highlight_stays_above_one(self) -> None:
        """The plate branch is unbounded. A clamp here is the failure resize.py exists for."""
        pixels = grey_frame(1.0)
        color.apply(pixels, color.processor(color.plate_transform()))
        assert pixels[0, 0, 0] > 200.0

    def test_it_is_not_its_own_inverse(self) -> None:
        """Applying it twice is the double conversion a graded plate must not get."""
        once, twice = grey_frame(ACESCCT_MID_GREY), grey_frame(ACESCCT_MID_GREY)
        cpu = color.processor(color.plate_transform())
        color.apply(once, cpu)
        color.apply(twice, cpu)
        color.apply(twice, cpu)
        assert twice[0, 0, 0] != pytest.approx(once[0, 0, 0], abs=1e-3)


class TestProcessor:
    def test_a_chain_is_one_group(self) -> None:
        """Input and plate together, which is what a run with no CLF would apply."""
        chained = grey_frame(ACESCCT_MID_GREY)
        color.apply(chained, color.processor(color.input_transform(), color.plate_transform()))
        assert chained[0, 0] == pytest.approx([0.18, 0.18, 0.18], abs=1e-4)

    def test_an_empty_chain_does_nothing(self) -> None:
        assert color.processor().isNoOp()


class TestApply:
    def test_it_transforms_the_caller_s_own_array(self) -> None:
        """In place: a 4k float32 frame is 95 MB and a copy would be thrown away."""
        pixels = grey_frame(ACESCCT_MID_GREY)
        before = pixels.copy()
        color.apply(pixels, color.processor(color.plate_transform()))
        assert not np.array_equal(pixels, before)

    def test_alpha_is_refused(self) -> None:
        pixels = np.zeros((1, 1, 4), dtype=np.float32)
        with pytest.raises(color.ColorError, match="RGB"):
            color.apply(pixels, color.processor(color.plate_transform()))

    def test_half_float_is_refused(self) -> None:
        pixels = np.zeros((1, 1, 3), dtype=np.float16)
        with pytest.raises(color.ColorError, match="float32"):
            color.apply(pixels, color.processor(color.plate_transform()))  # type: ignore[arg-type]

    def test_a_non_contiguous_view_is_refused(self) -> None:
        """OCIO reads the buffer directly, so a strided view would transform the wrong bytes."""
        pixels = np.zeros((1, 4, 3), dtype=np.float32)[:, ::2]
        with pytest.raises(color.ColorError, match="contiguous"):
            color.apply(pixels, color.processor(color.plate_transform()))


class TestOutputTransform:
    def test_the_view_is_one_the_pinned_config_carries(self) -> None:
        """OQ-29's open half. A view name that does not exist fails at the first bake."""
        assert color.VIEW in color.config().getViews(color.DISPLAY)

    def test_it_starts_where_the_clf_lands(self) -> None:
        """ACEScg, not ACEScct: the CLF ends in linear, so the view branch starts there."""
        assert color.output_transform().getSrc() == color.PLATE_SPACE

    def test_white_comes_out_in_display_range(self) -> None:
        """222 in scene linear arrives at 1. This is the tone map QC-039 probes for."""
        pixels = grey_frame(1.0)
        color.apply(pixels, color.processor(color.plate_transform(), color.output_transform()))
        assert pixels[0, 0, 0] == pytest.approx(1.0, abs=0.05)

    def test_mid_grey_comes_out_where_aces_puts_it(self) -> None:
        """0.18 lands at 0.36, not at sRGB's 0.46: the ODT is a rendering, not a curve."""
        pixels = grey_frame(ACESCCT_MID_GREY)
        color.apply(pixels, color.processor(color.plate_transform(), color.output_transform()))
        assert pixels[0, 0, 0] == pytest.approx(0.356, abs=0.01)


class TestViewLut:
    """The view branch as one `.cube`, which is how an OCIO transform reaches ffmpeg."""

    def chain(self) -> tuple[ocio.Transform, ...]:
        """A view branch with no CLF in it: input, plate, output transform."""
        return (color.input_transform(), color.plate_transform(), color.output_transform())

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

    def test_trilinear_is_the_worse_answer_the_constant_exists_to_avoid(
        self, tmp_path: Path
    ) -> None:
        """Read the same cube the default way and mid grey moves twice as far."""
        cube = color.view_lut(tmp_path / "MELT0001_view.cube", *self.chain())
        exact, trilinear = grey_frame(ACESCCT_MID_GREY), grey_frame(ACESCCT_MID_GREY)
        color.apply(exact, color.processor(*self.chain()))
        color.apply(
            trilinear,
            color.processor(ocio.FileTransform(src=str(cube), interpolation=ocio.INTERP_LINEAR)),
        )
        assert abs(float(trilinear[0, 0, 0] - exact[0, 0, 0])) > 0.005

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
        completed = ffmpeg.run([
            str(ffmpeg.resolve_tool("ffmpeg")), "-y",
            "-f", "rawvideo", "-pix_fmt", "rgb48le", "-s", f"{width}x1", "-i", str(source),
            "-vf", f"lut3d=file={cube}:interp=tetrahedral",
            "-f", "rawvideo", "-pix_fmt", "rgb48le", str(result),
        ])
        assert completed.returncode == 0, completed.stderr
        got = np.frombuffer(result.read_bytes(), dtype="<u2").astype(np.float32) / 65535.0
        assert got.reshape(1, width, 3) == pytest.approx(np.clip(expected, 0.0, 1.0), abs=0.005)

    def test_a_part_file_is_not_left_behind(self, tmp_path: Path) -> None:
        """Renamed onto the destination, so ffmpeg cannot read a half written cube."""
        color.view_lut(tmp_path / "MELT0001_view.cube", *self.chain(), size=9)
        assert [path.name for path in tmp_path.iterdir()] == ["MELT0001_view.cube"]
