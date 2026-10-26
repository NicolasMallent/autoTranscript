"""Point d'entrée : ``python app/main.py`` ouvre l'interface, ``--check`` vérifie l'installation."""
import os
import sys

# Les modules de app/ s'importent « à plat » (import log_setup, import gui…). Ce chemin est ajouté
# explicitement car le Python embarqué de Windows tourne en mode isolé (fichier ._pth) : le dossier
# du script n'y est pas dans sys.path. Ne pas le retirer sans tester une installation Windows
# (tests/functional/test_main_functional.py le vérifie avec « python -I »).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Aucune télémétrie : promesse « entièrement local » du README (à définir avant tout import
# de huggingface_hub / pyannote, qui lisent ces variables au chargement)
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
os.environ["PYANNOTE_METRICS_ENABLED"] = "false"
# Téléchargement HuggingFace sans le protocole Xet : ses serveurs (*.xethub.hf.co) sont souvent
# bloqués par les pare-feu d'entreprise. setdefault permet de le réactiver depuis l'environnement.
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")

import log_setup

if __name__ == "__main__":
    if "--check" in sys.argv:
        # Smoke test : vérifie que les fichiers et dépendances GUI sont présents
        import json
        import pathlib

        base = pathlib.Path(__file__).parent.parent
        missing = []
        for p in [base / "models.json", base / "i18n" / "fr.json", base / "i18n" / "en.json"]:
            if not p.exists():
                missing.append(str(p))
        if missing:
            print("ERREUR : fichiers manquants :", missing)
            sys.exit(1)

        try:
            import customtkinter  # noqa: F401
        except ImportError as e:
            print(f"ERREUR : {e}")
            sys.exit(1)

        print("OK")
        sys.exit(0)

    log_setup.setup_logging()

    from gui import App
    app = App()
    app.mainloop()
