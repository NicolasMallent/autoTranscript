"""
Réglages de l'application.
"""
from pathlib import Path

APP_NAME = "TranscriptionAudio"

# Dossier local où le modèle de diarisation sera stocké après le premier
# téléchargement (un dossier caché dans le profil de l'utilisateur).
MODEL_DIR = Path.home() / f".{APP_NAME.lower()}" / "models" / "pyannote-community-1"

# URL de l'asset à télécharger depuis une Release GitHub.
# >>> À REMPLACER par l'URL réelle une fois que tu as créé ta Release <<<
# Exemple : "https://github.com/TON_COMPTE/TON_REPO/releases/download/v1.0/pyannote-community-1.zip"
MODEL_RELEASE_URL = "https://github.com/TON_COMPTE/TON_REPO/releases/download/v1.0/pyannote-community-1.zip"

# Fichier dont la présence indique que le modèle est déjà installé localement.
MODEL_MARKER_FILE = "config.yaml"

# Tailles de modèle Whisper proposées dans l'interface (vitesse <-> précision).
WHISPER_MODEL_SIZES = ["tiny", "base", "small", "medium", "large-v2", "large-v3"]
DEFAULT_WHISPER_MODEL = "small"

# Langues proposées dans l'interface (libellé affiché -> code Whisper).
# "" = détection automatique de la langue.
LANGUAGES = {
    "Détection automatique": "",
    "Français": "fr",
    "Anglais": "en",
    "Espagnol": "es",
    "Allemand": "de",
    "Italien": "it",
}
