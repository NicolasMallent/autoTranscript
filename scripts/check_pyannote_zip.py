"""
Script CI : vérifie que le zip du modèle pyannote se charge hors ligne et sans token,
exactement comme le fait l'application chez l'utilisateur.

Usage (depuis la racine du repo, après download_pyannote.py) :
    python scripts/check_pyannote_zip.py

Nécessite : pip install pyannote.audio
"""
import hashlib
import os
import sys
import tempfile
import zipfile
from pathlib import Path

ZIP_PATH = Path("dist/pyannote-community-1.zip")

# Simule le poste d'un utilisateur : pas de token, aucun accès à HuggingFace
for name in ("HF_TOKEN", "HUGGING_FACE_HUB_TOKEN"):
    os.environ.pop(name, None)
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["PYANNOTE_METRICS_ENABLED"] = "false"


def check_sha256() -> None:
    expected = Path(str(ZIP_PATH) + ".sha256").read_text(encoding="ascii").split()[0]
    actual = hashlib.sha256(ZIP_PATH.read_bytes()).hexdigest()
    if actual != expected:
        print("ERREUR : empreinte SHA-256 incohérente avec l'archive.", file=sys.stderr)
        sys.exit(1)
    print("✓ SHA-256")


def main() -> None:
    check_sha256()

    with tempfile.TemporaryDirectory() as tmp:
        with zipfile.ZipFile(ZIP_PATH) as archive:
            archive.extractall(tmp)
        (model_dir,) = list(Path(tmp).iterdir())

        from pyannote.audio import Pipeline

        pipeline = Pipeline.from_pretrained(str(model_dir))
        if pipeline is None:
            print("ERREUR : la pipeline n'a pas pu être chargée depuis le zip.", file=sys.stderr)
            sys.exit(1)
        print(f"✓ Pipeline chargée hors ligne depuis {model_dir.name}")


if __name__ == "__main__":
    main()
