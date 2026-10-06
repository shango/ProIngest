"""When this build stops loading work: one calendar month after its release (user, 2026-10-05).

The release date is the day the app was built. `build/build.py` writes it to
`RELEASE_FILE`, which is untracked and ships inside the bundle. Only a frozen app
expires: running from source (`python -m proingest`, `ProIngest.command`, the tests, CI)
never does, so a stale stamp left by a local build cannot lock a developer out.

It reads the computer's clock, so it asks the editor to update rather than enforcing it.
"""

from __future__ import annotations

import calendar
import logging
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from proingest import __version__

log = logging.getLogger(__name__)

RELEASE_FILE = Path(__file__).resolve().parent.parent / "resources" / "release.txt"
"""One ISO date, `2026-10-05`. Written by `build/build.py`, never committed."""

WARNING_DAYS = 7
"""The last week before expiry, when the window says it is coming (user, 2026-10-05)."""


def one_month_after(released: date) -> date:
    """The same day next month, or that month's last day when it is shorter (31 Jan -> 28 Feb)."""
    year, month = (released.year + 1, 1) if released.month == 12 else (released.year, released.month + 1)
    return date(year, month, min(released.day, calendar.monthrange(year, month)[1]))


@dataclass(frozen=True)
class Expiry:
    released: date

    @property
    def expires(self) -> date:
        return one_month_after(self.released)

    def expired(self, today: date) -> bool:
        return today >= self.expires

    def days_left(self, today: date) -> int:
        return (self.expires - today).days

    def warning(self, today: date) -> bool:
        return not self.expired(today) and self.days_left(today) <= WARNING_DAYS

    def expired_message(self) -> str:
        return (
            f"ProIngest {__version__} expired on {_long(self.expires)}, one month after its release.\n\n"
            "Install the next version of ProIngest to continue."
        )

    def warning_message(self, today: date) -> str:
        days = self.days_left(today)
        when = "tomorrow" if days == 1 else f"in {days} days"
        return (
            f"ProIngest {__version__} expires {when}, on {_long(self.expires)}. "
            "Install the next version before then."
        )


def _long(day: date) -> str:
    return f"{day.day} {day:%B %Y}"


def read_stamp(path: Path) -> Expiry | None:
    """The stamp at `path`, or None when there is none or it does not read as a date."""
    try:
        return Expiry(date.fromisoformat(path.read_text(encoding="utf-8").strip()))
    except (OSError, ValueError) as exc:
        log.warning("no release date in %s (%s): this build does not expire", path, exc)
        return None


def current() -> Expiry | None:
    """This build's expiry, or None when it is running from source."""
    if not getattr(sys, "frozen", False):
        return None
    return read_stamp(RELEASE_FILE)


def refusal(today: date | None = None) -> str | None:
    """The message to refuse work with, or None while this build may still load it."""
    expiry = current()
    if expiry is None or not expiry.expired(today or date.today()):
        return None
    return expiry.expired_message()
