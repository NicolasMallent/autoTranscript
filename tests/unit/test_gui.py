"""
Tests unitaires de app/gui.py.

Aucune fenêtre n'est ouverte (pas d'écran requis) : les méthodes de App sont appelées
« à vide », avec un faux ``self`` qui ne fournit que les variables Tk lues par la méthode.
"""
import json
import types

import pytest

pytest.importorskip("tkinter")
pytest.importorskip("customtkinter")

import gui  # noqa: E402


class Var:
    """Remplace une variable Tk (StringVar / BooleanVar) : seul ``get`` est utilisé."""

    def __init__(self, value):
        self._value = value

    def get(self):
        return self._value


def fake_app(**variables):
    return types.SimpleNamespace(**{name: Var(value) for name, value in variables.items()})


class TestSelectedSpeakers:
    @pytest.mark.parametrize("minimum, maximum, expected", [
        ("", "", (None, None)),
        ("2", "5", (2, 5)),
        (" 3 ", " 4 ", (3, 4)),
        ("0", "-2", (None, None)),
        ("abc", "2.5", (None, None)),
        ("2", "", (2, None)),
        ("", "10", (None, 10)),
        ("   ", "1", (None, 1)),
    ])
    def test_parsing(self, minimum, maximum, expected):
        app = fake_app(_min_speakers_var=minimum, _max_speakers_var=maximum)
        assert gui.App._selected_speakers(app) == expected


class TestSelectedFormats:
    @pytest.mark.parametrize("txt, srt, js, expected", [
        (True, True, False, ["txt", "srt"]),
        (False, False, True, ["json"]),
        (True, True, True, ["txt", "srt", "json"]),
        (False, False, False, []),
    ])
    def test_formats(self, txt, srt, js, expected):
        app = fake_app(_fmt_txt=txt, _fmt_srt=srt, _fmt_json=js)
        assert gui.App._selected_formats(app) == expected


class TestSelectedWhisperLang:
    @pytest.mark.parametrize("key, expected", [
        ("whisper_lang_french", "fr"),
        ("whisper_lang_english", "en"),
        ("whisper_lang_auto", ""),
    ])
    @pytest.mark.parametrize("ui", ["fr", "en"])
    def test_label_is_mapped_to_a_code(self, ui_lang, ui, key, expected):
        ui_lang.load(ui)
        app = fake_app(_whisper_lang_var=ui_lang.t(key))
        assert gui.App._selected_whisper_lang(app) == expected

    def test_unknown_label_means_auto_detection(self, ui_lang):
        assert gui.App._selected_whisper_lang(fake_app(_whisper_lang_var="Klingon")) == ""

    def test_every_language_key_has_a_translation(self, ui_lang):
        for key in gui.WHISPER_LANGUAGES:
            assert ui_lang.t(key) != key


class TestSelectedModelId:
    @pytest.mark.parametrize("label, expected", [
        ("base  (139 MB) — Fast, decent accuracy", "base"),
        ("large-v3  (2.9 GB) — Meilleure qualité (recommandé)", "large-v3"),
        ("tiny", "tiny"),
    ])
    def test_id_is_the_first_word(self, label, expected):
        assert gui.App._selected_model_id(fake_app(_model_var=label)) == expected

    def test_labels_built_from_models_json_round_trip(self):
        for model in gui._load_models():
            label = f"{model['id']}  ({model['size']}) — {model['fr']}"
            assert gui.App._selected_model_id(fake_app(_model_var=label)) == model["id"]


class TestModelsJson:
    def test_structure(self):
        models = gui._load_models()
        assert models, "models.json est vide"
        for model in models:
            assert {"id", "size", "fr", "en"} <= set(model)
            assert " " not in model["id"]

    def test_ids_are_unique(self):
        ids = [m["id"] for m in gui._load_models()]
        assert len(ids) == len(set(ids))


class TestConfig:
    @pytest.fixture
    def config_path(self, tmp_path, monkeypatch):
        path = tmp_path / "dossier" / "config.json"
        monkeypatch.setattr(gui, "_CONFIG_PATH", str(path))
        return path

    def test_defaults_when_no_file(self, config_path):
        assert gui._load_config() == {"lang": "fr", "last_model": "base", "last_folder": ""}

    def test_save_creates_the_folder_and_roundtrips(self, config_path):
        config = {"lang": "en", "last_model": "large-v3", "last_folder": "/données/été", "debug": True}
        gui._save_config(config)
        assert config_path.is_file()
        assert gui._load_config() == config

    def test_accents_are_not_escaped(self, config_path):
        gui._save_config({"last_folder": "été"})
        assert "été" in config_path.read_text(encoding="utf-8")

    def test_save_overwrites(self, config_path):
        gui._save_config({"lang": "fr"})
        gui._save_config({"lang": "en"})
        assert json.loads(config_path.read_text(encoding="utf-8")) == {"lang": "en"}

    @pytest.mark.xfail(strict=True, reason="D12 : une configuration corrompue fait planter le démarrage")
    def test_corrupted_file_falls_back_to_defaults(self, config_path):
        config_path.parent.mkdir(parents=True)
        config_path.write_text("{pas du json", encoding="utf-8")
        assert gui._load_config()["lang"] == "fr"


class TestSafeScrollableFrame:
    """Contournement du bug customtkinter 6.0.0 : ``event.widget`` peut être une chaîne."""

    @pytest.fixture
    def frame(self):
        instance = gui._SafeScrollableFrame.__new__(gui._SafeScrollableFrame)  # sans créer de widget Tk
        instance._parent_canvas = types.SimpleNamespace(id="canvas", master=None)
        return instance

    def test_string_widget_is_ignored(self, frame):
        assert frame._check_if_valid_scroll(".!ctkcombobox.!dropdownmenu") is False

    def test_empty_string_is_ignored(self, frame):
        assert frame._check_if_valid_scroll("") is False

    def test_own_canvas_is_valid(self, frame):
        assert frame._check_if_valid_scroll(frame._parent_canvas) is True

    def test_child_of_the_canvas_is_valid(self, frame):
        child = types.SimpleNamespace(id="enfant", master=frame._parent_canvas)
        assert frame._check_if_valid_scroll(child) is True

    def test_unrelated_widget_is_not_valid(self, frame):
        assert frame._check_if_valid_scroll(types.SimpleNamespace(id="autre", master=None)) is False
