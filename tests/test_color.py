"""The source colour space setting, which is the answer to OQ-17.

Getting the reference transfer backwards does not fail loudly, it just produces
washed out or crushed mp4s, so both directions are pinned here.
"""

from __future__ import annotations

from proingest.core import color


class TestDefault:
    def test_v01_sources_carry_a_baked_srgb_curve(self) -> None:
        """What the shooters deliver today: display referred, EXRs included."""
        assert color.DEFAULT_SOURCE_COLORSPACE == color.SRGB_DISPLAY


class TestExrAttribute:
    def test_display_referred(self) -> None:
        assert color.exr_attribute(color.SRGB_DISPLAY) == "sRGB_display"

    def test_scene_referred(self) -> None:
        assert color.exr_attribute(color.SCENE_LINEAR_SRGB) == "scene_linear_sRGB"

    def test_the_two_are_distinguishable(self) -> None:
        assert color.exr_attribute(color.SRGB_DISPLAY) != color.exr_attribute(
            color.SCENE_LINEAR_SRGB
        )


class TestDisplayTransform:
    def test_a_baked_source_is_left_alone(self) -> None:
        """Applying the curve to a file that already has it is the OQ-17 failure."""
        assert color.display_transform(color.SRGB_DISPLAY) is None

    def test_a_linear_source_gets_the_transfer(self) -> None:
        applied = color.display_transform(color.SCENE_LINEAR_SRGB)
        assert applied is not None
        assert "transferin=linear" in applied
        assert "transfer=iec61966-2-1" in applied
