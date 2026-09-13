"""The scan running off the UI thread. `ui/scanner.py`, M5.4.

Most of these replace `core.scan.scan_turnover` with a stand-in, because what is under
test is the thread, the handover and the cancelling, and a real scan would make each
case cost a second of ffmpeg to prove something about Qt. One test at the end does run
the real thing, so that the stand-in cannot be the only thing this module is proved
against. The stand-in replaces it on `core.scan` itself, which is the module
`ui/scanner.py` reaches through, so nothing about the patch depends on how it imported.

Nothing here waits on a signal with `QSignalSpy.wait`: a signal that fires before the
wait starts leaves it sitting until the timeout. `pump_until` spins the event loop and
asks, which cannot lose a result that arrived early.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import QThread
from PySide6.QtWidgets import QApplication

from proingest.core import scan
from proingest.core.models import MediaInfo, ShotRow, Turnover
from proingest.ui.scanner import Scanner
from tests.fixtures import media as media_fixtures
from tests.fixtures.batches import row

TIMEOUT_MS = 30_000


@pytest.fixture
def scanner(qt_app: QApplication) -> Iterator[Scanner]:
    built = Scanner()
    yield built
    built.shutdown()


def pump_until(predicate: Callable[[], bool], timeout_ms: int = TIMEOUT_MS) -> bool:
    """Run the event loop until the predicate holds or the time is up."""
    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        QApplication.processEvents()
        if predicate():
            return True
        time.sleep(0.005)
    return predicate()


class Collected:
    """Everything one scan emitted, in the order it arrived."""

    def __init__(self, scanner: Scanner) -> None:
        self.results: list[tuple[Turnover, list[ShotRow], dict[str, MediaInfo]]] = []
        self.folders: list[Path] = []
        self.finished = False
        scanner.scanned.connect(lambda t, r, c: self.results.append((t, r, c)))
        scanner.started_folder.connect(self.folders.append)
        scanner.finished.connect(self._done)

    def _done(self) -> None:
        self.finished = True


def fake_scan(
    on_folder: Callable[[Path], None] | None = None,
) -> Callable[..., tuple[Turnover, list[ShotRow]]]:
    """A stand-in for `scan_turnover` that answers instantly."""

    def scan_turnover(
        folder: Path,
        turnover_id: str,
        settings: scan.ScanSettings | None = None,
        probe_cache: dict[str, MediaInfo] | None = None,
        timeline_path: Path | None = None,
    ) -> tuple[Turnover, list[ShotRow]]:
        if on_folder is not None:
            on_folder(folder)
        return Turnover(turnover_id=turnover_id, folder=folder), [row(turnover_id=turnover_id)]

    return scan_turnover


class TestWhereItRuns:
    def test_the_scan_happens_on_another_thread(
        self, scanner: Scanner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """CLAUDE.md forbids it on the UI thread, and a network mount is why."""
        threads: list[QThread] = []
        monkeypatch.setattr(
            scan,
            "scan_turnover",
            fake_scan(lambda _f: threads.append(QThread.currentThread())),
        )
        collected = Collected(scanner)
        scanner.start([(tmp_path, "t1")], scan.ScanSettings())

        assert pump_until(lambda: collected.finished)
        assert threads and threads[0] is not QThread.currentThread()

    def test_it_says_which_folder_it_is_on(
        self, scanner: Scanner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setattr(scan, "scan_turnover", fake_scan())
        collected = Collected(scanner)
        scanner.start([(tmp_path / "one", "t1")], scan.ScanSettings())

        assert pump_until(lambda: collected.finished)
        assert collected.folders == [tmp_path / "one"]

    def test_each_folder_comes_back_as_it_finishes(
        self, scanner: Scanner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Per folder rather than at the end, so a four turnover batch fills as it goes."""
        monkeypatch.setattr(scan, "scan_turnover", fake_scan())
        collected = Collected(scanner)
        scanner.start([(tmp_path / "a", "t1"), (tmp_path / "b", "t2")], scan.ScanSettings())

        assert pump_until(lambda: collected.finished)
        assert [turnover.turnover_id for turnover, _rows, _cache in collected.results] == ["t1", "t2"]


class TestTheHandover:
    def test_the_probe_cache_the_worker_gets_is_a_copy(
        self, scanner: Scanner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """The UI thread's dictionary is only ever written by the UI thread."""

        def scan_turnover(
            folder: Path,
            turnover_id: str,
            settings: scan.ScanSettings | None = None,
            probe_cache: dict[str, MediaInfo] | None = None,
            timeline_path: Path | None = None,
        ) -> tuple[Turnover, list[ShotRow]]:
            assert probe_cache is not None
            probe_cache["probed|1|2"] = media_fixtures.media_info_with_tags({})
            return Turnover(turnover_id=turnover_id, folder=folder), []

        monkeypatch.setattr(scan, "scan_turnover", scan_turnover)
        owned: dict[str, MediaInfo] = {}
        collected = Collected(scanner)
        scanner.start([(tmp_path, "t1")], scan.ScanSettings(), owned)

        assert pump_until(lambda: collected.finished)
        assert owned == {}
        assert "probed|1|2" in collected.results[0][2]

    def test_a_folder_that_raises_does_not_take_the_rest_with_it(
        self, scanner: Scanner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """`scan_turnover` reports a bad folder rather than raising, so this is a bug,
        and losing the three good folders to it would be a second one."""

        def scan_turnover(
            folder: Path, turnover_id: str, *args: object, **kwargs: object
        ) -> tuple[Turnover, list[ShotRow]]:
            if turnover_id == "t1":
                raise RuntimeError("something nobody planned for")
            return Turnover(turnover_id=turnover_id, folder=folder), []

        monkeypatch.setattr(scan, "scan_turnover", scan_turnover)
        collected = Collected(scanner)
        scanner.start([(tmp_path / "a", "t1"), (tmp_path / "b", "t2")], scan.ScanSettings())

        assert pump_until(lambda: collected.finished)
        assert [turnover.turnover_id for turnover, _rows, _cache in collected.results] == ["t2"]


class TestStartingAndStopping:
    def test_it_is_busy_while_it_runs_and_free_afterwards(
        self, scanner: Scanner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setattr(scan, "scan_turnover", fake_scan())
        collected = Collected(scanner)
        scanner.start([(tmp_path, "t1")], scan.ScanSettings())
        assert scanner.busy

        assert pump_until(lambda: collected.finished)
        assert not scanner.busy

    def test_a_second_scan_on_top_of_one_is_refused(
        self, scanner: Scanner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setattr(scan, "scan_turnover", fake_scan())
        collected = Collected(scanner)
        scanner.start([(tmp_path, "t1")], scan.ScanSettings())
        with pytest.raises(RuntimeError):
            scanner.start([(tmp_path, "t2")], scan.ScanSettings())
        assert pump_until(lambda: collected.finished)

    def test_no_folders_still_reports_finished(self, scanner: Scanner) -> None:
        """The window turns its progress bar off on `finished`, so it always fires."""
        collected = Collected(scanner)
        scanner.start([], scan.ScanSettings())
        assert collected.finished
        assert not scanner.busy

    def test_cancelling_stops_after_the_folder_in_flight(
        self, scanner: Scanner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setattr(scan, "scan_turnover", fake_scan(lambda _f: scanner.cancel()))
        collected = Collected(scanner)
        scanner.start([(tmp_path / "a", "t1"), (tmp_path / "b", "t2")], scan.ScanSettings())

        assert pump_until(lambda: collected.finished)
        assert [turnover.turnover_id for turnover, _rows, _cache in collected.results] == ["t1"]

    def test_shutdown_waits_for_the_thread(
        self, scanner: Scanner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """A `QThread` still running when its owner is collected is a crash on the way out."""
        monkeypatch.setattr(scan, "scan_turnover", fake_scan())
        scanner.start([(tmp_path, "t1")], scan.ScanSettings())
        thread = scanner._thread
        assert thread is not None
        scanner.shutdown()
        assert thread.isFinished()


def test_a_real_turnover_scans_through_the_worker(scanner: Scanner, tmp_path: Path) -> None:
    """The one case with no stand-in: core is really called and really answers."""
    folder = tmp_path / "turnover001_02_23_2026_danielluckett"
    media_fixtures.make_turnover(folder, shots=1, frames=6)
    collected = Collected(scanner)
    scanner.start([(folder, "t1")], scan.ScanSettings(rules=media_fixtures.SMALL_RULES))

    assert pump_until(lambda: collected.finished)
    turnover, rows, cache = collected.results[0]
    assert turnover.shooter == "danielluckett"
    assert len(rows) == 1
    assert rows[0].media is not None
    assert cache, "the worker's probe cache comes back so the batch can keep it"
