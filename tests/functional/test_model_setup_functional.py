"""
Tests fonctionnels de app/model_setup.py.

Le cycle de vie complet du modèle (téléchargement, vérification, utilisation en cache, réparation)
et le contrat entre le script du CI (scripts/download_pyannote.py) et l'application : le zip que
produit l'un doit être exactement celui que l'autre accepte.
"""
import importlib.util
import urllib.error
from pathlib import Path

import pytest

from helpers import ReleaseServer, make_model_zip, no_network, populate_model_dir


class TestModelLifecycle:
    def test_download_then_cache_then_repair(self, model_setup_dirs, monkeypatch):
        ms = model_setup_dirs
        zip_bytes = make_model_zip()

        # 1. premier usage : téléchargement, avec la progression attendue par l'interface
        server = ReleaseServer(monkeypatch, zip_bytes)
        messages = []
        assert ms.ensure_model(lambda m, p: messages.append(m)) == ms.MODEL_DIR
        assert messages[0] == "diarization_model_connecting" and messages[-1] == "diarization_model_ready"
        assert len(server.urls) == 2 and ms.is_model_ready()

        # 2. usages suivants : aucun accès réseau
        no_network(monkeypatch)
        messages.clear()
        ms.ensure_model(lambda m, p: messages.append(m))
        assert messages == ["diarization_model_cached"]

        # 3. installation endommagée : le modèle est retéléchargé et réparé
        (ms.MODEL_DIR / "embedding" / "pytorch_model.bin").unlink()
        assert not ms.is_model_ready()
        repair = ReleaseServer(monkeypatch, zip_bytes)
        ms.ensure_model()
        assert ms.is_model_ready() and len(repair.urls) == 2

    def test_failed_attempt_then_successful_retry(self, model_setup_dirs, monkeypatch):
        ms = model_setup_dirs
        ReleaseServer(monkeypatch, make_model_zip(), zip_error=urllib.error.URLError("coupure"))
        with pytest.raises(RuntimeError, match="Cannot download"):
            ms.ensure_model()
        assert not ms.MODEL_DIR.exists() and not list(ms._MODELS_DIR.glob(".download-*"))

        ReleaseServer(monkeypatch, make_model_zip())
        ms.ensure_model()
        assert ms.is_model_ready()

    def test_upgrade_from_the_previous_version_cache(self, model_setup_dirs, monkeypatch):
        """Un utilisateur de l'ancienne version (cache HuggingFace) est migré puis nettoyé."""
        ms = model_setup_dirs
        old = ms._LEGACY_CACHE_DIR / "hub" / "models--pyannote--speaker-diarization-3.1" / "snapshots"
        old.mkdir(parents=True)
        (old / "config.yaml").write_text("ancien")
        ReleaseServer(monkeypatch, make_model_zip())
        ms.ensure_model()
        assert ms.is_model_ready() and not ms._LEGACY_CACHE_DIR.exists()


class TestCiScriptContract:
    @pytest.fixture
    def script(self, project_root):
        pytest.importorskip("huggingface_hub")
        spec = importlib.util.spec_from_file_location(
            "download_pyannote", project_root / "scripts" / "download_pyannote.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    @pytest.fixture
    def release_assets(self, script, monkeypatch, tmp_path):
        """Exécute main() du script du CI avec un faux HuggingFace et renvoie (zip, fichier .sha256)."""
        work = tmp_path / "ci"
        work.mkdir()
        monkeypatch.chdir(work)
        monkeypatch.setenv("HF_TOKEN", "hf_" + "B" * 34)
        monkeypatch.setattr(script, "MIN_ZIP_BYTES", 1)

        def fake_snapshot_download(**kwargs):
            target = Path(kwargs["local_dir"])
            for name in script.REQUIRED_FILES:
                (target / name).parent.mkdir(parents=True, exist_ok=True)
                (target / name).write_bytes(b"poids " + name.encode())
            (target / ".cache" / "huggingface").mkdir(parents=True)
            (target / ".cache" / "huggingface" / "download.metadata").write_text("interne")
        monkeypatch.setattr(script, "snapshot_download", fake_snapshot_download)
        script.main()
        return work / "dist" / "pyannote-community-1.zip", work / "dist" / "pyannote-community-1.zip.sha256"

    def test_sha256_file_uses_the_sha256sum_format(self, release_assets):
        zip_path, sha_path = release_assets
        digest, name = sha_path.read_text(encoding="ascii").split()
        assert len(digest) == 64 and name == zip_path.name

    def test_the_application_installs_what_the_ci_script_produces(
            self, release_assets, model_setup_dirs, monkeypatch):
        zip_path, sha_path = release_assets
        ReleaseServer(monkeypatch, zip_path.read_bytes(), sha=sha_path.read_bytes())
        model_setup_dirs.ensure_model()
        assert model_setup_dirs.is_model_ready()
        assert (model_setup_dirs.MODEL_DIR / "LICENSE-NOTICE.txt").is_file()    # attribution CC BY 4.0
        assert not (model_setup_dirs.MODEL_DIR / ".cache").exists()             # métadonnées HF exclues
        assert (model_setup_dirs.MODEL_DIR / "plda" / "plda.npz").read_bytes() == b"poids plda/plda.npz"

    def test_a_tampered_archive_is_refused(self, release_assets, model_setup_dirs, monkeypatch):
        zip_path, sha_path = release_assets
        tampered = zip_path.read_bytes() + b"\x00"
        ReleaseServer(monkeypatch, tampered, sha=sha_path.read_bytes())
        with pytest.raises(RuntimeError, match="SHA-256"):
            model_setup_dirs.ensure_model()
        assert not model_setup_dirs.is_model_ready()

    def test_license_notice_credits_the_authors(self, release_assets, model_setup_dirs, monkeypatch):
        zip_path, sha_path = release_assets
        ReleaseServer(monkeypatch, zip_path.read_bytes(), sha=sha_path.read_bytes())
        model_setup_dirs.ensure_model()
        notice = (model_setup_dirs.MODEL_DIR / "LICENSE-NOTICE.txt").read_text(encoding="utf-8")
        assert "CC BY 4.0" in notice and "Bredin" in notice and "pyannote/speaker-diarization-community-1" in notice

    def test_the_token_does_not_end_up_in_the_archive(self, release_assets):
        zip_path, _ = release_assets
        assert b"hf_" + b"B" * 34 not in zip_path.read_bytes()
