"""
Journal de l'application : fichier tournant dans ~/.autotranscript/logs.

Le fichier est destiné au support : un utilisateur peut l'envoyer pour qu'on puisse voir
les erreurs. Les tokens HuggingFace et le dossier personnel y sont masqués.
"""
import logging
import logging.handlers
import os
import platform
import re
import subprocess
import sys
import threading
from importlib import metadata
from pathlib import Path

LOG_DIR = Path.home() / ".autotranscript" / "logs"
LOG_FILE = LOG_DIR / "autotranscript.log"

_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
_MAX_BYTES = 1_000_000
_BACKUP_COUNT = 3

_HF_TOKEN_RE = re.compile(r"hf_[A-Za-z0-9]+")
# Chemin d'un fichier audio/vidéo (les noms peuvent être sensibles : entretiens, etc.)
_MEDIA_PATH_RE = re.compile(
    r"""[^\s'"<>|]*\.(?:mp3|wav|m4a|ogg|flac|aac|wma|mp4|mkv|avi|mov|webm|wmv|flv)\b""",
    re.IGNORECASE,
)
_HOME = str(Path.home())

# Bibliothèques dont la version est utile pour diagnostiquer un problème
_TRACKED_PACKAGES = (
    "whisperx", "pyannote.audio", "torch", "huggingface_hub",
    "faster-whisper", "openai-whisper", "customtkinter",
)

# Bibliothèques trop bavardes en DEBUG, sans intérêt pour le support
_NOISY_LOGGERS = ("matplotlib", "PIL", "urllib3", "numba", "fsspec", "filelock")

_logger = logging.getLogger("autotranscript.log_setup")
_configured = False


def redact(text: str) -> str:
    """
    Masque les informations sensibles d'un message de log.

    Args:
        text: Texte à nettoyer.

    Returns:
        Le texte où les tokens HuggingFace deviennent ``hf_***``, les chemins de fichiers
        audio/vidéo ``<media>`` et où le dossier personnel est remplacé par ``~``. Le
        masquage des chemins est au mieux : un nom contenant des espaces peut en laisser
        une partie.
    """
    text = _HF_TOKEN_RE.sub("hf_***", text)
    text = _MEDIA_PATH_RE.sub("<media>", text)
    return text.replace(_HOME, "~")


class _RedactingFormatter(logging.Formatter):
    """Formatter qui masque les secrets, y compris dans les tracebacks."""

    def format(self, record: logging.LogRecord) -> str:
        return redact(super().format(record))


def _log_uncaught(exc_type, exc_value, exc_tb) -> None:
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_tb)
        return
    logging.getLogger("autotranscript").critical(
        "Exception non gérée", exc_info=(exc_type, exc_value, exc_tb)
    )


def _log_uncaught_thread(args: threading.ExceptHookArgs) -> None:
    logging.getLogger("autotranscript").critical(
        "Exception non gérée dans le thread %s",
        args.thread.name if args.thread else "?",
        exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
    )


def setup_logging(debug: bool = False) -> Path:
    """
    Configure le journal (fichier tournant + console) et capte les exceptions non gérées.

    Les messages de l'application (logger ``autotranscript``) sont toujours écrits en
    DEBUG dans le fichier ; les bibliothèques tierces le sont en INFO, ou en DEBUG si
    ``debug`` est activé. Sans accès en écriture au dossier de logs, seule la console
    est utilisée.

    Args:
        debug: Active le niveau DEBUG pour toutes les bibliothèques.

    Returns:
        Chemin du fichier de log.
    """
    global _configured
    if _configured:
        set_debug(debug)
        return LOG_FILE

    root = logging.getLogger()
    root.handlers.clear()
    formatter = _RedactingFormatter(_FORMAT)

    # Sous pythonw (Windows), stderr vaut None : pas de console
    if sys.stderr is not None:
        console = logging.StreamHandler(sys.stderr)
        console.setLevel(logging.WARNING)
        console.setFormatter(formatter)
        root.addHandler(console)

    file_error = None
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            LOG_FILE, maxBytes=_MAX_BYTES, backupCount=_BACKUP_COUNT, encoding="utf-8",
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)
    except OSError as exc:
        file_error = exc

    logging.getLogger("autotranscript").setLevel(logging.DEBUG)
    set_debug(debug)

    sys.excepthook = _log_uncaught
    threading.excepthook = _log_uncaught_thread
    logging.captureWarnings(True)
    _configured = True

    if file_error is not None:
        _logger.warning("Journal fichier indisponible (%s) : console uniquement", file_error)
    return LOG_FILE


def set_debug(enabled: bool) -> None:
    """
    Active ou désactive le niveau DEBUG pour les bibliothèques tierces.

    Args:
        enabled: True pour tout journaliser en DEBUG, False pour INFO.
    """
    logging.getLogger().setLevel(logging.DEBUG if enabled else logging.INFO)
    for name in _NOISY_LOGGERS:
        logging.getLogger(name).setLevel(logging.DEBUG if enabled else logging.WARNING)


def _package_version(name: str) -> str:
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return "absent"


def log_environment(app_version: str) -> None:
    """
    Écrit en tête du journal les informations d'environnement utiles au support.

    Ne charge aucune bibliothèque lourde (torch, whisperx) : seules les versions
    installées sont lues. Aucun secret n'est écrit.

    Args:
        app_version: Version affichée de l'application.
    """
    _logger.info("=== AutoTranscript v%s ===", app_version)
    _logger.info("Système : %s %s (%s)", platform.system(), platform.release(), platform.machine())
    _logger.info("Python : %s", sys.version.split()[0])
    _logger.info(
        "Paquets : %s",
        ", ".join(f"{name}={_package_version(name)}" for name in _TRACKED_PACKAGES),
    )
    try:
        import model_setup
        _logger.info("Modèle de diarisation présent : %s", model_setup.is_model_ready())
    except Exception:
        _logger.warning("Etat du modèle de diarisation illisible", exc_info=True)


def open_log_folder() -> bool:
    """
    Ouvre le dossier des logs dans le gestionnaire de fichiers.

    Returns:
        True si la commande d'ouverture a pu être lancée, False sinon.
    """
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        if sys.platform == "win32":
            os.startfile(LOG_DIR)  # noqa: S606
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(LOG_DIR)])
        else:
            subprocess.Popen(["xdg-open", str(LOG_DIR)])
        return True
    except OSError:
        _logger.warning("Impossible d'ouvrir le dossier des logs", exc_info=True)
        return False
