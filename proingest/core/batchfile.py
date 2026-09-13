"""Reading and writing `.pibatch` files (FR-11).

Written temp-then-rename so a crash mid-write cannot truncate a batch, which is the
same atomic discipline the render pipeline uses for deliverables. A `.bak` copy is
taken when an existing file is opened, so the previous state survives one bad save.

The loader reconciles deliverable status against the filesystem, because FR-11 and
the non-functional requirements say the display must never lie after a crash.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from proingest.core.models import Batch

SUFFIX = ".pibatch"
BACKUP_SUFFIX = ".pibatch.bak"

FAILED_MARKER = ".failed"
"""A deliverable that failed post-render QC keeps a sidecar so the file is not trusted."""


class BatchFileError(RuntimeError):
    """The batch file could not be read."""


def save(batch: Batch, path: Path) -> Path:
    """Write a batch atomically.

    The temp file is created beside the target so the rename stays on one filesystem
    and is therefore atomic.
    """
    path = path.with_suffix(SUFFIX)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".part")
    temp.write_text(json.dumps(batch.to_dict(), indent=2), encoding="utf-8")
    temp.replace(path)
    return path


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
    still claim done. A `.failed` marker beside a deliverable outranks the recorded
    status, because post-render QC put it there.
    """
    for row in batch.rows:
        for deliverable in row.deliverables:
            path = deliverable.path
            if path.with_name(path.name + FAILED_MARKER).exists():
                deliverable.status = "failed"
            elif deliverable.status in ("done", "exists") and not path.exists():
                deliverable.status = "planned"
            elif deliverable.status == "rendering":
                # Nothing is rendering in a batch being opened.
                deliverable.status = "failed" if path.exists() else "planned"
