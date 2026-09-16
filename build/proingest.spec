# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec. A shim: every decision in it lives in `build/bundle.py`.

A spec file is executed by PyInstaller, so nothing lints or tests it. Keeping it this
thin is what lets `tests/test_bundle.py` cover the parts that can be got wrong.

Run it through `python build/build.py` rather than by hand; that script checks the
things this one assumes, such as the ffmpeg binaries being present before a macOS
build collects them.
"""

import sys
from pathlib import Path

# `SPECPATH` is injected by PyInstaller and is this file's folder. The repo root goes on
# the path too, so `bundle.version()` can import `proingest` even from a bare checkout.
SPEC_DIR = Path(SPECPATH).resolve()  # noqa: F821
sys.path.insert(0, str(SPEC_DIR.parent))

from build import bundle  # noqa: E402

analysis = Analysis(  # noqa: F821
    [str(SPEC_DIR / "entry.py")],
    pathex=[str(SPEC_DIR.parent)],
    binaries=bundle.binaries(),
    datas=bundle.datas(),
    hiddenimports=bundle.hidden_imports(),
    excludes=bundle.excludes(),
    noarchive=False,
)

pyz = PYZ(analysis.pure)  # noqa: F821

# `onedir`, per PACKAGING.md: an `.app` is already a directory, so `onefile` would only
# add a ~200 MB unpack to every launch.
exe = EXE(  # noqa: F821
    pyz,
    analysis.scripts,
    exclude_binaries=True,
    name=bundle.APP_NAME,
    console=False,
    # Stripping and UPX save little against PySide6 and have both been known to produce
    # a bundle that will not load a Qt plugin. A working app beats a smaller one.
    strip=False,
    upx=False,
)

collect = COLLECT(  # noqa: F821
    exe,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    name=bundle.APP_NAME,
)

if sys.platform == bundle.MACOS:
    app = BUNDLE(  # noqa: F821
        collect,
        name=f"{bundle.APP_NAME}.app",
        bundle_identifier=bundle.BUNDLE_IDENTIFIER,
        version=bundle.version(),
        info_plist=bundle.info_plist(),
    )
