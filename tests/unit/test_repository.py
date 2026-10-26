"""
Contrôles sur le contenu du dépôt git : pas de script hérité qui prête à confusion, pas de gros
binaire suivi (ils alourdissent définitivement l'historique de tous les clones).
"""
import shutil
import subprocess

import pytest

MAX_TRACKED_BYTES = 25 * 1024 * 1024

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git indisponible")


def git(project_root, *args):
    return subprocess.run(["git", *args], cwd=project_root, capture_output=True, text=True)


@pytest.fixture
def tracked(project_root):
    result = git(project_root, "ls-files", "-z")
    if result.returncode != 0:
        pytest.skip("pas un dépôt git (archive téléchargée ?)")
    return [name for name in result.stdout.split("\0") if name]


def test_the_legacy_root_script_is_gone(project_root, tracked):
    """Le main.py racine (ancien script en ligne de commande) prêtait à confusion avec app/main.py."""
    assert "main.py" not in tracked
    assert not (project_root / "main.py").exists()


def test_the_real_entry_point_is_tracked(tracked):
    assert "app/main.py" in tracked


def test_no_large_file_is_tracked(project_root, tracked):
    offenders = {}
    for name in tracked:
        path = project_root / name
        if path.is_file() and path.stat().st_size > MAX_TRACKED_BYTES:
            offenders[name] = f"{path.stat().st_size / 1024 / 1024:.0f} Mo"
    assert offenders == {}, "gros fichiers suivis par git : les télécharger dans le CI plutôt que les versionner"


@pytest.mark.parametrize("path", [
    "ffmpeg/windows/ffmpeg-master-latest-win64-gpl-shared.zip",
    "ffmpeg/windows/ffmpeg.exe",
    "ffmpeg/linux/ffmpeg",
])
def test_ffmpeg_binaries_are_ignored(project_root, path):
    assert git(project_root, "check-ignore", "-q", path).returncode == 0


@pytest.mark.parametrize("path", ["ffmpeg/windows/.gitkeep", "ffmpeg/linux/.gitkeep"])
def test_ffmpeg_folders_are_kept(project_root, path):
    assert git(project_root, "check-ignore", "-q", path).returncode == 1
