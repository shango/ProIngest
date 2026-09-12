"""The colour pipeline: the pinned config, the two legs of the chain, and applying them.

COLOR_AND_FORMAT section 1. Every failure this guards against is a plausible looking
wrong image rather than a crash, which is why the anchors here are real numbers and not
just shapes: mid grey has to land on 0.18 and a highlight has to stay above 1.0.
"""

from __future__ import annotations

import numpy as np
import pytest

from proingest.core import color

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


class TestSupersededDisplayEncode:
    """M3's display referred path, kept until M4.5.4 moves render and exr off it."""

    def test_v01_sources_carry_a_baked_srgb_curve(self) -> None:
        assert color.DEFAULT_SOURCE_COLORSPACE == color.SRGB_DISPLAY

    def test_display_referred_attribute(self) -> None:
        assert color.exr_attribute(color.SRGB_DISPLAY) == "sRGB_display"

    def test_scene_referred_attribute(self) -> None:
        assert color.exr_attribute(color.SCENE_LINEAR_SRGB) == "scene_linear_sRGB"

    def test_the_two_are_distinguishable(self) -> None:
        assert color.exr_attribute(color.SRGB_DISPLAY) != color.exr_attribute(
            color.SCENE_LINEAR_SRGB
        )

    def test_a_baked_source_is_left_alone(self) -> None:
        assert color.display_transform(color.SRGB_DISPLAY) is None

    def test_a_linear_source_gets_the_transfer(self) -> None:
        applied = color.display_transform(color.SCENE_LINEAR_SRGB)
        assert applied is not None
        assert "transferin=linear" in applied
        assert "transfer=iec61966-2-1" in applied
