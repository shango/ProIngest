"""Batch file persistence, atomic writes and crash reconciliation (FR-11)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from proingest.core import batchfile, scan
from proingest.core.batchfile import BatchFileError
from proingest.core.models import Batch, Deliverable, InOut, ShotRow, Turnover
from tests.fixtures import media as fixtures


def batch_with_deliverable(path: Path, status: str) -> Batch:
    row = ShotRow(turnover_id="t1", clip_name="MELT0001_pl01", current=InOut(1001, 1240))
    row.deliverables.append(
        Deliverable(kind="ref", name=path.name, path=path, version=1, res="HD", status=status)  # type: ignore[arg-type]
    )
    return Batch(name="b", rows=[row])


class TestSaveAndLoad:
    def test_round_trip(self, tmp_path: Path) -> None:
        batch = Batch(name="melt", delivery_root=Path("/delivery"))
        saved = batchfile.save(batch, tmp_path / "b")
        assert saved.suffix == ".pibatch"
        assert batchfile.load(saved) == batch

    def test_suffix_is_appended(self, tmp_path: Path) -> None:
        """Appended rather than swapped for whatever follows the last dot (review, 2026-11-08):
        `b.json` was written as `b.pibatch`, and so was any name with a dot in it."""
        assert batchfile.save(Batch(), tmp_path / "b.json").name == "b.json.pibatch"
        assert batchfile.save(Batch(), tmp_path / "b.pibatch").name == "b.pibatch"

    def test_a_name_with_a_dot_is_its_own_batch(self, tmp_path: Path) -> None:
        """Review, 2026-11-08: `melt_10.30` was saved as `melt_10.pibatch`, over another batch."""
        other = batchfile.save(Batch(name="melt_10"), tmp_path / "melt_10")
        saved = batchfile.save(Batch(name="melt_10.30"), tmp_path / "melt_10.30")
        assert saved.name == "melt_10.30.pibatch"
        assert batchfile.load(other).name == "melt_10", "the other batch is untouched"
        assert batchfile.batch_path(tmp_path / "melt_10.30").stem == "melt_10.30"

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        saved = batchfile.save(Batch(), tmp_path / "deep" / "nested" / "b")
        assert saved.is_file()

    def test_written_file_is_readable_json(self, tmp_path: Path) -> None:
        saved = batchfile.save(Batch(name="melt"), tmp_path / "b")
        assert json.loads(saved.read_text())["name"] == "melt"

    def test_no_part_file_survives_a_save(self, tmp_path: Path) -> None:
        """The temp file is renamed, not copied, so nothing is left behind."""
        batchfile.save(Batch(), tmp_path / "b")
        assert list(tmp_path.glob("*.part")) == []

    def test_overwrite_replaces_cleanly(self, tmp_path: Path) -> None:
        path = tmp_path / "b"
        batchfile.save(Batch(name="first"), path)
        saved = batchfile.save(Batch(name="second"), path)
        assert batchfile.load(saved).name == "second"

    def test_a_full_scan_round_trips(self, tmp_path: Path) -> None:
        """The real shape, not a hand-built one: rows, media, qc and probe cache."""
        folder = tmp_path / "turnover001_02_23_2026_dan"
        fixtures.make_turnover(folder, shots=2, frames=4)
        batch = scan.scan_batch([folder], name="melt")

        saved = batchfile.save(batch, tmp_path / "melt")
        restored = batchfile.load(saved)
        assert restored == batch
        assert restored.rows[0].media is not None
        assert len(restored.probe_cache) == 2


class TestLoadFailures:
    def test_missing_file(self, tmp_path: Path) -> None:
        with pytest.raises(BatchFileError, match="does not exist"):
            batchfile.load(tmp_path / "nope.pibatch")

    def test_invalid_json(self, tmp_path: Path) -> None:
        path = tmp_path / "b.pibatch"
        path.write_text("{not json")
        with pytest.raises(BatchFileError, match="not valid JSON"):
            batchfile.load(path)

    def test_json_that_is_not_an_object(self, tmp_path: Path) -> None:
        path = tmp_path / "x.pibatch"
        path.write_text("[1, 2, 3]")
        with pytest.raises(BatchFileError, match="not a JSON object"):
            batchfile.load(path)

    def test_a_field_of_the_wrong_type(self, tmp_path: Path) -> None:
        path = tmp_path / "x.pibatch"
        path.write_text(json.dumps({"schema_version": 1, "rows": 5}))
        with pytest.raises(BatchFileError, match="could not be read"):
            batchfile.load(path)

    def test_a_file_that_cannot_be_opened(self, tmp_path: Path) -> None:
        path = tmp_path / "x.pibatch"
        path.mkdir()
        with pytest.raises(BatchFileError):
            batchfile.load(path)

    def test_unknown_schema_version(self, tmp_path: Path) -> None:
        path = tmp_path / "b.pibatch"
        data = Batch().to_dict()
        data["schema_version"] = 99
        path.write_text(json.dumps(data))
        with pytest.raises(BatchFileError, match="could not be read"):
            batchfile.load(path)


class TestBackup:
    def test_copies_an_existing_batch(self, tmp_path: Path) -> None:
        saved = batchfile.save(Batch(name="melt"), tmp_path / "b")
        copy = batchfile.backup(saved)
        assert copy is not None
        assert copy.name == "b.pibatch.bak"
        assert json.loads(copy.read_text())["name"] == "melt"

    def test_returns_none_when_there_is_nothing_to_copy(self, tmp_path: Path) -> None:
        assert batchfile.backup(tmp_path / "absent.pibatch") is None


class TestReconciliation:
    """The display must never lie after a crash."""

    def test_done_without_a_file_reverts_to_planned(self, tmp_path: Path) -> None:
        missing = tmp_path / "MELT0001_pl01_ref_HD_v01.mp4"
        batch = batch_with_deliverable(missing, "done")
        saved = batchfile.save(batch, tmp_path / "b")
        assert batchfile.load(saved).rows[0].deliverables[0].status == "planned"

    def test_done_with_a_file_stays_done(self, tmp_path: Path) -> None:
        present = tmp_path / "MELT0001_pl01_ref_HD_v01.mp4"
        present.write_bytes(b"x")
        batch = batch_with_deliverable(present, "done")
        saved = batchfile.save(batch, tmp_path / "b")
        assert batchfile.load(saved).rows[0].deliverables[0].status == "done"

    def test_rendering_becomes_done_when_the_file_landed(self, tmp_path: Path) -> None:
        """A file takes its final name only after it passed its checks (D11)."""
        present = tmp_path / "MELT0001_pl01_ref_HD_v01.mp4"
        present.write_bytes(b"x")
        batch = batch_with_deliverable(present, "rendering")
        saved = batchfile.save(batch, tmp_path / "b")
        assert batchfile.load(saved).rows[0].deliverables[0].status == "done"

    def test_rendering_becomes_planned_when_nothing_landed(self, tmp_path: Path) -> None:
        """Nothing is rendering in a batch being opened, so the status is stale."""
        missing = tmp_path / "MELT0001_pl01_ref_HD_v01.mp4"
        batch = batch_with_deliverable(missing, "rendering")
        saved = batchfile.save(batch, tmp_path / "b")
        assert batchfile.load(saved).rows[0].deliverables[0].status == "planned"

    @pytest.mark.parametrize("status", ["planned", "skipped"])
    def test_a_file_that_landed_under_a_stale_status_is_done(self, tmp_path: Path, status: str) -> None:
        """Review, 2026-11-08 (E1): a batch saved mid run still says planned or skipped for
        a file that landed later. A final name only exists after its checks (D11)."""
        present = tmp_path / "MELT0001_pl01_ref_HD_v01.mp4"
        present.write_bytes(b"x")
        batch = batch_with_deliverable(present, status)
        saved = batchfile.save(batch, tmp_path / "b")
        assert batchfile.load(saved).rows[0].deliverables[0].status == "done"

    def test_a_failed_deliverable_is_left_failed(self, tmp_path: Path) -> None:
        """A failed check waits for the editor's Re-scan (D11), whatever is on disk."""
        present = tmp_path / "MELT0001_pl01_ref_HD_v01.mp4"
        present.write_bytes(b"x")
        batch = batch_with_deliverable(present, "failed")
        saved = batchfile.save(batch, tmp_path / "b")
        assert batchfile.load(saved).rows[0].deliverables[0].status == "failed"

    def test_reconciliation_can_be_skipped(self, tmp_path: Path) -> None:
        missing = tmp_path / "MELT0001_pl01_ref_HD_v01.mp4"
        batch = batch_with_deliverable(missing, "done")
        saved = batchfile.save(batch, tmp_path / "b")
        loaded = batchfile.load(saved, reconcile=False)
        assert loaded.rows[0].deliverables[0].status == "done"


class TestSavingARunInFlight:
    """Review, 2026-11-08 (E1): nothing ever wrote `rendering`, so a crash mid run left the
    batch on disk saying what it said before the plan, and the next Run's version check saw
    the new files and rendered the shot again at the next version."""

    def test_what_is_in_flight_is_saved_as_rendering(self, tmp_path: Path) -> None:
        target = tmp_path / "MELT0001_pl01_ref_HD_v01.mp4"
        batch = batch_with_deliverable(target, "planned")
        saved = batchfile.save_in_flight(batch, tmp_path / "b", {target})
        on_disk = batchfile.load(saved, reconcile=False)
        assert on_disk.rows[0].deliverables[0].status == "rendering"
        assert batch.rows[0].deliverables[0].status == "planned", "the open batch is unchanged"

    def test_what_is_not_in_flight_keeps_its_status(self, tmp_path: Path) -> None:
        target = tmp_path / "MELT0001_pl01_ref_HD_v01.mp4"
        batch = batch_with_deliverable(target, "done")
        saved = batchfile.save_in_flight(batch, tmp_path / "b", set())
        assert batchfile.load(saved, reconcile=False).rows[0].deliverables[0].status == "done"

    def test_the_status_is_put_back_when_the_write_fails(self, tmp_path: Path) -> None:
        target = tmp_path / "MELT0001_pl01_ref_HD_v01.mp4"
        batch = batch_with_deliverable(target, "planned")
        blocker = tmp_path / "file"
        blocker.write_text("")
        with pytest.raises(OSError):
            batchfile.save_in_flight(batch, blocker / "b", {target})
        assert batch.rows[0].deliverables[0].status == "planned"

    def test_a_crash_after_it_reopens_as_what_landed(self, tmp_path: Path) -> None:
        landed = tmp_path / "MELT0001_pl01_ref_HD_v01.mp4"
        unfinished = tmp_path / "MELT0001_pl01_ref_4k_v01.mp4"
        batch = batch_with_deliverable(landed, "planned")
        batch.rows[0].deliverables.append(
            Deliverable(kind="ref", name=unfinished.name, path=unfinished, version=1, res="4k")
        )
        saved = batchfile.save_in_flight(batch, tmp_path / "b", {landed, unfinished})
        landed.write_bytes(b"x")
        assert [d.status for d in batchfile.load(saved).rows[0].deliverables] == ["done", "planned"]


class TestTurnoverPersistence:
    def test_turnover_fields_survive(self, tmp_path: Path) -> None:
        batch = Batch(
            turnovers=[
                Turnover("t1", tmp_path, number=1, month=2, day=23, year=2026, shooter="Daniel Luckett")
            ]
        )
        saved = batchfile.save(batch, tmp_path / "b")
        restored = batchfile.load(saved).turnovers[0]
        assert restored.shooter == "Daniel Luckett", "the unnormalized name is kept (OQ-15)"
