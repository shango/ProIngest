"""The only place ffmpeg and ffprobe are invoked.

Nothing else in the codebase shells out. Every command is logged verbatim before it
runs so the user can paste it into a terminal and reproduce a render, which is a
stated requirement in CLAUDE.md.

Binary resolution order is: an explicit Settings override, then the bundled binary
for this platform, then PATH. The bundled binaries are Windows `.exe` files, so on a
non-Windows dev machine the lookup falls through to PATH on its own.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

BUNDLED_DIR = Path(__file__).resolve().parent.parent / "resources" / "ffmpeg"

DEFAULT_TIMEOUT = 120


class FFmpegNotFound(RuntimeError):
    """Neither the bundled binary, the override, nor PATH produced a usable tool."""


class FFprobeError(RuntimeError):
    """ffprobe ran but could not read the file. Reported as QC-014."""


def _platform_binary(tool: str) -> str:
    return f"{tool}.exe" if os.name == "nt" else tool


def resolve_tool(tool: str, override: Path | None = None) -> Path:
    """Locate `ffmpeg` or `ffprobe`.

    An override is honoured whether it names the binary itself or the folder holding
    it, because both are natural things to paste into a settings field.
    """
    if override is not None:
        candidate = override / _platform_binary(tool) if override.is_dir() else override
        if candidate.is_file():
            return candidate
        raise FFmpegNotFound(f"{tool} override {override} does not exist")

    bundled = BUNDLED_DIR / _platform_binary(tool)
    if bundled.is_file():
        return bundled

    found = shutil.which(tool)
    if found:
        return Path(found)

    raise FFmpegNotFound(
        f"{tool} not found. Looked for a Settings override, then {bundled}, then PATH. "
        f"Run `python build/fetch_ffmpeg.py` to populate the bundled binaries."
    )


def run(command: list[str], timeout: int = DEFAULT_TIMEOUT) -> subprocess.CompletedProcess[str]:
    """Run a command, logging it verbatim first. Does not raise on a non-zero exit."""
    log.info("running: %s", " ".join(command))
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def probe_raw(path: Path, ffprobe: Path | None = None) -> dict[str, Any]:
    """Return ffprobe's JSON for one file.

    Raises FFprobeError when the file cannot be read, which the caller turns into
    QC-014 rather than letting it escape.
    """
    tool = ffprobe or resolve_tool("ffprobe")
    command = [
        str(tool),
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(path),
    ]
    result = run(command)
    if result.returncode != 0:
        raise FFprobeError(f"ffprobe failed on {path}: {result.stderr.strip()}")
    try:
        parsed: dict[str, Any] = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise FFprobeError(f"ffprobe returned unreadable JSON for {path}: {exc}") from exc
    if not parsed.get("streams"):
        raise FFprobeError(f"ffprobe found no streams in {path}")
    return parsed


def count_frames(path: Path, ffprobe: Path | None = None) -> int:
    """Exact frame count by decoding. Slow, so it is only used by QC-111."""
    tool = ffprobe or resolve_tool("ffprobe")
    command = [
        str(tool),
        "-v",
        "error",
        "-count_frames",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=nb_read_frames",
        "-print_format",
        "json",
        str(path),
    ]
    result = run(command, timeout=600)
    if result.returncode != 0:
        raise FFprobeError(f"frame count failed on {path}: {result.stderr.strip()}")
    streams = json.loads(result.stdout).get("streams", [])
    if not streams:
        raise FFprobeError(f"no video stream in {path}")
    return int(streams[0]["nb_read_frames"])


@dataclass(frozen=True)
class ToolInfo:
    """Recorded in every QC log, per docs/PACKAGING.md."""

    path: Path
    version: str

    def __str__(self) -> str:
        return self.version


def tool_info(tool: str = "ffmpeg", override: Path | None = None) -> ToolInfo:
    """First line of `-version`, which carries the build string we pin in the lock file."""
    path = resolve_tool(tool, override)
    result = run([str(path), "-hide_banner", "-version"], timeout=30)
    first_line = result.stdout.splitlines()[0].strip() if result.stdout else "unknown"
    return ToolInfo(path=path, version=first_line)


@lru_cache(maxsize=1)
def available_encoders(ffmpeg: Path | None = None) -> frozenset[str]:
    """Encoder names this build supports. Cached; the binary does not change at runtime."""
    path = ffmpeg or resolve_tool("ffmpeg")
    result = run([str(path), "-hide_banner", "-encoders"], timeout=30)
    names = set()
    for line in result.stdout.splitlines():
        parts = line.split()
        # Encoder rows look like " V....D libx264   libx264 H.264 ..."
        if len(parts) >= 2 and len(parts[0]) == 6 and parts[0][0] in "VAS":
            names.add(parts[1])
    return frozenset(names)


def has_nvenc(ffmpeg: Path | None = None) -> bool:
    """Whether NVENC H.264 encoding is compiled in.

    Presence in the build does not prove a working NVIDIA GPU is attached; FR-7 wants
    detection at startup, and an actual encode attempt is the only real proof.
    """
    return "h264_nvenc" in available_encoders(ffmpeg)
