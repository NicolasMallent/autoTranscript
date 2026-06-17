"""
Téléchargement et préparation du modèle de diarisation (pyannote, licence CC-BY-4.0).

Le modèle est téléchargé une seule fois, au premier lancement de
l'application, depuis une Release GitHub préparée par le développeur (voir
README.md). Aucun compte Hugging Face ni token n'est nécessaire pour les
utilisateurs finaux.
"""
import shutil
import tempfile
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable, Optional

from config import MODEL_DIR, MODEL_MARKER_FILE, MODEL_RELEASE_URL

ProgressCallback = Optional[Callable[[str, float], None]]


def is_model_ready(model_dir: Path = MODEL_DIR) -> bool:
    """Renvoie True si le modèle est déjà installé localement."""
    return (model_dir / MODEL_MARKER_FILE).exists()


def _report(callback: ProgressCallback, message: str, fraction: float) -> None:
    if callback is not None:
        callback(message, fraction)


def download_and_extract_model(
    model_dir: Path = MODEL_DIR,
    url: str = MODEL_RELEASE_URL,
    progress_callback: ProgressCallback = None,
) -> None:
    """
    Télécharge l'archive du modèle depuis `url` et l'extrait dans `model_dir`.
    Signale la progression via `progress_callback(message, fraction_0_a_1)`.
    """
    model_dir.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp_dir:
        zip_path = Path(tmp_dir) / "model.zip"

        _report(progress_callback, "Connexion au serveur de modèles…", 0.0)
        with urllib.request.urlopen(url) as response:
            total_size = int(response.headers.get("Content-Length", 0))
            downloaded = 0
            chunk_size = 1024 * 256  # 256 Ko

            with open(zip_path, "wb") as out_file:
                while True:
                    chunk = response.read(chunk_size)
                    if not chunk:
                        break
                    out_file.write(chunk)
                    downloaded += len(chunk)
                    if total_size > 0:
                        fraction = min(downloaded / total_size, 1.0)
                        mb_done = downloaded / (1024 * 1024)
                        mb_total = total_size / (1024 * 1024)
                        _report(
                            progress_callback,
                            f"Téléchargement du modèle… {mb_done:.0f} / {mb_total:.0f} Mo",
                            fraction * 0.9,  # on garde les derniers 10% pour l'extraction
                        )

        _report(progress_callback, "Extraction du modèle…", 0.95)

        extract_root = Path(tmp_dir) / "extracted"
        with zipfile.ZipFile(zip_path, "r") as archive:
            archive.extractall(extract_root)

        # L'archive peut contenir directement les fichiers du modèle, ou un
        # unique sous-dossier qui les contient : on gère les deux cas.
        contents = list(extract_root.iterdir())
        source_dir = contents[0] if len(contents) == 1 and contents[0].is_dir() else extract_root

        if model_dir.exists():
            shutil.rmtree(model_dir)
        shutil.move(str(source_dir), str(model_dir))

    _report(progress_callback, "Modèle prêt.", 1.0)


def ensure_model(progress_callback: ProgressCallback = None) -> Path:
    """
    S'assure que le modèle de diarisation est disponible localement, le
    télécharge si besoin, et renvoie le chemin local à utiliser.
    """
    if not is_model_ready():
        download_and_extract_model(progress_callback=progress_callback)
    else:
        _report(progress_callback, "Modèle déjà installé.", 1.0)
    return MODEL_DIR
