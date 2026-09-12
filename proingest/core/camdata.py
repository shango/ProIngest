"""Reading the camera data side file.

OQ-11's default: the file is `key: value` lines and every pair goes to the QC log's
Camera Data sheet. Nobody has specified more than that, and nothing here assumes more:
unrecognised lines are dropped rather than guessed at, and no key is special.

The files really arrive as RTF as often as plain text (34 of the studio tracker's
camData entries are `.rtf`), which is why this strips RTF before looking for pairs.
That strip is deliberately not an RTF parser. It handles what a text editor's "save as
rich text" produces - control words, escaped characters, a font table - and anything
more elaborate simply yields fewer pairs, which is visible in QC-053's count rather
than silently wrong.
"""

from __future__ import annotations

import re
from pathlib import Path

_RTF_DISCARDED_GROUP = re.compile(r"\{\\\*.*?\}", re.DOTALL)
"""`{\\*\\...}` is RTF for "ignore this group if you do not understand it"."""

_RTF_LINE_BREAK = re.compile(r"\\(?:par|line)\b|\\\n")
_RTF_CONTROL_WORD = re.compile(r"\\[a-zA-Z]+-?\d*\s?")
_RTF_HEX_ESCAPE = re.compile(r"\\'([0-9a-fA-F]{2})")
_RTF_ESCAPED_CHAR = re.compile(r"\\([\\{}])")

KEY_VALUE = re.compile(r"^\s*(?P<key>[^:]{1,80}?)\s*:\s*(?P<value>.*?)\s*$")
"""One `key: value` line. The key is bounded so a prose line with a colon in it,
which is what a free text camera report looks like, does not become a 200 character
key. Everything after the first colon is the value, so `Time: 14:32` survives."""


def strip_rtf(text: str) -> str:
    """Plain text out of an RTF document, good enough to find `key: value` lines in."""
    if not text.lstrip().startswith(r"{\rtf"):
        return text
    text = _RTF_DISCARDED_GROUP.sub("", text)
    text = _RTF_LINE_BREAK.sub("\n", text)
    text = _RTF_HEX_ESCAPE.sub(lambda m: bytes([int(m[1], 16)]).decode("cp1252", "replace"), text)
    text = _RTF_CONTROL_WORD.sub("", text)
    text = _RTF_ESCAPED_CHAR.sub(r"\1", text)
    return text.replace("{", "").replace("}", "")


def parse(path: Path) -> dict[str, str]:
    """Every `key: value` pair in a camData file, in the order it appears.

    A later repeat of a key wins, which is the only behaviour a dict can have and is
    also the right one: these files are written by hand and a corrected line is added
    below rather than edited in place.

    Returns an empty dict for a file that holds no pairs. Unreadable is the caller's
    problem to report, so OSError and UnicodeDecodeError travel.
    """
    text = strip_rtf(path.read_text(encoding="utf-8", errors="replace"))
    pairs: dict[str, str] = {}
    for line in text.splitlines():
        match = KEY_VALUE.match(line)
        if match and match["key"] and match["value"]:
            pairs[match["key"]] = match["value"]
    return pairs
