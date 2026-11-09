"""Reading and writing `.pibatch` files (FR-11).

Written temp-then-rename so a crash mid-write cannot truncate a batch, which is the
same atomic discipline the render pipeline uses for deliverables. A `.bak` copy is
taken when an existing file is opened, so the previous state survives one bad save.

The loader reconciles deliverable status against the filesystem, because FR-11 and
the non-functional requirements say the display must never lie after a crash.
"""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path

from proingest.core.models import Batch, Deliverable

log = logging.getLogger(__name__)

SUFFIX = ".pibatch"
BACKUP_SUFFIX = ".pibatch.bak"


class BatchFileError(RuntimeError):
    """The batch file could not be read."""


def batch_path(path: Path) -> Path:
    """`path` as the batch file it names: `.pibatch` appended unless it is there already.

    Appended rather than swapped in with `with_suffix`, which takes whatever follows the
    last dot for a suffix: `melt_10.30` became `melt_10.pibatch`, over a different batch
    (review, 2026-11-08). A save dialog does not always add the suffix itself.
    """
    return path if path.suffix == SUFFIX else path.with_name(path.name + SUFFIX)


def save(batch: Batch, path: Path) -> Path:
    """Write a batch atomically, to `batch_path(path)`.

    The temp file is created beside the target so the rename stays on one filesystem
    and is therefore atomic.
    """
    path = batch_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".part")
    temp.write_text(json.dumps(batch.to_dict(), indent=2), encoding="utf-8")
    temp.replace(path)
    return path


def save_in_flight(batch: Batch, path: Path, in_flight: set[Path]) -> Path:
    """Write a batch with the deliverables at `in_flight` marked `rendering`.

    What a run writes before its first job starts (review, 2026-11-08), so a crash
    during it reopens as what landed (`reconcile_with_filesystem`) rather than as the
    batch before the plan, whose next Run would render the shot again at the next
    version. Only the file says rendering: in the open batch a queued row stays as it
    is, because the shot list draws rendering from the live run (`ShotListModel.state_for`).
    """
    marked = [item for row in batch.rows for item in row.deliverables if item.path in in_flight]
    before = [item.status for item in marked]
    for item in marked:
        item.status = "rendering"
    try:
        return save(batch, path)
    finally:
        for item, status in zip(marked, before, strict=True):
            item.status = status


def load(path: Path, reconcile: bool = True) -> Batch:
    """Read a batch and, by default, reconcile deliverable status with what is on disk."""
    if not path.is_file():
        raise BatchFileError(f"batch file {path} does not exist")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise BatchFileError(f"batch file {path} could not be opened: {exc}") from exc
    except ValueError as exc:
        # JSONDecodeError and UnicodeDecodeError are both ValueErrors.
        raise BatchFileError(f"batch file {path} is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise BatchFileError(f"batch file {path} is not a JSON object")
    try:
        batch = Batch.from_dict(data)
    except (KeyError, TypeError, ValueError) as exc:
        raise BatchFileError(f"batch file {path} could not be read: {exc}") from exc
    if reconcile:
        reconcile_with_filesystem(batch)
    return batch


def backup(path: Path) -> Path | None:
    """Copy an existing batch to `.pibatch.bak`. Returns None when there is nothing to copy."""
    if not path.is_file():
        return None
    destination = path.with_suffix(BACKUP_SUFFIX)
    shutil.copy2(path, destination)
    return destination


def reconcile_with_filesystem(batch: Batch) -> None:
    """Correct deliverable status from what actually exists on disk.

    A batch saved as "done" that was interrupted before the file landed must not
    still claim done. A file only takes its final name after it passed its checks
    (D11), so one that is there did land, whatever the batch last said of it:
    rendering, or planned or skipped in a batch saved before the run got that far
    (review, 2026-11-08). Its frame checksums were never recorded, so QC-106 has
    nothing to compare it against; that is logged. A failed one is left failed: it
    waits for the editor's Re-scan (D11).

    One stat per deliverable, so the window calls this off the UI thread.
    """
    for row in batch.rows:
        for deliverable in row.deliverables:
            path = deliverable.path
            if deliverable.status in ("done", "exists"):
                if not path.exists():
                    deliverable.status = "planned"
            elif deliverable.status != "failed":
                # Nothing is rendering in a batch being opened.
                landed_unrecorded(deliverable)


def landed_unrecorded(deliverable: Deliverable) -> bool:
    """Mark a deliverable done if its final name is on disk. True when it was.

    Shared with the planner, which asks the same question of a row before it plans
    one: a file that landed after the batch was last saved is not rendered again.
    """
    if not deliverable.path.exists():
        if deliverable.status == "rendering":
            deliverable.status = "planned"
        return False
    log.info("%s is on disk though the batch did not record it landing; taken as done", deliverable.name)
    deliverable.status = "done"
    return True
