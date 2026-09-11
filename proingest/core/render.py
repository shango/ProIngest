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

The reference mp4 is the one deliverable this module does not build frame by frame.
It hands the source to ffmpeg and lets x264 read it directly, so there is no progress
between its start and its finish, and a cancelled run waits for an encode already in
flight rather than stopping it. The stringout is not here at all; it is M6.
"""

from __future__ import annotations

import logging
import multiprocessing
import shutil
import threading
from collections.abc import Callable, Generator, Sequence
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from multiprocessing.queues import Queue as MPQueue
from multiprocessing.synchronize import Event as EventType
from pathlib import Path
from typing import Any, Literal

import numpy as np
import numpy.typing as npt
import xxhash

from proingest.core import color, exr, ffmpeg, media, resize
from proingest.core.models import Batch, Deliverable, QCResult
from proingest.core.planner import DeliverableJob

log = logging.getLogger(__name__)

DIGEST_CHUNK = 1 << 20

COPY_KINDS = frozenset({"hdri", "camdata", "bts"})
"""Byte copies under a delivery name. NAMING_SPEC section 2."""

WAV_SUFFIX = ".wav"

EXR_SUFFIX = ".exr"


class RenderError(RuntimeError):
    """The job could not be produced. Nothing is left at the destination."""


class RenderCancelled(RuntimeError):
    """The run was cancelled while this job was in flight.

    Deliberately not a RenderError: a cancelled job did not fail, it was never
    finished, and it should not be reported as a defect in the source or the plan.
    """


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
    on_frame: Callable[[int], None] | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> Deliverable:
    """Produce one deliverable and return the record of what was written.

    `colorspace` labels the EXR output and is never used to transform it, so it is
    passed in rather than stored on the job: it is a Settings value about the whole
    turnover, not a fact about this source.

    `on_frame` is called with the running frame count, and `cancelled` is checked
    between frames. Both are plain callables rather than a queue and an event, so
    this stays free of multiprocessing and both hooks are testable synchronously;
    `execute` is what wraps the real queue and event around them.

    On any failure the temp is discarded and the exception propagates, so the caller
    sees the real reason and the destination stays absent.
    """
    deliverable = job.to_deliverable()
    if cancelled is not None and cancelled():
        raise RenderCancelled(f"{job.name} was cancelled before it started")
    _prepare(job)
    try:
        if job.kind == "raw_dir":
            _render_sequence(job, deliverable, colorspace, on_frame, cancelled)
        elif job.kind == "aux_still":
            _render_still(job, deliverable, colorspace)
        elif job.kind == "audio":
            _render_audio(job, deliverable)
        elif job.kind == "ref_mp4":
            _render_reference(job, deliverable, colorspace)
        elif job.kind in COPY_KINDS:
            _render_copy(job, deliverable)
        else:
            raise RenderError(f"no renderer for a {job.kind} job")
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
    job: DeliverableJob,
    deliverable: Deliverable,
    colorspace: color.SourceColorSpace,
    on_frame: Callable[[int], None] | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> None:
    """Write every frame of the range into the temp folder, hashing as it goes.

    The frame boundary is where a run is interrupted. Checking between frames rather
    than mid-frame means a cancelled job never leaves a half written EXR, and the
    temp is discarded anyway on the way out.
    """
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
            if on_frame is not None:
                on_frame(written)
            if cancelled is not None and cancelled():
                raise RenderCancelled(f"{job.name} cancelled after {written} frames")
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


# --- Reference mp4. COLOR_AND_FORMAT section 3. ---


def _render_reference(
    job: DeliverableJob, deliverable: Deliverable, colorspace: color.SourceColorSpace
) -> None:
    """Encode the delivered range to a reference mp4, audio included when there is any.

    One ffmpeg pass reading the source itself, rather than the decode-and-write loop
    the raw path uses. x264 needs every frame anyway, so pulling them into this process
    first would copy 95 MB a frame across a pipe to hand straight back.

    The consequence is that this is the only job kind with no per-frame progress and no
    mid-job cancellation: ffmpeg is running, and the job is over when it returns.

    **The transfer is read from `color.display_transform`, never re-derived here.** It
    returns a filter for a scene linear source and None for the baked sRGB source the
    turnovers actually carry today, and applying the curve to pixels that already have
    it washes out every reference without failing.
    """
    if job.in_frame is None or job.out_frame is None:
        raise RenderError(f"{job.name} has no frame range")
    if job.rate is None:
        raise RenderError(f"{job.name} has no frame rate, so the reference would play wrong")

    source = media.printf_pattern_for(job.source) if job.source_is_sequence else str(job.source)
    # Same rule as the raw path: only scale when the size actually changes, so a 4k
    # reference off a 4k source never touches a resampler.
    scale = job.target_size if job.target_size != job.source_size else None
    ffmpeg.encode_reference(
        source,
        job.temp,
        job.in_frame,
        job.out_frame,
        is_sequence=job.source_is_sequence,
        rate=f"{job.rate.numerator}/{job.rate.denominator}",
        target_size=scale,
        display_filter=color.display_transform(colorspace),
        audio=job.audio_source,
        audio_skip=_audio_skip(job),
    )
    if not job.temp.is_file():
        raise RenderError(f"{job.name}: the encode reported success and wrote nothing")

    # ffmpeg exits 0 when the source runs out before the range does: asked for 100
    # frames of a 4 frame plate it writes 4 and says nothing. The raw path catches the
    # same case by counting what it wrote, and a short reference recorded as done is
    # exactly the delivery this module exists to prevent.
    written = ffmpeg.container_frame_count(job.temp)
    if written != job.frame_count:
        raise RenderError(
            f"{job.name} wanted {job.frame_count} frames and the encode wrote {written}"
        )
    _record_file(deliverable, job.temp)
    deliverable.frame_count = written


def _audio_skip(job: DeliverableJob) -> float:
    """Seconds of audio to drop so the sound stays with the picture.

    The wav covers the whole clip and the picture may be a trimmed range of it, so
    without this a shot the editor trimmed in delivers a reference whose sound runs
    ahead of it by the length of the trim. Computed from integer frames and converted
    only here, at the ffmpeg boundary.

    The audio starts where the picture starts and ends where it ends, cut point to cut
    point, confirmed by the user 2026-09-11. OQ-27. That also means the wav does not
    extend past the delivered range, so a shot extended into the handles outruns it; see
    the `apad` note in `ffmpeg.encode_command` for why that does not truncate the picture.
    """
    if job.audio_source is None or job.in_frame is None or job.rate is None:
        return 0.0
    offset = job.in_frame - job.source_start_frame
    return max(0, offset) / job.rate.as_float()


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


# --- Running a batch of jobs. ARCHITECTURE.md "Concurrency". ---

ProgressState = Literal["started", "frame", "done", "failed", "cancelled"]

RENDER_FAILED = "QC-100"
"""The render did not complete. Every other QC-1xx is NA when this one fails."""

DEFAULT_WORKERS = 4
"""Capped rather than one per core on purpose.

Each worker may run its own ffmpeg, and ffmpeg is already multi-threaded, so more
workers than this mostly buys contention. It is a parameter because the right number
depends on the machine and on whether the source is on a network mount; measuring it
against a real turnover is M8.
"""

_DRAIN_TIMEOUT = 5.0


@dataclass(frozen=True)
class Progress:
    """One message from a worker. Picklable, because it crosses a process boundary."""

    name: str
    state: ProgressState
    frames_done: int = 0
    frames_total: int = 0
    message: str = ""

    @property
    def fraction(self) -> float:
        """0.0 to 1.0, and 0.0 rather than a division error for a job with no frames."""
        if self.frames_total <= 0:
            return 0.0
        return min(1.0, self.frames_done / self.frames_total)


# Set once per worker process by the pool initializer. A module global rather than an
# argument because a multiprocessing Queue cannot be pickled through a task submission;
# it can only be handed over at process creation, which is what initargs does.
_QUEUE: MPQueue[Progress | None] | None = None
_CANCEL: EventType | None = None


def _worker_init(queue: MPQueue[Progress | None], cancel: EventType) -> None:
    global _QUEUE, _CANCEL
    _QUEUE, _CANCEL = queue, cancel


def _publish(message: Progress) -> None:
    """Send progress, or do nothing when there is no pool. Never raises."""
    if _QUEUE is not None:
        _QUEUE.put(message)


def _worker(job: DeliverableJob, colorspace: color.SourceColorSpace) -> Deliverable:
    """Run one job in a worker process. Always returns a record, never raises.

    A failure comes back as a `failed` Deliverable carrying QC-100, so one job going
    wrong is a result the run reports rather than an exception that stops the rest.
    """

    def on_frame(done: int) -> None:
        _publish(Progress(job.name, "frame", done, job.frame_count))

    def cancelled() -> bool:
        return _CANCEL is not None and _CANCEL.is_set()

    _publish(Progress(job.name, "started", 0, job.frame_count))
    try:
        deliverable = render_job(job, colorspace, on_frame=on_frame, cancelled=cancelled)
    except RenderCancelled:
        skipped = job.to_deliverable()
        skipped.status = "skipped"
        _publish(Progress(job.name, "cancelled", 0, job.frame_count))
        return skipped
    except Exception as exc:
        # Broad on purpose: one bad job is a result, not a reason to stop the run.
        failed = job.to_deliverable()
        failed.status = "failed"
        failed.qc.append(QCResult(RENDER_FAILED, "error", "deliverable", f"{job.name}: {exc}"))
        _publish(Progress(job.name, "failed", 0, job.frame_count, str(exc)))
        return failed

    _publish(Progress(job.name, "done", deliverable.frame_count, job.frame_count))
    return deliverable


def _drain(
    queue: MPQueue[Progress | None], on_progress: Callable[[Progress], None] | None
) -> None:
    """Forward progress to the caller until the None sentinel arrives.

    The queue carries `Progress | None` rather than a sentinel Progress value because
    a queue round trip pickles, so an identity check would not survive it.
    """
    while True:
        message = queue.get()
        if message is None:
            return
        if on_progress is not None:
            on_progress(message)


def execute(
    jobs: Sequence[DeliverableJob],
    colorspace: color.SourceColorSpace = color.DEFAULT_SOURCE_COLORSPACE,
    workers: int = DEFAULT_WORKERS,
    on_progress: Callable[[Progress], None] | None = None,
    cancel: EventType | None = None,
) -> list[Deliverable]:
    """Render every job, in parallel, and return one record per job.

    Every job produces a Deliverable whatever happens: `done`, `failed` with QC-100,
    or `skipped` when the run was cancelled. Results come back in job order rather
    than completion order, so a caller can line them up against what it planned.

    `cancel` is a `multiprocessing.Event` the caller keeps: setting it stops new jobs
    being submitted and makes in-flight jobs stop at their next frame boundary.

    `on_progress` is called on a drain thread in **this** process, not in a worker, so
    a UI callback can marshal to the main thread the way it normally would.

    The pool uses the spawn context on every platform. macOS, the target, spawns by
    default, so using it on the Linux dev machine too means the pickling constraints
    are the same in testing as in the field.
    """
    if not jobs:
        return []

    context = multiprocessing.get_context("spawn")
    cancel = cancel or context.Event()
    queue: MPQueue[Progress | None] = context.Queue()
    drain = threading.Thread(target=_drain, args=(queue, on_progress), daemon=True)
    drain.start()

    results: dict[int, Deliverable] = {}
    try:
        with ProcessPoolExecutor(
            max_workers=max(1, workers),
            mp_context=context,
            initializer=_worker_init,
            initargs=(queue, cancel),
        ) as pool:
            futures = {
                pool.submit(_worker, job, colorspace): index for index, job in enumerate(jobs)
            }
            for future in as_completed(futures):
                results[futures[future]] = future.result()
    finally:
        queue.put(None)
        drain.join(timeout=_DRAIN_TIMEOUT)

    return [results[index] for index in sorted(results)]


def apply_results(batch: Batch, deliverables: Sequence[Deliverable]) -> None:
    """Write executed records back onto the rows that planned them.

    Matched on destination path, which is unique across a run because the planner
    resolves one version per shot and never names two deliverables the same.
    """
    executed = {deliverable.path: deliverable for deliverable in deliverables}
    for row in batch.rows:
        row.deliverables = [executed.get(planned.path, planned) for planned in row.deliverables]
