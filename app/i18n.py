import json
import os

_strings: dict = {}
_current_lang: str = "fr"

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load(lang: str) -> None:
    global _strings, _current_lang
    path = os.path.join(_BASE_DIR, "i18n", f"{lang}.json")
    if not os.path.exists(path):
        lang = "fr"
        path = os.path.join(_BASE_DIR, "i18n", "fr.json")
    with open(path, encoding="utf-8") as f:
        _strings = json.load(f)
    _current_lang = lang


def t(key: str, **kwargs) -> str:
    text = _strings.get(key, key)
    if kwargs:
        text = text.format(**kwargs)
    return text


def current_lang() -> str:
    return _current_lang
