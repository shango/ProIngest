"""Producing one deliverable from one job.

Nothing here decides what to write or what to call it: the planner settled both. This
module is the execution half, and its one invariant is that a deliverable either
exists complete and verified, or does not exist at all.

**Every job writes to `job.temp` and renames onto `job.destination` on success.** That
is the `.part` path the job already carries, a folder for a sequence and a file for
everything else. A crash, a full disk or a killed worker therefore leaves a `.part`
behind and never a file that looks finished. `resolve_version` in the planner ignores
`.part` names for the same reason, so a leftover cannot inflate the next version
either.

The per-frame xxhash64 recorded here is what QC-106 checks a delivered sequence
against. It is a digest of the written file, not of the pixels: DWAA is lossy, so a
frame does not read back byte-identical to what went in, but the encoder is
deterministic, which makes the file hash stable across a re-render of the same pixels.

Reference mp4s and the stringout are not here yet; they are M3.5.
"""

from __future__ import annotations

import logging
import shutil
from collections.abc import Generator
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt
import xxhash

from proingest.core import color, exr, ffmpeg, media, resize
from proingest.core.models import Deliverable
from proingest.core.planner import DeliverableJob

log = logging.getLogger(__name__)

DIGEST_CHUNK = 1 << 20

COPY_KINDS = frozenset({"hdri", "camdata", "bts"})
"""Byte copies under a delivery name. NAMING_SPEC section 2."""

WAV_SUFFIX = ".wav"

EXR_SUFFIX = ".exr"


class RenderError(RuntimeError):
    """The job could not be produced. Nothing is left at the destination."""


def file_digest(path: Path) -> str:
    """xxhash64 of a file, read in chunks so a 4k frame never lands in memory twice."""
    digest = xxhash.xxh64()
    with path.open("rb") as handle:
        while block := handle.read(DIGEST_CHUNK):
            digest.update(block)
    return digest.hexdigest()


def render_job(
    job: DeliverableJob,
    colorspace: color.SourceColorSpace = color.DEFAULT_SOURCE_COLORSPACE,
) -> Deliverable:
    """Produce one deliverable and return the record of what was written.

    `colorspace` labels the EXR output and is never used to transform it, so it is
    passed in rather than stored on the job: it is a Settings value about the whole
    turnover, not a fact about this source.

    On any failure the temp is discarded and the exception propagates, so the caller
    sees the real reason and the destination stays absent.
    """
    deliverable = job.to_deliverable()
    _prepare(job)
    try:
        if job.kind == "raw_dir":
            _render_sequence(job, deliverable, colorspace)
        elif job.kind == "aux_still":
            _render_still(job, deliverable, colorspace)
        elif job.kind == "audio":
            _render_audio(job, deliverable)
        elif job.kind in COPY_KINDS:
            _render_copy(job, deliverable)
        else:
            raise RenderError(f"{job.kind} cannot be rendered yet: reference encodes are M3.5")
    except ffmpeg.FFmpegError as exc:
        # One exception type out of here, so a worker pool has one thing to catch.
        _discard(job.temp)
        raise RenderError(f"{job.name}: {exc}") from exc
    except BaseException:
        # BaseException, not Exception: a cancelled worker must still clean up.
        _discard(job.temp)
        raise

    job.temp.replace(job.destination)
    deliverable.status = "done"
    log.info("wrote %s", job.destination)
    return deliverable


# --- The atomic envelope every kind shares. ---


def _prepare(job: DeliverableJob) -> None:
    """Make the shot folder, refuse an occupied destination, clear a stale temp.

    A destination that already exists means the version the planner resolved is not
    actually free, which is a bug or a concurrent run rather than something to
    overwrite: a delivered frame is not ours to replace.
    """
    job.destination.parent.mkdir(parents=True, exist_ok=True)
    if job.destination.exists():
        raise RenderError(f"{job.destination} already exists; the planned version is not free")
    _discard(job.temp)


def _discard(temp: Path) -> None:
    """Remove a temp, file or folder, whether it is finished or half written."""
    if temp.is_dir():
        shutil.rmtree(temp, ignore_errors=True)
    elif temp.exists():
        temp.unlink(missing_ok=True)


def _record_file(deliverable: Deliverable, path: Path) -> None:
    deliverable.checksum = file_digest(path)
    deliverable.size = path.stat().st_size


# --- Raw EXR delivery. COLOR_AND_FORMAT sections 3 and 7. ---


def _render_sequence(
    job: DeliverableJob, deliverable: Deliverable, colorspace: color.SourceColorSpace
) -> None:
    """Write every frame of the range into the temp folder, hashing as it goes."""
    job.temp.mkdir(parents=True)
    written = 0
    stream = _source_pixels(job)
    try:
        for output_frame, pixels in zip(job.output_frames(), stream, strict=False):
            path = job.frame_path(output_frame, temp=True)
            _write_frame(job, path, pixels, output_frame, colorspace)
            deliverable.frame_checksums.append(file_digest(path))
            deliverable.size += path.stat().st_size
            written += 1
    finally:
        # Closing rather than letting it fall out of scope: the decode owns an ffmpeg
        # process, and a short read must not leave it running until the next collection.
        stream.close()

    if written != job.frame_count:
        raise RenderError(
            f"{job.name} wanted {job.frame_count} frames and the source gave {written}"
        )
    deliverable.frame_count = written


def _render_still(
    job: DeliverableJob, deliverable: Deliverable, colorspace: color.SourceColorSpace
) -> None:
    """One EXR from one source frame. An aux still is a file, not a folder."""
    stream = _source_pixels(job)
    try:
        pixels = next(stream, None)
    finally:
        stream.close()
    if pixels is None:
        raise RenderError(f"{job.name}: the source gave no frame at {job.in_frame}")
    _write_frame(job, job.temp, pixels, next(iter(job.output_frames())), colorspace)
    _record_file(deliverable, job.temp)
    deliverable.frame_count = 1


def _write_frame(
    job: DeliverableJob,
    path: Path,
    pixels: npt.NDArray[Any],
    output_frame: int,
    colorspace: color.SourceColorSpace,
) -> None:
    exr.write_frame(
        path,
        pixels,
        timecode_frames=job.timecode_for(output_frame),
        fps=job.rate.as_float() if job.rate else 24.0,
        colorspace=colorspace,
    )


def _source_pixels(job: DeliverableJob) -> Generator[npt.NDArray[np.float32], None, None]:
    """The job's source frames, at the target size, in output order.

    Two branches, which COLOR_AND_FORMAT section 7 keeps apart deliberately. An EXR
    sequence is read with the OpenEXR bindings and resampled in numpy, because
    ffmpeg's scaler clamps float to 0-1 and would flatten a scene linear highlight.
    Everything else decodes through ffmpeg, which scales with the same Lanczos filter
    (OQ-7 measured the two against each other).
    """
    if job.in_frame is None or job.out_frame is None:
        raise RenderError(f"{job.name} has no frame range")

    if job.source_is_sequence and job.source.suffix.lower() == EXR_SUFFIX:
        for output_frame in job.output_frames():
            frame_path = media.frame_path_for(job.source, job.source_frame(output_frame))
            if not frame_path.is_file():
                raise RenderError(f"{job.name}: source frame {frame_path} is missing")
            yield _fit(exr.read_pixels(frame_path), job.target_size)
        return

    if job.source_size is None:
        raise RenderError(f"{job.name} has no source resolution, so the decode cannot be sized")
    source = (
        media.printf_pattern_for(job.source) if job.source_is_sequence else str(job.source)
    )
    # Only ask ffmpeg to scale when the size actually changes: a 4k pass from a 4k
    # source should not run the source through a resampler at all.
    scale = job.target_size if job.target_size != job.source_size else None
    yield from ffmpeg.decode_frames(
        source,
        job.source_size,
        job.in_frame,
        job.out_frame,
        is_sequence=job.source_is_sequence,
        target_size=scale,
    )


def _fit(
    pixels: npt.NDArray[np.float32], target: tuple[int, int] | None
) -> npt.NDArray[np.float32]:
    """Resample to the target, or pass the frame through when it is already there."""
    if target is None or pixels.shape[:2] == (target[1], target[0]):
        return pixels
    return resize.lanczos_resize(pixels, target[0], target[1])


# --- Audio and byte copies. ---


def _render_audio(job: DeliverableJob, deliverable: Deliverable) -> None:
    """A wav is copied byte for byte; audio inside a container is extracted.

    Copying rather than re-encoding is the point: a delivered wav that came in as a
    wav has the same checksum as the source, which is what QC-120 compares.
    """
    if job.source.suffix.lower() == WAV_SUFFIX:
        shutil.copyfile(job.source, job.temp)
    else:
        ffmpeg.extract_audio(job.source, job.temp)
    if not job.temp.is_file():
        raise RenderError(f"{job.name}: no audio was produced from {job.source}")
    _record_file(deliverable, job.temp)


def _render_copy(job: DeliverableJob, deliverable: Deliverable) -> None:
    """HDRI, camData and BTS: the same bytes under the delivery name.

    Nothing is converted, which is why the scan filters side files by extension: a
    rename cannot turn a jpg into an exr.
    """
    shutil.copyfile(job.source, job.temp)
    _record_file(deliverable, job.temp)
