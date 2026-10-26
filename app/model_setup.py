"""
Gestion du modèle de diarisation pyannote (speaker-diarization-community-1, CC BY 4.0).

Le modèle est téléchargé une seule fois depuis un asset de la GitHub Release, vérifié par
SHA-256, puis stocké dans ~/.autotranscript/models. Il est ensuite chargé depuis ce dossier
local : aucun compte ni token HuggingFace n'est nécessaire côté utilisateur.
"""
import hashlib
import logging
import os
import shutil
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable, Optional

from paths import APP_DATA_DIR

ProgressCallback = Optional[Callable[[str, float], None]]

_logger = logging.getLogger("autotranscript.model_setup")

_MODELS_DIR = APP_DATA_DIR / "models"

# Dossier du modèle, tel que pyannote le charge (config.yaml + sous-dossiers)
MODEL_DIR = _MODELS_DIR / "speaker-diarization-community-1"

# Cache des versions précédentes (poids stockés au format HuggingFace), supprimé après migration
_LEGACY_CACHE_DIR = _MODELS_DIR / "pyannote-cache"

# Fichiers sans lesquels le modèle est inutilisable
_REQUIRED_FILES = (
    "config.yaml",
    "segmentation/pytorch_model.bin",
    "embedding/pytorch_model.bin",
    "plda/plda.npz",
    "plda/xvec_transform.npz",
)

# URL de l'asset sur la Release GitHub (publié par release.yml avec son empreinte .sha256)
_RELEASE_URL = (
    "https://github.com/NicolasMallent/autoTranscript"
    "/releases/latest/download/pyannote-community-1.zip"
)

_TIMEOUT_SECONDS = 30
_CHUNK_SIZE = 256 * 1024


def model_path() -> Path:
    """Renvoie le dossier local du modèle de diarisation (présent ou non)."""
    return MODEL_DIR


def is_model_ready() -> bool:
    """Indique si tous les fichiers nécessaires du modèle sont présents en local."""
    return all((MODEL_DIR / name).is_file() for name in _REQUIRED_FILES)


def _report(cb: ProgressCallback, msg: str, pct: float) -> None:
    if cb:
        cb(msg, pct)


def _fetch_expected_sha256() -> str:
    """Lit l'empreinte SHA-256 publiée à côté de l'archive."""
    url = _RELEASE_URL + ".sha256"
    try:
        with urllib.request.urlopen(url, timeout=_TIMEOUT_SECONDS) as response:
            # Format de sha256sum : "<empreinte>  <nom de fichier>"
            return response.read().decode("ascii").split()[0].lower()
    except (urllib.error.URLError, TimeoutError, UnicodeDecodeError, IndexError) as exc:
        raise RuntimeError(f"Cannot read the model checksum ({url}): {exc}") from exc


def _download(zip_path: Path, progress_callback: ProgressCallback) -> str:
    """Télécharge l'archive dans zip_path et renvoie son SHA-256."""
    digest = hashlib.sha256()
    try:
        with urllib.request.urlopen(_RELEASE_URL, timeout=_TIMEOUT_SECONDS) as response:
            total = int(response.headers.get("Content-Length", 0))
            _logger.info("Téléchargement du modèle (%d Mo)", total // (1024 * 1024))
            done = 0
            with open(zip_path, "wb") as f:
                while chunk := response.read(_CHUNK_SIZE):
                    f.write(chunk)
                    digest.update(chunk)
                    done += len(chunk)
                    if total > 0:
                        _report(
                            progress_callback,
                            f"diarization_model_dl:{done // (1024*1024)}/{total // (1024*1024)}",
                            (done / total) * 0.9,
                        )
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError(f"Cannot download the diarization model ({_RELEASE_URL}): {exc}") from exc
    return digest.hexdigest()


def _download_and_extract(progress_callback: ProgressCallback = None) -> None:
    _MODELS_DIR.mkdir(parents=True, exist_ok=True)

    # Dossier de travail sur le même disque que MODEL_DIR, pour un déplacement atomique
    work_dir = Path(tempfile.mkdtemp(prefix=".download-", dir=_MODELS_DIR))
    try:
        zip_path = work_dir / "model.zip"

        _report(progress_callback, "diarization_model_connecting", 0.0)
        expected = _fetch_expected_sha256()
        actual = _download(zip_path, progress_callback)
        if actual != expected:
            _logger.error("Empreinte SHA-256 différente : attendue %s, obtenue %s", expected, actual)
            raise RuntimeError("Diarization model archive is corrupted or altered (SHA-256 mismatch)")
        _logger.info("Empreinte SHA-256 vérifiée")

        _report(progress_callback, "diarization_model_extracting", 0.92)
        extract_root = work_dir / "extracted"
        with zipfile.ZipFile(zip_path) as archive:
            archive.extractall(extract_root)

        contents = list(extract_root.iterdir())
        source = contents[0] if len(contents) == 1 and contents[0].is_dir() else extract_root

        missing = [name for name in _REQUIRED_FILES if not (source / name).is_file()]
        if missing:
            raise RuntimeError(f"Diarization model archive is incomplete, missing: {missing}")

        # Le dossier existant, s'il y en a un, est incomplet (sinon on ne serait pas ici)
        shutil.rmtree(MODEL_DIR, ignore_errors=True)
        os.replace(source, MODEL_DIR)
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)

    if _LEGACY_CACHE_DIR.exists():
        _logger.info("Suppression de l'ancien cache de modèles : %s", _LEGACY_CACHE_DIR)
        shutil.rmtree(_LEGACY_CACHE_DIR, ignore_errors=True)

    _logger.info("Modèle de diarisation installé dans %s", MODEL_DIR)
    _report(progress_callback, "diarization_model_ready", 1.0)


def ensure_model(progress_callback: ProgressCallback = None) -> Path:
    """
    Télécharge le modèle de diarisation s'il est absent ou incomplet.

    Args:
        progress_callback: Appelé avec (code_message, progression entre 0 et 1).

    Returns:
        Le dossier local du modèle, à passer tel quel à pyannote.

    Raises:
        RuntimeError: Si le téléchargement échoue, si l'archive est corrompue ou incomplète.
    """
    if not is_model_ready():
        _logger.info("Modèle de diarisation absent ou incomplet : téléchargement")
        _download_and_extract(progress_callback)
    else:
        _logger.debug("Modèle de diarisation déjà présent")
        _report(progress_callback, "diarization_model_cached", 1.0)
    return MODEL_DIR
