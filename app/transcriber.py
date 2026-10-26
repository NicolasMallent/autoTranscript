import gc
import importlib.util
import json
import logging
import os
import platform
import subprocess
import sys
import tempfile
import time
from typing import Callable, Optional

import i18n
import model_setup
from paths import BASE_DIR

_logger = logging.getLogger("autotranscript.transcriber")

AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".ogg", ".flac", ".aac", ".wma"}
VIDEO_EXTENSIONS = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".wmv", ".flv"}
ALL_EXTENSIONS = AUDIO_EXTENSIONS | VIDEO_EXTENSIONS

# Taille de lot de la transcription whisperx
_BATCH_SIZE = 8

# find_spec évite d'importer whisperx (et torch, lent) au démarrage de l'interface.
# Une installation cassée n'est donc détectée qu'au premier import réel.
try:
    WHISPERX_AVAILABLE = importlib.util.find_spec("whisperx") is not None
except (ImportError, ValueError):
    WHISPERX_AVAILABLE = False
if not WHISPERX_AVAILABLE:
    _logger.warning("whisperx non installé : repli sur openai-whisper, sans diarisation")


def _find_ffmpeg() -> str:
    """
    Renvoie l'exécutable ffmpeg embarqué (ffmpeg/<système>/) s'il existe, sinon ``ffmpeg`` du PATH.
    """
    system = platform.system().lower()
    binary = "ffmpeg.exe" if system == "windows" else "ffmpeg"
    bundled = os.path.join(BASE_DIR, "ffmpeg", system, binary)
    if os.path.isfile(bundled):
        return bundled
    return "ffmpeg"


def _split_hms(seconds: float) -> tuple[int, int, int, int]:
    """
    Découpe une durée en (heures, minutes, secondes, millisecondes).

    La durée est d'abord arrondie à la milliseconde : aucun champ ne peut donc afficher
    60 (ex. 59,9996 s donne 00:01:00,000 et non 00:00:60,000).

    Args:
        seconds: Durée en secondes.

    Returns:
        Le tuple (h, m, s, ms).
    """
    total_ms = int(round(seconds * 1000))
    h, rem = divmod(total_ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return h, m, s, ms


def _float_to_time(seconds: float) -> str:
    """Formate une durée en ``HH:MM:SS.mmm`` (fichier .txt horodaté)."""
    h, m, s, ms = _split_hms(seconds)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


def _srt_timestamp(seconds: float) -> str:
    """Formate une durée en ``HH:MM:SS,mmm`` (séparateur décimal imposé par le format SRT)."""
    h, m, s, ms = _split_hms(seconds)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _format_hms(seconds: float) -> str:
    """Formate une durée en ``HH:MM:SS`` (fichier .txt avec locuteurs)."""
    h, m, s, _ = _split_hms(seconds)
    return f"{h:02d}:{m:02d}:{s:02d}"


def _extract_audio(video_path: str, ffmpeg_bin: str) -> str:
    """
    Extrait la piste audio d'une vidéo en WAV mono 16 kHz dans un fichier temporaire.

    Args:
        video_path: Chemin de la vidéo.
        ffmpeg_bin: Exécutable ffmpeg (embarqué ou du PATH).

    Returns:
        Chemin du fichier WAV temporaire, que l'appelant doit supprimer.

    Raises:
        RuntimeError: Si ffmpeg est introuvable ou échoue (les dernières lignes de sa
            sortie d'erreur sont incluses dans le message). Le fichier temporaire est
            alors déjà supprimé.
    """
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp.close()
    try:
        subprocess.run(
            [ffmpeg_bin, "-y", "-i", video_path, "-vn", "-ar", "16000", "-ac", "1", tmp.name],
            check=True, capture_output=True, text=True, errors="replace",
        )
    except FileNotFoundError as exc:
        os.unlink(tmp.name)
        raise RuntimeError(f"ffmpeg not found ({ffmpeg_bin})") from exc
    except subprocess.CalledProcessError as exc:
        os.unlink(tmp.name)
        # Le chemin du fichier source est remplacé : le log est destiné à être partagé
        tail = "\n".join((exc.stderr or "").strip().splitlines()[-5:]).replace(video_path, "<input>")
        _logger.error("ffmpeg a échoué (code %s) :\n%s", exc.returncode, tail)
        # "from None" : la CalledProcessError d'origine contient la commande, donc le chemin du fichier
        raise RuntimeError(f"ffmpeg failed (exit code {exc.returncode}): {tail}") from None
    return tmp.name


def _write_txt_simple(segments: list, output_path: str) -> None:
    """
    Écrit le .txt horodaté : une ligne ``[début --> fin] texte`` par segment.

    Après l'alignement des mots, un segment est une phrase ; sans alignement (langue sans
    modèle, openai-whisper), c'est un bloc de parole Whisper, donc une ligne plus longue.

    Args:
        segments: Segments whisper (clés ``start``, ``end``, ``text``).
        output_path: Fichier à écrire (écrasé s'il existe).
    """
    with open(output_path, "w", encoding="utf-8") as f:
        for seg in segments:
            start = _float_to_time(seg["start"])
            end = _float_to_time(seg["end"])
            f.write(f"[{start} --> {end}] {seg['text'].strip()}\n")


def _write_txt_speakers(segments: list, output_path: str) -> None:
    """
    Écrit le .txt avec locuteurs : ``Locuteur 1 [début - fin] : texte``, un segment par paragraphe.

    Args:
        segments: Segments avec la clé ``speaker`` (voir ``_rename_speakers``).
        output_path: Fichier à écrire (écrasé s'il existe).
    """
    with open(output_path, "w", encoding="utf-8") as f:
        for seg in segments:
            start = _format_hms(seg["start"])
            end = _format_hms(seg["end"])
            f.write(f"{seg['speaker']} [{start} - {end}] : {seg['text']}\n\n")


def _write_srt(segments: list, output_path: str, with_speakers: bool) -> None:
    """
    Écrit un fichier de sous-titres SRT.

    Args:
        segments: Segments whisper (clés ``start``, ``end``, ``text``, et ``speaker`` si présent).
        output_path: Fichier à écrire (écrasé s'il existe).
        with_speakers: Préfixe chaque sous-titre par le locuteur quand le segment en a un.
    """
    with open(output_path, "w", encoding="utf-8") as f:
        for i, seg in enumerate(segments, 1):
            text = seg["text"].strip()
            if with_speakers and "speaker" in seg:
                text = f"{seg['speaker']} : {text}"
            f.write(f"{i}\n{_srt_timestamp(seg['start'])} --> {_srt_timestamp(seg['end'])}\n{text}\n\n")


def _write_json(data: dict | list, output_path: str) -> None:
    """Écrit ``data`` en JSON indenté (UTF-8, sans échappement des accents)."""
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _write_outputs(
    segments: list, raw: dict | list, file_path: str, suffix: str,
    formats: list[str], with_speakers: bool,
) -> None:
    """
    Écrit les fichiers de sortie demandés à côté du fichier source.

    Args:
        segments: Segments à écrire dans les formats texte et sous-titres.
        raw: Données écrites telles quelles dans le fichier JSON.
        file_path: Fichier source ; les sorties portent son nom sans extension.
        suffix: Suffixe ajouté au nom (ex. ``_base`` ou ``_base_diarized``).
        formats: Sous-ensemble de {"txt", "srt", "json"}.
        with_speakers: True si les segments portent une clé ``speaker``.
    """
    stem = os.path.splitext(file_path)[0]
    writers = {
        "txt": lambda path: (_write_txt_speakers if with_speakers else _write_txt_simple)(segments, path),
        "srt": lambda path: _write_srt(segments, path, with_speakers),
        "json": lambda path: _write_json(raw, path),
    }
    for fmt in formats:
        writers[fmt](f"{stem}{suffix}.{fmt}")
        _logger.debug("Sortie écrite : .%s", fmt)


def _rename_speakers(raw_segments: list) -> list:
    """
    Remplace les identifiants pyannote (SPEAKER_00…) par « Locuteur 1 », « Locuteur 2 »…

    Les locuteurs sont numérotés dans l'ordre de première apparition. Un segment que
    pyannote n'a attribué à personne reçoit le libellé « Locuteur ? » : il ne doit pas
    passer pour un locuteur supplémentaire.

    Args:
        raw_segments: Segments whisperx après ``assign_word_speakers``.

    Returns:
        Nouvelle liste de segments, avec la clé ``speaker`` renommée (libellés traduits
        dans la langue de l'interface).
    """
    mapping: dict = {}
    result = []
    for seg in raw_segments:
        raw = seg.get("speaker")
        if raw is None:
            result.append({**seg, "speaker": i18n.t("speaker_unknown")})
            continue
        if raw not in mapping:
            mapping[raw] = f"{i18n.t('speaker_label')} {len(mapping) + 1}"
        result.append({**seg, "speaker": mapping[raw]})
    return result


class Transcriber:
    """
    Transcrit des fichiers audio/vidéo avec Whisper, avec identification des locuteurs en option.

    Une instance garde le modèle Whisper chargé entre deux appels à ``transcribe`` tant que
    le modèle demandé ne change pas. Les modèles d'alignement et de diarisation, plus lourds,
    ne sont gardés que le temps d'un lot de fichiers. ``transcribe`` est bloquant : l'interface
    l'appelle depuis un thread et reçoit la progression par callback.
    """
    def __init__(self):
        self._model = None
        self._model_name: str = ""
        self._device: str = "cpu"
        self._cancelled: bool = False
        # Modèles d'alignement et de diarisation : gardés le temps d'un lot de fichiers
        # pour ne pas les recharger à chaque fichier, libérés à la fin du lot
        self._align_model = None
        self._align_metadata = None
        self._align_lang: Optional[str] = None
        self._diarizer = None

    def cancel(self) -> None:
        """
        Demande l'arrêt de la transcription en cours.

        L'arrêt n'est pris en compte qu'entre deux fichiers : le fichier en cours va jusqu'au bout.
        """
        self._cancelled = True

    def transcribe(
        self,
        path: str,
        model_name: str,
        language: str,
        formats: list[str],
        diarize: bool,
        min_speakers: Optional[int],
        max_speakers: Optional[int],
        progress_callback: Callable[[str, float], None],
    ) -> None:
        """
        Transcrit un fichier audio/vidéo, ou tous ceux d'un dossier (non récursif, ordre alphabétique).

        Les sorties sont écrites à côté de chaque fichier source. Un fichier en échec est signalé
        par le callback puis ignoré : il n'interrompt pas le reste du lot.

        Args:
            path: Fichier ou dossier à traiter.
            model_name: Identifiant du modèle Whisper (cf. models.json).
            language: Code langue (« fr », « en ») ou chaîne vide pour la détection automatique.
            formats: Sous-ensemble de {"txt", "srt", "json"}.
            diarize: Active l'identification des locuteurs (ignoré sans whisperx). Télécharge le
                modèle pyannote au premier usage.
            min_speakers: Nombre minimal de locuteurs, ou None.
            max_speakers: Nombre maximal de locuteurs, ou None.
            progress_callback: Appelé avec (code_message, progression entre 0 et 1). Codes émis :
                loading_model, processing_file, extracting_audio, aligning, diarizing, done_file,
                error, done_with_errors, all_done, no_audio_found et diarization_model_*.

        Raises:
            RuntimeError: Si le modèle de diarisation ne peut pas être téléchargé ou chargé.
            Exception: Toute erreur de chargement du modèle Whisper (l'appelant doit la gérer).
        """
        self._cancelled = False
        ffmpeg_bin = _find_ffmpeg()
        _logger.info("ffmpeg : %s", ffmpeg_bin)

        if os.path.isdir(path):
            files = sorted(
                os.path.join(path, f)
                for f in os.listdir(path)
                if os.path.splitext(f)[1].lower() in ALL_EXTENSIONS
            )
        else:
            files = [path]

        if not files:
            _logger.warning("Aucun fichier audio/vidéo trouvé dans la sélection")
            progress_callback("no_audio_found", 1.0)
            return
        _logger.info("%d fichier(s) à traiter", len(files))

        # diarize est impossible sans whisperx
        if diarize and not WHISPERX_AVAILABLE:
            _logger.warning("Diarisation demandée mais whisperx est indisponible : ignorée")
        diarize = diarize and WHISPERX_AVAILABLE

        if diarize:
            model_setup.ensure_model(progress_callback)
            if self._cancelled:
                _logger.info("Annulé pendant la préparation du modèle de diarisation")
                progress_callback("cancelled", 0.0)
                return

        self._load_model(model_name, progress_callback)

        failed = 0
        skipped = False
        reached = 0.0
        try:
            for i, file_path in enumerate(files):
                if self._cancelled:
                    _logger.info("Annulation prise en compte avant le fichier %d/%d", i + 1, len(files))
                    skipped = True
                    reached = i / len(files)
                    break

                base_progress = i / len(files)
                file_progress = 1.0 / len(files)
                started = time.monotonic()
                # Pas de nom de fichier dans le log (il peut être partagé) : index et extension seulement
                _logger.info(
                    "Fichier %d/%d (%s) : début", i + 1, len(files),
                    os.path.splitext(file_path)[1].lower(),
                )
                progress_callback(f"processing_file:{os.path.basename(file_path)}", base_progress)

                tmp_audio = None
                try:
                    audio_path = file_path
                    if os.path.splitext(file_path)[1].lower() in VIDEO_EXTENSIONS:
                        progress_callback(f"extracting_audio:{os.path.basename(file_path)}", base_progress)
                        tmp_audio = _extract_audio(file_path, ffmpeg_bin)
                        audio_path = tmp_audio

                    if diarize:
                        segments = self._run_diarization_pipeline(
                            audio_path, file_path, language,
                            min_speakers, max_speakers,
                            formats, base_progress, file_progress,
                            progress_callback,
                        )
                    else:
                        segments = self._run_simple_transcription(
                            audio_path, file_path, language, formats,
                            base_progress, file_progress, progress_callback,
                        )
                except Exception as exc:
                    # Un fichier en échec ne doit pas interrompre le reste du lot
                    failed += 1
                    _logger.exception("Fichier %d/%d : échec", i + 1, len(files))
                    progress_callback(
                        f"error:{os.path.basename(file_path)} — {exc}", base_progress + file_progress,
                    )
                    continue
                finally:
                    if tmp_audio and os.path.exists(tmp_audio):
                        os.unlink(tmp_audio)

                _logger.info(
                    "Fichier %d/%d : terminé en %.1f s (%d segments)",
                    i + 1, len(files), time.monotonic() - started, len(segments),
                )
                progress_callback(f"done_file:{os.path.basename(file_path)}", base_progress + file_progress)
        finally:
            self._release_diarization_models()

        # Annulé = au moins un fichier n'a pas été traité ; une annulation demandée pendant le
        # dernier fichier ne change rien : le lot est complet
        if skipped:
            _logger.info("Transcription annulée")
            progress_callback("cancelled", reached)
            return
        if failed:
            _logger.warning("%d fichier(s) en échec sur %d", failed, len(files))
            progress_callback(f"done_with_errors:{failed}/{len(files)}", 1.0)
        else:
            _logger.info("Toutes les transcriptions sont terminées")
            progress_callback("all_done", 1.0)

    # ── private ──────────────────────────────────────────────────────────────

    @staticmethod
    def _free_memory() -> None:
        """Ramasse les objets libérés et vide le cache GPU (sans importer torch s'il est absent)."""
        gc.collect()
        torch = sys.modules.get("torch")
        if torch is not None and torch.cuda.is_available():
            torch.cuda.empty_cache()

    def _load_model(self, model_name: str, cb: Callable) -> None:
        """
        Charge le modèle Whisper (whisperx si disponible, sinon openai-whisper).

        Le modèle déjà chargé est réutilisé s'il porte le même nom ; sinon il est libéré
        avant de charger le suivant.

        Args:
            model_name: Identifiant du modèle (cf. models.json).
            cb: Callback de progression.
        """
        if WHISPERX_AVAILABLE:
            import torch
            self._device = "cuda" if torch.cuda.is_available() else "cpu"

        if self._model is not None and self._model_name == model_name:
            return
        if self._model is not None:
            self._model = None
            self._free_memory()

        cb(f"loading_model:{model_name}", 0.0)
        started = time.monotonic()
        if WHISPERX_AVAILABLE:
            import whisperx
            compute_type = "float16" if self._device == "cuda" else "int8"
            _logger.info("Chargement du modèle whisperx %s (device=%s, compute_type=%s)",
                         model_name, self._device, compute_type)
            self._model = whisperx.load_model(model_name, self._device, compute_type=compute_type)
        else:
            import whisper
            _logger.info("Chargement du modèle openai-whisper %s", model_name)
            self._model = whisper.load_model(model_name)
        self._model_name = model_name
        _logger.info("Modèle chargé en %.1f s", time.monotonic() - started)

    def _load_diarization_pipeline(self, pipeline_class):
        """
        Charge la pipeline pyannote depuis le dossier local du modèle.

        Le dossier est passé à pyannote à la place d'un identifiant HuggingFace : aucun
        accès réseau ni token n'est nécessaire.

        Args:
            pipeline_class: Classe ``whisperx.diarize.DiarizationPipeline``.

        Returns:
            L'instance de pipeline prête à être appelée.

        Raises:
            RuntimeError: Si le modèle est absent ou ne peut pas être chargé.
        """
        model_dir = model_setup.model_path()
        if not model_setup.is_model_ready():
            raise RuntimeError(f"Diarization model not found in {model_dir}")
        _logger.info("Chargement de la pipeline de diarisation depuis %s", model_dir)
        try:
            return pipeline_class(model_name=str(model_dir), device=self._device)
        except Exception as exc:
            _logger.exception("Echec du chargement de la pipeline de diarisation")
            raise RuntimeError(f"Cannot load the diarization model from {model_dir}: {exc}") from exc

    def _get_align_model(self, lang: str):
        """
        Renvoie le modèle d'alignement pour la langue donnée, en le chargeant si besoin.

        Un seul modèle est gardé : il est remplacé quand la langue change d'un fichier
        à l'autre (détection automatique).

        Args:
            lang: Code langue (ex. "fr").

        Returns:
            Le tuple (modèle, métadonnées) attendu par ``whisperx.align``.
        """
        import whisperx

        if self._align_lang != lang:
            if self._align_model is not None:
                # _align_lang est remis à zéro avec le modèle : si le chargement suivant échoue,
                # la langue précédente doit être rechargée et non servie à vide
                self._align_model = self._align_metadata = self._align_lang = None
                self._free_memory()
            _logger.info("Chargement du modèle d'alignement (%s)", lang)
            self._align_model, self._align_metadata = whisperx.load_align_model(
                language_code=lang, device=self._device,
            )
            self._align_lang = lang
        return self._align_model, self._align_metadata

    def _get_diarizer(self):
        """Renvoie la pipeline de diarisation, chargée une seule fois par lot."""
        if self._diarizer is None:
            from whisperx.diarize import DiarizationPipeline
            self._diarizer = self._load_diarization_pipeline(DiarizationPipeline)
        return self._diarizer

    def _release_diarization_models(self) -> None:
        """Libère les modèles d'alignement et de diarisation (et la mémoire GPU associée)."""
        if self._align_model is None and self._diarizer is None:
            return
        self._align_model = self._align_metadata = self._align_lang = None
        self._diarizer = None
        self._free_memory()

    def _transcribe(self, audio, language: str) -> dict:
        """
        Lance la transcription Whisper avec le moteur chargé.

        Args:
            audio: Tableau audio (whisperx) ou chemin du fichier (openai-whisper).
            language: Code langue, ou chaîne vide pour la détection automatique.

        Returns:
            Le résultat du moteur (clés ``segments`` et ``language``).
        """
        kwargs = {}
        if language:
            kwargs["language"] = language
        if WHISPERX_AVAILABLE:
            kwargs["batch_size"] = _BATCH_SIZE
        return self._model.transcribe(audio, **kwargs)

    def _align(
        self, result: dict, audio, language: str, file_path: str,
        base_progress: float, file_progress: float, cb: Callable,
    ) -> dict:
        """
        Aligne les mots sur l'audio : chaque segment devient une ou plusieurs phrases horodatées.

        Args:
            result: Résultat de ``_transcribe`` (clés ``segments`` et ``language``).
            audio: Tableau audio chargé par ``whisperx.load_audio``.
            language: Langue demandée par l'utilisateur, ou chaîne vide (détection automatique).
            file_path: Fichier source (pour le message de progression).
            base_progress: Progression du lot au début de ce fichier (entre 0 et 1).
            file_progress: Part de la progression totale que représente ce fichier.
            cb: Callback de progression.

        Returns:
            Le résultat whisperx : ``segments`` (une entrée par phrase, avec ``words``) et
            ``word_segments``.

        Raises:
            Exception: Si aucun modèle d'alignement n'existe pour la langue ou ne peut être
                téléchargé (l'appelant décide s'il peut s'en passer).
        """
        import whisperx

        detected_lang = result.get("language", language or "fr")
        _logger.info("Langue utilisée pour l'alignement : %s", detected_lang)
        cb(f"aligning:{os.path.basename(file_path)}", base_progress + file_progress * 0.4)
        model_a, metadata = self._get_align_model(detected_lang)
        return whisperx.align(result["segments"], model_a, metadata, audio, self._device)

    def _run_simple_transcription(
        self, audio_path: str, file_path: str, language: str, formats: list[str],
        base_progress: float, file_progress: float, cb: Callable,
    ) -> list:
        """
        Transcrit un fichier sans identification des locuteurs et écrit les sorties demandées.

        Avec whisperx, les mots sont alignés pour obtenir un horodatage par phrase. Si
        l'alignement est impossible (langue sans modèle, téléchargement refusé), on garde les
        segments Whisper, plus longs, et l'interface en est informée.

        Args:
            audio_path: Fichier audio à lire (déjà extrait si la source est une vidéo).
            file_path: Fichier source, qui donne son nom aux sorties.
            language: Code langue, ou chaîne vide pour la détection automatique.
            formats: Sous-ensemble de {"txt", "srt", "json"}.
            base_progress: Progression du lot au début de ce fichier (entre 0 et 1).
            file_progress: Part de la progression totale que représente ce fichier.
            cb: Callback de progression.

        Returns:
            Les segments (une entrée par phrase si l'alignement a eu lieu).
        """
        if WHISPERX_AVAILABLE:
            import whisperx
            audio = whisperx.load_audio(audio_path)
        else:
            audio = audio_path
        result = self._transcribe(audio, language)

        if WHISPERX_AVAILABLE:
            lang = result.get("language", language or "fr")
            try:
                aligned = self._align(result, audio, language, file_path, base_progress, file_progress, cb)
                result = {"language": lang, **aligned}
            except Exception:
                _logger.warning(
                    "Alignement impossible (langue %s) : horodatage par segment", lang, exc_info=True,
                )
                cb(f"align_unavailable:{lang}", base_progress + file_progress * 0.4)
        segments = result["segments"]

        _write_outputs(segments, result, file_path, f"_{self._model_name}", formats, with_speakers=False)
        return segments

    def _run_diarization_pipeline(
        self, audio_path: str, file_path: str, language: str,
        min_speakers: Optional[int], max_speakers: Optional[int],
        formats: list[str], base_progress: float, file_progress: float,
        cb: Callable,
    ) -> list:
        """
        Transcrit, aligne les mots, identifie les locuteurs et écrit les sorties demandées.

        Args:
            audio_path: Fichier audio à lire (déjà extrait si la source est une vidéo).
            file_path: Fichier source, qui donne son nom aux sorties (suffixe ``_diarized``).
            language: Code langue, ou chaîne vide pour la détection automatique.
            min_speakers: Nombre minimal de locuteurs, ou None.
            max_speakers: Nombre maximal de locuteurs, ou None.
            formats: Sous-ensemble de {"txt", "srt", "json"}.
            base_progress: Progression du lot au début de ce fichier (entre 0 et 1).
            file_progress: Part de la progression totale que représente ce fichier.
            cb: Callback de progression.

        Returns:
            Les segments, avec la clé ``speaker`` renommée (voir ``_rename_speakers``).

        Raises:
            RuntimeError: Si le modèle de diarisation est absent ou illisible.
        """
        import whisperx
        from whisperx.diarize import assign_word_speakers

        audio = whisperx.load_audio(audio_path)
        result = self._transcribe(audio, language)
        result = self._align(result, audio, language, file_path, base_progress, file_progress, cb)

        cb(f"diarizing:{os.path.basename(file_path)}", base_progress + file_progress * 0.65)
        diarize_kwargs = {}
        if min_speakers:
            diarize_kwargs["min_speakers"] = min_speakers
        if max_speakers:
            diarize_kwargs["max_speakers"] = max_speakers
        _logger.info("Diarisation (min=%s, max=%s)", min_speakers, max_speakers)
        diarize_segments = self._get_diarizer()(audio, **diarize_kwargs)

        result = assign_word_speakers(diarize_segments, result)
        segments = _rename_speakers(result["segments"])

        _write_outputs(
            segments, segments, file_path, f"_{self._model_name}_diarized", formats, with_speakers=True,
        )
        return segments
