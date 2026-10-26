"""
Tests fonctionnels de app/log_setup.py : comportement observé dans un vrai processus Python,
avec un dossier personnel jetable (exceptions non gérées, threads, whisperx, dossier illisible).
"""
import importlib.util
import os
import subprocess
import sys

import pytest

TOKEN = "hf_" + "aB3dE5gH7jK9mN1pQ3rS5tU7vW9xY1zA2"


@pytest.fixture
def home(tmp_path):
    path = tmp_path / "home"
    path.mkdir()
    return path


def run_python(code: str, home, project_root, **env_overrides):
    env = {**os.environ, "HOME": str(home), "USERPROFILE": str(home),
           "PYTHONPATH": str(project_root / "app")}
    env.update(env_overrides)
    return subprocess.run([sys.executable, "-c", code], env=env, capture_output=True,
                          text=True, timeout=120)


def log_text(home) -> str:
    return (home / ".autotranscript" / "logs" / "autotranscript.log").read_text(encoding="utf-8")


def test_uncaught_exception_is_logged_and_redacted(home, project_root):
    result = run_python(f"""
import logging, log_setup
log_setup.setup_logging()
logging.getLogger("autotranscript.demo").info("token {TOKEN} sur /x/entretien.mp3")
raise RuntimeError("fin brutale {TOKEN}")
""", home, project_root)
    assert result.returncode == 1
    content = log_text(home)
    assert "hf_***" in content and "<media>" in content
    assert "Exception non gérée" in content and "RuntimeError: fin brutale hf_***" in content
    assert TOKEN not in content and "entretien" not in content
    assert TOKEN not in result.stderr and "Exception non gérée" in result.stderr   # console : WARNING et +


def test_exception_in_a_thread_is_logged(home, project_root):
    result = run_python("""
import threading, log_setup
log_setup.setup_logging()
def work():
    raise ValueError("échec dans le thread de transcription")
thread = threading.Thread(target=work, name="transcription")
thread.start(); thread.join()
""", home, project_root)
    assert result.returncode == 0
    content = log_text(home)
    assert "thread transcription" in content and "échec dans le thread de transcription" in content


@pytest.mark.skipif(importlib.util.find_spec("whisperx") is None, reason="whisperx non installé")
def test_whisperx_logs_reach_the_file_and_not_stdout(home, project_root):
    """Régression : whisperx installait son propre handler console et coupait la propagation."""
    result = run_python("""
import log_setup
log_setup.setup_logging()
from whisperx.log_utils import get_logger
get_logger("whisperx.asr").info("détection de voix en cours")
""", home, project_root)
    assert result.returncode == 0
    assert "détection de voix en cours" in log_text(home)
    assert result.stdout == ""


def test_application_still_starts_when_the_log_folder_is_unwritable(tmp_path, project_root):
    not_a_folder = tmp_path / "fichier"
    not_a_folder.write_text("je ne suis pas un dossier")
    result = run_python("""
import logging, log_setup
log_setup.setup_logging()
logging.getLogger("autotranscript.demo").warning("toujours là")
print("démarré")
""", not_a_folder, project_root)
    assert result.returncode == 0 and "démarré" in result.stdout
    assert "Journal fichier indisponible" in result.stderr and "toujours là" in result.stderr


def test_log_file_is_shared_between_runs(home, project_root):
    for run_number in (1, 2):
        run_python(f"""
import logging, log_setup
log_setup.setup_logging()
logging.getLogger("autotranscript.demo").info("exécution numéro {run_number}")
""", home, project_root)
    content = log_text(home)
    assert "exécution numéro 1" in content and "exécution numéro 2" in content


def test_environment_header_has_no_secret(home, project_root):
    result = run_python(f"""
import os, log_setup
os.environ["HF_TOKEN"] = "{TOKEN}"
log_setup.setup_logging()
log_setup.log_environment("1.2.3")
""", home, project_root)
    assert result.returncode == 0
    content = log_text(home)
    assert "=== AutoTranscript v1.2.3 ===" in content and "Paquets : " in content
    assert TOKEN not in content
