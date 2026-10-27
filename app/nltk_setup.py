"""
Données NLTK `punkt_tab` (découpage en phrases) utilisées par l'alignement des mots de whisperx.

NLTK >= 3.10 refuse tout dossier de données qu'un autre compte pourrait modifier : propriétaire ni
l'utilisateur ni root, ou droit d'écriture pour le groupe ou les autres, sur la racine, sur les dossiers
jusqu'à la ressource et sur chaque fichier. Sous Ubuntu (umask 002), un ~/nltk_data créé par NLTK est en
775 et donc refusé : whisperx échoue alors à l'alignement, après la partie longue du travail.

L'application gère donc son propre dossier privé (~/.autotranscript/nltk_data), placé en tête du chemin
de recherche de NLTK, et vérifie ces données avant de commencer.
"""
import logging
import os
import socket
import stat
from pathlib import Path
from typing import Callable, Optional

from paths import APP_DATA_DIR

ProgressCallback = Optional[Callable[[str, float], None]]

_logger = logging.getLogger("autotranscript.nltk_setup")

NLTK_DATA_DIR = APP_DATA_DIR / "nltk_data"

_PACKAGE = "punkt_tab"
# whisperx retombe sur l'anglais pour les langues sans modèle : c'est cette ressource qui doit exister
_RESOURCE = "tokenizers/punkt_tab/english/"

# Sans délai, un pare-feu qui ignore les paquets ferait attendre le téléchargement indéfiniment
_DOWNLOAD_TIMEOUT_SECONDS = 30


def _report(cb: ProgressCallback, msg: str, pct: float) -> None:
    if cb:
        cb(msg, pct)


def _make_private(root: Path) -> None:
    """
    Rend ``root`` privé : 0700 pour le dossier, et plus aucun droit d'écriture pour le groupe ou les autres
    sur tout ce qu'il contient. Les droits ne sont jamais augmentés. Sans effet hors POSIX.

    Args:
        root: Dossier de données NLTK (ignoré s'il n'existe pas).
    """
    if os.name != "posix" or not Path(root).exists():
        return
    try:
        os.chmod(root, 0o700)
        for current, dirs, files in os.walk(root):
            for name in (*dirs, *files):
                path = os.path.join(current, name)
                if os.path.islink(path):
                    continue
                mode = stat.S_IMODE(os.lstat(path).st_mode)
                os.chmod(path, mode & ~(stat.S_IWGRP | stat.S_IWOTH))
    except OSError:
        _logger.warning("Impossible de restreindre les droits de %s", root, exc_info=True)


def setup_env() -> None:
    """
    Prépare le dossier privé de données NLTK et le place en tête de la variable ``NLTK_DATA``.

    À appeler au démarrage, avant tout import de ``nltk`` (qui lit cette variable une seule fois). Une
    erreur d'E/S (dossier personnel en lecture seule) est journalisée et n'empêche pas de démarrer.
    """
    try:
        NLTK_DATA_DIR.mkdir(parents=True, exist_ok=True)
        _make_private(NLTK_DATA_DIR)
    except OSError:
        _logger.warning("Impossible de préparer le dossier de données NLTK %s", NLTK_DATA_DIR, exc_info=True)
    ours = str(NLTK_DATA_DIR)
    others = [entry for entry in os.environ.get("NLTK_DATA", "").split(os.pathsep) if entry and entry != ours]
    os.environ["NLTK_DATA"] = os.pathsep.join([ours, *others])


def _add_to_search_path(nltk) -> None:
    """Complète ``nltk.data.path`` : si nltk est déjà importé, il a lu NLTK_DATA avant ``setup_env``."""
    ours = str(NLTK_DATA_DIR)
    if ours not in nltk.data.path:
        nltk.data.path.insert(0, ours)


def is_punkt_ready() -> bool:
    """
    Indique si NLTK peut lire les données de découpage en phrases.

    Utilise le même appel, donc les mêmes contrôles de droits, que le tokenizer de phrases de NLTK.

    Returns:
        True si les données sont présentes et acceptées par NLTK ; False sinon (aussi si nltk est absent).
    """
    try:
        import nltk
        _add_to_search_path(nltk)
        nltk.data.find(_RESOURCE)
        return True
    except (ImportError, LookupError, OSError):
        return False


def ensure_punkt(progress_callback: ProgressCallback = None) -> bool:
    """
    S'assure que les données de découpage en phrases sont lisibles, en les téléchargeant si besoin.

    Le téléchargement se fait dans le dossier privé de l'application, sous un umask restrictif et avec un
    délai de connexion ; ce qui a été écrit est ensuite rendu privé. Cette fonction ne lève jamais : une
    panne réseau ou de droits est journalisée et signalée par la valeur de retour, pour que l'appelant
    puisse se passer de l'alignement plutôt que d'échouer après plusieurs minutes de calcul.

    Args:
        progress_callback: Reçoit ``sentence_data_download`` quand un téléchargement commence.

    Returns:
        True si les données sont utilisables, False sinon.
    """
    if is_punkt_ready():
        return True
    try:
        import nltk
    except ImportError:
        _logger.warning("nltk n'est pas installé : données de découpage en phrases indisponibles")
        return False

    _report(progress_callback, "sentence_data_download", 0.0)
    _logger.info("Téléchargement des données NLTK %s dans %s", _PACKAGE, NLTK_DATA_DIR)
    previous_umask = os.umask(0o077)
    previous_timeout = socket.getdefaulttimeout()
    socket.setdefaulttimeout(_DOWNLOAD_TIMEOUT_SECONDS)
    try:
        NLTK_DATA_DIR.mkdir(parents=True, exist_ok=True)
        nltk.download(_PACKAGE, download_dir=str(NLTK_DATA_DIR), quiet=True, raise_on_error=True)
    except Exception:
        _logger.warning("Téléchargement des données NLTK impossible", exc_info=True)
        return False
    finally:
        socket.setdefaulttimeout(previous_timeout)
        os.umask(previous_umask)
        _make_private(NLTK_DATA_DIR)

    if is_punkt_ready():
        _logger.info("Données NLTK installées")
        return True
    _logger.warning(
        "Données NLTK téléchargées mais toujours refusées ou introuvables (droits du dossier %s ?)",
        NLTK_DATA_DIR,
    )
    return False
