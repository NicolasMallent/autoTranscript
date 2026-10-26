"""Tests unitaires de scripts/download_pyannote.py (script du CI)."""
import hashlib
import importlib.util
import zipfile
from pathlib import Path

import pytest

pytest.importorskip("huggingface_hub")
requests = pytest.importorskip("requests")

from huggingface_hub.errors import HfHubHTTPError  # noqa: E402


@pytest.fixture
def script(project_root):
    spec = importlib.util.spec_from_file_location(
        "download_pyannote", project_root / "scripts" / "download_pyannote.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def http_error(status):
    response = requests.Response()
    response.status_code = status
    return HfHubHTTPError(f"HTTP {status}", response=response)


class TestIsRateLimit:
    def test_429(self, script):
        assert script.is_rate_limit(http_error(429)) is True

    @pytest.mark.parametrize("status", [401, 403, 404, 500, 503])
    def test_other_statuses(self, script, status):
        assert script.is_rate_limit(http_error(status)) is False

    def test_text_containing_429_is_not_enough(self, script):
        assert script.is_rate_limit(RuntimeError("erreur 429 inventée")) is False

    def test_error_without_response(self, script):
        assert script.is_rate_limit(HfHubHTTPError("sans réponse")) is False


class TestDownloadModel:
    @pytest.fixture
    def sleeps(self, script, monkeypatch):
        calls = []
        monkeypatch.setattr(script.time, "sleep", calls.append)
        return calls

    def test_passes_repo_token_and_target(self, script, monkeypatch, tmp_path, sleeps):
        calls = []
        monkeypatch.setattr(script, "snapshot_download", lambda **kw: calls.append(kw))
        script.download_model("hf_secret", tmp_path)
        assert calls[0]["repo_id"] == script.MODEL_ID
        assert calls[0]["token"] == "hf_secret" and calls[0]["local_dir"] == tmp_path
        assert sleeps == []

    def test_retries_after_rate_limit_with_growing_delays(self, script, monkeypatch, tmp_path, sleeps):
        attempts = []

        def flaky(**kwargs):
            attempts.append(1)
            if len(attempts) < 3:
                raise http_error(429)
        monkeypatch.setattr(script, "snapshot_download", flaky)
        script.download_model("t", tmp_path)
        assert len(attempts) == 3 and sleeps == [60, 120]

    def test_gives_up_after_max_retries(self, script, monkeypatch, tmp_path, sleeps):
        def always_limited(**kwargs):
            raise http_error(429)
        monkeypatch.setattr(script, "snapshot_download", always_limited)
        with pytest.raises(HfHubHTTPError):
            script.download_model("t", tmp_path)
        assert len(sleeps) == script.MAX_RETRIES - 1

    def test_other_errors_are_not_retried(self, script, monkeypatch, tmp_path, sleeps):
        attempts = []

        def forbidden(**kwargs):
            attempts.append(1)
            raise http_error(403)
        monkeypatch.setattr(script, "snapshot_download", forbidden)
        with pytest.raises(HfHubHTTPError):
            script.download_model("t", tmp_path)
        assert attempts == [1] and sleeps == []


class TestCheckModel:
    def _populate(self, script, root, skip=None):
        for name in script.REQUIRED_FILES:
            if name != skip:
                (root / name).parent.mkdir(parents=True, exist_ok=True)
                (root / name).write_bytes(b"x")

    def test_complete_model(self, script, tmp_path):
        self._populate(script, tmp_path)
        script.check_model(tmp_path)  # ne doit pas quitter

    def test_missing_file_exits_with_an_error(self, script, tmp_path, capsys):
        self._populate(script, tmp_path, skip="plda/plda.npz")
        with pytest.raises(SystemExit) as info:
            script.check_model(tmp_path)
        assert info.value.code == 1
        assert "plda/plda.npz" in capsys.readouterr().err


class TestBuildZip:
    @pytest.fixture
    def model_dir(self, script, tmp_path):
        root = tmp_path / "source"
        for name in script.REQUIRED_FILES:
            (root / name).parent.mkdir(parents=True, exist_ok=True)
            (root / name).write_bytes(b"poids")
        (root / "LICENSE-NOTICE.txt").write_text("CC BY 4.0")
        (root / ".cache" / "huggingface").mkdir(parents=True)
        (root / ".cache" / "huggingface" / "metadata").write_text("interne")
        return root

    def test_layout_has_a_single_top_level_folder(self, script, model_dir, tmp_path):
        zip_path = tmp_path / "dist" / "model.zip"
        script.build_zip(model_dir, zip_path)
        with zipfile.ZipFile(zip_path) as archive:
            tops = {name.split("/")[0] for name in archive.namelist()}
            names = set(archive.namelist())
        assert tops == {script.MODEL_DIR_NAME}
        assert f"{script.MODEL_DIR_NAME}/LICENSE-NOTICE.txt" in names
        assert all(f"{script.MODEL_DIR_NAME}/{n}" in names for n in script.REQUIRED_FILES)

    def test_huggingface_cache_metadata_is_excluded(self, script, model_dir, tmp_path):
        zip_path = tmp_path / "model.zip"
        script.build_zip(model_dir, zip_path)
        with zipfile.ZipFile(zip_path) as archive:
            assert not [n for n in archive.namelist() if ".cache" in n]

    def test_returns_the_sha256_of_the_archive(self, script, model_dir, tmp_path):
        zip_path = tmp_path / "model.zip"
        digest = script.build_zip(model_dir, zip_path)
        assert digest == hashlib.sha256(zip_path.read_bytes()).hexdigest()

    def test_creates_the_destination_folder(self, script, model_dir, tmp_path):
        zip_path = tmp_path / "pas" / "encore" / "model.zip"
        zip_path.parent.parent.mkdir()
        script.build_zip(model_dir, zip_path)
        assert zip_path.is_file()


class TestMain:
    def test_requires_a_token(self, script, monkeypatch, capsys):
        monkeypatch.delenv("HF_TOKEN", raising=False)
        with pytest.raises(SystemExit) as info:
            script.main()
        assert info.value.code == 1
        assert "HF_TOKEN" in capsys.readouterr().err

    def test_token_is_never_printed(self, script, monkeypatch, tmp_path, capsys):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("HF_TOKEN", "hf_" + "A" * 34)

        def fake_download(**kwargs):
            for name in script.REQUIRED_FILES:
                path = Path(kwargs["local_dir"]) / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"x" * 100)
        monkeypatch.setattr(script, "snapshot_download", fake_download)
        monkeypatch.setattr(script, "MIN_ZIP_BYTES", 1)
        script.main()
        output = capsys.readouterr()
        assert "hf_" + "A" * 34 not in output.out + output.err

    def test_too_small_archive_is_rejected(self, script, monkeypatch, tmp_path, capsys):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("HF_TOKEN", "t")

        def fake_download(**kwargs):
            for name in script.REQUIRED_FILES:
                path = Path(kwargs["local_dir"]) / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"x")
        monkeypatch.setattr(script, "snapshot_download", fake_download)
        with pytest.raises(SystemExit) as info:
            script.main()
        assert info.value.code == 1
        assert not (tmp_path / "dist" / "pyannote-community-1.zip.sha256").exists()


def test_required_files_match_the_application(script):
    """Le script du CI et l'application doivent s'accorder sur le contenu du zip."""
    import model_setup
    assert tuple(script.REQUIRED_FILES) == tuple(model_setup._REQUIRED_FILES)
