"""
Contrôles statiques du packaging : `requirements.txt` est la source unique des versions, et
aucun installateur ni workflow ne doit installer ces paquets sans version.

Un `pip install whisperx` sans version dans le postinst du .deb donnait aux utilisateurs Linux
une autre version que celle testée ; ces tests empêchent le retour de ce genre d'écart.
"""
import re

import pytest

PINNED_LINE = re.compile(r"^[A-Za-z0-9_.\-]+==[0-9][A-Za-z0-9_.\-+]*$")
REQUIRED_PACKAGES = {"whisperx", "pyannote.audio", "huggingface_hub", "customtkinter"}


@pytest.fixture
def requirements(project_root):
    lines = (project_root / "requirements.txt").read_text(encoding="utf-8").splitlines()
    return [line.strip() for line in lines if line.strip() and not line.strip().startswith("#")]


@pytest.fixture
def packaging_files(project_root):
    """Fichiers qui installent des paquets Python : installateurs et workflows."""
    patterns = ("installer/**/*.sh", "installer/**/*.ps1", "installer/**/*.iss",
                ".github/workflows/*.yml")
    files = [path for pattern in patterns for path in project_root.glob(pattern)]
    assert files, "aucun fichier de packaging trouvé : le test ne vérifie plus rien"
    return files


def package_names(requirements):
    return {line.split("==")[0] for line in requirements}


class TestRequirementsFile:
    def test_every_line_is_pinned_to_an_exact_version(self, requirements):
        unpinned = [line for line in requirements if not PINNED_LINE.match(line)]
        assert unpinned == []

    def test_expected_packages_are_listed(self, requirements):
        assert package_names(requirements) >= REQUIRED_PACKAGES

    def test_no_duplicate_package(self, requirements):
        names = [line.split("==")[0].lower() for line in requirements]
        assert len(names) == len(set(names))


class TestNoUnpinnedInstall:
    def test_pinned_packages_are_never_installed_without_a_version(self, requirements, packaging_files, project_root):
        """Toute ligne `pip install` qui cite un paquet de requirements.txt doit le lire dans ce fichier."""
        offenders = []
        for path in packaging_files:
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if "pip install" not in line and "pip.exe install" not in line:
                    continue
                if "requirements" in line:      # `-r requirements.txt` ou version lue dans ce fichier
                    continue
                for name in package_names(requirements):
                    if re.search(rf"(?<![\w.\-]){re.escape(name)}(?![\w.\-=])", line):
                        offenders.append(f"{path.relative_to(project_root)}:{number}: {line.strip()}")
        assert offenders == []


class TestDebPackage:
    @pytest.fixture
    def script(self, project_root):
        return (project_root / "installer" / "linux" / "build-deb.sh").read_text(encoding="utf-8")

    @pytest.fixture
    def postinst(self, script):
        start = script.index("DEBIAN/postinst")
        return script[start:script.index("POSTINST\nchmod", start)]

    def test_postinst_installs_from_requirements(self, postinst):
        assert re.search(r'pip install -r "\$REQUIREMENTS"', postinst)
        assert 'REQUIREMENTS=$INSTALL_DIR/requirements.txt' in postinst

    def test_requirements_file_is_shipped_in_the_package(self, script):
        assert 'cp    "$APP_DIR/requirements.txt"' in script

    def test_fallback_uses_the_pinned_customtkinter(self, postinst):
        assert "openai-whisper" in postinst
        assert "grep -i '^customtkinter'" in postinst

    def test_pip_output_is_kept_instead_of_discarded(self, postinst):
        assert "install.log" in postinst
        assert not [line for line in postinst.splitlines()
                    if "pip install" in line and "2>/dev/null" in line]

    def test_install_log_is_removed_with_the_package(self, script):
        prerm = script[script.index("DEBIAN/prerm"):script.index("PRERM\nchmod")]
        assert "install.log" in prerm
