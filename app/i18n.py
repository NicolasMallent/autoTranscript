import json
import logging
import os

from paths import BASE_DIR

_logger = logging.getLogger("autotranscript.i18n")

_strings: dict = {}
_current_lang: str = "fr"


def load(lang: str) -> None:
    """
    Charge les textes de l'interface (i18n/<lang>.json).

    Args:
        lang: Code langue (« fr » ou « en »). Une langue sans fichier retombe sur « fr ».
    """
    global _strings, _current_lang
    path = os.path.join(BASE_DIR, "i18n", f"{lang}.json")
    if not os.path.exists(path):
        lang = "fr"
        path = os.path.join(BASE_DIR, "i18n", "fr.json")
    with open(path, encoding="utf-8") as f:
        _strings = json.load(f)
    _current_lang = lang


def t(key: str, **kwargs) -> str:
    """
    Renvoie le texte traduit d'une clé.

    Args:
        key: Clé du texte dans le fichier de langue.
        **kwargs: Valeurs des champs ``{nom}`` du texte.

    Returns:
        Le texte formaté, ou la clé elle-même si elle n'existe pas dans la langue chargée.
        Si le formatage échoue (paramètre manquant, accolades invalides), le texte est renvoyé
        tel quel et l'incident est journalisé.
    """
    text = _strings.get(key, key)
    if kwargs:
        try:
            text = text.format(**kwargs)
        except (KeyError, IndexError, ValueError):
            # Un texte de traduction mal formé ne doit pas faire planter l'interface
            _logger.warning("Texte mal formé ou paramètre manquant pour la clé %r", key, exc_info=True)
    return text


def current_lang() -> str:
    """Renvoie le code de la langue chargée (« fr » ou « en »)."""
    return _current_lang
