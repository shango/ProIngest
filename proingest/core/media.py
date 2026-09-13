"""Media resolution and probing.

Turnover folders live on a Google Drive mount, so the directory is walked exactly
once into a DirectoryIndex and every later lookup reads that index. Nothing here
stats a file inside a loop.

Image sequences are detected by the `name.####.ext` pattern and carried as a single
media item with a frame range (FR-2).
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from proingest.core import ffmpeg
from proingest.core.models import AudioInfo, FrameRate, MediaInfo

SEQUENCE_PATTERN = re.compile(r"^(?P<base>.+)\.(?P<frame>\d{4,})$")

MEDIA_EXTENSIONS = frozenset(
    {".exr", ".dpx", ".mov", ".mp4", ".mxf", ".tif", ".tiff", ".png", ".jpg", ".jpeg"}
)
AUDIO_EXTENSIONS = frozenset({".wav", ".aif", ".aiff"})


@dataclass(frozen=True)
class FileEntry:
    """One file, with the stat values already read so nothing re-stats later."""

    path: Path
    size: int
    mtime: float

    @property
    def name(self) -> str:
        return self.path.name

    @property
    def stem(self) -> str:
        return self.path.stem

    @property
    def suffix(self) -> str:
        return self.path.suffix.lower()


@dataclass(frozen=True)
class Sequence:
    """An image sequence treated as one media item.

    `frames` is sorted and may contain gaps, which is QC-015. The frame numbers are
    the source numbering, which is not necessarily 1001-based.
    """

    directory: Path
    base: str
    ext: str
    frames: tuple[int, ...]
    padding: int
    size: int = 0
    mtime: float = 0.0

    @property
    def first(self) -> int:
        return self.frames[0]

    @property
    def last(self) -> int:
        return self.frames[-1]

    @property
    def count(self) -> int:
        return len(self.frames)

    @property
    def has_gaps(self) -> bool:
        """QC-015. A contiguous run spans exactly as many numbers as it has frames."""
        return self.last - self.first + 1 != self.count

    @property
    def missing_frames(self) -> list[int]:
        present = set(self.frames)
        return [n for n in range(self.first, self.last + 1) if n not in present]

    def path_for(self, frame: int) -> Path:
        return self.directory / f"{self.base}.{frame:0{self.padding}d}{self.ext}"

    @property
    def first_path(self) -> Path:
        return self.path_for(self.first)

    def printf_pattern(self) -> str:
        """`name.%04d.exr`, the form ffmpeg's image2 demuxer expects."""
        return printf_pattern_for(self.first_path)


def _split_frame(frame: Path) -> tuple[str, int]:
    """A sequence frame's base name and its zero padding."""
    match = SEQUENCE_PATTERN.match(frame.stem)
    if match is None:
        raise ValueError(f"{frame} is not a numbered sequence frame")
    return match["base"], len(match["frame"])


def printf_pattern_for(frame: Path) -> str:
    """The same pattern, rebuilt from any one frame of the sequence.

    `MediaInfo.path` for a sequence is its first frame, not its pattern, so a
    DeliverableJob handed to a worker process carries a frame path and this is how
    that worker names the ffmpeg input. Padding comes from the digits actually on
    the file, so a five digit sequence stays five digits.
    """
    base, padding = _split_frame(frame)
    return str(frame.with_name(f"{base}.%0{padding}d{frame.suffix}"))


def frame_path_for(frame: Path, number: int) -> Path:
    """Another frame of the same sequence, by number.

    The EXR source path reads frames itself rather than going through ffmpeg, so it
    needs real paths where the container path needs a printf pattern. Both come from
    the same split, so they cannot disagree about padding.
    """
    base, padding = _split_frame(frame)
    return frame.with_name(f"{base}.{number:0{padding}d}{frame.suffix}")


@dataclass
class DirectoryIndex:
    """One recursive walk of a turnover folder. Built once, queried many times."""

    root: Path
    sequences: list[Sequence] = field(default_factory=list)
    singles: list[FileEntry] = field(default_factory=list)

    def by_stem(self, stem: str) -> list[Sequence | FileEntry]:
        """Everything whose base name equals `stem`, sequences and single files alike."""
        matches: list[Sequence | FileEntry] = [s for s in self.sequences if s.base == stem]
        matches.extend(entry for entry in self.singles if entry.stem == stem)
        return matches

    def media_matching(self, stem: str) -> list[Sequence | FileEntry]:
        """Media candidates for a clip name. FR-2: one hit resolves, zero or many is QC."""
        return [
            item
            for item in self.by_stem(stem)
            if (item.ext if isinstance(item, Sequence) else item.suffix) in MEDIA_EXTENSIONS
        ]

    def audio_matching(self, stem: str) -> list[FileEntry]:
        """Used by the EDL fallback, which cannot associate audio from the timeline."""
        return [
            entry
            for entry in self.singles
            if entry.stem == stem and entry.suffix in AUDIO_EXTENSIONS
        ]

    def containing(self, fragment: str) -> list[FileEntry]:
        """Single files whose name contains `fragment`. Used for HDRI and camData."""
        lowered = fragment.lower()
        return [entry for entry in self.singles if lowered in entry.name.lower()]


def index_directory(root: Path) -> DirectoryIndex:
    """Walk `root` once and group image sequences.

    Every file is stat-ed exactly once here. Callers must not stat again.
    """
    index = DirectoryIndex(root=root)
    entries: list[FileEntry] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        stat = path.stat()
        entries.append(FileEntry(path=path, size=stat.st_size, mtime=stat.st_mtime))

    grouped: dict[tuple[Path, str, str, int], list[tuple[int, FileEntry]]] = defaultdict(list)
    for entry in entries:
        match = SEQUENCE_PATTERN.match(entry.stem)
        if match is None or entry.suffix not in MEDIA_EXTENSIONS:
            index.singles.append(entry)
            continue
        digits = match["frame"]
        key = (entry.path.parent, match["base"], entry.suffix, len(digits))
        grouped[key].append((int(digits), entry))

    for (directory, base, ext, padding), members in grouped.items():
        if len(members) == 1:
            # A lone numbered file is a still, not a sequence.
            index.singles.append(members[0][1])
            continue
        members.sort()
        first_entry = members[0][1]
        index.sequences.append(
            Sequence(
                directory=directory,
                base=base,
                ext=ext,
                frames=tuple(number for number, _ in members),
                padding=padding,
                size=first_entry.size,
                mtime=first_entry.mtime,
            )
        )
    index.sequences.sort(key=lambda s: (str(s.directory), s.base))
    index.singles.sort(key=lambda e: str(e.path))
    return index


# --- Path mapping, FR-2. ---


def url_to_path(url: str) -> Path:
    """Turn an OTIO `target_url` into a local path.

    Resolve writes either a plain path or a `file://` URL depending on platform and
    version, so both are accepted.
    """
    if url.startswith("file://"):
        parsed = urlparse(url)
        raw = unquote(parsed.path)
        # A Windows URL looks like file:///G:/media, leaving a leading slash to drop.
        if re.match(r"^/[A-Za-z]:", raw):
            raw = raw[1:]
        return Path(raw)
    return Path(url)


def remap(path: Path, path_map: dict[str, str]) -> Path:
    """Rewrite a Resolve path onto the local mount.

    Longest prefix wins, so a specific mapping beats a general one. Comparison is
    case-insensitive and slash-insensitive because the paths come from another OS.
    """

    def normalize(text: str) -> str:
        return text.replace("\\", "/").rstrip("/").lower()

    candidate = normalize(str(path))
    for source in sorted(path_map, key=len, reverse=True):
        prefix = normalize(source)
        if candidate == prefix or candidate.startswith(prefix + "/"):
            remainder = str(path).replace("\\", "/")[len(source.rstrip("/\\")) :].lstrip("/")
            target = path_map[source]
            return Path(target) / remainder if remainder else Path(target)
    return path


# --- Probing, FR-3. ---


def _rate_from_string(text: str) -> FrameRate:
    """ffprobe reports rates as `24/1` or `24000/1001`, which is already exact."""
    if "/" in text:
        numerator, denominator = text.split("/", 1)
        return FrameRate(int(numerator), int(denominator))
    return FrameRate(int(text))


def _timecode_from(probe: dict[str, Any], rate: FrameRate) -> int | None:
    """Start timecode in frames, or None when the media carries none (QC-028)."""
    from proingest.core import frames as frame_math

    sources: list[dict[str, Any]] = [probe.get("format", {}).get("tags", {})]
    sources.extend(stream.get("tags", {}) for stream in probe.get("streams", []))
    for tags in sources:
        text = tags.get("timecode") or tags.get("TIMECODE")
        if not text:
            continue
        try:
            return frame_math.timecode_to_frames(text, rate.as_float())
        except ValueError:
            continue
    return None


def _video_stream(probe: dict[str, Any]) -> dict[str, Any]:
    """The first usable video stream.

    A corrupt file is not necessarily an ffprobe failure: given a damaged EXR,
    ffprobe exits 0 and reports a stream of 0x0 while logging the real complaint to
    stderr only. Zero dimensions therefore mean unreadable, which is QC-014.
    """
    streams: list[dict[str, Any]] = probe["streams"]
    for stream in streams:
        if stream.get("codec_type") != "video":
            continue
        if not int(stream.get("width", 0)) or not int(stream.get("height", 0)):
            raise ffmpeg.FFprobeError(
                f"video stream reports {stream.get('width')}x{stream.get('height')}; "
                f"the file is unreadable or truncated"
            )
        return stream
    raise ffmpeg.FFprobeError("no video stream found")


def _audio_fields(probe: dict[str, Any]) -> tuple[bool, int, int, int]:
    for stream in probe["streams"]:
        if stream.get("codec_type") != "audio":
            continue
        depth = int(stream.get("bits_per_raw_sample") or stream.get("bits_per_sample") or 0)
        return True, int(stream.get("channels", 0)), int(stream.get("sample_rate", 0)), depth
    return False, 0, 0, 0


def probe(
    item: Sequence | FileEntry | Path,
    ffprobe_path: Path | None = None,
    fallback_rate: FrameRate | None = None,
) -> MediaInfo:
    """Probe one media item into a MediaInfo.

    For a sequence the first frame is probed for its format and the frame range comes
    from the index, because probing the whole sequence would read every file.

    `fallback_rate` is the timeline's rate and wins whenever it is given. Shooters
    conform every clip to the project rate in Resolve before making the stringout
    and EDL, so the timeline is what the media is actually played at, and any rate
    baked into the media may be stale camera metadata. Computing with that stale
    value would misread timecode and block every row on QC-026.

    What the media claims is kept separately as `stated_rate` so QC-026 can still
    report a genuine mismatch. Nothing computes with it.
    """
    if isinstance(item, Sequence):
        target, size, mtime = item.first_path, item.size, item.mtime
    elif isinstance(item, FileEntry):
        target, size, mtime = item.path, item.size, item.mtime
    else:
        stat = item.stat()
        target, size, mtime = item, stat.st_size, stat.st_mtime

    raw = ffmpeg.probe_raw(target, ffprobe_path)
    stream = _video_stream(raw)
    tags = _tags_from(raw, stream)
    has_audio, channels, sample_rate, depth = _audio_fields(raw)

    if isinstance(item, Sequence):
        # ffprobe invents 25/1 for a single frame, so it is never a source here.
        stated = _exr_stated_rate(target)
        frame_count, start_frame = item.count, item.first
    else:
        stated = _rate_from_string(stream.get("r_frame_rate", "24/1"))
        # Frame count is a property of the file, so it counts at the file's own rate.
        frame_count, start_frame = _container_frame_count(stream, stated), 0

    rate = fallback_rate or stated or FrameRate(24)

    return MediaInfo(
        path=target,
        codec=str(stream.get("codec_name", "")),
        pixel_format=str(stream.get("pix_fmt", "")),
        width=int(stream.get("width", 0)),
        height=int(stream.get("height", 0)),
        rate=rate,
        frame_count=frame_count,
        start_frame=start_frame,
        start_timecode=_timecode_from(raw, rate) or _exr_timecode(target, rate),
        is_sequence=isinstance(item, Sequence),
        has_audio=has_audio,
        audio_channels=channels,
        audio_sample_rate=sample_rate,
        audio_bit_depth=depth,
        size=size,
        mtime=mtime,
        stated_rate=stated,
        tags=tags,
    )


def _tags_from(probe: dict[str, Any], stream: dict[str, Any]) -> dict[str, str]:
    """The container's own tags, the format's and the video stream's in one dict.

    The stream's win where both name a tag, because a tag written per stream was written
    about this picture. What reads them is the source encoding lookup (OQ-44); nothing
    else does, and nothing here decides how to decode a file.
    """
    merged: dict[str, str] = {}
    for source in (probe.get("format", {}).get("tags", {}), stream.get("tags", {})):
        for key, value in source.items():
            if isinstance(value, str):
                merged[str(key)] = value
    return merged


def _exr_stated_rate(first_frame: Path) -> FrameRate | None:
    """The rate an EXR sequence claims in its header, if it claims one at all."""
    if first_frame.suffix.lower() != ".exr":
        return None
    from proingest.core import exr

    try:
        stated = exr.read_header(first_frame).frames_per_second
    except exr.ExrError:
        return None
    return FrameRate(stated[0], stated[1]) if stated is not None else None


def _exr_timecode(path: Path, rate: FrameRate) -> int | None:
    """EXR carries its timecode in a header attribute that ffprobe does not report.

    A header that will not parse is not fatal here; the row simply has no timecode,
    which QC-028 reports. QC-014 covers media that is unreadable outright.
    """
    if path.suffix.lower() != ".exr":
        return None
    from proingest.core import exr

    try:
        return exr.start_timecode_frames(path, rate.as_float())
    except (exr.ExrError, ValueError):
        return None


def _container_frame_count(stream: dict[str, Any], rate: FrameRate) -> int:
    """`nb_frames` when the container states it, otherwise duration times rate.

    Rounding rather than truncating avoids losing the last frame to float duration.
    """
    stated = stream.get("nb_frames")
    if stated and int(stated) > 0:
        return int(stated)
    duration = stream.get("duration")
    if duration:
        return round(float(duration) * rate.as_float())
    return 0


def probe_cached(
    item: Sequence | FileEntry | Path,
    cache: dict[str, MediaInfo],
    ffprobe_path: Path | None = None,
    fallback_rate: FrameRate | None = None,
) -> MediaInfo:
    """Probe once per path, size and mtime. FR-3.

    A re-exported file changes size or mtime and so misses the cache on its own.
    """
    if isinstance(item, Sequence):
        key = f"{item.first_path}|{item.size}|{item.mtime}"
    elif isinstance(item, FileEntry):
        key = f"{item.path}|{item.size}|{item.mtime}"
    else:
        stat = item.stat()
        key = f"{item}|{stat.st_size}|{stat.st_mtime}"

    hit = cache.get(key)
    if hit is not None:
        return hit
    info = probe(item, ffprobe_path, fallback_rate)
    cache[key] = info
    return info


def probe_audio(path: Path, ffprobe_path: Path | None = None) -> AudioInfo:
    """Probe an audio file for what sync checking needs.

    Format is not constrained here. Duration is converted to samples so the later
    comparison against a frame count stays integer.
    """
    raw = ffmpeg.probe_raw(path, ffprobe_path)
    for stream in raw["streams"]:
        if stream.get("codec_type") != "audio":
            continue
        sample_rate = int(stream.get("sample_rate", 0))
        samples = stream.get("duration_ts")
        if samples is None and stream.get("duration"):
            samples = round(float(stream["duration"]) * sample_rate)
        depth = int(stream.get("bits_per_raw_sample") or stream.get("bits_per_sample") or 0)
        return AudioInfo(
            path=path,
            duration_samples=int(samples or 0),
            sample_rate=sample_rate,
            channels=int(stream.get("channels", 0)),
            bit_depth=depth,
        )
    raise ffmpeg.FFprobeError(f"no audio stream in {path}")
