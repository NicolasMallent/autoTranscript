"""
Moteur de transcription + diarisation, basé sur WhisperX et pyannote.audio.
"""
from pathlib import Path
from typing import Callable, List, Optional

import torch
import whisperx
from whisperx.diarize import DiarizationPipeline, assign_word_speakers

ProgressCallback = Optional[Callable[[str, float], None]]


def _report(callback: ProgressCallback, message: str, fraction: float) -> None:
    if callback is not None:
        callback(message, fraction)


def format_timestamp(seconds: float) -> str:
    """Convertit des secondes en hh:mm:ss."""
    total_seconds = int(round(seconds))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def transcribe_and_diarize(
    audio_path: str,
    model_dir: Path,
    whisper_model_size: str = "small",
    language: str = "",
    min_speakers: Optional[int] = None,
    max_speakers: Optional[int] = None,
    device: Optional[str] = None,
    progress_callback: ProgressCallback = None,
) -> List[dict]:
    """
    Transcrit `audio_path` et identifie les locuteurs.
    Renvoie une liste de segments : {"speaker", "start", "end", "text"}.
    """
    if device is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"
    compute_type = "float16" if device == "cuda" else "int8"
    batch_size = 16

    _report(progress_callback, "Chargement du modèle Whisper…", 0.05)
    model = whisperx.load_model(whisper_model_size, device, compute_type=compute_type)

    _report(progress_callback, "Lecture du fichier audio…", 0.15)
    audio = whisperx.load_audio(audio_path)

    _report(progress_callback, "Transcription en cours…", 0.2)
    transcribe_kwargs = {"batch_size": batch_size}
    if language:
        transcribe_kwargs["language"] = language
    result = model.transcribe(audio, **transcribe_kwargs)
    del model  # libère la mémoire avant l'étape suivante

    _report(progress_callback, "Alignement précis des mots…", 0.5)
    model_a, metadata = whisperx.load_align_model(language_code=result["language"], device=device)
    result = whisperx.align(result["segments"], model_a, metadata, audio, device)
    del model_a

    _report(progress_callback, "Identification des locuteurs…", 0.6)
    # On pointe directement vers le dossier local du modèle : pas de token,
    # pas de compte Hugging Face, pas de connexion internet nécessaires ici.
    diarize_model = DiarizationPipeline(model_name=str(model_dir), device=device)

    def _diarize_progress(pct: float) -> None:
        _report(progress_callback, "Identification des locuteurs…", 0.6 + (pct / 100) * 0.25)

    diarize_kwargs = {"progress_callback": _diarize_progress}
    if min_speakers:
        diarize_kwargs["min_speakers"] = min_speakers
    if max_speakers:
        diarize_kwargs["max_speakers"] = max_speakers
    diarize_segments = diarize_model(audio, **diarize_kwargs)
    del diarize_model

    _report(progress_callback, "Association du texte aux locuteurs…", 0.9)
    result = assign_word_speakers(diarize_segments, result)

    # On renomme les labels bruts (SPEAKER_00, SPEAKER_01…) en "Locuteur 1",
    # "Locuteur 2"… dans l'ordre de leur première apparition.
    segments: List[dict] = []
    speaker_numbers: dict = {}
    for raw_segment in result["segments"]:
        raw_speaker = raw_segment.get("speaker", "INCONNU")
        if raw_speaker not in speaker_numbers:
            speaker_numbers[raw_speaker] = len(speaker_numbers) + 1
        friendly_name = f"Locuteur {speaker_numbers[raw_speaker]}"

        segments.append(
            {
                "speaker": friendly_name,
                "start": raw_segment["start"],
                "end": raw_segment["end"],
                "text": raw_segment["text"].strip(),
            }
        )

    _report(progress_callback, "Terminé.", 1.0)
    return segments


def segments_to_text(segments: List[dict]) -> str:
    """Formate les segments en texte lisible : Locuteur X [hh:mm:ss - hh:mm:ss] : ..."""
    lines = []
    for seg in segments:
        start = format_timestamp(seg["start"])
        end = format_timestamp(seg["end"])
        lines.append(f"{seg['speaker']} [{start} - {end}] : {seg['text']}")
    return "\n".join(lines)


def segments_to_srt(segments: List[dict]) -> str:
    """Formate les segments au format sous-titres .srt, avec le locuteur en préfixe."""

    def srt_timestamp(seconds: float) -> str:
        total_ms = int(round(seconds * 1000))
        hours, rem = divmod(total_ms, 3600000)
        minutes, rem = divmod(rem, 60000)
        secs, ms = divmod(rem, 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"

    lines = []
    for index, seg in enumerate(segments, start=1):
        lines.append(str(index))
        lines.append(f"{srt_timestamp(seg['start'])} --> {srt_timestamp(seg['end'])}")
        lines.append(f"{seg['speaker']} : {seg['text']}")
        lines.append("")
    return "\n".join(lines)
