"""
Tests unitaires de app/nltk_setup.py (données NLTK `punkt_tab`, avec un faux module nltk).

Contexte : NLTK >= 3.10 refuse tout dossier de données modifiable par un autre compte. Sous Ubuntu
(umask 002), un ~/nltk_data créé par NLTK est en 775 et donc refusé : l'application gère son propre
dossier privé et vérifie les données avant les longues étapes.
"""
import logging
import os
import socket
import stat
import sys

import pytest

import nltk_setup
from helpers import FakeNltk, posix_only

GROUP_OR_WORLD_WRITE = stat.S_IWGRP | stat.S_IWOTH


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    path = tmp_path / ".autotranscript" / "nltk_data"
    monkeypatch.setattr(nltk_setup, "NLTK_DATA_DIR", path)
    monkeypatch.delenv("NLTK_DATA", raising=False)
    return path


def loose_entries(root):
    """Entrées de l'arborescence modifiables par le groupe ou les autres."""
    found = []
    for current, dirs, files in os.walk(root):
        for name in [".", *dirs, *files]:
            path = os.path.join(current, name)
            if os.lstat(path).st_mode & GROUP_OR_WORLD_WRITE:
                found.append(path)
    return found


class TestSetupEnv:
    def test_creates_the_folder_and_its_parents(self, data_dir):
        nltk_setup.setup_env()
        assert data_dir.is_dir()

    @posix_only
    def test_folder_is_private(self, data_dir):
        nltk_setup.setup_env()
        assert stat.S_IMODE(data_dir.stat().st_mode) == 0o700

    @posix_only
    def test_an_existing_group_writable_tree_is_tightened(self, data_dir):
        """Ce que NLTK produit sous umask 002 : dossiers en 775 et fichiers en 664."""
        leaf = data_dir / "tokenizers" / "punkt_tab" / "english"
        leaf.mkdir(parents=True)
        (leaf / "collocations.tab").write_text("x")
        for current, dirs, files in os.walk(data_dir):
            os.chmod(current, 0o775)
            for name in files:
                os.chmod(os.path.join(current, name), 0o664)
        assert loose_entries(data_dir)
        nltk_setup.setup_env()
        assert loose_entries(data_dir) == []

    @posix_only
    def test_permissions_are_only_ever_reduced(self, data_dir):
        data_dir.mkdir(parents=True)
        script = data_dir / "lisible.txt"
        script.write_text("x")
        os.chmod(script, 0o644)
        nltk_setup.setup_env()
        assert script.stat().st_mode & stat.S_IRUSR     # le propriétaire garde la lecture

    def test_sets_the_search_path_when_unset(self, data_dir):
        nltk_setup.setup_env()
        assert os.environ["NLTK_DATA"] == str(data_dir)

    def test_goes_first_and_keeps_existing_entries(self, data_dir, monkeypatch):
        monkeypatch.setenv("NLTK_DATA", os.pathsep.join(["/opt/a", "/opt/b"]))
        nltk_setup.setup_env()
        assert os.environ["NLTK_DATA"].split(os.pathsep) == [str(data_dir), "/opt/a", "/opt/b"]

    def test_is_idempotent(self, data_dir):
        nltk_setup.setup_env()
        nltk_setup.setup_env()
        assert os.environ["NLTK_DATA"].split(os.pathsep) == [str(data_dir)]

    def test_an_existing_entry_for_the_same_folder_is_moved_to_the_front(self, data_dir, monkeypatch):
        monkeypatch.setenv("NLTK_DATA", os.pathsep.join(["/opt/a", str(data_dir)]))
        nltk_setup.setup_env()
        assert os.environ["NLTK_DATA"].split(os.pathsep) == [str(data_dir), "/opt/a"]

    def test_an_unwritable_home_does_not_prevent_startup(self, data_dir, monkeypatch, caplog):
        def refuse(self, *args, **kwargs):
            raise PermissionError("lecture seule")
        monkeypatch.setattr(type(data_dir), "mkdir", refuse)
        with caplog.at_level(logging.WARNING, logger="autotranscript.nltk_setup"):
            nltk_setup.setup_env()      # ne doit pas lever
        assert "nltk_data" in caplog.text


class TestIsPunktReady:
    def test_ready(self, monkeypatch, data_dir):
        nltk = FakeNltk(monkeypatch, ready=True)
        assert nltk_setup.is_punkt_ready() is True
        # whisperx retombe sur l'anglais pour les langues sans modèle : c'est lui qu'on vérifie
        assert nltk.find_calls == ["tokenizers/punkt_tab/english/"]

    def test_missing(self, monkeypatch, data_dir):
        FakeNltk(monkeypatch, ready=False)
        assert nltk_setup.is_punkt_ready() is False

    def test_nltk_not_installed(self, monkeypatch, data_dir):
        monkeypatch.setitem(sys.modules, "nltk", None)     # « import nltk » lève ImportError
        assert nltk_setup.is_punkt_ready() is False

    def test_os_error_while_reading(self, monkeypatch, data_dir):
        nltk = FakeNltk(monkeypatch, ready=True)

        def broken(resource):
            raise PermissionError("refusé")
        nltk.module.data.find = broken
        assert nltk_setup.is_punkt_ready() is False

    def test_the_data_folder_is_added_to_the_search_path(self, monkeypatch, data_dir):
        """nltk lit NLTK_DATA une seule fois à l'import : s'il est déjà importé, on complète sa liste."""
        nltk = FakeNltk(monkeypatch, ready=True)
        nltk.module.data.path.extend(["/usr/share/nltk_data"])
        nltk_setup.is_punkt_ready()
        nltk_setup.is_punkt_ready()
        assert nltk.module.data.path == [str(data_dir), "/usr/share/nltk_data"]


class TestEnsurePunkt:
    def test_nothing_to_do_when_ready(self, monkeypatch, data_dir):
        nltk = FakeNltk(monkeypatch, ready=True)
        messages = []
        assert nltk_setup.ensure_punkt(lambda m, p: messages.append(m)) is True
        assert nltk.download_calls == [] and messages == []

    def test_downloads_into_the_private_folder(self, monkeypatch, data_dir):
        nltk = FakeNltk(monkeypatch, ready=False)
        assert nltk_setup.ensure_punkt() is True
        (call,) = nltk.download_calls
        assert call["name"] == "punkt_tab" and call["download_dir"] == str(data_dir)
        assert call["quiet"] is True and call["raise_on_error"] is True

    def test_reports_the_download_once(self, monkeypatch, data_dir):
        FakeNltk(monkeypatch, ready=False)
        messages = []
        nltk_setup.ensure_punkt(lambda m, p: messages.append(m))
        assert messages == ["sentence_data_download"]

    @posix_only
    def test_downloads_under_a_restrictive_umask_and_a_timeout(self, monkeypatch, data_dir):
        nltk = FakeNltk(monkeypatch, ready=False)
        nltk_setup.ensure_punkt()
        (call,) = nltk.download_calls
        assert call["umask"] == 0o077 and call["timeout"] == 30

    @posix_only
    def test_umask_and_timeout_are_restored(self, monkeypatch, data_dir):
        FakeNltk(monkeypatch, ready=False)
        previous = os.umask(0o022)
        socket.setdefaulttimeout(7)
        try:
            nltk_setup.ensure_punkt()
            current = os.umask(previous)
            assert current == 0o022 and socket.getdefaulttimeout() == 7
        finally:
            os.umask(previous)
            socket.setdefaulttimeout(None)

    @posix_only
    def test_umask_and_timeout_are_restored_after_a_failure(self, monkeypatch, data_dir):
        FakeNltk(monkeypatch, ready=False, download_fails=OSError("coupure"))
        previous = os.umask(0o022)
        socket.setdefaulttimeout(None)
        try:
            nltk_setup.ensure_punkt()
            assert os.umask(previous) == 0o022 and socket.getdefaulttimeout() is None
        finally:
            os.umask(previous)

    @posix_only
    def test_what_the_download_wrote_is_made_private(self, monkeypatch, data_dir):
        nltk = FakeNltk(monkeypatch, ready=False)

        def write_like_nltk_under_umask_002():
            leaf = data_dir / "tokenizers" / "punkt_tab" / "english"
            leaf.mkdir(parents=True, exist_ok=True)
            (leaf / "collocations.tab").write_text("x")
            for current, dirs, files in os.walk(data_dir):
                os.chmod(current, 0o775)
                for name in files:
                    os.chmod(os.path.join(current, name), 0o664)
        nltk.on_download = write_like_nltk_under_umask_002
        assert nltk_setup.ensure_punkt() is True
        assert loose_entries(data_dir) == []

    @pytest.mark.parametrize("error", [OSError("pas de réseau"), TimeoutError("trop long"),
                                       RuntimeError("inattendu"), ValueError("index corrompu")])
    def test_a_failed_download_returns_false_and_never_raises(self, monkeypatch, data_dir, caplog, error):
        FakeNltk(monkeypatch, ready=False, download_fails=error)
        with caplog.at_level(logging.WARNING, logger="autotranscript.nltk_setup"):
            assert nltk_setup.ensure_punkt() is False
        assert str(error) in caplog.text       # la cause est dans le log, traceback comprise

    def test_data_that_stay_refused_after_the_download_are_reported(self, monkeypatch, data_dir, caplog):
        """NLTK répond « réussi » mais refuse le dossier : c'est exactement l'incident d'origine."""
        FakeNltk(monkeypatch, ready=False, download_without_data=True)
        with caplog.at_level(logging.WARNING, logger="autotranscript.nltk_setup"):
            assert nltk_setup.ensure_punkt() is False
        assert "toujours" in caplog.text

    def test_works_without_a_callback(self, monkeypatch, data_dir):
        FakeNltk(monkeypatch, ready=False)
        assert nltk_setup.ensure_punkt() is True

    def test_nltk_not_installed(self, monkeypatch, data_dir):
        monkeypatch.setitem(sys.modules, "nltk", None)
        assert nltk_setup.ensure_punkt() is False

    def test_the_data_folder_is_on_the_search_path_after_a_download(self, monkeypatch, data_dir):
        nltk = FakeNltk(monkeypatch, ready=False)
        nltk_setup.ensure_punkt()
        assert str(data_dir) in nltk.module.data.path
