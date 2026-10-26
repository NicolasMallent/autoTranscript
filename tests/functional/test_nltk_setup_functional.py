"""
Tests fonctionnels avec le **vrai NLTK**, dans des sous-processus : reproduction de l'incident (NLTK refuse
un dossier de données en 775, comme celui créé sous un umask 002) et preuve que le dossier privé géré par
l'application règle le problème.

Ignorés si NLTK n'est pas installé, ou si sa version n'applique pas ce contrôle de droits.
"""
import importlib.util
import os
import subprocess
import sys

import pytest

from helpers import posix_only

pytestmark = [
    posix_only,
    pytest.mark.skipif(importlib.util.find_spec("nltk") is None, reason="nltk non installé"),
]

FIND = 'import nltk; nltk.data.find("tokenizers/punkt_tab/english/"); print("TROUVE")'


def run(code, home, project_root, **env):
    full_env = {**os.environ, "HOME": str(home), "USERPROFILE": str(home),
                "PYTHONPATH": str(project_root / "app")}
    full_env.pop("NLTK_DATA", None)
    full_env.update(env)
    return subprocess.run([sys.executable, "-c", code], env=full_env, capture_output=True,
                          text=True, timeout=120, cwd=home)


def build_tree(root, mode_dir, mode_file):
    """Arborescence minimale `tokenizers/punkt_tab/english/` avec les droits demandés."""
    leaf = root / "tokenizers" / "punkt_tab" / "english"
    leaf.mkdir(parents=True)
    (leaf / "collocations.tab").write_text("x")
    for current, dirs, files in os.walk(root):
        os.chmod(current, mode_dir)
        for name in files:
            os.chmod(os.path.join(current, name), mode_file)


@pytest.fixture
def home(tmp_path):
    path = tmp_path / "home"
    path.mkdir()
    return path


@pytest.fixture
def nltk_enforces_private_dirs(home, project_root):
    """Ignore le test si cette version de NLTK accepte un dossier de données en 775."""
    build_tree(home / "probe", 0o775, 0o664)
    result = run(FIND, home, project_root, NLTK_DATA=str(home / "probe"))
    if "TROUVE" in result.stdout:
        pytest.skip("cette version de NLTK ne refuse pas les dossiers modifiables par le groupe")


def test_nltk_refuses_a_group_writable_data_folder(home, project_root, nltk_enforces_private_dirs):
    """Reproduction de l'incident : mêmes données, refusées parce que le dossier est en 775."""
    build_tree(home / "nltk_data", 0o775, 0o664)
    result = run(FIND, home, project_root)
    assert "TROUVE" not in result.stdout
    assert "LookupError" in result.stderr


def test_the_same_data_are_accepted_when_private(home, project_root, nltk_enforces_private_dirs):
    build_tree(home / "nltk_data", 0o700, 0o600)
    assert "TROUVE" in run(FIND, home, project_root).stdout


def test_setup_env_makes_loose_application_data_readable(home, project_root, nltk_enforces_private_dirs):
    data = home / ".autotranscript" / "nltk_data"
    build_tree(data, 0o775, 0o664)
    without = run("import nltk_setup, nltk; print(nltk_setup.is_punkt_ready())", home, project_root)
    assert without.stdout.strip() == "False"                       # témoin : sans setup_env, refusé
    fixed = run("import nltk_setup; nltk_setup.setup_env(); import nltk; print(nltk_setup.is_punkt_ready())",
                home, project_root)
    assert fixed.stdout.strip() == "True", fixed.stderr


def test_a_loose_home_nltk_data_does_not_hide_ours(home, project_root, nltk_enforces_private_dirs):
    """Le ~/nltk_data de l'incident reste refusé, mais le dossier de l'application passe devant."""
    build_tree(home / "nltk_data", 0o775, 0o664)                    # le dossier refusé de l'utilisateur
    build_tree(home / ".autotranscript" / "nltk_data", 0o775, 0o664)
    result = run("import nltk_setup; nltk_setup.setup_env(); import nltk; print(nltk_setup.is_punkt_ready())",
                 home, project_root)
    assert result.stdout.strip() == "True", result.stderr


def test_ensure_punkt_repairs_a_download_made_under_umask_002(home, project_root, nltk_enforces_private_dirs):
    """NLTK « réussit » son téléchargement mais écrit en 775/664 : ensure_punkt rend les données lisibles."""
    code = '''
import os, nltk, nltk_setup

def download_like_nltk_under_umask_002(name, download_dir=None, quiet=False, raise_on_error=False):
    leaf = os.path.join(download_dir, "tokenizers", "punkt_tab", "english")
    os.makedirs(leaf, exist_ok=True)
    open(os.path.join(leaf, "collocations.tab"), "w").close()
    for current, dirs, files in os.walk(download_dir):
        os.chmod(current, 0o775)
        for name in files:
            os.chmod(os.path.join(current, name), 0o664)
    return True

nltk.download = download_like_nltk_under_umask_002
nltk_setup.setup_env()
print(nltk_setup.ensure_punkt())
'''
    result = run(code, home, project_root)
    assert result.stdout.strip().endswith("True"), result.stderr


def test_ensure_punkt_does_not_download_when_the_data_are_there(home, project_root, nltk_enforces_private_dirs):
    build_tree(home / ".autotranscript" / "nltk_data", 0o700, 0o600)
    code = '''
import nltk, nltk_setup
def forbidden(*args, **kwargs):
    raise AssertionError("téléchargement inutile")
nltk.download = forbidden
nltk_setup.setup_env()
print(nltk_setup.ensure_punkt())
'''
    result = run(code, home, project_root)
    assert result.stdout.strip().endswith("True"), result.stderr
