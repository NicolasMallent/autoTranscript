import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

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

    from gui import App
    app = App()
    app.mainloop()
