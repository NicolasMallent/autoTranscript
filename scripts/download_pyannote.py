"""
Script CI : télécharge le modèle pyannote depuis HuggingFace et le package en zip
(avec son empreinte SHA-256) pour upload dans la GitHub Release.

Le token n'est utilisé qu'ici : les utilisateurs de l'application téléchargent le zip depuis
la Release et n'ont besoin d'aucun compte HuggingFace.

Usage (depuis la racine du repo) :
    HF_TOKEN=<token> python scripts/download_pyannote.py

Nécessite : pip install huggingface_hub
Le compte du token doit avoir accepté les conditions d'utilisation du modèle sur
https://huggingface.co/pyannote/speaker-diarization-community-1
"""
import hashlib
import os
import sys
import time
import zipfile
from pathlib import Path

try:
    from huggingface_hub import snapshot_download
    from huggingface_hub.errors import HfHubHTTPError
except ImportError:
    print("ERREUR : pip install huggingface_hub", file=sys.stderr)
    sys.exit(1)

MODEL_ID = "pyannote/speaker-diarization-community-1"
MODEL_DIR_NAME = "speaker-diarization-community-1"
ZIP_PATH = Path("dist/pyannote-community-1.zip")

# Doit rester aligné avec _REQUIRED_FILES dans app/model_setup.py
REQUIRED_FILES = (
    "config.yaml",
    "segmentation/pytorch_model.bin",
    "embedding/pytorch_model.bin",
    "plda/plda.npz",
    "plda/xvec_transform.npz",
)

MAX_RETRIES = 6
# Délais croissants : 60s, 120s, 180s, 240s, 300s
WAIT_SECONDS = [60, 120, 180, 240, 300]

# Un zip plus petit est forcément incomplet (le modèle pèse plusieurs dizaines de Mo)
MIN_ZIP_BYTES = 10 * 1024 * 1024

LICENSE_NOTICE = """\
This archive redistributes {model_id} (pyannote.audio speaker diarization), unmodified.
Authors: Hervé Bredin et al., pyannoteAI. License: CC BY 4.0
https://creativecommons.org/licenses/by/4.0/
Source: https://huggingface.co/{model_id}
Redistributed by AutoTranscript (https://github.com/NicolasMallent/autoTranscript).
"""


def is_rate_limit(exc: Exception) -> bool:
    """Indique si l'exception est une réponse HTTP 429 de HuggingFace."""
    return isinstance(exc, HfHubHTTPError) and exc.response is not None and exc.response.status_code == 429


def download_model(token: str, target: Path) -> None:
    """Télécharge le modèle dans target, en réessayant en cas de rate limit (429)."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            snapshot_download(
                repo_id=MODEL_ID,
                token=token,
                local_dir=target,
                ignore_patterns=["*.gif", ".gitattributes"],
            )
            return
        except Exception as exc:
            if is_rate_limit(exc) and attempt < MAX_RETRIES:
                wait = WAIT_SECONDS[min(attempt - 1, len(WAIT_SECONDS) - 1)]
                print(f"  Rate limit (429) — attente {wait}s avant tentative {attempt + 1}/{MAX_RETRIES}...")
                time.sleep(wait)
            else:
                raise


def check_model(target: Path) -> None:
    """Quitte avec une erreur si un fichier indispensable manque."""
    missing = [name for name in REQUIRED_FILES if not (target / name).is_file()]
    if missing:
        print(f"ERREUR : fichiers manquants dans le modèle téléchargé : {missing}", file=sys.stderr)
        sys.exit(1)


def build_zip(source: Path, zip_path: Path) -> str:
    """Crée le zip (dossier racine = nom du modèle) et renvoie son SHA-256."""
    zip_path.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file in sorted(source.rglob("*")):
            # .cache : métadonnées internes de huggingface_hub, inutiles aux utilisateurs
            if file.is_file() and ".cache" not in file.relative_to(source).parts:
                zf.write(file, Path(MODEL_DIR_NAME) / file.relative_to(source))
    return hashlib.sha256(zip_path.read_bytes()).hexdigest()


def main() -> None:
    token = os.environ.get("HF_TOKEN")
    if not token:
        print("ERREUR : variable d'environnement HF_TOKEN manquante.", file=sys.stderr)
        sys.exit(1)

    target = Path("pyannote-community-1") / MODEL_DIR_NAME
    target.mkdir(parents=True, exist_ok=True)

    print(f"→ Téléchargement de {MODEL_ID}...")
    download_model(token, target)
    check_model(target)
    print(f"  ✓ {MODEL_ID}")

    (target / "LICENSE-NOTICE.txt").write_text(LICENSE_NOTICE.format(model_id=MODEL_ID), encoding="utf-8")

    print(f"\n→ Création de {ZIP_PATH}...")
    sha256 = build_zip(target, ZIP_PATH)
    size = ZIP_PATH.stat().st_size
    if size < MIN_ZIP_BYTES:
        print(f"ERREUR : archive trop petite ({size} octets), téléchargement incomplet ?", file=sys.stderr)
        sys.exit(1)

    # Format de sha256sum, relu par app/model_setup.py
    Path(str(ZIP_PATH) + ".sha256").write_text(f"{sha256}  {ZIP_PATH.name}\n", encoding="utf-8")
    print(f"✓ {ZIP_PATH} ({size / (1024 * 1024):.0f} Mo, sha256 {sha256[:12]}…)")


if __name__ == "__main__":
    main()
