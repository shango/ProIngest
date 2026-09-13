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

    def test_suffix_is_forced(self, tmp_path: Path) -> None:
        assert batchfile.save(Batch(), tmp_path / "b.json").name == "b.pibatch"

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

    def test_a_failed_marker_outranks_a_done_status(self, tmp_path: Path) -> None:
        """Post-render QC wrote the marker, so it is the more recent truth."""
        present = tmp_path / "MELT0001_pl01_ref_HD_v01.mp4"
        present.write_bytes(b"x")
        present.with_name(present.name + ".failed").write_text("QC-111")
        batch = batch_with_deliverable(present, "done")
        saved = batchfile.save(batch, tmp_path / "b")
        assert batchfile.load(saved).rows[0].deliverables[0].status == "failed"

    def test_rendering_becomes_planned_when_nothing_landed(self, tmp_path: Path) -> None:
        """Nothing is rendering in a batch being opened, so the status is stale."""
        missing = tmp_path / "MELT0001_pl01_ref_HD_v01.mp4"
        batch = batch_with_deliverable(missing, "rendering")
        saved = batchfile.save(batch, tmp_path / "b")
        assert batchfile.load(saved).rows[0].deliverables[0].status == "planned"

    def test_reconciliation_can_be_skipped(self, tmp_path: Path) -> None:
        missing = tmp_path / "MELT0001_pl01_ref_HD_v01.mp4"
        batch = batch_with_deliverable(missing, "done")
        saved = batchfile.save(batch, tmp_path / "b")
        loaded = batchfile.load(saved, reconcile=False)
        assert loaded.rows[0].deliverables[0].status == "done"


class TestTurnoverPersistence:
    def test_turnover_fields_survive(self, tmp_path: Path) -> None:
        batch = Batch(
            turnovers=[
                Turnover(
                    "t1", tmp_path, number=1, month=2, day=23, year=2026, shooter="Daniel Luckett"
                )
            ]
        )
        saved = batchfile.save(batch, tmp_path / "b")
        restored = batchfile.load(saved).turnovers[0]
        assert restored.shooter == "Daniel Luckett", "the unnormalized name is kept (OQ-15)"
        assert restored.has_stringout_fields
