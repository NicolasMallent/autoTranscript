"""Tests unitaires de app/log_setup.py."""
import logging
import logging.handlers
import os
import sys
import threading
import types

import pytest

import log_setup

TOKEN = "hf_" + "aB3dE5gH7jK9mN1pQ3rS5tU7vW9xY1zA2"


@pytest.fixture
def clean_logging(monkeypatch, tmp_path):
    """Isole la configuration du logging (handlers, niveaux, hooks) et renvoie le fichier de log."""
    root = logging.getLogger()
    saved_handlers, saved_level = root.handlers[:], root.level
    saved_hooks = (sys.excepthook, threading.excepthook)
    whisperx_logger = logging.getLogger("whisperx")
    saved_whisperx = whisperx_logger.handlers[:]
    names = (*log_setup._NOISY_LOGGERS, "autotranscript", "somelib")
    saved_levels = {name: logging.getLogger(name).level for name in names}

    log_file = tmp_path / "logs" / "autotranscript.log"
    monkeypatch.setattr(log_setup, "LOG_DIR", log_file.parent)
    monkeypatch.setattr(log_setup, "LOG_FILE", log_file)
    monkeypatch.setattr(log_setup, "_configured", False)
    root.handlers.clear()

    yield log_file

    for handler in root.handlers:
        handler.close()
    root.handlers[:] = saved_handlers
    root.setLevel(saved_level)
    sys.excepthook, threading.excepthook = saved_hooks
    whisperx_logger.handlers[:] = saved_whisperx
    for name, level in saved_levels.items():
        logging.getLogger(name).setLevel(level)
    logging.captureWarnings(False)


def _text(log_file) -> str:
    return log_file.read_text(encoding="utf-8")


class TestRedact:
    def test_token_is_masked(self):
        assert log_setup.redact(f"token={TOKEN}") == "token=hf_***"

    def test_several_tokens(self):
        assert log_setup.redact(f"{TOKEN} et {TOKEN}") == "hf_*** et hf_***"

    def test_function_names_are_not_masked(self):
        text = "in hf_hub_download and _inner_hf_hub_download"
        assert log_setup.redact(text) == text

    def test_short_hf_prefix_is_kept(self):
        # Les vrais tokens ont plus de 30 caractères : un mot plus court n'est pas un token
        assert log_setup.redact("hf_ABCDEF123") == "hf_ABCDEF123"

    def test_home_directory_is_abbreviated(self):
        text = f"{log_setup._HOME}/Documents/notes.txt"
        assert log_setup.redact(text) == "~/Documents/notes.txt"

    @pytest.mark.parametrize("ext", ["mp3", "wav", "m4a", "ogg", "flac", "aac", "wma",
                                     "mp4", "mkv", "avi", "mov", "webm", "wmv", "flv"])
    def test_media_paths_are_masked(self, ext):
        assert log_setup.redact(f"lecture de /data/entretien.{ext} impossible") == "lecture de <media> impossible"

    def test_media_extension_is_case_insensitive(self):
        assert log_setup.redact("fichier /data/Interview.MKV") == "fichier <media>"

    def test_path_with_spaces_is_partially_masked(self):
        # Limite documentée : le masquage est « au mieux » pour les noms contenant des espaces
        result = log_setup.redact("/data/Mon Dossier/entretien final.mp4")
        assert "final" not in result or result.endswith("<media>")
        assert ".mp4" not in result

    @pytest.mark.parametrize("text", [
        "Fichier 1/1 (.mp4) : début", "Fichier 1/1 (type mp4) : début", "fichier .wav seul",
        "extensions : .mp3, .mkv et .flac",
    ])
    def test_an_extension_without_a_file_name_is_not_a_path(self, text):
        """Le log du transcripteur écrit l'extension seule : elle ne doit pas être prise pour un chemin."""
        assert log_setup.redact(text) == text

    def test_a_file_name_next_to_parentheses_is_still_masked(self):
        assert log_setup.redact("échec sur (entretien.mp4) puis [autre.wav]") == "échec sur (<media>) puis [<media>]"

    def test_other_extensions_are_kept(self):
        assert log_setup.redact("config.json et notes.txt") == "config.json et notes.txt"

    def test_empty_string(self):
        assert log_setup.redact("") == ""


class TestSetupLogging:
    def test_creates_log_file_and_returns_its_path(self, clean_logging):
        path = log_setup.setup_logging()
        logging.getLogger("autotranscript.test").info("bonjour")
        assert path == clean_logging
        assert "bonjour" in _text(clean_logging)

    def test_file_content_is_redacted(self, clean_logging):
        log_setup.setup_logging()
        logging.getLogger("autotranscript.test").info("token %s fichier /x/interview.mp3", TOKEN)
        content = _text(clean_logging)
        assert "hf_***" in content and "<media>" in content
        assert TOKEN not in content and "interview" not in content

    def test_traceback_is_redacted(self, clean_logging):
        log_setup.setup_logging()
        try:
            raise RuntimeError(f"échec avec {TOKEN}")
        except RuntimeError:
            logging.getLogger("autotranscript.test").exception("boom")
        content = _text(clean_logging)
        assert "RuntimeError" in content and TOKEN not in content

    def test_app_debug_messages_are_always_written(self, clean_logging):
        log_setup.setup_logging(debug=False)
        logging.getLogger("autotranscript.test").debug("détail appli")
        assert "détail appli" in _text(clean_logging)

    def test_third_party_debug_hidden_by_default(self, clean_logging):
        log_setup.setup_logging(debug=False)
        lib = logging.getLogger("somelib")
        lib.debug("bavard")
        lib.info("utile")
        content = _text(clean_logging)
        assert "utile" in content and "bavard" not in content

    def test_third_party_debug_visible_in_debug_mode(self, clean_logging):
        log_setup.setup_logging(debug=True)
        logging.getLogger("somelib").debug("bavard")
        assert "bavard" in _text(clean_logging)

    def test_second_call_does_not_duplicate_handlers(self, clean_logging):
        log_setup.setup_logging()
        count = len(logging.getLogger().handlers)
        log_setup.setup_logging()
        assert len(logging.getLogger().handlers) == count

    def test_second_call_updates_debug_level(self, clean_logging):
        log_setup.setup_logging(debug=False)
        log_setup.setup_logging(debug=True)
        assert logging.getLogger().level == logging.DEBUG

    def test_whisperx_logger_gets_a_null_handler(self, clean_logging):
        whisperx_logger = logging.getLogger("whisperx")
        whisperx_logger.handlers.clear()
        log_setup.setup_logging()
        assert any(isinstance(h, logging.NullHandler) for h in whisperx_logger.handlers)
        assert whisperx_logger.propagate

    def test_whisperx_messages_reach_the_file(self, clean_logging):
        log_setup.setup_logging()
        logging.getLogger("whisperx.asr").info("détection de voix")
        assert "détection de voix" in _text(clean_logging)

    def test_console_shows_warnings_only(self, clean_logging):
        log_setup.setup_logging()
        console = [h for h in logging.getLogger().handlers
                   if type(h) is logging.StreamHandler]
        assert len(console) == 1 and console[0].level == logging.WARNING

    def test_no_console_handler_when_stderr_is_none(self, clean_logging, monkeypatch):
        monkeypatch.setattr(sys, "stderr", None)  # pythonw sous Windows
        log_setup.setup_logging()
        assert not [h for h in logging.getLogger().handlers if type(h) is logging.StreamHandler]

    def test_unwritable_log_dir_falls_back_to_console(self, clean_logging, monkeypatch, tmp_path):
        blocker = tmp_path / "not-a-dir"
        blocker.write_text("fichier, pas dossier")
        monkeypatch.setattr(log_setup, "LOG_DIR", blocker / "logs")
        log_setup.setup_logging()  # ne doit pas lever
        assert not any(isinstance(h, logging.handlers.RotatingFileHandler)
                       for h in logging.getLogger().handlers)

    def test_log_file_rotates(self, clean_logging, monkeypatch):
        monkeypatch.setattr(log_setup, "_MAX_BYTES", 300)
        monkeypatch.setattr(log_setup, "_BACKUP_COUNT", 2)
        log_setup.setup_logging()
        logger = logging.getLogger("autotranscript.test")
        for i in range(60):
            logger.info("ligne numéro %d avec du remplissage", i)
        assert clean_logging.with_name("autotranscript.log.1").exists()
        assert not clean_logging.with_name("autotranscript.log.3").exists()

    def test_accents_are_written_in_utf8(self, clean_logging):
        log_setup.setup_logging()
        logging.getLogger("autotranscript.test").info("café — élève")
        assert "café — élève" in clean_logging.read_bytes().decode("utf-8")


class TestSetDebug:
    def test_enable_and_disable(self, clean_logging):
        log_setup.setup_logging()
        assert logging.getLogger().level == logging.INFO
        assert logging.getLogger("matplotlib").level == logging.WARNING
        log_setup.set_debug(True)
        assert logging.getLogger().level == logging.DEBUG
        assert logging.getLogger("matplotlib").level == logging.DEBUG
        log_setup.set_debug(False)
        assert logging.getLogger().level == logging.INFO
        assert logging.getLogger("matplotlib").level == logging.WARNING


class TestExceptionHooks:
    def test_uncaught_exception_is_logged(self, clean_logging):
        log_setup.setup_logging()
        try:
            raise ValueError("pas gérée")
        except ValueError:
            sys.excepthook(*sys.exc_info())
        content = _text(clean_logging)
        assert "Exception non gérée" in content and "ValueError: pas gérée" in content

    def test_keyboard_interrupt_is_delegated(self, clean_logging, monkeypatch):
        calls = []
        monkeypatch.setattr(sys, "__excepthook__", lambda *args: calls.append(args))
        log_setup.setup_logging()
        sys.excepthook(KeyboardInterrupt, KeyboardInterrupt(), None)
        assert len(calls) == 1
        assert "Exception non gérée" not in _text(clean_logging)

    def test_thread_exception_is_logged(self, clean_logging):
        log_setup.setup_logging()
        try:
            raise OSError("dans un thread")
        except OSError as exc:
            args = types.SimpleNamespace(
                exc_type=type(exc), exc_value=exc, exc_traceback=exc.__traceback__,
                thread=threading.current_thread(),
            )
        threading.excepthook(args)
        assert "dans un thread" in _text(clean_logging)

    def test_thread_exception_without_thread(self, clean_logging):
        log_setup.setup_logging()
        args = types.SimpleNamespace(exc_type=OSError, exc_value=OSError("x"),
                                     exc_traceback=None, thread=None)
        threading.excepthook(args)  # ne doit pas lever
        assert "Exception non gérée" in _text(clean_logging)


class TestLogEnvironment:
    def test_header_content(self, clean_logging, monkeypatch):
        import model_setup
        monkeypatch.setattr(model_setup, "is_model_ready", lambda: True)
        log_setup.setup_logging()
        log_setup.log_environment("9.9.9")
        content = _text(clean_logging)
        assert "=== AutoTranscript v9.9.9 ===" in content
        assert "Python : " in content and "Système : " in content
        assert "Paquets : " in content and "customtkinter=" in content
        assert "Modèle de diarisation présent : True" in content

    def test_unreadable_model_state_is_a_warning(self, clean_logging, monkeypatch):
        import model_setup

        def boom():
            raise OSError("disque illisible")
        monkeypatch.setattr(model_setup, "is_model_ready", boom)
        log_setup.setup_logging()
        log_setup.log_environment("1.0")
        assert "illisible" in _text(clean_logging)

    def test_package_version(self):
        assert log_setup._package_version("pytest") != "absent"
        assert log_setup._package_version("paquet-qui-n-existe-pas") == "absent"


class TestOpenLogFolder:
    @pytest.fixture
    def popen_calls(self, monkeypatch, tmp_path):
        monkeypatch.setattr(log_setup, "LOG_DIR", tmp_path / "logs")
        calls = []
        monkeypatch.setattr(log_setup.subprocess, "Popen", lambda cmd: calls.append(cmd))
        return calls

    def test_linux_uses_xdg_open(self, popen_calls, monkeypatch, tmp_path):
        monkeypatch.setattr(sys, "platform", "linux")
        assert log_setup.open_log_folder() is True
        assert popen_calls == [["xdg-open", str(tmp_path / "logs")]]
        assert (tmp_path / "logs").is_dir()

    def test_macos_uses_open(self, popen_calls, monkeypatch, tmp_path):
        monkeypatch.setattr(sys, "platform", "darwin")
        assert log_setup.open_log_folder() is True
        assert popen_calls == [["open", str(tmp_path / "logs")]]

    def test_windows_uses_startfile(self, monkeypatch, tmp_path):
        opened = []
        monkeypatch.setattr(log_setup, "LOG_DIR", tmp_path / "logs")
        monkeypatch.setattr(sys, "platform", "win32")
        monkeypatch.setattr(os, "startfile", opened.append, raising=False)
        assert log_setup.open_log_folder() is True
        assert opened == [tmp_path / "logs"]

    def test_failure_returns_false(self, monkeypatch, tmp_path):
        monkeypatch.setattr(log_setup, "LOG_DIR", tmp_path / "logs")
        monkeypatch.setattr(sys, "platform", "linux")

        def missing(cmd):
            raise FileNotFoundError("xdg-open")
        monkeypatch.setattr(log_setup.subprocess, "Popen", missing)
        assert log_setup.open_log_folder() is False
