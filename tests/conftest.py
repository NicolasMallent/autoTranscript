"""
Configuration pytest : isole le dossier personnel et expose le code de app/ comme le fait
l'application (modules importés à plat : ``import transcriber``).
"""
import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

# HOME est remplacé AVANT tout import de l'application : paths.APP_DATA_DIR est calculé à
# l'import, et aucun test ne doit toucher au vrai ~/.autotranscript de l'utilisateur.
_TEST_HOME = tempfile.mkdtemp(prefix="autotranscript-tests-home-")
os.environ["HOME"] = _TEST_HOME
os.environ["USERPROFILE"] = _TEST_HOME

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "app"))


def pytest_sessionfinish(session, exitstatus):
    shutil.rmtree(_TEST_HOME, ignore_errors=True)


@pytest.fixture
def project_root() -> Path:
    """Racine du dépôt."""
    return _ROOT


@pytest.fixture
def model_setup_dirs(tmp_path, monkeypatch):
    """Redirige les dossiers de model_setup vers un dossier temporaire et renvoie le module."""
    import model_setup

    models = tmp_path / "models"
    monkeypatch.setattr(model_setup, "_MODELS_DIR", models)
    monkeypatch.setattr(model_setup, "MODEL_DIR", models / "speaker-diarization-community-1")
    monkeypatch.setattr(model_setup, "_LEGACY_CACHE_DIR", models / "pyannote-cache")
    return model_setup


@pytest.fixture
def ui_lang():
    """Charge l'interface en français et restaure l'état de i18n après le test."""
    import i18n

    saved = (i18n._strings, i18n._current_lang)
    i18n.load("fr")
    yield i18n
    i18n._strings, i18n._current_lang = saved


@pytest.fixture
def fake_tmpdir(tmp_path, monkeypatch):
    """Dossier temporaire du module tempfile, pour détecter les fichiers qui fuient."""
    path = tmp_path / "tmp"
    path.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(path))
    return path
