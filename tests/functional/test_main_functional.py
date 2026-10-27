"""Tests fonctionnels de app/main.py : point d'entrée lancé comme le fait l'utilisateur."""
import os
import subprocess
import sys

import pytest


def run_main(args, home, project_root, **env_overrides):
    env = {**os.environ, "HOME": str(home), "USERPROFILE": str(home)}
    env.pop("HF_HUB_DISABLE_XET", None)
    env.update(env_overrides)
    return subprocess.run([sys.executable, str(project_root / "app" / "main.py"), *args],
                          env=env, capture_output=True, text=True, timeout=120)


def import_main_and_print_env(home, project_root, **env_overrides):
    env = {**os.environ, "HOME": str(home), "USERPROFILE": str(home),
           "PYTHONPATH": str(project_root / "app")}
    for name in ("HF_HUB_DISABLE_XET", "HF_HUB_DISABLE_TELEMETRY", "PYANNOTE_METRICS_ENABLED"):
        env.pop(name, None)
    env.update(env_overrides)
    code = ("import os, main; "
            "print(os.environ['HF_HUB_DISABLE_XET'], os.environ['HF_HUB_DISABLE_TELEMETRY'], "
            "os.environ['PYANNOTE_METRICS_ENABLED'])")
    # cwd=home : sinon ``import main`` trouverait le main.py de la racine du dépôt (ancien script CLI)
    return subprocess.run([sys.executable, "-c", code], env=env, capture_output=True,
                          text=True, timeout=120, cwd=home)


@pytest.fixture
def home(tmp_path):
    path = tmp_path / "home"
    path.mkdir()
    return path


def test_check_passes_on_a_complete_installation(home, project_root):
    pytest.importorskip("tkinter")
    pytest.importorskip("customtkinter")
    result = run_main(["--check"], home, project_root)
    assert result.returncode == 0 and result.stdout.strip() == "OK"


def test_check_does_not_open_a_window_nor_write_a_log(home, project_root):
    pytest.importorskip("tkinter")
    pytest.importorskip("customtkinter")
    run_main(["--check"], home, project_root)
    # Le démarrage prépare le dossier privé des données NLTK (voir nltk_setup), mais n'écrit aucun log
    assert not (home / ".autotranscript" / "logs").exists()


def test_check_passes_in_isolated_mode_like_the_embedded_windows_python(home, project_root):
    """
    Le Python embarqué de Windows tourne en mode isolé (fichier ._pth) : le dossier du script n'est
    pas dans ``sys.path``. C'est le ``sys.path.insert`` de app/main.py qui permet les imports à plat
    (``import log_setup``) : il ne doit pas être retiré sans tester une installation Windows.
    """
    pytest.importorskip("tkinter")
    pytest.importorskip("customtkinter")
    env = {**os.environ, "HOME": str(home), "USERPROFILE": str(home)}
    result = subprocess.run([sys.executable, "-I", str(project_root / "app" / "main.py"), "--check"],
                            env=env, capture_output=True, text=True, timeout=120)
    assert result.returncode == 0 and result.stdout.strip() == "OK", result.stderr


def test_telemetry_is_disabled_and_xet_is_off_by_default(home, project_root):
    result = import_main_and_print_env(home, project_root)
    assert result.returncode == 0, result.stderr
    assert result.stdout.split() == ["1", "1", "false"]


def test_telemetry_cannot_be_re_enabled_from_the_environment(home, project_root):
    result = import_main_and_print_env(
        home, project_root, HF_HUB_DISABLE_TELEMETRY="0", PYANNOTE_METRICS_ENABLED="true")
    assert result.stdout.split()[1:] == ["1", "false"]


def test_xet_can_be_re_enabled_from_the_environment(home, project_root):
    result = import_main_and_print_env(home, project_root, HF_HUB_DISABLE_XET="0")
    assert result.stdout.split()[0] == "0"


def import_main_and_print(home, project_root, expression, **env_overrides):
    env = {**os.environ, "HOME": str(home), "USERPROFILE": str(home),
           "PYTHONPATH": str(project_root / "app")}
    env.pop("NLTK_DATA", None)
    env.update(env_overrides)
    return subprocess.run([sys.executable, "-c", f"import os, main; print({expression})"], env=env,
                          capture_output=True, text=True, timeout=120, cwd=home)


def test_private_nltk_data_folder_comes_first_in_the_search_path(home, project_root):
    result = import_main_and_print(home, project_root, "os.environ['NLTK_DATA']", NLTK_DATA="/opt/autre")
    assert result.returncode == 0, result.stderr
    ours = str(home / ".autotranscript" / "nltk_data")
    assert result.stdout.strip().split(os.pathsep) == [ours, "/opt/autre"]


@pytest.mark.skipif(sys.platform == "win32", reason="droits POSIX")
def test_nltk_data_folder_is_created_private_at_startup(home, project_root):
    result = import_main_and_print(home, project_root, "oct(os.stat(os.environ['NLTK_DATA'].split(os.pathsep)[0]).st_mode & 0o777)")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "0o700"
