"""What goes into the frozen app (M7).

These cover `build/bundle.py`, which exists so that the contents of the bundle are
checkable at all: a PyInstaller `.spec` is executed rather than imported, so nothing
otherwise reads it and a mistake in it ships rather than failing a build.

The tests worth having here are the ones that pin a packaging decision against the code
that depends on it, so that moving one without the other fails in the suite rather than
in a delivered app. Whether the bundle actually *works* is not answerable from here and
is `build/smoke_test.py`'s job, which the packaging CI job runs against a real build.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

from build import bundle
from proingest import __version__
from proingest.core import ffmpeg

DARWIN = bundle.MACOS
LINUX = "linux"


class TestVersion:
    def test_the_package_and_pyproject_agree(self) -> None:
        """The dmg is named from one and the About box reads the other.

        They are two literals in two files, so nothing but this stops them drifting,
        and the symptom of drift is an installer whose filename disagrees with the
        version printed inside every QC log it produces.
        """
        pyproject = tomllib.loads((bundle.REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        assert bundle.version() == pyproject["project"]["version"] == __version__


class TestBinaries:
    def test_the_bundled_ffmpeg_lands_where_core_looks_for_it(self) -> None:
        """`core/ffmpeg.py` resolves its bundled pair relative to its own `__file__`,
        which in a frozen app is inside the bundle. Laying the binaries out anywhere
        else gives an app that starts and then cannot probe a single file."""
        assert bundle.REPO_ROOT / bundle.FFMPEG_DIR == ffmpeg.BUNDLED_DIR

    def test_the_pair_is_the_pair_core_resolves(self) -> None:
        assert set(bundle.FFMPEG_TOOLS) == {"ffmpeg", "ffprobe"}

    def test_macos_collects_both_tools(self) -> None:
        destinations = {Path(source).name: dest for source, dest in bundle.binaries(DARWIN)}
        assert set(destinations) == set(bundle.FFMPEG_TOOLS)
        assert set(destinations.values()) == {str(bundle.FFMPEG_DIR)}

    def test_no_binaries_off_macos(self) -> None:
        """They are arm64 Mach-O and `core/ffmpeg.py` skips them off macOS, so
        collecting them elsewhere would be 132 MB in an artifact that cannot run them."""
        assert bundle.binaries(LINUX) == []


class TestDatas:
    def sources(self, platform: str) -> list[str]:
        return [source for source, _ in bundle.datas(platform)]

    def test_the_stylesheet_is_collected(self) -> None:
        """`ui/app.py` treats a missing theme as survivable on purpose, so nothing at
        run time would report its absence: it would simply ship looking wrong."""
        assert str(bundle.REPO_ROOT / "proingest" / "ui" / "theme.qss") in self.sources(LINUX)

    def test_opentimelineio_is_not_bundled(self) -> None:
        """Gone 2026-09-23: `clf.read_final_edl` reads the EDL, and nothing imports otio."""
        assert not any("otio" in name or "opentimelineio" in name for name in self.sources(LINUX))

    def test_ffmpeg_s_licence_ships_with_the_binaries_on_macos(self) -> None:
        names = {Path(source).name for source in self.sources(DARWIN)}
        assert {"LICENSE.ffmpeg.txt", "PROVENANCE.md"} <= names
        assert not {"LICENSE.ffmpeg.txt", "PROVENANCE.md"} & {
            Path(source).name for source in self.sources(LINUX)
        }


class TestHiddenImports:
    def test_there_are_none_since_otio_went(self) -> None:
        assert bundle.hidden_imports() == []


class TestInfoPlist:
    def test_it_carries_the_identifier_and_the_version(self) -> None:
        plist = bundle.info_plist()
        assert plist["CFBundleIdentifier"] == bundle.BUNDLE_IDENTIFIER
        assert plist["CFBundleShortVersionString"] == bundle.version()

    def test_it_claims_retina_and_a_floor_macos(self) -> None:
        plist = bundle.info_plist()
        assert plist["NSHighResolutionCapable"] is True
        assert plist["LSMinimumSystemVersion"] == bundle.MINIMUM_MACOS


class TestEntryPoint:
    def test_freeze_support_is_called_before_main(self) -> None:
        """`build/entry.py` exists for this one line, and reading it against the
        standard library says it is a no-op off Windows. It is not: PyInstaller's
        runtime hook rebinds the name. Deleting it costs a packaged app that opens a
        new window per worker instead of rendering, which no test but this one and the
        smoke test would notice.
        """
        source = (bundle.REPO_ROOT / "build" / "entry.py").read_text(encoding="utf-8")
        assert source.index("freeze_support()") < source.index("main()")
