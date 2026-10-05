"""`core/expiry.py`: a packaged build stops loading work a calendar month after its
release, and says so in its last week (user, 2026-10-05)."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest

from proingest import __version__
from proingest.core import expiry
from proingest.core.expiry import Expiry, one_month_after


class TestOneMonthAfter:
    @pytest.mark.parametrize(
        ("released", "expires"),
        [
            (date(2026, 10, 5), date(2026, 11, 5)),
            (date(2026, 12, 15), date(2027, 1, 15)),
            (date(2026, 1, 31), date(2026, 2, 28)),
            (date(2028, 1, 31), date(2028, 2, 29)),
            (date(2026, 8, 31), date(2026, 9, 30)),
        ],
    )
    def test_it_is_a_calendar_month_kept_inside_a_shorter_one(self, released: date, expires: date) -> None:
        assert one_month_after(released) == expires


class TestExpiry:
    stamp = Expiry(date(2026, 10, 5))

    def test_it_expires_on_the_day_itself(self) -> None:
        assert not self.stamp.expired(date(2026, 11, 4))
        assert self.stamp.expired(date(2026, 11, 5))

    def test_it_warns_in_the_last_week_only(self) -> None:
        assert not self.stamp.warning(date(2026, 10, 28))
        assert self.stamp.warning(date(2026, 10, 29))
        assert self.stamp.warning(date(2026, 11, 4))
        assert not self.stamp.warning(date(2026, 11, 5)), "past it, the refusal says so instead"

    def test_the_messages_name_the_version_and_the_day(self) -> None:
        assert f"ProIngest {__version__} expired on 5 November 2026" in self.stamp.expired_message()
        assert "Install the next version" in self.stamp.expired_message()
        assert "expires tomorrow, on 5 November 2026" in self.stamp.warning_message(date(2026, 11, 4))
        assert "expires in 3 days" in self.stamp.warning_message(date(2026, 11, 2))


class TestTheStamp:
    def test_it_is_read_as_an_iso_date(self, tmp_path: Path) -> None:
        path = tmp_path / "release.txt"
        path.write_text("2026-10-05\n", encoding="utf-8")
        assert expiry.read_stamp(path) == Expiry(date(2026, 10, 5))

    def test_none_or_garbage_means_no_expiry(self, tmp_path: Path) -> None:
        assert expiry.read_stamp(tmp_path / "missing.txt") is None
        (tmp_path / "bad.txt").write_text("soon", encoding="utf-8")
        assert expiry.read_stamp(tmp_path / "bad.txt") is None

    def test_running_from_source_never_expires(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """A stamp a local build left behind must not lock out the tests or a developer."""
        old = tmp_path / "release.txt"
        old.write_text("2020-01-01", encoding="utf-8")
        monkeypatch.setattr(expiry, "RELEASE_FILE", old)
        monkeypatch.delattr(sys, "frozen", raising=False)
        assert expiry.current() is None
        assert expiry.refusal() is None

    def test_a_frozen_build_reads_its_stamp(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        stamp = tmp_path / "release.txt"
        stamp.write_text("2026-10-05", encoding="utf-8")
        monkeypatch.setattr(expiry, "RELEASE_FILE", stamp)
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        assert expiry.current() == Expiry(date(2026, 10, 5))
        assert expiry.refusal(date(2026, 11, 4)) is None
        refused = expiry.refusal(date(2026, 11, 5))
        assert refused is not None and "expired on 5 November 2026" in refused
