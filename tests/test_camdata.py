"""Reading camData side files (OQ-11's default, QC-053).

The files arrive as RTF as often as plain text, so both are pinned here. The point of
the RTF half is not that it parses RTF - it does not - but that a "save as rich text"
camera report still yields its pairs instead of one 200 character key.
"""

from __future__ import annotations

from pathlib import Path

from proingest.core import camdata

RTF = (
    "{\\rtf1\\ansi\\ansicpg1252\\cocoartf2709\n"
    "{\\fonttbl\\f0\\fswiss\\fcharset0 Helvetica;}\n"
    "{\\*\\expandedcolortbl;;}\n"
    "\\f0\\fs24 \\cf0 Camera: ARRI Alexa 35\\\n"
    "Lens: 32mm Signature Prime\\\n"
    "Filter: ND0.9\\\n"
    "Shot at 14:32\\\n"
    "Notes: handheld, 48\\'b0 shutter\\\n"
    "}"
)

PLAIN = "Camera: RED V-Raptor\nISO: 800\nTime In: 14:32\n\nnot a pair at all\n"


def write(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


class TestPlainText:
    def test_pairs_are_read_in_order(self, tmp_path: Path) -> None:
        pairs = camdata.parse(write(tmp_path, "a.txt", PLAIN))
        assert list(pairs) == ["Camera", "ISO", "Time In"]
        assert pairs["Camera"] == "RED V-Raptor"

    def test_a_value_may_contain_a_colon(self, tmp_path: Path) -> None:
        """Only the first colon splits, so a timecode or a time of day survives."""
        assert camdata.parse(write(tmp_path, "a.txt", PLAIN))["Time In"] == "14:32"

    def test_a_line_that_is_not_a_pair_is_dropped(self, tmp_path: Path) -> None:
        assert "not a pair at all" not in camdata.parse(write(tmp_path, "a.txt", PLAIN))

    def test_a_file_with_no_pairs_reads_as_empty(self, tmp_path: Path) -> None:
        assert camdata.parse(write(tmp_path, "a.txt", "free prose, no pairs\n")) == {}

    def test_a_repeated_key_takes_the_later_value(self, tmp_path: Path) -> None:
        """These are hand written: a correction is added below, not edited in place."""
        text = "Lens: 32mm\nLens: 40mm\n"
        assert camdata.parse(write(tmp_path, "a.txt", text))["Lens"] == "40mm"

    def test_a_prose_line_does_not_become_a_key(self, tmp_path: Path) -> None:
        long_prose = "x" * 100 + ": tail\n"
        assert camdata.parse(write(tmp_path, "a.txt", long_prose)) == {}


class TestRichText:
    def test_the_pairs_survive_the_markup(self, tmp_path: Path) -> None:
        pairs = camdata.parse(write(tmp_path, "a.rtf", RTF))
        assert pairs["Camera"] == "ARRI Alexa 35"
        assert pairs["Lens"] == "32mm Signature Prime"
        assert pairs["Filter"] == "ND0.9"

    def test_every_line_is_its_own_pair(self, tmp_path: Path) -> None:
        """The failure this guards: one key holding the whole document."""
        pairs = camdata.parse(write(tmp_path, "a.rtf", RTF))
        assert len(pairs) == 5
        assert all(len(key) < 20 for key in pairs)

    def test_a_prose_line_with_a_colon_becomes_a_pair_anyway(self, tmp_path: Path) -> None:
        """Known noise, not a defect: `Shot at 14:32` reads as `Shot at 14` = `32`.

        OQ-11 says parse every `key: value` line and dump them all, so the alternative
        is a list of keys that count as real, which is exactly the kind of table that
        looks right and is not. The noise lands in one sheet of the QC log where a
        human can see it, and QC-053 reports the count rather than vouching for it.
        """
        assert camdata.parse(write(tmp_path, "a.rtf", RTF))["Shot at 14"] == "32"

    def test_an_escaped_character_is_decoded(self, tmp_path: Path) -> None:
        assert camdata.parse(write(tmp_path, "a.rtf", RTF))["Notes"] == "handheld, 48° shutter"

    def test_the_font_table_is_not_a_pair(self, tmp_path: Path) -> None:
        assert not any("fonttbl" in key for key in camdata.parse(write(tmp_path, "a.rtf", RTF)))

    def test_plain_text_is_left_alone(self) -> None:
        """The strip only runs on something that opens like RTF."""
        assert camdata.strip_rtf(PLAIN) == PLAIN
