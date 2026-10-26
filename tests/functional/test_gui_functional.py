"""
Test de contrat entre le thread de transcription et la fenêtre.

Chaque code que ``transcriber.py`` ou ``model_setup.py`` envoie à la fenêtre doit être compris par
``gui._translate_message`` : sans cela, le message serait ignoré en silence (aucune ligne dans le
journal de la fenêtre). Et inversement, la fenêtre ne doit pas garder de code que personne n'émet.
"""
import ast
import json

import pytest

pytest.importorskip("tkinter")
pytest.importorskip("customtkinter")

import gui  # noqa: E402

# Fonctions par lesquelles un module envoie un code : (nom de l'appel, position du code dans les arguments)
CALLBACKS = {"cb": 0, "progress_callback": 0, "_report": 1}


def emitted_codes(source_path) -> set[str]:
    """Codes envoyés par un module, relevés dans le code source (la partie avant le « : » d'un f-string)."""
    codes = set()
    for node in ast.walk(ast.parse(source_path.read_text(encoding="utf-8"))):
        if not isinstance(node, ast.Call):
            continue
        name = node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", None)
        position = CALLBACKS.get(name)
        if position is None or len(node.args) <= position:
            continue
        code = node.args[position]
        if isinstance(code, ast.Constant) and isinstance(code.value, str):
            codes.add(code.value.split(":")[0])
        elif isinstance(code, ast.JoinedStr) and code.values and isinstance(code.values[0], ast.Constant):
            codes.add(code.values[0].value.split(":")[0])
    return codes


@pytest.fixture
def all_codes(project_root):
    codes = set()
    for module in ("transcriber.py", "model_setup.py", "nltk_setup.py"):
        codes |= emitted_codes(project_root / "app" / module)
    return codes


def example_message(code: str) -> str:
    """Un message plausible pour ce code (« 1/2 » convient aux codes à argument comme à ceux à compteurs)."""
    needs_argument = code in gui._EVENTS_WITH_ARGUMENT or code in gui._EVENTS_WITH_COUNTS
    return f"{code}:1/2" if needs_argument else code


def test_the_source_scan_finds_the_known_codes(all_codes):
    assert {"processing_file", "done_file", "all_done", "cancelled", "diarization_model_dl",
            "diarization_model_ready", "error", "done_with_errors", "sentence_data_download",
            "sentence_data_unavailable"} <= all_codes
    assert len(all_codes) >= 15


def test_every_emitted_code_is_understood_by_the_window(all_codes):
    ignored = sorted(code for code in all_codes if gui._translate_message(example_message(code)) is None)
    assert ignored == [], f"codes émis mais ignorés par la fenêtre : {ignored}"


def test_every_translated_code_is_emitted_by_someone(all_codes):
    known = set(gui._EVENTS_WITH_ARGUMENT) | set(gui._EVENTS_WITHOUT_ARGUMENT) | set(gui._EVENTS_WITH_COUNTS)
    assert sorted(known - all_codes) == [], "codes traduits mais jamais émis (code mort ?)"


def test_every_journal_line_has_a_translation_in_both_languages(project_root):
    keys = {key for key, _ in gui._EVENTS_WITH_ARGUMENT.values()}
    keys |= set(gui._EVENTS_WITHOUT_ARGUMENT.values())
    keys |= {key for key, _, _ in gui._EVENTS_WITH_COUNTS.values()}
    for lang in ("fr", "en"):
        texts = json.loads((project_root / "i18n" / f"{lang}.json").read_text(encoding="utf-8"))
        assert sorted(keys - set(texts)) == [], f"clés absentes de {lang}.json"
