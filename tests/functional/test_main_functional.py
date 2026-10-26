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
    assert not (home / ".autotranscript").exists()


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
