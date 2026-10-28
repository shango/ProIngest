"""Getting the pinned ffmpeg onto a machine (M7, and the macOS setup).

`build/fetch_ffmpeg.py` is the only supported way to obtain the two binaries, so it is
also the only thing standing between a fresh clone and a bundle built around whatever
ffmpeg happened to be lying around. These cover the part that matters: that a file which
is not the pinned build is rejected whether it was downloaded or handed over by hand,
and that a rejected one leaves nothing behind that looks finished.

Nothing here touches the network. The download path is exercised by CI on every push,
which fetches the real pair on the macOS and Windows runners.
"""

from __future__ import annotations

import hashlib
import json
import re
import stat
import sys
import zipfile
from pathlib import Path
from typing import Any

import pytest

from build import bundle, fetch_ffmpeg
from proingest.core import ffmpeg as core_ffmpeg

PAYLOAD = b"not really a video tool" * 100


def entry_for(payload: bytes, *, dest_name: str = "ffmpeg", member: str | None = "ffmpeg") -> dict[str, Any]:
    """A lock file entry describing `payload`, with or without an archive around it."""
    return {
        "dest_name": dest_name,
        "url": f"https://example.invalid/download/{dest_name}.zip",
        "archive_member": member,
        "size": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "executable": True,
    }


def zip_containing(path: Path, member: str, payload: bytes) -> Path:
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(member, payload)
    return path


SHIPPED = pytest.mark.parametrize("platform", bundle.SHIPPED_PLATFORMS)


class TestTheRealLockFile:
    def test_it_pins_exactly_the_platforms_that_ship(self) -> None:
        platforms = json.loads(fetch_ffmpeg.LOCK_PATH.read_text(encoding="utf-8"))["platforms"]
        assert set(platforms) == set(bundle.SHIPPED_PLATFORMS) == core_ffmpeg.BUNDLED_PLATFORMS

    @SHIPPED
    def test_it_parses_and_every_entry_carries_what_the_installer_reads(self, platform: str) -> None:
        spec = fetch_ffmpeg.load_spec(platform)
        assert spec["downloads"]
        for entry in spec["downloads"]:
            assert {"dest_name", "url", "size", "sha256", "executable"} <= entry.keys()
            assert len(str(entry["sha256"])) == 64

    @SHIPPED
    def test_it_installs_where_core_resolves_the_bundled_pair(self, platform: str) -> None:
        """The lock says where the binaries go and `core/ffmpeg.py` says where they are
        looked for. They are two literals in two files and this is what holds them
        together; drift gives a build that fetches 132 MB into a folder nothing reads."""
        spec = fetch_ffmpeg.load_spec(platform)
        assert fetch_ffmpeg.REPO_ROOT / str(spec["dest_dir"]) == core_ffmpeg.BUNDLED_DIR

    @SHIPPED
    def test_the_pinned_binaries_are_the_two_the_bundle_collects(self, platform: str) -> None:
        names = {str(e["dest_name"]) for e in fetch_ffmpeg.load_spec(platform)["downloads"]}
        assert set(bundle.ffmpeg_files(platform)) <= names

    def test_both_platforms_render_with_the_same_ffmpeg(self) -> None:
        """Parity (2026-10-28): the two apps are one tool, so a render on either machine
        is the same ffmpeg release, and a difference between them is never the encoder."""
        versions = {fetch_ffmpeg.load_spec(p)["version"].split("-")[0] for p in bundle.SHIPPED_PLATFORMS}
        assert versions == {"9.0.1"}

    def test_linux_has_none_and_says_what_it_uses_instead(self) -> None:
        with pytest.raises(SystemExit, match="ffmpeg on PATH"):
            fetch_ffmpeg.load_spec("linux")


class TestAcceptedNames:
    def test_it_takes_the_archive_as_downloaded_or_the_file_extracted(self) -> None:
        assert fetch_ffmpeg.accepted_names(entry_for(PAYLOAD)) == ["ffmpeg.zip", "ffmpeg"]

    def test_a_plain_file_is_named_by_its_url_and_its_destination(self) -> None:
        entry = entry_for(PAYLOAD, dest_name="LICENSE.ffmpeg.txt", member=None)
        entry["url"] = "https://example.invalid/COPYING.GPLv3"
        assert fetch_ffmpeg.accepted_names(entry) == ["COPYING.GPLv3", "LICENSE.ffmpeg.txt"]

    def test_the_same_name_twice_is_listed_once(self) -> None:
        """The url basename and the destination name are usually the same file."""
        entry = entry_for(PAYLOAD, dest_name="ffmpeg", member=None)
        entry["url"] = "https://example.invalid/ffmpeg"
        assert fetch_ffmpeg.accepted_names(entry) == ["ffmpeg"]


class TestFindLocal:
    def test_it_finds_the_zip_the_browser_left(self, tmp_path: Path) -> None:
        zip_containing(tmp_path / "ffmpeg.zip", "ffmpeg", PAYLOAD)
        assert fetch_ffmpeg.find_local(entry_for(PAYLOAD), tmp_path) == tmp_path / "ffmpeg.zip"

    def test_it_finds_the_binary_the_finder_extracted(self, tmp_path: Path) -> None:
        (tmp_path / "ffmpeg").write_bytes(PAYLOAD)
        assert fetch_ffmpeg.find_local(entry_for(PAYLOAD), tmp_path) == tmp_path / "ffmpeg"

    def test_an_empty_folder_finds_nothing(self, tmp_path: Path) -> None:
        assert fetch_ffmpeg.find_local(entry_for(PAYLOAD), tmp_path) is None


class TestInstallLocal:
    def test_a_bare_binary_lands_executable(self, tmp_path: Path) -> None:
        source = tmp_path / "src" / "ffmpeg"
        source.parent.mkdir()
        source.write_bytes(PAYLOAD)
        dest_dir = tmp_path / "resources"
        dest_dir.mkdir()

        fetch_ffmpeg.install_local(entry_for(PAYLOAD), source, dest_dir)

        installed = dest_dir / "ffmpeg"
        assert installed.read_bytes() == PAYLOAD
        assert installed.stat().st_mode & stat.S_IXUSR

    def test_a_zip_is_unpacked_by_its_member_name(self, tmp_path: Path) -> None:
        source = zip_containing(tmp_path / "ffmpeg.zip", "ffmpeg", PAYLOAD)
        dest_dir = tmp_path / "resources"
        dest_dir.mkdir()

        fetch_ffmpeg.install_local(entry_for(PAYLOAD), source, dest_dir)

        assert (dest_dir / "ffmpeg").read_bytes() == PAYLOAD

    def test_the_wrong_build_is_refused_and_leaves_nothing_behind(self, tmp_path: Path) -> None:
        """The failure this exists to catch: a real ffmpeg, but not *the* ffmpeg. It
        would run, so nothing downstream would notice, and the version in every QC log
        would be a lie."""
        source = tmp_path / "ffmpeg"
        source.write_bytes(b"some other build of ffmpeg entirely")
        dest_dir = tmp_path / "resources"
        dest_dir.mkdir()

        with pytest.raises(SystemExit, match="sha256 mismatch"):
            fetch_ffmpeg.install_local(entry_for(PAYLOAD), source, dest_dir)

        assert list(dest_dir.iterdir()) == []

    def test_a_file_that_is_not_the_advertised_archive_is_refused(self, tmp_path: Path) -> None:
        """Half a download, or an HTML error page saved under the archive's name."""
        source = tmp_path / "ffmpeg.zip"
        source.write_bytes(b"<html>404</html>")
        dest_dir = tmp_path / "resources"
        dest_dir.mkdir()

        with pytest.raises(SystemExit, match="sha256 mismatch"):
            fetch_ffmpeg.install_local(entry_for(PAYLOAD), source, dest_dir)

    def test_it_copies_contents_rather_than_the_file(self, tmp_path: Path) -> None:
        """macOS puts `com.apple.quarantine` on anything a browser wrote, and a
        quarantined ffmpeg is killed on first exec. Writing a new file is what avoids
        inheriting it, so the installed copy must not be the same inode."""
        source = tmp_path / "ffmpeg"
        source.write_bytes(PAYLOAD)
        dest_dir = tmp_path / "resources"
        dest_dir.mkdir()

        fetch_ffmpeg.install_local(entry_for(PAYLOAD), source, dest_dir)

        assert (dest_dir / "ffmpeg").stat().st_ino != source.stat().st_ino


class TestIsSatisfied:
    def test_the_right_bytes_without_the_exec_bit_are_not_enough(self, tmp_path: Path) -> None:
        dest = tmp_path / "ffmpeg"
        dest.write_bytes(PAYLOAD)
        dest.chmod(0o644)
        assert not fetch_ffmpeg.is_satisfied(dest, entry_for(PAYLOAD))
        dest.chmod(0o755)
        assert fetch_ffmpeg.is_satisfied(dest, entry_for(PAYLOAD))


class TestMain:
    def fake_lock(self, tmp_path: Path, payload: bytes) -> Path:
        lock = tmp_path / "ffmpeg.lock.json"
        spec = {
            "version": "0.0.0-test",
            "license": "GPL-3.0-or-later",
            "dest_dir": "resources",
            "downloads": [entry_for(payload)],
        }
        lock.write_text(json.dumps({"platforms": {sys.platform: {"label": "test", "ffmpeg": spec}}}))
        return lock

    @pytest.fixture(autouse=True)
    def _point_at_a_fake_lock(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(fetch_ffmpeg, "REPO_ROOT", tmp_path)
        monkeypatch.setattr(fetch_ffmpeg, "LOCK_PATH", self.fake_lock(tmp_path, PAYLOAD))

    def test_from_a_folder_installs_without_touching_the_network(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(fetch_ffmpeg, "download", lambda *a: pytest.fail("--from must not download"))
        downloads = tmp_path / "Downloads"
        downloads.mkdir()
        zip_containing(downloads / "ffmpeg.zip", "ffmpeg", PAYLOAD)

        assert fetch_ffmpeg.main(["--from", str(downloads)]) == 0
        assert (tmp_path / "resources" / "ffmpeg").read_bytes() == PAYLOAD

    def test_from_a_folder_missing_the_file_says_what_to_put_there(self, tmp_path: Path) -> None:
        downloads = tmp_path / "Downloads"
        downloads.mkdir()
        with pytest.raises(SystemExit, match=re.escape("ffmpeg.zip, ffmpeg")):
            fetch_ffmpeg.main(["--from", str(downloads)])

    def test_from_a_folder_that_is_not_one(self, tmp_path: Path) -> None:
        with pytest.raises(SystemExit, match="not a folder"):
            fetch_ffmpeg.main(["--from", str(tmp_path / "nowhere")])

    def test_verify_reports_what_is_missing_and_fails(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert fetch_ffmpeg.main(["--verify"]) == 1
        assert "missing ffmpeg" in capsys.readouterr().out

    def test_verify_names_a_file_that_is_present_but_wrong(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        (tmp_path / "resources").mkdir()
        (tmp_path / "resources" / "ffmpeg").write_bytes(b"something else")
        assert fetch_ffmpeg.main(["--verify"]) == 1
        assert "WRONG   ffmpeg" in capsys.readouterr().out

    def test_verify_passes_once_the_file_is_in_place(self, tmp_path: Path) -> None:
        downloads = tmp_path / "Downloads"
        downloads.mkdir()
        (downloads / "ffmpeg").write_bytes(PAYLOAD)
        fetch_ffmpeg.main(["--from", str(downloads)])
        assert fetch_ffmpeg.main(["--verify"]) == 0

    def test_a_second_run_downloads_nothing(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        downloads = tmp_path / "Downloads"
        downloads.mkdir()
        (downloads / "ffmpeg").write_bytes(PAYLOAD)
        fetch_ffmpeg.main(["--from", str(downloads)])

        monkeypatch.setattr(fetch_ffmpeg, "download", lambda *a: pytest.fail("nothing to fetch"))
        assert fetch_ffmpeg.main([]) == 0

    def test_show_prints_the_url_and_the_hash(self, capsys: pytest.CaptureFixture[str]) -> None:
        assert fetch_ffmpeg.main(["--show"]) == 0
        out = capsys.readouterr().out
        assert "https://example.invalid/download/ffmpeg.zip" in out
        assert hashlib.sha256(PAYLOAD).hexdigest() in out


class TestASharedArchive:
    def test_it_is_downloaded_once_for_every_file_in_it(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The Windows build's ffmpeg, ffprobe and licence are one 111 MB zip."""
        tool, probe = b"tool" * 50, b"probe" * 50
        archive = zip_containing(tmp_path / "source.zip", "build/bin/ffmpeg.exe", tool)
        with zipfile.ZipFile(archive, "a") as zf:
            zf.writestr("build/bin/ffprobe.exe", probe)
        url = "https://example.invalid/build.zip"
        entries = [
            {**entry_for(tool, dest_name="ffmpeg.exe", member="build/bin/ffmpeg.exe"), "url": url},
            {**entry_for(probe, dest_name="ffprobe.exe", member="build/bin/ffprobe.exe"), "url": url},
        ]
        fetched: list[str] = []

        def download(source: str, dest: Path) -> None:
            fetched.append(source)
            dest.write_bytes(archive.read_bytes())

        monkeypatch.setattr(fetch_ffmpeg, "download", download)
        dest_dir, work = tmp_path / "resources", tmp_path / "work"
        dest_dir.mkdir()
        work.mkdir()
        for entry in entries:
            fetch_ffmpeg.fetch(entry, dest_dir, work)

        assert fetched == [url]
        assert (dest_dir / "ffmpeg.exe").read_bytes() == tool
        assert (dest_dir / "ffprobe.exe").read_bytes() == probe
