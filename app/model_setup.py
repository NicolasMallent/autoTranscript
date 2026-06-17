"""
Gestion du modèle de diarisation pyannote.
Le modèle est téléchargé une seule fois depuis un asset GitHub Release,
puis mis en cache — les utilisateurs finaux n'ont besoin d'aucun compte HuggingFace.
"""
import os
import shutil
import tempfile
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable, Optional

ProgressCallback = Optional[Callable[[str, float], None]]

# Répertoire de cache local
MODEL_CACHE_DIR = Path.home() / ".autotranscript" / "models" / "pyannote-cache"

# Indicateur de présence du modèle (créé par snapshot_download)
_MARKER = MODEL_CACHE_DIR / "hub" / "models--pyannote--speaker-diarization-3.1"

# URL de l'asset sur la Release GitHub (mise à jour par la CI à chaque release)
_RELEASE_URL = (
    "https://github.com/NicolasMallent/autoTranscript"
    "/releases/latest/download/pyannote-community-1.zip"
)


def is_model_ready() -> bool:
    return _MARKER.exists()


def setup_env() -> None:
    """Pointe HF_HOME vers notre cache local pour que pyannote ne télécharge pas."""
    os.environ["HF_HOME"] = str(MODEL_CACHE_DIR)


def _report(cb: ProgressCallback, msg: str, pct: float) -> None:
    if cb:
        cb(msg, pct)


def _download_and_extract(progress_callback: ProgressCallback = None) -> None:
    MODEL_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        zip_path = Path(tmp) / "model.zip"

        _report(progress_callback, "diarization_model_connecting", 0.0)
        with urllib.request.urlopen(_RELEASE_URL) as response:
            total = int(response.headers.get("Content-Length", 0))
            done = 0
            with open(zip_path, "wb") as f:
                while chunk := response.read(256 * 1024):
                    f.write(chunk)
                    done += len(chunk)
                    if total > 0:
                        _report(
                            progress_callback,
                            f"diarization_model_dl:{done // (1024*1024)}/{total // (1024*1024)}",
                            (done / total) * 0.9,
                        )

        _report(progress_callback, "diarization_model_extracting", 0.92)
        extract_root = Path(tmp) / "extracted"
        with zipfile.ZipFile(zip_path) as archive:
            archive.extractall(extract_root)

        contents = list(extract_root.iterdir())
        source = contents[0] if len(contents) == 1 and contents[0].is_dir() else extract_root

        if MODEL_CACHE_DIR.exists():
            shutil.rmtree(MODEL_CACHE_DIR)
        shutil.move(str(source), str(MODEL_CACHE_DIR))

    _report(progress_callback, "diarization_model_ready", 1.0)


def ensure_model(progress_callback: ProgressCallback = None) -> Path:
    """Télécharge le modèle si absent, configure HF_HOME, renvoie le répertoire de cache."""
    if not is_model_ready():
        _download_and_extract(progress_callback)
    else:
        _report(progress_callback, "diarization_model_cached", 1.0)
    setup_env()
    return MODEL_CACHE_DIR
