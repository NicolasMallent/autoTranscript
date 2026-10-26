"""
Test fonctionnel du garde-fou de release : le script réel de l'étape `check-version`, extrait de
release.yml, est exécuté avec bash dans une copie minimale du dépôt, comme le fait GitHub Actions
(`bash -e`), pour plusieurs tags.
"""
import re
import subprocess
import sys

import pytest

yaml = pytest.importorskip("yaml")

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="le script du workflow est écrit pour bash")


def check_script(project_root) -> str:
    workflow = yaml.safe_load((project_root / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8"))
    steps = workflow["jobs"]["check-version"]["steps"]
    return next(step["run"] for step in steps if "_VERSION" in step.get("run", ""))


@pytest.fixture
def repo(tmp_path, project_root):
    """Copie minimale du dépôt : seul app/gui.py est lu par le script."""
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "gui.py").write_text(
        (project_root / "app" / "gui.py").read_text(encoding="utf-8"), encoding="utf-8")
    return tmp_path


def code_version(repo) -> str:
    return re.search(r'^_VERSION = "([^"]+)"$', (repo / "app" / "gui.py").read_text(encoding="utf-8"),
                     re.MULTILINE).group(1)


def run_check(project_root, repo, tag):
    env = {"PATH": "/usr/bin:/bin"}
    if tag is not None:
        env["GITHUB_REF_NAME"] = tag
    return subprocess.run(["bash", "-e", "-c", check_script(project_root)], cwd=repo, env=env,
                          capture_output=True, text=True, timeout=30)


def test_matching_tag_is_accepted(project_root, repo):
    result = run_check(project_root, repo, f"v{code_version(repo)}")
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("tag", ["v2.9.9", "v0.0.1", "v2.0.1", "v99.0.0"])
def test_other_tags_are_refused_with_both_versions_in_the_message(project_root, repo, tag):
    result = run_check(project_root, repo, tag)
    assert result.returncode == 1
    assert tag in result.stderr and code_version(repo) in result.stderr


def test_tag_without_the_v_prefix_is_compared_as_is(project_root, repo):
    assert run_check(project_root, repo, code_version(repo)).returncode == 0


def test_missing_tag_variable_is_refused(project_root, repo):
    assert run_check(project_root, repo, None).returncode == 1


def test_a_gui_file_without_version_is_refused(project_root, repo):
    (repo / "app" / "gui.py").write_text("# plus de version ici\n", encoding="utf-8")
    result = run_check(project_root, repo, "v2.1.0")
    assert result.returncode == 1


def test_a_commented_out_version_is_not_picked_up(project_root, repo):
    (repo / "app" / "gui.py").write_text('# _VERSION = "2.1.0"\n', encoding="utf-8")
    assert run_check(project_root, repo, "v2.1.0").returncode == 1


def test_other_lines_mentioning_the_version_do_not_cause_a_false_refusal(project_root, repo):
    """Un commentaire ou une autre variable contenant « _VERSION » ne doit pas faire refuser un tag valide."""
    (repo / "app" / "gui.py").write_text(
        '# Ancienne valeur : _VERSION = "1.0.0"\n'
        'APP_VERSION = "7.7.7"\n'
        '_VERSION = "2.1.0"\n'
        'print("_VERSION = 3.0.0")\n',
        encoding="utf-8")
    result = run_check(project_root, repo, "v2.1.0")
    assert result.returncode == 0, result.stderr
