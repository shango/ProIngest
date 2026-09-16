"""The frozen bundle's entry script. Nothing imports this; PyInstaller runs it.

It exists for one line. `core/render.py` runs its workers on the **spawn** start method
on every platform, and in a frozen bundle `multiprocessing.spawn.get_command_line`
spawns a child by re-launching `sys.executable` - which is `ProIngest.app` itself -
with a `--multiprocessing-fork` argument. Without `freeze_support()` to intercept that
argument, every worker the pool asks for opens another copy of the window instead of
rendering a frame, and pressing Run once opens four more ProIngests.

**Why this works on macOS, which reading CPython would say it does not.**
`multiprocessing.freeze_support` in the standard library is `BaseContext.freeze_support`,
and its body is gated on `sys.platform == "win32"`, so on macOS it does nothing at all.
PyInstaller's `pyi_rth_multiprocessing` runtime hook **rebinds the name**: it replaces
both `multiprocessing.freeze_support` and `multiprocessing.spawn.freeze_support` with
its own version, which is gated on nothing and also diverts the resource tracker. That
hook is registered against the `multiprocessing` module and so runs, before this script,
in any bundle that imports it. The call below is therefore a no-op when running from
source on any platform but Windows, and load bearing in the shipped app on all of them.
Anyone checking this line against the standard library will conclude it is dead code.
It is not, and deleting it costs a bug that only appears in a packaged build.
"""

from __future__ import annotations

import multiprocessing
import sys

from proingest.__main__ import main

if __name__ == "__main__":
    # Before argparse, and before anything else: on a spawned worker this call never
    # returns. A `--multiprocessing-fork` argument that reached the parser would be
    # rejected as unknown, and one that got past it would launch a second window.
    multiprocessing.freeze_support()
    sys.exit(main())
