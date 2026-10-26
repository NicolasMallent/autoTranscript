"""Outils partagés par les tests : faux serveur de Release, faux whisperx, faux ffmpeg."""
import hashlib
import io
import os
import socket
import sys
import types
import urllib.request
import zipfile
from pathlib import Path

import pytest

posix_only = pytest.mark.skipif(sys.platform == "win32", reason="faux ffmpeg écrit en shell")

TOP_DIR = "speaker-diarization-community-1"


# ── modèle de diarisation ────────────────────────────────────────────────────

def make_model_zip(files=None, top_dir=TOP_DIR, extra=None) -> bytes:
    """
    Fabrique le zip d'un faux modèle de diarisation.

    Args:
        files: Fichiers à inclure (par défaut tous ceux que model_setup exige).
        top_dir: Dossier racine dans l'archive ; None pour une archive « à plat ».
        extra: Entrées supplémentaires {nom dans l'archive: octets}.
    """
    import model_setup

    names = model_setup._REQUIRED_FILES if files is None else files
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        for name in names:
            archive.writestr(f"{top_dir}/{name}" if top_dir else name, b"x" * 64)
        for arcname, data in (extra or {}).items():
            archive.writestr(arcname, data)
    return buf.getvalue()


def populate_model_dir(model_setup) -> Path:
    """Crée dans MODEL_DIR tous les fichiers exigés : le modèle est alors « prêt »."""
    for name in model_setup._REQUIRED_FILES:
        path = model_setup.MODEL_DIR / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x")
    return model_setup.MODEL_DIR


def sha256_of(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class FakeResponse(io.BytesIO):
    """Réponse HTTP minimale : context manager, ``read`` et ``headers``."""

    def __init__(self, data: bytes, with_length: bool = True):
        super().__init__(data)
        self.headers = {"Content-Length": str(len(data))} if with_length else {}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


class ReleaseServer:
    """Faux serveur de Release GitHub : sert le zip et son .sha256, et garde la trace des appels."""

    def __init__(self, monkeypatch, zip_bytes, sha=None, *, with_length=True,
                 sha_error=None, zip_error=None):
        self.urls = []
        self._zip = zip_bytes
        self._sha = sha if sha is not None else sha256_of(zip_bytes)
        self._with_length = with_length
        self._sha_error = sha_error
        self._zip_error = zip_error
        monkeypatch.setattr(urllib.request, "urlopen", self._urlopen)

    def _urlopen(self, url, timeout=None):
        self.urls.append(url)
        if url.endswith(".sha256"):
            if self._sha_error:
                raise self._sha_error
            body = self._sha if isinstance(self._sha, bytes) else f"{self._sha}  pyannote-community-1.zip\n".encode()
            return FakeResponse(body)
        if self._zip_error:
            raise self._zip_error
        return FakeResponse(self._zip, self._with_length)


def no_network(monkeypatch):
    """Fait échouer tout accès réseau (pour prouver qu'un chemin n'en fait pas)."""
    def _fail(*args, **kwargs):
        raise AssertionError("accès réseau inattendu")
    monkeypatch.setattr(urllib.request, "urlopen", _fail)


# ── faux ffmpeg ──────────────────────────────────────────────────────────────

def make_fake_ffmpeg(tmp_path: Path, *, fail_if_contains=None, fail_always=False) -> str:
    """
    Écrit un faux ffmpeg (script shell) et renvoie son chemin.

    Il écrit quelques octets dans le fichier de sortie (dernier argument). Il échoue, avec
    le chemin d'entrée dans son message d'erreur, si ``fail_always`` ou si ce chemin contient
    ``fail_if_contains``.
    """
    script = tmp_path / "fake-ffmpeg"
    if fail_always:
        condition = "true"
    elif fail_if_contains:
        condition = f'case "$3" in *{fail_if_contains}*) true ;; *) false ;; esac'
    else:
        condition = "false"
    script.write_text(
        "#!/bin/sh\n"
        f"if {condition}; then\n"
        '  echo "first line" >&2\n'
        '  echo "Error opening input $3: Invalid data found" >&2\n'
        "  exit 1\n"
        "fi\n"
        'for a; do last="$a"; done\n'
        'printf "RIFF" > "$last"\n'
    )
    script.chmod(0o755)
    return str(script)


# ── faux nltk ────────────────────────────────────────────────────────────────

class FakeNltk:
    """
    Faux module ``nltk`` installé dans ``sys.modules``.

    ``data.find`` échoue (``LookupError``) tant que les données ne sont pas « prêtes » ; ``download``
    les rend prêtes, sauf indication contraire. Il note aussi le umask et le délai de socket en
    vigueur pendant le téléchargement.

    Args:
        monkeypatch: Fixture pytest.
        ready: Les données sont déjà présentes.
        download_fails: Exception levée par ``download`` (ex. ``OSError("pas de réseau")``).
        download_without_data: ``download`` répond « réussi » mais les données restent refusées
            (c'est ce que fait NLTK quand le dossier n'est pas privé).
        order: Liste partagée qui reçoit ``("nltk_download",)`` à chaque téléchargement.
    """

    def __init__(self, monkeypatch, *, ready=False, download_fails=None,
                 download_without_data=False, order=None):
        self.ready = ready
        self.download_fails = download_fails
        self.download_without_data = download_without_data
        self.order = order if order is not None else []
        self.find_calls = []
        self.download_calls = []
        self.on_download = None     # appelé au début du téléchargement (ex. pour annuler)
        self.module = types.ModuleType("nltk")
        self.module.data = types.SimpleNamespace(find=self._find, path=[])
        self.module.download = self._download
        monkeypatch.setitem(sys.modules, "nltk", self.module)

    def _find(self, resource):
        self.find_calls.append(resource)
        if not self.ready:
            raise LookupError(f"Resource {resource} not found")
        return object()

    def _download(self, name, download_dir=None, quiet=False, raise_on_error=False):
        umask = os.umask(0)
        os.umask(umask)
        self.download_calls.append({
            "name": name, "download_dir": download_dir, "quiet": quiet,
            "raise_on_error": raise_on_error, "umask": umask, "timeout": socket.getdefaulttimeout(),
        })
        self.order.append(("nltk_download",))
        if self.on_download:
            self.on_download()
        if self.download_fails:
            raise self.download_fails
        if not self.download_without_data:
            self.ready = True
        return True


# ── faux whisperx / torch / whisper ──────────────────────────────────────────

SENTENCES = [
    {"start": 18.796, "end": 25.0, "text": " Premiere phrase.", "words": []},
    {"start": 25.5, "end": 31.0, "text": "Deuxieme phrase ?", "words": []},
    {"start": 32.0, "end": 43.231, "text": "Troisieme.", "words": []},
]
CHUNK_TEXT = " Premiere phrase. Deuxieme phrase ? Troisieme."


def _guess_lang(audio, kwargs) -> str:
    if kwargs.get("language"):
        return kwargs["language"]
    stem = os.path.splitext(os.path.basename(str(audio)))[0]
    return stem.rsplit("_", 1)[-1] if "_" in stem else "fr"


class FakeEngine:
    """
    Faux whisperx, torch et whisper installés dans ``sys.modules``.

    Il compte les chargements de modèles et renvoie des résultats déterministes : un segment
    Whisper de trois phrases, que l'alignement découpe en trois segments. La langue est lue
    dans le nom du fichier (``a_fr.wav`` → « fr ») si elle n'est pas imposée.

    Args:
        monkeypatch: Fixture pytest (tout est restauré à la fin du test).
        align_fail: Langues pour lesquelles ``load_align_model`` échoue.
        openai: True pour simuler l'absence de whisperx (repli openai-whisper).
        cuda: Valeur de ``torch.cuda.is_available()``.
        punkt_ready: Les données NLTK (punkt_tab) sont déjà présentes.
        punkt_download_fails: Exception levée par le téléchargement des données NLTK.
        align_error: Exception levée par ``whisperx.align`` (ex. ``LookupError`` de punkt_tab).
        diarizer_error: Exception levée au CHARGEMENT de la pipeline de diarisation.
        diarize_error: Exception levée par la diarisation elle-même (après la transcription).
    """

    def __init__(self, monkeypatch, *, align_fail=(), openai=False, cuda=False,
                 punkt_ready=True, punkt_download_fails=None, align_error=None,
                 diarizer_error=None, diarize_error=None):
        import transcriber

        self.model_loads = []        # (nom, device, compute_type)
        self.openai_loads = []
        self.align_loads = []        # langues
        self.diarizer_loads = []     # (model_name, device)
        self.diarize_calls = []      # kwargs de chaque appel (min_speakers, max_speakers)
        self.transcribe_calls = []   # (audio, kwargs)
        self.cuda_empty_cache_calls = 0
        self.align_fail = set(align_fail)
        self.align_error = align_error
        self.diarizer_error = diarizer_error
        self.diarize_error = diarize_error
        # Ordre des étapes lourdes : ("load_model", nom), ("nltk_download",), ("diarizer_load",),
        # ("align_load", langue), ("transcribe", audio)
        self.order = []
        self.nltk = FakeNltk(monkeypatch, ready=punkt_ready, download_fails=punkt_download_fails,
                             order=self.order)
        engine = self

        class Model:
            def transcribe(self, audio, **kwargs):
                engine.transcribe_calls.append((audio, kwargs))
                engine.order.append(("transcribe", audio))
                return {"segments": [{"start": 18.796, "end": 43.231, "text": CHUNK_TEXT}],
                        "language": _guess_lang(audio, kwargs)}

        wx = types.ModuleType("whisperx")

        def load_model(name, device, compute_type=None):
            engine.model_loads.append((name, device, compute_type))
            engine.order.append(("load_model", name))
            return Model()

        def load_align_model(language_code, device):
            engine.order.append(("align_load", language_code))
            if language_code in engine.align_fail:
                raise ValueError(f"No default align-model for language: {language_code}")
            engine.align_loads.append(language_code)
            return object(), {}

        wx.load_model = load_model
        wx.load_audio = lambda path: path
        wx.load_align_model = load_align_model
        def align(segs, model, meta, audio, device):
            if engine.align_error:
                raise engine.align_error
            return {"segments": [dict(s) for s in SENTENCES], "word_segments": []}

        wx.align = align

        diarize = types.ModuleType("whisperx.diarize")

        class DiarizationPipeline:
            def __init__(self, model_name, device):
                engine.order.append(("diarizer_load",))
                if engine.diarizer_error:
                    raise engine.diarizer_error
                engine.diarizer_loads.append((model_name, device))

            def __call__(self, audio, **kwargs):
                if engine.diarize_error:
                    raise engine.diarize_error
                engine.diarize_calls.append(kwargs)
                return "diarization"

        def assign_word_speakers(diarization, result):
            segments = [dict(s) for s in result["segments"]]
            for seg, speaker in zip(segments, ("SPEAKER_07", "SPEAKER_02")):
                seg["speaker"] = speaker   # le 3e segment reste sans locuteur
            return {"segments": segments}

        diarize.DiarizationPipeline = DiarizationPipeline
        diarize.assign_word_speakers = assign_word_speakers
        wx.diarize = diarize

        torch = types.ModuleType("torch")

        def empty_cache():
            engine.cuda_empty_cache_calls += 1

        torch.cuda = types.SimpleNamespace(is_available=lambda: cuda, empty_cache=empty_cache)

        whisper = types.ModuleType("whisper")

        class OpenAIModel:
            def transcribe(self, path, **kwargs):
                engine.transcribe_calls.append((path, kwargs))
                return {"segments": [{"start": 18.796, "end": 43.231, "text": CHUNK_TEXT}],
                        "language": _guess_lang(path, kwargs)}

        def openai_load_model(name):
            engine.openai_loads.append(name)
            return OpenAIModel()

        whisper.load_model = openai_load_model

        for name, module in (("whisperx", wx), ("whisperx.diarize", diarize),
                             ("torch", torch), ("whisper", whisper)):
            monkeypatch.setitem(sys.modules, name, module)
        monkeypatch.setattr(transcriber, "WHISPERX_AVAILABLE", not openai)


def write_media(directory: Path, *names: str) -> list[str]:
    """Crée des fichiers factices (vides) et renvoie leurs chemins."""
    paths = []
    for name in names:
        path = directory / name
        path.write_bytes(b"")
        paths.append(str(path))
    return paths
