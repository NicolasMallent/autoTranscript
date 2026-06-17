"""
Script CI : télécharge les modèles pyannote depuis HuggingFace et les package
en zip pour upload dans la GitHub Release.

Usage (depuis la racine du repo) :
    HF_TOKEN=<token> python scripts/download_pyannote.py

Nécessite : pip install huggingface_hub
"""
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

TOKEN = os.environ.get("HF_TOKEN")
if not TOKEN:
    print("ERREUR : variable d'environnement HF_TOKEN manquante.", file=sys.stderr)
    sys.exit(1)

CACHE_DIR = Path("pyannote-community-1") / "hub"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

MODELS = [
    "pyannote/speaker-diarization-3.1",
    "pyannote/segmentation-3.0",
    "pyannote/wespeaker-voxceleb-resnet34-LM",
]

MAX_RETRIES = 5

for model_id in MODELS:
    print(f"→ Téléchargement de {model_id}...")
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            snapshot_download(
                repo_id=model_id,
                token=TOKEN,
                cache_dir=CACHE_DIR,
                ignore_patterns=["*.h5", "*.msgpack", "flax_model*", "tf_model*", "rust_model*"],
            )
            print(f"  ✓ {model_id}")
            break
        except HfHubHTTPError as e:
            if "429" in str(e) and attempt < MAX_RETRIES:
                wait = 30 * attempt
                print(f"  Rate limit (429), attente {wait}s avant tentative {attempt + 1}/{MAX_RETRIES}...")
                time.sleep(wait)
            else:
                raise

# Création du zip
zip_path = Path("dist/pyannote-community-1.zip")
zip_path.parent.mkdir(exist_ok=True)
print(f"\n→ Création de {zip_path}...")
with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
    for file in sorted(Path("pyannote-community-1").rglob("*")):
        if file.is_file():
            zf.write(file, file.relative_to("pyannote-community-1"))

size_mb = zip_path.stat().st_size / (1024 * 1024)
print(f"✓ {zip_path} ({size_mb:.0f} Mo)")
