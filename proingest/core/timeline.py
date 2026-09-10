"""Timeline loading. OTIO first, CMX3600 EDL as a reduced fallback (FR-1).

Every video clip on every track becomes a shot candidate; a clip on V2 is as real as
one on V1. Gaps and transitions are ignored.

OTIO expresses a clip's `source_range` in the media's own coordinates, which for
media with a start timecode means timecode frames rather than an index from zero.
The offset into the media is therefore `source_range.start - available_range.start`,
and that offset is what gets added to the media's real first frame number. Keeping
the raw values on ClipRecord lets that mapping happen once media is resolved,
rather than guessing here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import opentimelineio as otio

from proingest.core.models import FrameRate

TIMELINE_EXTENSIONS = (".otio", ".edl")


class TimelineError(RuntimeError):
    """The timeline could not be parsed. Reported as QC-002."""


class DropFrameError(TimelineError):
    """The timeline uses drop-frame timecode, which is QC-027.

    Raised before parsing rather than after, because otio rejects a drop-frame
    timecode at a non-drop rate with a generic error. Letting that escape would
    report QC-002 "failed to parse" when the real answer is QC-027.
    """


@dataclass(frozen=True)
class ClipRecord:
    """One clip lifted out of a timeline, before any media is resolved."""

    name: str
    track: str
    record_start: int
    duration: int
    source_start: int
    available_start: int | None = None
    media_url: str | None = None
    is_audio: bool = False

    @property
    def record_end(self) -> int:
        """Inclusive last record frame."""
        return self.record_start + self.duration - 1

    def overlaps(self, other: ClipRecord) -> bool:
        """Record-range overlap, used to associate audio with video (FR-1)."""
        return self.record_start <= other.record_end and other.record_start <= self.record_end

    def source_offset(self) -> int:
        """Frames from the start of the media to this clip's first frame.

        When the media reference states its available range, the offset is the
        difference. Without one, the source range is already an offset.
        """
        if self.available_start is None:
            return self.source_start
        return self.source_start - self.available_start


@dataclass
class Timeline:
    """A parsed timeline. `rate` is compared against the project rate for QC-025."""

    path: Path
    rate: FrameRate
    video: list[ClipRecord]
    audio: list[ClipRecord]
    global_start: int = 0
    is_edl: bool = False
    is_drop_frame: bool = False

    def audio_for(self, clip: ClipRecord) -> list[ClipRecord]:
        """Audio clips whose record range overlaps this video clip.

        Zero is QC-040 for a plate and more than one is QC-041; both are the
        caller's decision, so all matches are returned.
        """
        return [candidate for candidate in self.audio if candidate.overlaps(clip)]


def find_timeline_files(folder: Path) -> list[Path]:
    """Timelines in a turnover folder, `.otio` preferred over `.edl`.

    None found is QC-001. More than one `.otio` is OQ-14, where the user picks.
    """
    found = [
        path
        for path in sorted(folder.rglob("*"))
        if path.is_file() and path.suffix.lower() in TIMELINE_EXTENSIONS
    ]
    return sorted(found, key=lambda p: (p.suffix.lower() != ".otio", str(p)))


def load(path: Path) -> Timeline:
    """Load a timeline. Dispatches on extension; both routes go through otio."""
    if not path.is_file():
        raise TimelineError(f"timeline {path} does not exist")
    is_edl = path.suffix.lower() == ".edl"
    if is_edl and _edl_is_drop_frame(path):
        raise DropFrameError(f"{path} uses drop-frame timecode (QC-027)")
    try:
        timeline = otio.adapters.read_from_file(str(path))
    except Exception as exc:
        raise TimelineError(f"could not parse {path}: {exc}") from exc

    video, audio = _extract_clips(timeline)
    if not video and not audio:
        raise TimelineError(f"{path} contains no clips at all")

    return Timeline(
        path=path,
        rate=_timeline_rate(timeline),
        video=video,
        audio=audio,
        global_start=_global_start(timeline),
        is_edl=is_edl,
        is_drop_frame=_otio_is_drop_frame(timeline),
    )


def _extract_clips(timeline: otio.schema.Timeline) -> tuple[list[ClipRecord], list[ClipRecord]]:
    """Walk every track. Track kind decides video or audio; nothing else is inspected."""
    video: list[ClipRecord] = []
    audio: list[ClipRecord] = []
    for index, track in enumerate(timeline.tracks):
        is_audio = track.kind == otio.schema.TrackKind.Audio
        label = track.name or f"{'A' if is_audio else 'V'}{index + 1}"
        target = audio if is_audio else video
        for clip in track.find_clips():
            record = _clip_record(clip, label, is_audio)
            if record is not None:
                target.append(record)
    video.sort(key=lambda c: (c.record_start, c.track))
    audio.sort(key=lambda c: (c.record_start, c.track))
    return video, audio


def _clip_record(clip: otio.schema.Clip, track: str, is_audio: bool) -> ClipRecord | None:
    """Convert one otio Clip. Returns None when it carries no usable range."""
    source_range = clip.source_range
    if source_range is None:
        return None
    in_parent = clip.range_in_parent()

    reference = clip.media_reference
    url = getattr(reference, "target_url", None)
    available = getattr(reference, "available_range", None)

    return ClipRecord(
        name=clip.name or "",
        track=track,
        record_start=round(in_parent.start_time.value),
        duration=round(in_parent.duration.value),
        source_start=round(source_range.start_time.value),
        available_start=round(available.start_time.value) if available is not None else None,
        media_url=str(url) if url else None,
        is_audio=is_audio,
    )


def _timeline_rate(timeline: otio.schema.Timeline) -> FrameRate:
    """The timeline's own rate, falling back to 24 when a timeline states none."""
    for source in (timeline.duration(), timeline.global_start_time):
        if source is not None and source.rate:
            return FrameRate.from_float(float(source.rate))
    return FrameRate(24)


def _global_start(timeline: otio.schema.Timeline) -> int:
    """Record timecode origin, in frames. Resolve writes 01:00:00:00 or 10:00:00:00."""
    start = timeline.global_start_time
    return round(start.value) if start is not None else 0


_DROP_FRAME_TIMECODE = re.compile(r"\d{2}:\d{2}:\d{2};\d{2}")


def _edl_is_drop_frame(path: Path) -> bool:
    """An EDL says so plainly: a `;` frame divider instead of `:`."""
    try:
        return bool(_DROP_FRAME_TIMECODE.search(path.read_text(errors="ignore")))
    except OSError:
        return False


def _otio_is_drop_frame(timeline: otio.schema.Timeline) -> bool:
    """OTIO carries no standard drop-frame flag, so only Resolve metadata can say."""
    metadata = dict(timeline.metadata or {})
    for key in ("drop_frame", "dropFrame", "df"):
        if key in metadata:
            return bool(metadata[key])
    return False
