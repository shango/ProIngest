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
from datetime import date
from pathlib import Path

import pytest

from build import build, bundle
from proingest import __version__
from proingest.core import expiry, ffmpeg, stringout

DARWIN = bundle.MACOS
WINDOWS = bundle.WINDOWS
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

    def test_windows_collects_both_exes(self) -> None:
        destinations = {Path(source).name: dest for source, dest in bundle.binaries(WINDOWS)}
        assert set(destinations) == {"ffmpeg.exe", "ffprobe.exe"}
        assert set(destinations.values()) == {str(bundle.FFMPEG_DIR)}

    def test_the_names_are_the_ones_core_resolves(self) -> None:
        """`core/ffmpeg.py` adds `.exe` itself on Windows; the bundle has to agree."""
        assert bundle.ffmpeg_files(WINDOWS) == ["ffmpeg.exe", "ffprobe.exe"]
        assert bundle.ffmpeg_files(DARWIN) == ["ffmpeg", "ffprobe"]
        assert set(bundle.SHIPPED_PLATFORMS) == ffmpeg.BUNDLED_PLATFORMS

    def test_no_binaries_on_linux(self) -> None:
        """The bundle holds Mach-O or Windows executables and `core/ffmpeg.py` skips it on
        Linux, so collecting it there would be 132 MB in an artifact that cannot run it."""
        assert bundle.binaries(LINUX) == []


class TestDatas:
    def sources(self, platform: str) -> list[str]:
        return [source for source, _ in bundle.datas(platform)]

    def test_the_stylesheet_is_collected(self) -> None:
        """`ui/app.py` treats a missing theme as survivable on purpose, so nothing at
        run time would report its absence: it would simply ship looking wrong."""
        assert str(bundle.REPO_ROOT / "proingest" / "ui" / "theme.qss") in self.sources(LINUX)

    @pytest.mark.parametrize("platform", [LINUX, DARWIN, WINDOWS])
    def test_the_burn_in_font_and_its_licence_ship_everywhere(self, platform: str) -> None:
        """`core/stringout.py` reads it by path; without it every stringout is QC-142."""
        wanted = {str(bundle.REPO_ROOT / bundle.FONTS_DIR / name) for name in bundle.FONT_FILES}
        assert wanted <= set(self.sources(platform))
        assert all(Path(source).is_file() for source in wanted)
        assert stringout.FONT == bundle.REPO_ROOT / bundle.FONTS_DIR / "OpenSans-Regular.ttf"

    def test_the_release_date_ships_where_expiry_reads_it(self) -> None:
        """Listed even before a build writes it, so PyInstaller fails a build that forgot."""
        assert (str(bundle.REPO_ROOT / bundle.RELEASE_FILE), str(bundle.RELEASE_FILE.parent)) in bundle.datas(
            LINUX
        )
        assert bundle.REPO_ROOT / bundle.RELEASE_FILE == expiry.RELEASE_FILE

    def test_a_build_stamps_its_own_date(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(build, "REPO_ROOT", tmp_path)
        (tmp_path / bundle.RELEASE_FILE).parent.mkdir(parents=True)
        written = build.stamp_release(date(2026, 10, 5))
        assert expiry.read_stamp(written) == expiry.Expiry(date(2026, 10, 5))

    def test_opentimelineio_is_not_bundled(self) -> None:
        """Gone 2026-09-23: `clf.read_final_edl` reads the EDL, and nothing imports otio."""
        assert not any("otio" in name or "opentimelineio" in name for name in self.sources(LINUX))

    @pytest.mark.parametrize("platform", [DARWIN, WINDOWS])
    def test_ffmpeg_s_licence_ships_with_the_binaries(self, platform: str) -> None:
        names = {Path(source).name for source in self.sources(platform)}
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


class TestTheInstaller:
    def test_each_shipped_platform_has_one_and_linux_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(build, "build_dmg", lambda version: Path(f"{version}.dmg"))
        monkeypatch.setattr(build, "build_setup", lambda version: Path(f"{version}.exe"))
        assert build.build_installer("1.0", DARWIN) == Path("1.0.dmg")
        assert build.build_installer("1.0", WINDOWS) == Path("1.0.exe")
        assert build.build_installer("1.0", LINUX) is None

    def test_the_setup_exe_is_named_as_the_inno_script_names_it(self) -> None:
        """`build.py` checks for the file `proingest.iss` writes, so the two must agree."""
        script = build.INSTALLER_SCRIPT.read_text(encoding="utf-8")
        assert "OutputBaseFilename=ProIngest-Setup-{#AppVersion}" in script
        assert build.setup_path("0.5.50").name == "ProIngest-Setup-0.5.50.exe"

    def test_it_installs_per_user_for_the_exe_the_build_makes(self) -> None:
        """No administrator rights, as a dmg needs none; and the shortcuts point at the
        executable PyInstaller writes, not at a name that only looks right."""
        script = build.INSTALLER_SCRIPT.read_text(encoding="utf-8")
        assert "PrivilegesRequired=lowest" in script
        assert f"{{app}}\\{build.executable_path(WINDOWS).name}" in script

    def test_a_missing_ffmpeg_stops_a_windows_build(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(build, "REPO_ROOT", tmp_path)
        with pytest.raises(build.BuildError, match=r"ffmpeg\.exe, ffprobe\.exe missing"):
            build.check_ffmpeg(WINDOWS)
        build.check_ffmpeg(LINUX)
