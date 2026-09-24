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

from proingest.core import exr, ffmpeg
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
        """Everything whose base name equals `stem` in any case, sequences and files alike.

        In any case because the CSV's `File Name` is typed by a person and `c0145.mp4`
        names `C0145.MP4` (F27). Two files differing only in case are then QC-013.
        """
        key = stem.casefold()
        matches: list[Sequence | FileEntry] = [s for s in self.sequences if s.base.casefold() == key]
        matches.extend(entry for entry in self.singles if entry.stem.casefold() == key)
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
        key = stem.casefold()
        return [
            entry
            for entry in self.singles
            if entry.stem.casefold() == key and entry.suffix in AUDIO_EXTENSIONS
        ]


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


STANDARD_RATES = tuple(
    FrameRate(n, d)
    for n, d in (
        (24000, 1001),
        (24, 1),
        (25, 1),
        (30000, 1001),
        (30, 1),
        (48, 1),
        (50, 1),
        (60000, 1001),
        (60, 1),
    )
)
"""The rates a camera records at, which an averaged rate is rounded to."""

RATE_TOLERANCE = 0.001
"""How far an averaged rate may sit from a standard one and still be it: 0.1%."""


def _stated_rate(stream: dict[str, Any]) -> FrameRate:
    """The rate a movie file runs at: `r_frame_rate`, unless the average says otherwise.

    `r_frame_rate` is ffprobe's lowest rate that every timestamp fits on. A file whose
    timestamps are uneven, as the iPhone writes them, reports a grid like 480/1 there
    while it plays at 24 (Turnover121, 2026-09-23: 320 frames in 13.33 s). When the two
    disagree the average is the truth, rounded to the nearest standard rate within 0.1%
    because an average over uneven timestamps is never exact.
    """
    stated = _rate_from_string(stream.get("r_frame_rate", "24/1"))
    numerator, _, denominator = str(stream.get("avg_frame_rate", "0/0")).partition("/")
    if not numerator.isdigit() or not denominator.isdigit() or 0 in (int(numerator), int(denominator)):
        return stated
    measured = int(numerator) / int(denominator)
    if measured == stated.as_float():
        return stated
    nearest = min(STANDARD_RATES, key=lambda rate: abs(rate.as_float() - measured))
    if abs(nearest.as_float() - measured) <= measured * RATE_TOLERANCE:
        return nearest
    return stated


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


def _is_drop_frame(probe: dict[str, Any]) -> bool:
    """Whether the media states drop-frame timecode: a `;` before the frames (QC-027)."""
    sources: list[dict[str, Any]] = [probe.get("format", {}).get("tags", {})]
    sources.extend(stream.get("tags", {}) for stream in probe.get("streams", []))
    return any(";" in str(tags.get("timecode") or tags.get("TIMECODE") or "") for tags in sources)


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

    header = _exr_header(target) if isinstance(item, Sequence) else None
    if isinstance(item, Sequence):
        # ffprobe invents 25/1 for a single frame, so it is never a source here.
        stated = _exr_stated_rate(header)
        frame_count, start_frame = item.count, item.first
    else:
        stated = _stated_rate(stream)
        # Frame count is a property of the file, so it counts at the file's own rate.
        frame_count, start_frame = _container_frame_count(stream, stated), 0

    rate = fallback_rate or stated or FrameRate(24)
    # `is None` and not `or`: 00:00:00:00 is frame 0, a timecode, not the absence of one (F8).
    timecode = _timecode_from(raw, rate)
    if timecode is None:
        timecode = _exr_timecode(header, rate)
    drop_frame = _is_drop_frame(raw)

    return MediaInfo(
        path=target,
        codec=str(stream.get("codec_name", "")),
        pixel_format=str(stream.get("pix_fmt", "")),
        width=int(stream.get("width", 0)),
        height=int(stream.get("height", 0)),
        rate=rate,
        frame_count=frame_count,
        start_frame=start_frame,
        start_timecode=timecode,
        drop_frame=drop_frame,
        is_sequence=isinstance(item, Sequence),
        has_audio=has_audio,
        audio_channels=channels,
        audio_sample_rate=sample_rate,
        audio_bit_depth=depth,
        size=size,
        mtime=mtime,
        stated_rate=stated,
        tags=tags,
        color_space=_color_tag(stream, "color_space"),
        color_range=_color_tag(stream, "color_range"),
        color_transfer=_color_tag(stream, "color_transfer"),
        color_primaries=_color_tag(stream, "color_primaries"),
    )


def _color_tag(stream: dict[str, Any], key: str) -> str:
    """A colour tag, or empty when the stream states none; ffprobe says "unknown"."""
    value = str(stream.get(key, ""))
    return "" if value in ("", "unknown", "unspecified") else value


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


def _exr_header(first_frame: Path) -> exr.ExrHeader | None:
    """The first frame's header, read once for everything the probe wants from it.

    Reading an EXR header decodes the frame with it in the pinned binding, and the
    sequence lives on a network mount, so it is read here and handed to the two
    readers below. A header that will not parse is not fatal: the row simply has no
    stated rate and no timecode, which QC-028 reports. QC-014 covers media that is
    unreadable outright.
    """
    if first_frame.suffix.lower() != ".exr":
        return None
    try:
        return exr.read_header(first_frame)
    except exr.ExrError:
        return None


def _exr_stated_rate(header: exr.ExrHeader | None) -> FrameRate | None:
    """The rate an EXR sequence claims in its header, if it claims one at all."""
    if header is None or header.frames_per_second is None:
        return None
    return FrameRate(header.frames_per_second[0], header.frames_per_second[1])


def _exr_timecode(header: exr.ExrHeader | None, rate: FrameRate) -> int | None:
    """EXR carries its timecode in a header attribute that ffprobe does not report."""
    if header is None:
        return None
    try:
        return exr.header_timecode_frames(header, rate.as_float())
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
