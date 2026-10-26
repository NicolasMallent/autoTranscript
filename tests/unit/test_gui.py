"""
Tests unitaires de app/gui.py.

Aucune fenêtre n'est ouverte (pas d'écran requis) : les méthodes de App sont appelées
« à vide », avec un faux ``self`` qui ne fournit que les widgets et variables Tk lus par la méthode.
"""
import json
import logging
import os
import queue
import types

import pytest

pytest.importorskip("tkinter")
pytest.importorskip("customtkinter")

import gui  # noqa: E402


class Var:
    """Remplace une variable Tk (StringVar / BooleanVar)."""

    def __init__(self, value=None):
        self._value = value

    def get(self):
        return self._value

    def set(self, value):
        self._value = value


class Widget:
    """Remplace un widget : garde la trace des appels à ``configure``."""

    def __init__(self):
        self.options = {}

    def configure(self, **options):
        self.options.update(options)


def fake_app(**variables):
    """Faux ``self`` : chaque argument devient une variable Tk (``.get()``)."""
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


class TestSpeakersRange:
    @pytest.mark.parametrize("minimum, maximum, valid", [
        (None, None, True),
        (2, None, True),
        (None, 4, True),
        (2, 4, True),
        (3, 3, True),
        (5, 2, False),
        (2, 1, False),
    ])
    def test_range_validation(self, minimum, maximum, valid):
        assert gui.speakers_range_is_valid(minimum, maximum) is valid


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

    @pytest.mark.parametrize("ui", ["fr", "en"])
    def test_language_code_for_label(self, ui_lang, ui):
        ui_lang.load(ui)
        for key, code in gui.WHISPER_LANGUAGES.items():
            assert gui._language_code_for_label(ui_lang.t(key)) == code

    def test_language_code_for_unknown_label_is_auto(self, ui_lang):
        assert gui._language_code_for_label("Klingon") == "auto"


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
    DEFAULTS = {"lang": "fr", "last_model": "base", "last_folder": "", "last_language": "fr",
                "last_formats": ["txt", "srt"], "last_mode": "file"}

    @pytest.fixture
    def config_path(self, tmp_path, monkeypatch):
        path = tmp_path / "dossier" / "config.json"
        monkeypatch.setattr(gui, "_CONFIG_PATH", str(path))
        return path

    def _write(self, config_path, content, mode="w"):
        config_path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            config_path.write_bytes(content)
        else:
            config_path.write_text(content, encoding="utf-8")

    def test_defaults_when_no_file(self, config_path):
        assert gui._load_config() == self.DEFAULTS

    def test_defaults_are_not_shared_between_calls(self, config_path):
        gui._load_config()["last_formats"].append("json")
        assert gui._load_config()["last_formats"] == ["txt", "srt"]

    def test_save_creates_the_folder_and_roundtrips(self, config_path):
        config = {"lang": "en", "last_model": "large-v3", "last_folder": "/données/été", "debug": True}
        gui._save_config(config)
        assert config_path.is_file()
        assert gui._load_config() == {**self.DEFAULTS, **config}

    def test_missing_keys_are_filled_with_defaults(self, config_path):
        self._write(config_path, json.dumps({"lang": "en"}))
        loaded = gui._load_config()
        assert loaded["lang"] == "en" and loaded["last_model"] == "base"

    def test_unknown_keys_are_kept(self, config_path):
        self._write(config_path, json.dumps({"debug": True, "autre": 1}))
        assert gui._load_config()["debug"] is True and gui._load_config()["autre"] == 1

    def test_accents_are_not_escaped(self, config_path):
        gui._save_config({"last_folder": "été"})
        assert "été" in config_path.read_text(encoding="utf-8")

    def test_save_overwrites(self, config_path):
        gui._save_config({"lang": "fr"})
        gui._save_config({"lang": "en"})
        assert json.loads(config_path.read_text(encoding="utf-8")) == {"lang": "en"}

    def test_corrupted_file_falls_back_to_defaults(self, config_path):
        self._write(config_path, "{pas du json")
        assert gui._load_config() == self.DEFAULTS

    @pytest.mark.parametrize("content", ["[1, 2, 3]", '"du texte"', "42", "null", ""])
    def test_valid_json_that_is_not_an_object_falls_back_to_defaults(self, config_path, content):
        self._write(config_path, content)
        assert gui._load_config() == self.DEFAULTS

    def test_binary_garbage_falls_back_to_defaults(self, config_path):
        self._write(config_path, b"\xff\xfe\x00\x80 pas de l'utf-8")
        assert gui._load_config() == self.DEFAULTS

    def test_corrupted_file_is_kept_aside_for_diagnosis(self, config_path):
        self._write(config_path, "{pas du json")
        gui._load_config()
        assert config_path.with_name("config.json.corrupt").read_text(encoding="utf-8") == "{pas du json"
        assert not config_path.exists()

    def test_corruption_is_logged(self, config_path, caplog):
        self._write(config_path, "{pas du json")
        with caplog.at_level(logging.WARNING, logger="autotranscript.gui"):
            gui._load_config()
        assert "Configuration illisible" in caplog.text

    def test_a_directory_instead_of_a_file_does_not_crash(self, config_path):
        config_path.mkdir(parents=True)
        assert gui._load_config() == self.DEFAULTS

    def test_save_leaves_no_temporary_file(self, config_path):
        gui._save_config({"lang": "en"})
        assert sorted(p.name for p in config_path.parent.iterdir()) == ["config.json"]

    def test_failed_save_keeps_the_previous_config(self, config_path, monkeypatch):
        gui._save_config({"lang": "fr"})

        def refuse(src, dst):
            raise OSError("disque plein")
        monkeypatch.setattr(os, "replace", refuse)
        gui._save_config({"lang": "en"})  # ne doit pas lever
        monkeypatch.undo()
        assert json.loads(config_path.read_text(encoding="utf-8")) == {"lang": "fr"}
        assert sorted(p.name for p in config_path.parent.iterdir()) == ["config.json"]

    def test_unwritable_location_does_not_crash_and_is_logged(self, tmp_path, monkeypatch, caplog):
        blocker = tmp_path / "fichier"
        blocker.write_text("pas un dossier")
        monkeypatch.setattr(gui, "_CONFIG_PATH", str(blocker / "config.json"))
        with caplog.at_level(logging.WARNING, logger="autotranscript.gui"):
            gui._save_config({"lang": "en"})
        assert "enregistrer la configuration" in caplog.text


class TestFormState:
    """Valeurs initiales de l'onglet Transcription, relues de la config."""

    def test_defaults(self):
        state = gui._form_state({}, whisperx_available=True)
        assert state == {"mode": "file", "language": "fr", "formats": ["txt", "srt"],
                         "diarize": True}

    def test_diarization_is_off_without_whisperx(self):
        assert gui._form_state({}, whisperx_available=False)["diarize"] is False
        assert gui._form_state({"last_diarize": True}, whisperx_available=False)["diarize"] is False

    def test_saved_values_are_restored(self):
        cfg = {"last_mode": "folder", "last_language": "auto", "last_formats": ["json"],
               "last_diarize": False}
        assert gui._form_state(cfg, whisperx_available=True) == {
            "mode": "folder", "language": "auto", "formats": ["json"], "diarize": False}

    @pytest.mark.parametrize("cfg, key, expected", [
        ({"last_mode": "n'importe quoi"}, "mode", "file"),
        ({"last_mode": 3}, "mode", "file"),
        ({"last_language": "klingon"}, "language", "fr"),
        ({"last_language": None}, "language", "fr"),
        ({"last_formats": "txt"}, "formats", ["txt", "srt"]),
        ({"last_formats": ["pdf", "srt"]}, "formats", ["srt"]),
        ({"last_formats": ["pdf"]}, "formats", ["txt", "srt"]),
        ({"last_formats": []}, "formats", ["txt", "srt"]),
        ({"last_diarize": "oui"}, "diarize", True),
    ])
    def test_invalid_values_fall_back_to_defaults(self, cfg, key, expected):
        assert gui._form_state(cfg, whisperx_available=True)[key] == expected


class TestSnapshotForm:
    def _app(self, ui_lang, **overrides):
        values = dict(
            _model_var="large-v3  (2.9 GB) — Meilleure qualité", _mode_var="folder",
            _whisper_lang_var=ui_lang.t("whisper_lang_auto"), _fmt_txt=False, _fmt_srt=True,
            _fmt_json=True, _diarize_var=False,
        )
        values.update(overrides)
        app = fake_app(**values)
        app._config = {}
        for name in ("_selected_model_id", "_selected_formats"):
            setattr(app, name, getattr(gui.App, name).__get__(app))
        return app

    def test_current_form_is_stored_in_the_config(self, ui_lang):
        app = self._app(ui_lang)
        gui.App._snapshot_form(app)
        assert app._config == {"last_model": "large-v3", "last_language": "auto",
                               "last_formats": ["srt", "json"], "last_diarize": False,
                               "last_mode": "folder"}

    def test_snapshot_survives_a_language_switch(self, ui_lang):
        """Le libellé de la langue change avec l'interface : c'est le code qui est mémorisé."""
        app = self._app(ui_lang)
        gui.App._snapshot_form(app)
        ui_lang.load("en")
        assert gui._form_state(app._config, True)["language"] == "auto"

    def test_snapshot_roundtrips_through_form_state(self, ui_lang):
        app = self._app(ui_lang, _whisper_lang_var=ui_lang.t("whisper_lang_english"), _diarize_var=True)
        gui.App._snapshot_form(app)
        state = gui._form_state(app._config, whisperx_available=True)
        assert state == {"mode": "folder", "language": "en", "formats": ["srt", "json"], "diarize": True}


class TestDiarizeToggle:
    @pytest.mark.parametrize("checked, state", [(True, "normal"), (False, "disabled")])
    def test_only_the_speaker_entries_are_configured(self, checked, state):
        app = types.SimpleNamespace(_diarize_var=Var(checked),
                                    _speaker_entries=[Widget(), Widget()])
        gui.App._on_diarize_toggle(app)
        assert [entry.options for entry in app._speaker_entries] == [{"state": state}] * 2

    def test_a_widget_error_is_not_swallowed(self):
        class Broken:
            def configure(self, **options):
                raise RuntimeError("widget cassé")
        app = types.SimpleNamespace(_diarize_var=Var(True), _speaker_entries=[Broken()])
        with pytest.raises(RuntimeError):
            gui.App._on_diarize_toggle(app)


class TestOnCancel:
    def test_cancel_is_requested_and_shown(self, ui_lang):
        calls = []
        app = types.SimpleNamespace(
            _transcriber=types.SimpleNamespace(cancel=lambda: calls.append("cancel")),
            _cancel_btn=Widget(), _log_append=calls.append,
        )
        gui.App._on_cancel(app)
        assert calls == ["cancel", ui_lang.t("log_cancel_requested")]
        assert app._cancel_btn.options == {"state": "disabled"}


class TestOnLangChange:
    @pytest.fixture
    def env(self, ui_lang, monkeypatch, tmp_path):
        monkeypatch.setattr(gui, "_CONFIG_PATH", str(tmp_path / "config.json"))
        events = []
        app = types.SimpleNamespace(_ui_lang_var=Var(ui_lang.t("settings_language_en")), _config={})

        def snapshot():
            events.append("snapshot")
            app._config["last_model"] = "small"
        app._snapshot_form = snapshot
        app._rebuild_ui = lambda: events.append("rebuild")
        return types.SimpleNamespace(app=app, events=events, ui=ui_lang, config_file=tmp_path / "config.json")

    def test_form_is_remembered_before_the_interface_is_rebuilt(self, env):
        gui.App._on_lang_change(env.app)
        assert env.events == ["snapshot", "rebuild"]

    def test_language_and_form_are_saved(self, env):
        gui.App._on_lang_change(env.app)
        assert json.loads(env.config_file.read_text(encoding="utf-8")) == {"last_model": "small", "lang": "en"}
        assert env.ui.current_lang() == "en"

    def test_french_can_be_selected_again(self, env):
        gui.App._on_lang_change(env.app)                      # -> en
        env.app._ui_lang_var.set(env.ui.t("settings_language_fr"))
        gui.App._on_lang_change(env.app)                      # -> fr
        assert env.ui.current_lang() == "fr" and env.app._config["lang"] == "fr"


class TestOnTranscribe:
    """``_on_transcribe`` en entier, avec un faux transcripteur et un thread synchrone."""

    @pytest.fixture
    def env(self, monkeypatch, ui_lang, tmp_path):
        monkeypatch.setattr(gui, "_CONFIG_PATH", str(tmp_path / "config.json"))
        warnings, started = [], []
        monkeypatch.setattr(gui.messagebox, "showwarning", lambda title, text: warnings.append(text))

        class SyncThread:
            def __init__(self, target, daemon=None):
                self._target = target

            def start(self):
                started.append(True)
                self._target()
        monkeypatch.setattr(gui.threading, "Thread", SyncThread)

        calls = []
        transcriber = types.SimpleNamespace(transcribe=lambda *args: calls.append(args))
        queue_items = []
        app = fake_app(
            _selected_path="/data/a.mp3", _model_var="base  (139 MB) — x", _mode_var="file",
            _whisper_lang_var=ui_lang.t("whisper_lang_french"), _fmt_txt=True, _fmt_srt=False,
            _fmt_json=False, _diarize_var=True, _min_speakers_var="", _max_speakers_var="",
        )
        app._config = {}
        app._transcriber = transcriber
        app._queue = types.SimpleNamespace(put=queue_items.append)
        app._transcribe_btn, app._cancel_btn = Widget(), Widget()
        app._progress = types.SimpleNamespace(set=lambda value: None)
        app._running = False
        for name in ("_selected_model_id", "_selected_whisper_lang", "_selected_formats",
                     "_selected_speakers", "_snapshot_form"):
            setattr(app, name, getattr(gui.App, name).__get__(app))
        return types.SimpleNamespace(app=app, warnings=warnings, started=started,
                                     calls=calls, queue=queue_items, ui=ui_lang)

    def test_valid_input_starts_the_transcription(self, env):
        gui.App._on_transcribe(env.app)
        assert env.calls == [("/data/a.mp3", "base", "fr", ["txt"], True, None, None, env.calls[0][-1])]
        assert env.queue[-1] == ("_done_", 1.0) and env.warnings == []
        assert env.app._transcribe_btn.options == {"state": "disabled"}
        assert env.app._cancel_btn.options == {"state": "normal"}

    def test_range_error_is_reported_and_nothing_starts(self, env):
        env.app._min_speakers_var.set("5")
        env.app._max_speakers_var.set("2")
        gui.App._on_transcribe(env.app)
        assert env.warnings == [env.ui.t("error_speakers_range")]
        assert env.calls == [] and env.started == []
        assert env.app._transcribe_btn.options == {}   # les boutons n'ont pas été touchés

    def test_range_is_ignored_when_diarization_is_off(self, env):
        env.app._diarize_var.set(False)
        env.app._min_speakers_var.set("5")
        env.app._max_speakers_var.set("2")
        gui.App._on_transcribe(env.app)
        assert env.warnings == [] and len(env.calls) == 1

    def test_speakers_are_forwarded(self, env):
        env.app._min_speakers_var.set("2")
        env.app._max_speakers_var.set("4")
        gui.App._on_transcribe(env.app)
        assert env.calls[0][5:7] == (2, 4)

    def test_no_input_is_reported(self, env):
        env.app._selected_path.set("")
        gui.App._on_transcribe(env.app)
        assert env.warnings == [env.ui.t("error_no_input")] and env.calls == []

    def test_no_format_is_reported(self, env):
        env.app._fmt_txt.set(False)
        gui.App._on_transcribe(env.app)
        assert env.warnings == [env.ui.t("error_no_format")] and env.calls == []

    def test_form_is_remembered_for_the_next_launch(self, env, tmp_path):
        gui.App._on_transcribe(env.app)
        saved = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
        assert saved["last_model"] == "base" and saved["last_formats"] == ["txt"]
        assert saved["last_language"] == "fr" and saved["last_mode"] == "file"

    def test_a_failure_is_queued_and_the_buttons_are_released(self, env):
        def explode(*args):
            raise RuntimeError("panne")
        env.app._transcriber.transcribe = explode
        gui.App._on_transcribe(env.app)
        assert env.queue[0] == ("error:panne", 0.0) and env.queue[-1] == ("_done_", 1.0)


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


class TestTranslateMessage:
    """Traduction des codes envoyés par le thread de transcription en lignes de journal."""

    @pytest.mark.parametrize("message, key, params", [
        ("loading_model:large-v3", "log_loading_model", {"model": "large-v3"}),
        ("processing_file:a.mp3", "log_processing_file", {"file": "a.mp3"}),
        ("extracting_audio:film.mp4", "log_extracting_audio", {"file": "film.mp4"}),
        ("aligning:a.mp3", "log_aligning", {"file": "a.mp3"}),
        ("diarizing:a.mp3", "log_diarizing", {"file": "a.mp3"}),
        ("done_file:a.mp3", "log_done_file", {"file": "a.mp3"}),
        ("align_unavailable:xx", "log_align_unavailable", {"lang": "xx"}),
        ("error:panne", "log_error", {"error": "panne"}),
        ("loading_align_model:fr", "log_loading_align_model", {"lang": "fr"}),
    ])
    def test_events_with_an_argument(self, message, key, params):
        assert gui._translate_message(message) == gui._LogLine(key, params)

    @pytest.mark.parametrize("message, key", [
        ("all_done", "log_all_done"),
        ("cancelled", "log_cancelled"),
        ("no_audio_found", "log_no_audio_found"),
        ("diarization_model_connecting", "log_diarization_model_connecting"),
        ("diarization_model_extracting", "log_diarization_model_extracting"),
        ("diarization_model_ready", "log_diarization_model_ready"),
        ("diarization_model_cached", "log_diarization_model_ready"),
        ("diarization_failed", "log_diarization_failed"),
    ])
    def test_events_without_an_argument(self, message, key):
        assert gui._translate_message(message) == gui._LogLine(key, {})

    def test_counts(self):
        assert gui._translate_message("done_with_errors:2/5") == gui._LogLine(
            "log_done_with_errors", {"failed": "2", "total": "5"})

    def test_download_progress_replaces_the_last_line(self):
        assert gui._translate_message("diarization_model_dl:12/34") == gui._LogLine(
            "log_diarization_model_dl", {"done": "12", "total": "34"}, replace_last=True)

    def test_argument_may_contain_colons_and_spaces(self):
        line = gui._translate_message("error:a:b.mp4 — ffmpeg failed (exit code 1): boom")
        assert line.params == {"error": "a:b.mp4 — ffmpeg failed (exit code 1): boom"}

    def test_empty_argument(self):
        assert gui._translate_message("processing_file:").params == {"file": ""}

    @pytest.mark.parametrize("message", ["", "_done_", "inconnu", "inconnu:arg", ":", "done_with_errors:3",
                                         "diarization_model_dl:sans-barre"])
    def test_unknown_or_malformed_messages_are_ignored(self, message):
        assert gui._translate_message(message) is None

    def test_a_no_argument_event_with_an_argument_is_ignored(self):
        assert gui._translate_message("all_done:x") is None


class FakeLog:
    """Faux CTkTextbox : garde la suite des opérations."""

    def __init__(self):
        self.operations = []

    def configure(self, **options):
        self.operations.append(("configure", options))

    def delete(self, start, end):
        self.operations.append(("delete", start, end))

    def insert(self, index, text):
        self.operations.append(("insert", index, text))

    def see(self, index):
        self.operations.append(("see", index))


class TestPollQueue:
    @pytest.fixture
    def env(self, ui_lang):
        lines, bar, scheduled = [], [], []
        app = types.SimpleNamespace(
            _queue=queue.Queue(), _log=FakeLog(), _running=True,
            _transcribe_btn=Widget(), _cancel_btn=Widget(),
            _progress=types.SimpleNamespace(set=bar.append),
            _log_append=lines.append, after=lambda delay, callback: scheduled.append(delay),
        )
        for name in ("_poll_queue", "_handle_message", "_show_log_line", "_log_replace_last"):
            setattr(app, name, getattr(gui.App, name).__get__(app))
        return types.SimpleNamespace(app=app, lines=lines, bar=bar, scheduled=scheduled, ui=ui_lang)

    def poll(self, env, *messages):
        for message in messages:
            env.app._queue.put(message)
        gui.App._poll_queue(env.app)

    def test_message_becomes_a_journal_line_and_moves_the_bar(self, env):
        self.poll(env, ("processing_file:a.mp3", 0.25))
        assert env.lines == ["Traitement : a.mp3"] and env.bar == [0.25]

    def test_every_pending_message_is_handled_in_order(self, env):
        self.poll(env, ("processing_file:a.mp3", 0.0), ("done_file:a.mp3", 0.5), ("all_done", 1.0))
        assert env.lines == ["Traitement : a.mp3", "Terminé : a.mp3", env.ui.t("log_all_done")]
        assert env.bar == [0.0, 0.5, 1.0]

    def test_the_poll_is_rescheduled_even_when_the_queue_is_empty(self, env):
        self.poll(env)
        assert env.scheduled == [100] and env.lines == [] and env.bar == []

    def test_done_releases_the_buttons_without_touching_the_bar(self, env):
        """Après une erreur ou une annulation, la barre ne doit pas se remplir à 100 %."""
        self.poll(env, ("cancelled", 0.25), ("_done_", 1.0))
        assert env.app._running is False
        assert env.app._transcribe_btn.options == {"state": "normal"}
        assert env.app._cancel_btn.options == {"state": "disabled"}
        assert env.bar == [0.25] and env.lines == [env.ui.t("log_cancelled")]

    def test_unknown_message_is_ignored_but_the_bar_still_follows(self, env):
        self.poll(env, ("inconnu:x", 0.5))
        assert env.lines == [] and env.bar == [0.5]

    def test_download_progress_updates_the_last_line_in_place(self, env):
        self.poll(env, ("diarization_model_dl:12/34", 0.3))
        assert env.lines == []   # pas de nouvelle ligne
        text = env.ui.t("log_diarization_model_dl", done="12", total="34") + "\n"
        assert env.app._log.operations == [
            ("configure", {"state": "normal"}), ("delete", "end-2l", "end-1c"),
            ("insert", "end", text), ("see", "end"), ("configure", {"state": "disabled"})]

    def test_counts_are_formatted(self, env):
        self.poll(env, ("done_with_errors:1/3", 1.0))
        assert env.lines == [env.ui.t("log_done_with_errors", failed="1", total="3")]

    def test_a_failing_handler_does_not_stop_the_polling(self, env, caplog):
        def broken(message):
            raise RuntimeError("zone de texte détruite")
        env.app._log_append = broken
        with caplog.at_level(logging.ERROR, logger="autotranscript.gui"):
            self.poll(env, ("all_done", 1.0), ("_done_", 1.0))
        assert env.app._running is False          # le message suivant a bien été traité
        assert env.scheduled == [100]              # et la boucle continue
        assert "zone de texte détruite" in caplog.text

    def test_language_follows_the_interface(self, env, ui_lang):
        ui_lang.load("en")
        self.poll(env, ("processing_file:a.mp3", 0.0))
        assert env.lines == ["Processing: a.mp3"]


class TestFileTypes:
    def test_labels_are_translated(self, ui_lang):
        assert [label for label, _ in gui._file_dialog_filetypes()] == ["Audio / Vidéo", "Tous les fichiers"]
        ui_lang.load("en")
        assert [label for label, _ in gui._file_dialog_filetypes()] == ["Audio / Video", "All files"]

    def test_every_supported_extension_is_offered(self, ui_lang):
        patterns = gui._file_dialog_filetypes()[0][1].split()
        for extension in gui.AUDIO_EXTENSIONS | gui.VIDEO_EXTENSIONS:
            assert f"*{extension}" in patterns

    def test_last_choice_shows_everything(self, ui_lang):
        assert gui._file_dialog_filetypes()[-1][1] == "*.*"
