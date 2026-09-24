"""Where the tool's log goes, and how a worker process gets its lines into it.

FR-13 asks for three things: a rotating log file, **every ffmpeg command line in it**,
and an in-app panel. This module is the first two. It is core rather than UI because
the second one is the interesting half and it happens inside a spawned render worker,
which knows nothing about Qt and must not.

**The worker half is the part that was missing rather than merely unconfigured.**
`core/ffmpeg.py` has logged every command verbatim since M1, but a render runs in a
process started by `multiprocessing`'s spawn context, so the child is a fresh
interpreter whose root logger has no handlers at all. `logging.lastResort` prints
WARNING and above to stderr and drops everything below it, so an `INFO` command line
logged in a worker went nowhere: not to the console, not to a file, and not to the
panel FR-13 asks for. Every ffmpeg invocation a *render* makes is in that position, so
the requirement was false for the commands that matter most. The fix is a
`QueueHandler` in the worker and a listener in the parent, which is the arrangement the
logging cookbook prescribes for exactly this and the only one that keeps a single
process writing the file.

**One process writes the log file.** A `TimedRotatingFileHandler` renames the file it
is holding open, so two processes rotating the same path is how a day's log gets lost.
Workers therefore hold no file handler; they hold a queue.

**The path comes from `ui/paths.py`**, the same arrangement `core/settings.py` uses and
for the same reason: UI_SPEC section 11 says Qt answers where a folder is, core imports
no Qt, so every function here takes the folder as an argument. The CLI has no Qt and
logs to the console only; `_launch_ui` is the one path that imports PySide6, and it is
also the one that writes a file.
"""

from __future__ import annotations

import csv
import logging
import logging.handlers
import re
from multiprocessing.queues import Queue as MPQueue
from pathlib import Path

LOG_FILENAME = "proingest.log"
"""The file being written now. Rotated copies are dated; PACKAGING.md "Runtime locations"."""

BACKUP_COUNT = 14
"""Days kept. PACKAGING.md. A fortnight is long enough to cover the turnover before last."""

DATE_SUFFIX = "%Y%m%d"
"""What a rotated file is dated with, giving `proingest-20260913.log`.

Not the handler's own default of `%Y-%m-%d`, because PACKAGING.md names the format and
a folder of logs is read by a person sorting filenames. `_DATE_PATTERN` has to be set
alongside it: see `file_handler`.
"""

_DATE_PATTERN = re.compile(r"(?<!\d)\d{8}(?!\d)")
"""How `getFilesToDelete` finds the date in a name this module's `namer` produced.

The handler builds its own from `when`, and it would be `\\d{4}-\\d{2}-\\d{2}`, which
matches nothing in `proingest-20260913.log`. A pattern that matches nothing does not
raise: it silently finds no files to delete, and `BACKUP_COUNT` quietly stops being
true. `tests/test_logsetup.py` pins the pruning for that reason.
"""

CONSOLE_FORMAT = "%(levelname)s %(name)s: %(message)s"

FILE_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"

DEFAULT_LEVEL = logging.INFO
"""What the app runs at. INFO is the level the ffmpeg command lines are logged at, and
FR-13 asks for them, so anything quieter would deliver a log with the one thing the
requirement names missing from it."""

LEVEL_NAMES: tuple[str, ...] = ("Debug", "Info", "Warning", "Error")
"""What the Settings page's Advanced section offers, quietest last.

Stored in `settings.json` by **name** rather than as a number, because a settings file
is read by a person now and then and `"log_level": 20` says nothing. Debug is offered
because it is the one that answers "what did the tool actually ask ffmpeg for", which is
the question a support conversation starts with.
"""


def level_of(name: str) -> int:
    """A name from `LEVEL_NAMES` as a logging level. Anything else is the default.

    Anything else includes a settings file written by a later version that grew a level
    this one does not know, which is a file to read as well as possible rather than an
    error to raise: `core/settings.py` says why a settings file is disposable.
    """
    level = logging.getLevelNamesMapping().get(name.upper())
    return level if name.capitalize() in LEVEL_NAMES and level is not None else DEFAULT_LEVEL


def name_of(level: int) -> str:
    """The `LEVEL_NAMES` entry for a level, for putting the page back as it was."""
    return logging.getLevelName(level).capitalize()


SHOT_FIELD = "shot"
"""The attribute a render worker stamps a record with, naming the shot it is about.

FR-13's log panel filters by row, and a record has no idea which row it belongs to:
`ffmpeg.run` logs a command line and knows only the command. `core/render.py` stamps
it, because the worker is the one place that holds both the job and the logging call.
Records made anywhere else do not carry it, so read it with `shot_of`.
"""


def shot_of(record: logging.LogRecord) -> str:
    """Which shot a record is about, or empty when it is about nothing in particular."""
    value = getattr(record, SHOT_FIELD, "")
    return value if isinstance(value, str) else ""


def file_handler(log_dir: Path) -> logging.handlers.TimedRotatingFileHandler:
    """The rotating file, created along with its folder.

    `suffix` and `extMatch` are set together on purpose. The first decides what a
    rotated file is called and the second is what finds the date in that name again
    when it is time to delete the fifteenth one; the handler derives both from `when`,
    and overriding one without the other leaves rotation working and pruning silently
    doing nothing.
    """
    log_dir.mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.TimedRotatingFileHandler(
        log_dir / LOG_FILENAME,
        when="midnight",
        backupCount=BACKUP_COUNT,
        encoding="utf-8",
    )
    handler.suffix = DATE_SUFFIX
    handler.extMatch = _DATE_PATTERN
    handler.namer = _dated_name
    handler.setFormatter(logging.Formatter(FILE_FORMAT))
    return handler


def _dated_name(default_name: str) -> str:
    """`/logs/proingest.log.20260913` as the handler builds it, to `proingest-20260913.log`."""
    base, _, date = default_name.rpartition(".")
    return str(Path(base).with_name(f"{Path(base).stem}-{date}{Path(base).suffix}"))


_INSTALLED: list[logging.Handler] = []
"""The handlers this module put on the root logger, so a second `configure` can take
them off again without touching anybody else's. A test runner's own handler is somebody
else's, and closing it is how a suite loses its captured output halfway through."""


def configure(
    log_dir: Path | None = None,
    level: int = DEFAULT_LEVEL,
    stream: bool = True,
) -> None:
    """Set the root logger up for this process, replacing this module's own handlers.

    `logging.basicConfig` is what this stands in for, and it does nothing at all when
    handlers already exist, which is the behaviour that makes a log level impossible to
    apply and a second call impossible to reason about.
    """
    root = logging.getLogger()
    for existing in _INSTALLED:
        root.removeHandler(existing)
        existing.close()
    _INSTALLED.clear()
    if stream:
        console = logging.StreamHandler()
        console.setFormatter(logging.Formatter(CONSOLE_FORMAT))
        _INSTALLED.append(console)
    if log_dir is not None:
        _INSTALLED.append(file_handler(log_dir))
    for handler in _INSTALLED:
        root.addHandler(handler)
    root.setLevel(level)


def set_level(level: int) -> None:
    """Change what is logged from now on, without rebuilding the handlers.

    The Settings page's Advanced section writes here. Handlers keep their own level at
    zero, so the root's level is the only gate and one call moves all of it.
    """
    logging.getLogger().setLevel(level)


def install_worker_handler(
    queue: MPQueue[logging.LogRecord | None], level: int
) -> logging.handlers.QueueHandler:
    """In a spawned worker: send every record to the parent instead of handling it.

    `level` is the parent's own effective level, handed over at process creation. The
    worker filters against it rather than sending everything and letting the parent
    decide, because the alternative is pickling a record per frame to throw it away.

    The handler comes back so the caller can hang a filter on it, which is how
    `core/render.py` stamps a record with the shot it is about.
    """
    root = logging.getLogger()
    for existing in list(root.handlers):
        root.removeHandler(existing)
    handler = logging.handlers.QueueHandler(queue)
    root.addHandler(handler)
    root.setLevel(level)
    return handler


class _Republish(logging.Handler):
    """Hand a worker's record to this process's loggers as if it were made here.

    `Logger.handle` skips the level check and goes straight to the handlers, which is
    what is wanted: the record has already passed the level test in the worker, and
    testing it twice against a level that may have changed mid-run would drop lines
    that were correctly emitted.
    """

    def emit(self, record: logging.LogRecord) -> None:
        logging.getLogger(record.name).handle(record)


def start_listener(queue: MPQueue[logging.LogRecord | None]) -> logging.handlers.QueueListener:
    """In the parent: a thread draining the worker queue into this process's handlers.

    Started here; the caller stops it. `core/render.execute` owns one per run, which is
    also what owns the queue, so nothing outside a render has to know this exists.
    """
    listener = logging.handlers.QueueListener(queue, _Republish())
    listener.start()
    return listener


# --- The diagnostics export: every kept log file as one CSV. ---

EXPORT_COLUMNS = ("Time", "Level", "Source", "Message", "File")

_LINE = re.compile(
    r"^(?P<time>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) "
    r"(?P<level>[A-Z]+)\s+(?P<source>[^:\s]+): (?P<message>.*)$"
)
"""One line as `FILE_FORMAT` writes it. A line that does not match continues the one
before it: a traceback, or a message with a newline in it."""


def log_files(log_dir: Path) -> list[Path]:
    """Every log file kept, oldest first: the dated ones, then the one being written."""
    dated = sorted(log_dir.glob(f"{Path(LOG_FILENAME).stem}-*{Path(LOG_FILENAME).suffix}"))
    current = log_dir / LOG_FILENAME
    return [*dated, current] if current.is_file() else dated


def log_rows(path: Path) -> list[list[str]]:
    """One file's records as `EXPORT_COLUMNS` rows, a multi-line record kept whole."""
    rows: list[list[str]] = []
    for text in path.read_text(encoding="utf-8", errors="replace").splitlines():
        match = _LINE.match(text)
        if match:
            rows.append([match["time"], match["level"], match["source"], match["message"], path.name])
        elif rows:
            rows[-1][3] += "\n" + text
        elif text.strip():
            rows.append(["", "", "", text, path.name])
    return rows


def export_csv(log_dir: Path, destination: Path, about: list[tuple[str, str]]) -> int:
    """Write every kept log file to one CSV for sending to whoever supports the tool.

    `about` goes first, one row each, so the file says which build and which machine it
    came from without a second message asking. Returns how many log records it holds.
    """
    records = [row for path in log_files(log_dir) for row in log_rows(path)]
    with destination.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(EXPORT_COLUMNS)
        for name, value in about:
            writer.writerow(["", "ABOUT", name, value, ""])
        writer.writerows(records)
    return len(records)
