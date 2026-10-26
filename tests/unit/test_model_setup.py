"""Tests unitaires de app/model_setup.py (réseau simulé par un faux serveur de Release)."""
import urllib.error
import zipfile

import pytest

from helpers import (ReleaseServer, make_model_zip, no_network, populate_model_dir,
                     sha256_of)


class TestModelState:
    def test_model_path_is_model_dir(self, model_setup_dirs):
        assert model_setup_dirs.model_path() == model_setup_dirs.MODEL_DIR

    def test_not_ready_when_absent(self, model_setup_dirs):
        assert model_setup_dirs.is_model_ready() is False

    def test_ready_when_all_files_present(self, model_setup_dirs):
        populate_model_dir(model_setup_dirs)
        assert model_setup_dirs.is_model_ready() is True

    @pytest.mark.parametrize("index", range(5))
    def test_not_ready_when_a_file_is_missing(self, model_setup_dirs, index):
        populate_model_dir(model_setup_dirs)
        missing = model_setup_dirs._REQUIRED_FILES[index]
        (model_setup_dirs.MODEL_DIR / missing).unlink()
        assert model_setup_dirs.is_model_ready() is False

    def test_not_ready_when_a_required_file_is_a_directory(self, model_setup_dirs):
        populate_model_dir(model_setup_dirs)
        target = model_setup_dirs.MODEL_DIR / "config.yaml"
        target.unlink()
        target.mkdir()
        assert model_setup_dirs.is_model_ready() is False


class TestFetchExpectedSha256:
    def test_reads_the_digest_and_normalizes_case(self, model_setup_dirs, monkeypatch):
        server = ReleaseServer(monkeypatch, b"zip", sha=b"ABCDEF0123  pyannote-community-1.zip\n")
        assert model_setup_dirs._fetch_expected_sha256() == "abcdef0123"
        assert server.urls == [model_setup_dirs._RELEASE_URL + ".sha256"]

    def test_network_error(self, model_setup_dirs, monkeypatch):
        ReleaseServer(monkeypatch, b"zip", sha_error=urllib.error.URLError("pas de réseau"))
        with pytest.raises(RuntimeError, match="checksum"):
            model_setup_dirs._fetch_expected_sha256()

    def test_http_404(self, model_setup_dirs, monkeypatch):
        error = urllib.error.HTTPError("https://x/y.sha256", 404, "Not Found", {}, None)
        ReleaseServer(monkeypatch, b"zip", sha_error=error)
        with pytest.raises(RuntimeError, match="404"):
            model_setup_dirs._fetch_expected_sha256()

    def test_empty_file(self, model_setup_dirs, monkeypatch):
        ReleaseServer(monkeypatch, b"zip", sha=b"")
        with pytest.raises(RuntimeError, match="checksum"):
            model_setup_dirs._fetch_expected_sha256()

    def test_binary_garbage(self, model_setup_dirs, monkeypatch):
        ReleaseServer(monkeypatch, b"zip", sha=b"\xff\xfe\xfd")
        with pytest.raises(RuntimeError, match="checksum"):
            model_setup_dirs._fetch_expected_sha256()


class TestDownload:
    def test_returns_digest_and_writes_file(self, model_setup_dirs, monkeypatch, tmp_path):
        data = b"contenu de l'archive" * 1000
        ReleaseServer(monkeypatch, data)
        target = tmp_path / "model.zip"
        assert model_setup_dirs._download(target, None) == sha256_of(data)
        assert target.read_bytes() == data

    def test_progress_messages(self, model_setup_dirs, monkeypatch, tmp_path):
        data = b"a" * (3 * 1024 * 1024 + 10)
        ReleaseServer(monkeypatch, data)
        messages = []
        model_setup_dirs._download(tmp_path / "m.zip", lambda m, p: messages.append((m, p)))
        assert messages[-1][0] == "diarization_model_dl:3/3"
        percents = [p for _, p in messages]
        assert percents == sorted(percents) and max(percents) == pytest.approx(0.9)

    def test_no_progress_without_content_length(self, model_setup_dirs, monkeypatch, tmp_path):
        ReleaseServer(monkeypatch, b"a" * 1000, with_length=False)
        messages = []
        model_setup_dirs._download(tmp_path / "m.zip", lambda m, p: messages.append(m))
        assert messages == []

    def test_no_callback_is_fine(self, model_setup_dirs, monkeypatch, tmp_path):
        ReleaseServer(monkeypatch, b"abc")
        model_setup_dirs._download(tmp_path / "m.zip", None)

    @pytest.mark.parametrize("error", [urllib.error.URLError("hors ligne"), TimeoutError("trop long")])
    def test_network_failures_become_runtime_errors(self, model_setup_dirs, monkeypatch, tmp_path, error):
        ReleaseServer(monkeypatch, b"abc", zip_error=error)
        with pytest.raises(RuntimeError, match="Cannot download"):
            model_setup_dirs._download(tmp_path / "m.zip", None)


class TestDownloadAndExtract:
    def _leftovers(self, ms):
        return list(ms._MODELS_DIR.glob(".download-*"))

    def test_installs_archive_with_top_level_folder(self, model_setup_dirs, monkeypatch):
        ReleaseServer(monkeypatch, make_model_zip())
        model_setup_dirs._download_and_extract()
        assert model_setup_dirs.is_model_ready()
        assert self._leftovers(model_setup_dirs) == []

    def test_installs_flat_archive(self, model_setup_dirs, monkeypatch):
        ReleaseServer(monkeypatch, make_model_zip(top_dir=None))
        model_setup_dirs._download_and_extract()
        assert model_setup_dirs.is_model_ready()

    def test_progress_sequence(self, model_setup_dirs, monkeypatch):
        ReleaseServer(monkeypatch, make_model_zip())
        messages = []
        model_setup_dirs._download_and_extract(lambda m, p: messages.append(m))
        assert messages[0] == "diarization_model_connecting"
        assert "diarization_model_extracting" in messages
        assert messages[-1] == "diarization_model_ready"

    def test_checksum_mismatch_is_rejected(self, model_setup_dirs, monkeypatch):
        ReleaseServer(monkeypatch, make_model_zip(), sha="0" * 64)
        with pytest.raises(RuntimeError, match="SHA-256"):
            model_setup_dirs._download_and_extract()
        assert not model_setup_dirs.MODEL_DIR.exists()
        assert self._leftovers(model_setup_dirs) == []

    def test_incomplete_archive_is_rejected(self, model_setup_dirs, monkeypatch):
        incomplete = make_model_zip(files=model_setup_dirs._REQUIRED_FILES[:-1])
        ReleaseServer(monkeypatch, incomplete)
        with pytest.raises(RuntimeError, match="incomplete"):
            model_setup_dirs._download_and_extract()
        assert not model_setup_dirs.MODEL_DIR.exists()
        assert self._leftovers(model_setup_dirs) == []

    def test_failure_keeps_an_existing_directory_untouched(self, model_setup_dirs, monkeypatch):
        model_setup_dirs.MODEL_DIR.mkdir(parents=True)
        (model_setup_dirs.MODEL_DIR / "reste.txt").write_text("ancien")
        ReleaseServer(monkeypatch, make_model_zip(), sha="0" * 64)
        with pytest.raises(RuntimeError):
            model_setup_dirs._download_and_extract()
        assert (model_setup_dirs.MODEL_DIR / "reste.txt").read_text() == "ancien"

    def test_replaces_an_incomplete_install(self, model_setup_dirs, monkeypatch):
        populate_model_dir(model_setup_dirs)
        (model_setup_dirs.MODEL_DIR / "plda" / "plda.npz").unlink()
        (model_setup_dirs.MODEL_DIR / "ancien.txt").write_text("à supprimer")
        ReleaseServer(monkeypatch, make_model_zip())
        model_setup_dirs._download_and_extract()
        assert model_setup_dirs.is_model_ready()
        assert not (model_setup_dirs.MODEL_DIR / "ancien.txt").exists()

    def test_removes_the_legacy_cache(self, model_setup_dirs, monkeypatch):
        legacy = model_setup_dirs._LEGACY_CACHE_DIR / "hub" / "models--pyannote--x"
        legacy.mkdir(parents=True)
        ReleaseServer(monkeypatch, make_model_zip())
        model_setup_dirs._download_and_extract()
        assert not model_setup_dirs._LEGACY_CACHE_DIR.exists()

    def test_legacy_cache_is_kept_when_install_fails(self, model_setup_dirs, monkeypatch):
        (model_setup_dirs._LEGACY_CACHE_DIR / "hub").mkdir(parents=True)
        ReleaseServer(monkeypatch, make_model_zip(), sha="0" * 64)
        with pytest.raises(RuntimeError):
            model_setup_dirs._download_and_extract()
        assert model_setup_dirs._LEGACY_CACHE_DIR.exists()

    def test_archive_entries_cannot_escape_the_work_folder(self, model_setup_dirs, monkeypatch, tmp_path):
        ReleaseServer(monkeypatch, make_model_zip(extra={"../../evil.txt": b"pwned"}))
        model_setup_dirs._download_and_extract()
        assert model_setup_dirs.is_model_ready()
        assert not list(tmp_path.rglob("evil.txt"))

    @pytest.mark.parametrize("extra", [
        {"__MACOSX/._config.yaml": b"metadonnees"},
        {"LICENSE.txt": b"CC BY 4.0"},
    ])
    def test_extra_top_level_entries_are_ignored(self, model_setup_dirs, monkeypatch, extra):
        ReleaseServer(monkeypatch, make_model_zip(extra=extra))
        model_setup_dirs._download_and_extract()
        assert model_setup_dirs.is_model_ready()
        assert not (model_setup_dirs.MODEL_DIR / "LICENSE.txt").exists()

    def test_corrupted_zip_with_matching_checksum(self, model_setup_dirs, monkeypatch):
        garbage = b"ceci n'est pas un zip"
        ReleaseServer(monkeypatch, garbage)
        with pytest.raises(zipfile.BadZipFile):
            model_setup_dirs._download_and_extract()
        assert self._leftovers(model_setup_dirs) == []

    def test_unreadable_checksum_aborts_before_downloading_the_archive(self, model_setup_dirs, monkeypatch):
        server = ReleaseServer(monkeypatch, make_model_zip(),
                               sha_error=urllib.error.URLError("hors ligne"))
        with pytest.raises(RuntimeError):
            model_setup_dirs._download_and_extract()
        assert all(url.endswith(".sha256") for url in server.urls)


class TestEnsureModel:
    def test_cached_model_needs_no_network(self, model_setup_dirs, monkeypatch):
        populate_model_dir(model_setup_dirs)
        no_network(monkeypatch)
        messages = []
        result = model_setup_dirs.ensure_model(lambda m, p: messages.append((m, p)))
        assert result == model_setup_dirs.MODEL_DIR
        assert messages == [("diarization_model_cached", 1.0)]

    def test_cached_model_without_callback(self, model_setup_dirs, monkeypatch):
        populate_model_dir(model_setup_dirs)
        no_network(monkeypatch)
        assert model_setup_dirs.ensure_model() == model_setup_dirs.MODEL_DIR

    def test_missing_model_is_downloaded(self, model_setup_dirs, monkeypatch):
        ReleaseServer(monkeypatch, make_model_zip())
        assert model_setup_dirs.ensure_model() == model_setup_dirs.MODEL_DIR
        assert model_setup_dirs.is_model_ready()

    def test_download_failure_propagates(self, model_setup_dirs, monkeypatch):
        ReleaseServer(monkeypatch, b"zip", sha_error=urllib.error.URLError("hors ligne"))
        with pytest.raises(RuntimeError):
            model_setup_dirs.ensure_model()
        assert not model_setup_dirs.is_model_ready()
