"""Lanczos resampling.

The property that matters is antialiasing: a 2:1 reduction has to integrate the
source, not sample it. A cubic spline interpolation passes every other test here and
fails `test_fine_detail_averages_rather_than_aliases`, which is why this exists at
all rather than a scipy call (OQ-7).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np
import pytest

from proingest.core import ffmpeg
from proingest.core.resize import lanczos_resize

FOUR_K = (2160, 3840)
HD = (1080, 1920)


def ramp(height: int, width: int, channels: int = 3) -> np.ndarray:
    """A horizontal gradient, the same in every channel."""
    row = np.linspace(0.0, 1.0, width, dtype=np.float32)
    return np.repeat(np.tile(row, (height, 1))[:, :, None], channels, axis=2)


class TestShape:
    def test_downscale_hits_the_target_exactly(self) -> None:
        result = lanczos_resize(ramp(216, 384), 192, 108)
        assert result.shape == (108, 192, 3)

    def test_alpha_survives_as_a_fourth_channel(self) -> None:
        result = lanczos_resize(ramp(64, 64, channels=4), 32, 32)
        assert result.shape == (32, 32, 4)

    def test_upscale_works_too(self) -> None:
        assert lanczos_resize(ramp(32, 32), 64, 64).shape == (64, 64, 3)

    def test_a_flat_image_is_not_an_image(self) -> None:
        with pytest.raises(ValueError, match="h, w, channels"):
            lanczos_resize(np.zeros((16, 16), dtype=np.float32), 8, 8)

    def test_output_is_float32_whatever_went_in(self) -> None:
        result = lanczos_resize(np.zeros((16, 16, 3), dtype=np.float16), 8, 8)
        assert result.dtype == np.float32


class TestFidelity:
    def test_same_size_is_a_no_op(self) -> None:
        source = ramp(64, 64)
        assert np.array_equal(lanczos_resize(source, 64, 64), source)

    def test_a_constant_image_stays_constant(self) -> None:
        source = np.full((216, 384, 3), 0.37, dtype=np.float32)
        result = lanczos_resize(source, 192, 108)
        assert np.allclose(result, 0.37, atol=1e-6)

    def test_a_gradient_stays_a_gradient(self) -> None:
        result = lanczos_resize(ramp(64, 512), 256, 32)
        row = result[16, :, 0]
        assert np.all(np.diff(row) > 0), "monotonic in, monotonic out"
        assert row[0] == pytest.approx(0.0, abs=0.02)
        assert row[-1] == pytest.approx(1.0, abs=0.02)

    def test_mean_is_preserved(self) -> None:
        rng = np.random.default_rng(7)
        source = rng.random((216, 384, 3), dtype=np.float32)
        result = lanczos_resize(source, 192, 108)
        assert result.mean() == pytest.approx(source.mean(), abs=1e-3)

    def test_scene_linear_values_above_one_are_not_clipped(self) -> None:
        """Half float carries highlights well past 1.0 and the resample must too."""
        source = np.full((64, 64, 3), 12.0, dtype=np.float32)
        assert lanczos_resize(source, 32, 32).max() == pytest.approx(12.0, abs=1e-3)

    def test_fine_detail_averages_rather_than_aliases(self) -> None:
        """A one pixel checkerboard at 2:1 must go grey, not stay checkered.

        This is the whole reason for an antialiased kernel. A plain subsample or a
        cubic spline returns the checkerboard, or an arbitrary phase of it.
        """
        row = np.indices((256, 256)).sum(axis=0) % 2
        source = np.repeat(row.astype(np.float32)[:, :, None], 3, axis=2)
        result = lanczos_resize(source, 128, 128)
        interior = result[8:-8, 8:-8]
        assert interior.min() == pytest.approx(0.5, abs=0.05)
        assert interior.max() == pytest.approx(0.5, abs=0.05)


class TestEdges:
    def test_the_frame_edge_is_not_darkened(self) -> None:
        """Weights are renormalized at the border, so an edge cannot fade to black."""
        source = np.full((128, 128, 3), 1.0, dtype=np.float32)
        result = lanczos_resize(source, 64, 64)
        assert result[0, 0, 0] == pytest.approx(1.0, abs=1e-5)
        assert result[-1, -1, 0] == pytest.approx(1.0, abs=1e-5)

    def test_a_horizontal_edge_stays_at_its_position(self) -> None:
        source = np.zeros((128, 128, 3), dtype=np.float32)
        source[:64] = 1.0
        result = lanczos_resize(source, 64, 64)
        assert result[:30, :, 0].min() > 0.98
        assert result[34:, :, 0].max() < 0.02


class TestDeliveryPass:
    """The one reduction this tool actually performs: 4k to HD."""

    def test_four_k_to_hd(self) -> None:
        source = ramp(*FOUR_K)
        result = lanczos_resize(source, HD[1], HD[0])
        assert result.shape == (1080, 1920, 3)
        assert result[540, 960, 0] == pytest.approx(source[1080, 1920, 0], abs=0.01)


def ffmpeg_scaled(source: np.ndarray, width: int, height: int, tmp_path: Path) -> np.ndarray:
    """The same reduction, done by `scale=...:flags=lanczos`, as 8 bit RGB."""
    height_in, width_in, _ = source.shape
    raw_in, raw_out = tmp_path / "in.raw", tmp_path / "out.raw"
    source.astype(np.uint8).tofile(raw_in)
    subprocess.run(
        [
            str(ffmpeg.resolve_tool("ffmpeg")),
            "-v",
            "error",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-s",
            f"{width_in}x{height_in}",
            "-i",
            str(raw_in),
            "-vf",
            f"scale={width}:{height}:flags=lanczos",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-y",
            str(raw_out),
        ],
        check=True,
        capture_output=True,
    )
    return np.fromfile(raw_out, dtype=np.uint8).reshape(height, width, 3).astype(np.float32)


class TestAgreesWithFfmpeg:
    """COLOR_AND_FORMAT section 4 names ffmpeg's filter, and a container source really
    does get it. The EXR path must not produce a visibly different HD from the same
    frames, so the two are compared directly.

    Tolerances are in 8 bit levels. swscale quantizes its kernel into fixed point, so
    exact equality is not expected on every pixel; a hard edge, where the kernel's
    shape and phase show most, does come back identical.
    """

    def as_rgb(self, plane: np.ndarray) -> np.ndarray:
        return np.repeat(plane.astype(np.float32)[:, :, None], 3, axis=2)

    def test_a_hard_edge_lands_in_the_same_place(self, tmp_path: Path) -> None:
        source = np.zeros((216, 384, 3), dtype=np.float32)
        source[:, :192] = 255.0
        theirs = ffmpeg_scaled(source, 192, 108, tmp_path)
        ours = np.clip(lanczos_resize(source, 192, 108), 0, 255)
        assert np.abs(theirs - ours).max() <= 1.0

    def test_a_gradient_matches_within_a_level(self, tmp_path: Path) -> None:
        row = np.linspace(0.0, 255.0, 384)
        source = self.as_rgb(np.tile(row, (216, 1)))
        theirs = ffmpeg_scaled(source, 192, 108, tmp_path)
        ours = np.clip(lanczos_resize(source, 192, 108), 0, 255)
        assert np.abs(theirs - ours).max() <= 1.5
