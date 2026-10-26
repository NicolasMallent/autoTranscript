"""Tests unitaires de app/i18n.py et cohérence des fichiers de langue."""
import ast
import json
import logging
import re

import pytest

import i18n

PLACEHOLDER = re.compile(r"\{(\w+)\}")


def _load_json(project_root, lang):
    path = project_root / "i18n" / f"{lang}.json"

    def no_duplicates(pairs):
        keys = [k for k, _ in pairs]
        duplicated = {k for k in keys if keys.count(k) > 1}
        assert not duplicated, f"clés en double dans {lang}.json : {duplicated}"
        return dict(pairs)

    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=no_duplicates)


@pytest.fixture
def restore_i18n():
    saved = (i18n._strings, i18n._current_lang)
    yield
    i18n._strings, i18n._current_lang = saved


@pytest.mark.usefixtures("restore_i18n")
class TestLoadAndTranslate:
    def test_load_french(self):
        i18n.load("fr")
        assert i18n.current_lang() == "fr"
        assert i18n.t("tab_settings") == "Paramètres"

    def test_load_english(self):
        i18n.load("en")
        assert i18n.current_lang() == "en"
        assert i18n.t("tab_settings") == "Settings"

    def test_unknown_language_falls_back_to_french(self):
        i18n.load("xx")
        assert i18n.current_lang() == "fr"
        assert i18n.t("tab_settings") == "Paramètres"

    def test_language_with_path_characters_falls_back(self):
        i18n.load("../fr")
        assert i18n.current_lang() == "fr"

    def test_unknown_key_returns_the_key(self):
        i18n.load("fr")
        assert i18n.t("cle_inexistante") == "cle_inexistante"

    def test_empty_key(self):
        i18n.load("fr")
        assert i18n.t("") == ""

    def test_placeholders_are_formatted(self):
        i18n.load("fr")
        assert i18n.t("log_done_file", file="a.mp3") == "Terminé : a.mp3"

    def test_extra_kwargs_are_ignored(self):
        i18n.load("fr")
        assert i18n.t("tab_settings", inutile=1) == "Paramètres"

    def test_switching_language_replaces_texts(self):
        i18n.load("fr")
        i18n.load("en")
        assert i18n.t("cancel_button") == "Cancel"

    def test_without_kwargs_placeholders_are_left_as_is(self):
        i18n.load("fr")
        assert i18n.t("log_done_file") == "Terminé : {file}"

    def test_missing_placeholder_does_not_crash(self):
        i18n.load("fr")
        assert i18n.t("log_done_file", autre=1) == "Terminé : {file}"

    def test_missing_placeholder_is_logged(self, caplog):
        i18n.load("fr")
        with caplog.at_level(logging.WARNING, logger="autotranscript.i18n"):
            i18n.t("log_done_file", autre=1)
        assert "log_done_file" in caplog.text

    @pytest.mark.parametrize("text", ["{", "positionnel {} vide", "{0} indexé", "accolade } seule {x"])
    def test_malformed_text_does_not_crash(self, monkeypatch, text):
        monkeypatch.setattr(i18n, "_strings", {"cle": text})
        assert i18n.t("cle", valeur=1) == text

    def test_correct_placeholders_still_work_after_a_failure(self):
        i18n.load("fr")
        i18n.t("log_done_file", autre=1)
        assert i18n.t("log_done_file", file="b.wav") == "Terminé : b.wav"


class TestLanguageFiles:
    def test_same_keys_in_both_languages(self, project_root):
        fr, en = _load_json(project_root, "fr"), _load_json(project_root, "en")
        assert set(fr) - set(en) == set(), "clés absentes de en.json"
        assert set(en) - set(fr) == set(), "clés absentes de fr.json"

    def test_same_placeholders_in_both_languages(self, project_root):
        fr, en = _load_json(project_root, "fr"), _load_json(project_root, "en")
        for key in fr:
            assert set(PLACEHOLDER.findall(fr[key])) == set(PLACEHOLDER.findall(en[key])), key

    @pytest.mark.parametrize("lang", ["fr", "en"])
    def test_no_empty_text(self, project_root, lang):
        empty = [k for k, v in _load_json(project_root, lang).items() if not v.strip()]
        assert empty == []

    def test_every_key_used_in_code_exists(self, project_root):
        """Toute clé passée en littéral à t(...) doit exister dans les fichiers de langue."""
        known = set(_load_json(project_root, "fr"))

        def literals(node):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                yield node.value
            elif isinstance(node, ast.IfExp):
                yield from literals(node.body)
                yield from literals(node.orelse)

        used = {}
        for source in (project_root / "app").glob("*.py"):
            for node in ast.walk(ast.parse(source.read_text(encoding="utf-8"))):
                if not isinstance(node, ast.Call) or not node.args:
                    continue
                func = node.func
                name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
                if name == "t":
                    for key in literals(node.args[0]):
                        used[key] = source.name
        missing = {k: f for k, f in used.items() if k not in known}
        assert used, "aucun appel t(...) trouvé : le test ne vérifie plus rien"
        assert missing == {}, f"clés utilisées mais absentes de fr.json : {missing}"
