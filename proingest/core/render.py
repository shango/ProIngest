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

**Colour is where the two split.** COLOR_AND_FORMAT section 1 branches after the shot's
CLF, and so does this module: the plate branch builds one OCIO processor per job and
applies it to every frame on its way to an EXR, and the view branch bakes the same chain
plus the ACES output transform into a `.cube` that ffmpeg applies as it encodes. Neither
branch decides anything about colour. What to apply arrives on the job as a
`clf.ShotColor`, which is a colour space name and the CDL, because that is what
survives the pickle into a worker process.
"""

from __future__ import annotations

import logging
import multiprocessing
import shutil
import tempfile
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
import PyOpenColorIO as ocio

from proingest.core import batchfile, color, exr, ffmpeg, frames, logsetup, media, naming, qc, resize
from proingest.core.models import DEFAULT_WORKERS, Batch, Deliverable, QCResult
from proingest.core.planner import DeliverableJob

log = logging.getLogger(__name__)

"""Byte copies under a delivery name. NAMING_SPEC section 2."""

WAV_SUFFIX = qc.WAV_SUFFIX

EXR_SUFFIX = qc.EXR_SUFFIX

file_digest = qc.file_digest
"""Moved to `qc.py` with the phase B checks that compare against it. Same function."""


class RenderError(RuntimeError):
    """The job could not be produced. Nothing is left at the destination."""


class RenderCancelled(RuntimeError):
    """The run was cancelled while this job was in flight.

    Deliberately not a RenderError: a cancelled job did not fail, it was never
    finished, and it should not be reported as a defect in the source or the plan.
    """


def render_job(
    job: DeliverableJob,
    on_frame: Callable[[int], None] | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> Deliverable:
    """Produce one deliverable and return the record of what was written.

    The colour chain comes off `job.shot_color`, which the planner resolved from the
    colour session. A job with no session carries the default, which renders the same
    plate ungraded rather than refusing: QC-008 is what stops a run that needs a grade
    and has none, and it is a rule about the batch rather than about this frame.

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
            _render_sequence(job, deliverable, on_frame, cancelled)
        elif job.kind == "aux_still":
            _render_still(job, deliverable)
        elif job.kind == "audio":
            _render_audio(job, deliverable)
        elif job.kind == "ref_mp4":
            _render_reference(job, deliverable)
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

    deliverable.qc.extend(qc.run_phase_b(job, deliverable))
    if any(result.severity == "error" for result in deliverable.qc):
        deliverable.status = "failed"
        _mark_failed(job.destination, deliverable)
        log.warning("%s failed post-render QC", job.destination)
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


def _mark_failed(destination: Path, deliverable: Deliverable) -> None:
    """Leave a `.failed` sidecar naming what went wrong, per QC_RULES phase B.

    The file itself stays: a deliverable that failed a check is evidence, and someone
    has to be able to open it and see what the check saw. The marker is what
    `batchfile.reconcile_with_filesystem` reads back, so a crash after this point
    still reopens as failed rather than as done.
    """
    lines = [f"{result.rule_id} {result.severity}: {result.message}" for result in deliverable.qc]
    marker = destination.with_name(destination.name + batchfile.FAILED_MARKER)
    marker.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _record_file(deliverable: Deliverable, path: Path) -> None:
    deliverable.checksum = file_digest(path)
    deliverable.size = path.stat().st_size


# --- Raw EXR delivery. COLOR_AND_FORMAT sections 3 and 7. ---


@dataclass(frozen=True)
class _PlateBranch:
    """The shot's plate chain, built once per job and applied to every frame.

    Building a processor is expensive and applying it is not, which is why this is
    resolved at the top of a job rather than inside the frame loop.
    """

    cpu: ocio.CPUProcessor

    def apply(self, pixels: npt.NDArray[np.float32]) -> npt.NDArray[np.float32]:
        """One decoded frame, transformed into linear ACEScg.

        In place when the frame is already contiguous float32 RGB, which is what both
        sources yield: a 4k frame is 95 MB and the branch holds one at a time.

        **Alpha does not go through the chain.** It is coverage rather than colour, and
        a transform applied to it would make an edge that was already correct wrong in
        a way that only shows up over a comp.
        """
        rgb = np.ascontiguousarray(pixels[..., :3], dtype=np.float32)
        color.apply(rgb, self.cpu)
        if pixels.shape[2] == 3:
            return rgb
        alpha = np.asarray(pixels[..., 3:], dtype=np.float32)
        return np.concatenate((rgb, alpha), axis=-1)


def _plate_branch(job: DeliverableJob) -> _PlateBranch:
    """Resolve the job's colour: compose the chain and build the processor."""
    return _PlateBranch(cpu=color.processor(*job.shot_color.plate_transforms()))


def _render_sequence(
    job: DeliverableJob,
    deliverable: Deliverable,
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
    graded = _plate_branch(job)
    stream = _source_pixels(job)
    try:
        # The stream is first so that it is asked for one frame past the plan and gets
        # to finish: a decode that ends on its own checks ffmpeg's exit code, one that
        # is closed part way through is killed and its exit code is never read.
        for pixels, output_frame in zip(stream, job.output_frames(), strict=False):
            path = job.frame_path(output_frame, temp=True)
            _write_frame(job, path, graded.apply(pixels), output_frame)
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
        raise RenderError(f"{job.name} wanted {job.frame_count} frames and the source gave {written}")
    deliverable.frame_count = written


def _render_still(job: DeliverableJob, deliverable: Deliverable) -> None:
    """One EXR from one source frame. An aux still is a file, not a folder."""
    graded = _plate_branch(job)
    stream = _source_pixels(job)
    try:
        pixels = next(stream, None)
    finally:
        stream.close()
    if pixels is None:
        raise RenderError(f"{job.name}: the source gave no frame at {job.in_frame}")
    _write_frame(job, job.temp, graded.apply(pixels), next(iter(job.output_frames())))
    _record_file(deliverable, job.temp)
    deliverable.frame_count = 1


def _write_frame(
    job: DeliverableJob,
    path: Path,
    pixels: npt.NDArray[Any],
    output_frame: int,
) -> None:
    exr.write_frame(
        path,
        pixels,
        timecode_frames=job.timecode_for(output_frame),
        fps=job.rate.as_float() if job.rate else 24.0,
        shot_color=job.shot_color,
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
    source = media.printf_pattern_for(job.source) if job.source_is_sequence else str(job.source)
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


def _fit(pixels: npt.NDArray[np.float32], target: tuple[int, int] | None) -> npt.NDArray[np.float32]:
    """Resample to the target, or pass the frame through when it is already there."""
    if target is None or pixels.shape[:2] == (target[1], target[0]):
        return pixels
    return resize.lanczos_resize(pixels, target[0], target[1])


# --- Reference mp4. COLOR_AND_FORMAT sections 1 and 3. ---

LUT_SUFFIX = ".cube"

LUT_TEMP_PREFIX = "proingest-lut-"
"""The viewing LUT's folder, on the system temp volume rather than the delivery root."""


def _render_reference(job: DeliverableJob, deliverable: Deliverable) -> None:
    """Encode the delivered range to a reference mp4, audio included when there is any.

    One ffmpeg pass reading the source itself, rather than the decode-and-write loop
    the raw path uses. x264 needs every frame anyway, so pulling them into this process
    first would copy 95 MB a frame across a pipe to hand straight back.

    The consequence is that this is the only job kind with no per-frame progress and no
    mid-job cancellation: ffmpeg is running, and the job is over when it returns.

    **The whole view branch goes in as one baked cube**, because ffmpeg has no OCIO
    filter and the encode has to stay a single pass. The cube is written for this job
    alone and deleted with the temp folder: it is not a deliverable, and the two
    reference jobs of one shot each bake their own rather than sharing one, which costs
    35937 samples through a processor and saves a lifetime nobody would own.
    """
    if job.in_frame is None or job.out_frame is None:
        raise RenderError(f"{job.name} has no frame range")
    if job.rate is None:
        raise RenderError(f"{job.name} has no frame rate, so the reference would play wrong")

    source = media.printf_pattern_for(job.source) if job.source_is_sequence else str(job.source)
    # Same rule as the raw path: only scale when the size actually changes, so a 4k
    # reference off a 4k source never touches a resampler.
    scale = job.target_size if job.target_size != job.source_size else None
    with tempfile.TemporaryDirectory(prefix=LUT_TEMP_PREFIX) as folder:
        ffmpeg.encode_reference(
            source,
            job.temp,
            job.in_frame,
            job.out_frame,
            is_sequence=job.source_is_sequence,
            rate=f"{job.rate.numerator}/{job.rate.denominator}",
            target_size=scale,
            lut=_view_lut(job, Path(folder)),
            audio=job.audio_source,
            audio_skip=_audio_skip(job),
            audio_tempo=_audio_tempo(job),
            timecode=_start_timecode(job),
        )
    if not job.temp.is_file():
        raise RenderError(f"{job.name}: the encode reported success and wrote nothing")

    # ffmpeg exits 0 when the source runs out before the range does: asked for 100
    # frames of a 4 frame plate it writes 4 and says nothing. The raw path catches the
    # same case by counting what it wrote, and a short reference recorded as done is
    # exactly the delivery this module exists to prevent.
    written = ffmpeg.container_frame_count(job.temp)
    if written != job.frame_count:
        raise RenderError(f"{job.name} wanted {job.frame_count} frames and the encode wrote {written}")
    _record_file(deliverable, job.temp)
    deliverable.frame_count = written


def _view_lut(job: DeliverableJob, folder: Path) -> Path:
    """Bake this job's view branch into `folder`, named after the deliverable.

    **Not under `job.temp`**, which is the one place the atomic envelope guarantees is
    cleaned but also sits in the delivery folder: that folder is a Google Drive mount
    (OQ-25), and a megabyte of LUT written there is a megabyte synced up and back for a
    file whose life is one encode. The name still carries the deliverable's, so the
    ffmpeg command this module logs verbatim says which shot the cube belonged to.
    """
    shot_color = job.shot_color
    transforms = shot_color.view_transforms()
    return color.view_lut(folder / f"{job.destination.stem}{LUT_SUFFIX}", *transforms)


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
    if job.in_frame is None or (job.kind == "ref_mp4" and job.audio_source is None):
        return 0.0
    rate = job.source_rate or job.rate
    if rate is None:
        return 0.0
    offset = job.in_frame - job.source_start_frame
    # At the source's own rate, because that is the rate its sound was recorded against.
    return max(0, offset) * rate.denominator / rate.numerator


def _audio_tempo(job: DeliverableJob) -> float:
    """How much faster the sound plays so it follows the picture played at 24.

    1.001 for the shooters' 24000/1001 files, 1.0 for a file already at 24. D2 of
    `docs/REVIEW_2026-09-23.md`: the picture is delivered frame for frame at 24, so it
    runs 0.1% faster than it was shot, and the sound does too or it drifts off it.
    """
    if job.rate is None or job.source_rate is None:
        return 1.0
    return (job.rate.numerator * job.source_rate.denominator) / (
        job.rate.denominator * job.source_rate.numerator
    )


def _start_timecode(job: DeliverableJob) -> str | None:
    """The reference's own timecode: the In frame's, which is what the EXRs carry too."""
    if job.rate is None or job.in_frame is None or job.source_start_timecode is None:
        return None
    first = frames.timecode_frames_for(job.in_frame, job.source_start_frame, job.source_start_timecode)
    return frames.frames_to_timecode(first, job.rate.as_float())


# --- Audio and byte copies. ---


def _render_audio(job: DeliverableJob, deliverable: Deliverable) -> None:
    """A wav is copied byte for byte; audio inside a container is extracted.

    Copying rather than re-encoding is the point: a delivered wav that came in as a
    wav has the same checksum as the source, which is what QC-120 compares.
    """
    if job.in_frame is None or job.rate is None:
        if job.source.suffix.lower() == WAV_SUFFIX:
            shutil.copyfile(job.source, job.temp)
        else:
            ffmpeg.extract_audio(job.source, job.temp)
    else:
        ffmpeg.extract_audio(
            job.source,
            job.temp,
            skip=_audio_skip(job),
            tempo=_audio_tempo(job),
            duration=job.frame_count * job.rate.denominator / job.rate.numerator,
        )
    if not job.temp.is_file():
        raise RenderError(f"{job.name}: no audio was produced from {job.source}")
    _record_file(deliverable, job.temp)


# --- Running a batch of jobs. ARCHITECTURE.md "Concurrency". ---

ProgressState = Literal["started", "frame", "done", "failed", "cancelled"]

RENDER_FAILED = qc.RENDER_FAILED
"""The render did not complete. Every other QC-1xx is NA when this one fails."""


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

_JOB_SHOT = ""
"""The shot the job in flight belongs to, stamped onto every record this worker makes.

A module global because a worker runs one job at a time and the logging calls it wants
stamped are five modules down, in `ffmpeg.run` and friends, which know about a command
line and nothing else. FR-13's panel filters by row, so a command line that cannot say
which row it was run for is a line the filter has to throw away.
"""


class _ShotFilter(logging.Filter):
    """Stamp `record.shot` on the way out of a worker. Never filters anything out.

    It goes on the **handler** rather than on the root logger. A logger's filters run
    only for records logged through that logger, and every record worth stamping is
    made by `proingest.core.ffmpeg` and merely propagates to the root; a handler's
    filters run for everything the handler is given.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        setattr(record, logsetup.SHOT_FIELD, _JOB_SHOT)
        return True


def _worker_init(
    queue: MPQueue[Progress | None],
    cancel: EventType,
    log_queue: MPQueue[logging.LogRecord | None],
    log_level: int,
    ffmpeg_override: Path | None,
    reference_crf: int,
    exr_compression_level: float,
) -> None:
    global _QUEUE, _CANCEL
    _QUEUE, _CANCEL = queue, cancel
    logsetup.install_worker_handler(log_queue, log_level).addFilter(_ShotFilter())
    ffmpeg.set_override(ffmpeg_override)
    ffmpeg.set_reference_crf(reference_crf)
    exr.set_compression_level(exr_compression_level)


def _publish(message: Progress) -> None:
    """Send progress, or do nothing when there is no pool. Never raises."""
    if _QUEUE is not None:
        _QUEUE.put(message)


def _worker(job: DeliverableJob) -> Deliverable:
    """Run one job in a worker process. Always returns a record, never raises.

    A failure comes back as a `failed` Deliverable carrying QC-100, so one job going
    wrong is a result the run reports rather than an exception that stops the rest.
    """

    def on_frame(done: int) -> None:
        _publish(Progress(job.name, "frame", done, job.frame_count))

    def cancelled() -> bool:
        return _CANCEL is not None and _CANCEL.is_set()

    global _JOB_SHOT
    _JOB_SHOT = job.shot_code
    _publish(Progress(job.name, "started", 0, job.frame_count))
    try:
        deliverable = render_job(job, on_frame=on_frame, cancelled=cancelled)
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


def _drain(queue: MPQueue[Progress | None], on_progress: Callable[[Progress], None] | None) -> None:
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

    # A spawned worker starts with no logging at all, so its ffmpeg command lines go
    # nowhere unless they are sent here to be handled (FR-13, and `core/logsetup.py`).
    # The queue and its listener belong to the run rather than to the process: nothing
    # outside a render has a worker to hear from.
    log_queue: MPQueue[logging.LogRecord | None] = context.Queue()
    listener = logsetup.start_listener(log_queue)
    log_level = logging.getLogger().getEffectiveLevel()

    # Read here rather than taken as an argument, for the reason the log level is: a
    # worker is a fresh interpreter that knows nothing this process was told, and a
    # setting a caller has to remember to forward is a setting that half works.
    ffmpeg_override = ffmpeg.current_override()

    # The Output section's two, on the same channel and for the same reason. A worker
    # that missed them would write a plate at one compression level and a reference at
    # one quality while the page said another, with nothing anywhere to say so.
    reference_crf = ffmpeg.current_reference_crf()
    exr_compression_level = exr.current_compression_level()

    results: dict[int, Deliverable] = {}
    try:
        with ProcessPoolExecutor(
            max_workers=max(1, workers),
            mp_context=context,
            initializer=_worker_init,
            initargs=(
                queue,
                cancel,
                log_queue,
                log_level,
                ffmpeg_override,
                reference_crf,
                exr_compression_level,
            ),
        ) as pool:
            futures = {pool.submit(_worker, job): index for index, job in enumerate(jobs)}
            for future in as_completed(futures):
                results[futures[future]] = future.result()
    finally:
        queue.put(None)
        drain.join(timeout=_DRAIN_TIMEOUT)
        # After the pool's own context manager has joined every worker, so nothing is
        # still writing to the queue when the listener stops reading it.
        listener.stop()

    return [results[index] for index in sorted(results)]


def apply_results(
    batch: Batch,
    deliverables: Sequence[Deliverable],
    show_pattern: str = naming.DEFAULT_SHOW_PATTERN,
) -> None:
    """Write executed records back onto the rows that planned them, then re-run QC-150.

    Matched on destination path, which is unique across a run because the planner
    resolves one version per shot and never names two deliverables the same.

    QC-150 and QC-151 are the only phase B rules that cannot run in a worker: one asks
    whether a whole row landed and the other reads every name in the batch, and a
    worker sees one job. They run here, where the results have just been collected,
    under the same show pattern the names were planned with.
    """
    executed = {deliverable.path: deliverable for deliverable in deliverables}
    for row in batch.rows:
        row.deliverables = [executed.get(planned.path, planned) for planned in row.deliverables]
    qc.apply_phase_b(batch, show_pattern)
