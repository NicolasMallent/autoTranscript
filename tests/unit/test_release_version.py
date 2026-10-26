"""
Contrôles statiques de la version : `_VERSION` (affichée par la fenêtre « À propos » et écrite dans
le log) doit rester alignée sur les installateurs, et `release.yml` doit refuser un tag qui ne
correspond pas à cette valeur avant de construire quoi que ce soit.
"""
import re

import pytest

yaml = pytest.importorskip("yaml")

SEMVER = re.compile(r"^\d+\.\d+\.\d+$")
BUILD_JOBS = ["build-windows", "build-linux", "package-pyannote"]


def code_version(project_root) -> str:
    text = (project_root / "app" / "gui.py").read_text(encoding="utf-8")
    match = re.search(r'^_VERSION = "([^"]+)"$', text, re.MULTILINE)
    assert match, "_VERSION introuvable dans app/gui.py"
    return match.group(1)


@pytest.fixture
def release(project_root):
    return yaml.safe_load((project_root / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8"))


def needs(job: dict) -> list:
    value = job.get("needs", [])
    return [value] if isinstance(value, str) else list(value)


class TestVersionConstant:
    def test_is_a_semantic_version(self, project_root):
        assert SEMVER.match(code_version(project_root))

    def test_inno_setup_default_matches(self, project_root):
        text = (project_root / "installer" / "windows" / "setup.iss").read_text(encoding="utf-8")
        version = code_version(project_root)
        assert f'#define MyAppVersion "{version}"' in text
        assert f'/DMyAppVersion="{version}"' in text

    def test_deb_default_matches(self, project_root):
        text = (project_root / "installer" / "linux" / "build-deb.sh").read_text(encoding="utf-8")
        version = code_version(project_root)
        assert f'VERSION="${{VERSION:-{version}}}"' in text
        assert f"VERSION={version} ./build-deb.sh" in text


class TestReleaseWorkflow:
    def test_has_a_version_check_job(self, release):
        assert "check-version" in release["jobs"]

    @pytest.mark.parametrize("job", BUILD_JOBS)
    def test_build_jobs_wait_for_the_version_check(self, release, job):
        assert "check-version" in needs(release["jobs"][job])

    def test_the_release_is_still_created_after_every_build(self, release):
        assert set(BUILD_JOBS) <= set(needs(release["jobs"]["create-release"]))

    def test_the_check_job_checks_out_the_repository(self, release):
        steps = release["jobs"]["check-version"]["steps"]
        assert any(step.get("uses", "").startswith("actions/checkout@") for step in steps)

    def test_the_check_compares_the_tag_with_the_code_version(self, release):
        script = "\n".join(step.get("run", "") for step in release["jobs"]["check-version"]["steps"])
        assert "GITHUB_REF_NAME" in script and "_VERSION" in script and "app/gui.py" in script
        assert "exit 1" in script

    def test_the_workflow_still_runs_on_version_tags_only(self, release):
        # PyYAML lit la clé « on » comme le booléen True
        triggers = release.get("on", release.get(True))
        assert triggers["push"]["tags"] == ["v*.*.*"]
