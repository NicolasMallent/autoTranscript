"""Chemins partagés par les modules de l'application."""
from pathlib import Path

# Racine de l'installation (dossier qui contient app/, i18n/, models.json, ffmpeg/)
BASE_DIR = Path(__file__).absolute().parent.parent

# Données de l'utilisateur : configuration, modèles téléchargés, journaux
APP_DATA_DIR = Path.home() / ".autotranscript"
