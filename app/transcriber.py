import datetime
import json
import os
import platform
import subprocess
import tempfile
from typing import Callable, Optional

AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".ogg", ".flac", ".aac", ".wma"}
VIDEO_EXTENSIONS = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".wmv", ".flv"}
ALL_EXTENSIONS = AUDIO_EXTENSIONS | VIDEO_EXTENSIONS

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _find_ffmpeg() -> str:
    system = platform.system().lower()
    binary = "ffmpeg.exe" if system == "windows" else "ffmpeg"
    bundled = os.path.join(_BASE_DIR, "ffmpeg", system, binary)
    if os.path.isfile(bundled):
        return bundled
    return "ffmpeg"


def _float_to_time(seconds: float) -> str:
    delta = datetime.timedelta(seconds=seconds)
    h, rem = divmod(delta.total_seconds(), 3600)
    m, s = divmod(rem, 60)
    return f"{int(h):02}:{int(m):02}:{s:06.3f}"


def _srt_timestamp(seconds: float) -> str:
    ms = int(round(seconds * 1000))
    h, rem = divmod(ms, 3600000)
    m, rem = divmod(rem, 60000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _extract_audio(video_path: str, ffmpeg_bin: str) -> str:
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp.close()
    subprocess.run(
        [ffmpeg_bin, "-y", "-i", video_path, "-vn", "-ar", "16000", "-ac", "1", tmp.name],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    return tmp.name


def _write_txt_simple(segments: list, output_path: str) -> None:
    with open(output_path, "w", encoding="utf-8") as f:
        for seg in segments:
            start = _float_to_time(seg["start"])
            end = _float_to_time(seg["end"])
            text = (
                seg["text"]
                .replace("... ", "...\n").replace(". ", ".\n")
                .replace("! ", "!\n").replace("? ", "?\n")
            )
            f.write(f"\n[{start} --> {end}]{text}")


def _write_txt_speakers(segments: list, output_path: str) -> None:
    with open(output_path, "w", encoding="utf-8") as f:
        for seg in segments:
            h_s, rem = divmod(int(seg["start"]), 3600)
            m_s, s_s = divmod(rem, 60)
            h_e, rem = divmod(int(seg["end"]), 3600)
            m_e, s_e = divmod(rem, 60)
            start = f"{h_s:02d}:{m_s:02d}:{s_s:02d}"
            end = f"{h_e:02d}:{m_e:02d}:{s_e:02d}"
            f.write(f"{seg['speaker']} [{start} - {end}] : {seg['text']}\n\n")


def _write_srt(segments: list, output_path: str, with_speakers: bool) -> None:
    with open(output_path, "w", encoding="utf-8") as f:
        for i, seg in enumerate(segments, 1):
            text = seg["text"].strip()
            if with_speakers and "speaker" in seg:
                text = f"{seg['speaker']} : {text}"
            f.write(f"{i}\n{_srt_timestamp(seg['start'])} --> {_srt_timestamp(seg['end'])}\n{text}\n\n")


def _write_json(data: dict | list, output_path: str) -> None:
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _rename_speakers(raw_segments: list) -> list:
    """Traduit SPEAKER_00 → Locuteur 1 en ordre d'apparition."""
    mapping: dict = {}
    result = []
    for seg in raw_segments:
        raw = seg.get("speaker", "INCONNU")
        if raw not in mapping:
            mapping[raw] = f"Locuteur {len(mapping) + 1}"
        result.append({**seg, "speaker": mapping[raw]})
    return result


class Transcriber:
    def __init__(self):
        self._model = None
        self._model_name: str = ""
        self._cancelled: bool = False

    def cancel(self) -> None:
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
        self._cancelled = False
        ffmpeg_bin = _find_ffmpeg()

        if os.path.isdir(path):
            files = [
                os.path.join(path, f)
                for f in os.listdir(path)
                if os.path.splitext(f)[1].lower() in ALL_EXTENSIONS
            ]
        else:
            files = [path]

        if not files:
            progress_callback("no_audio_found", 1.0)
            return

        if diarize:
            import model_setup
            model_setup.ensure_model(progress_callback)
            if self._cancelled:
                return

        self._load_whisperx_model(model_name, progress_callback)

        for i, file_path in enumerate(files):
            if self._cancelled:
                break

            base_progress = i / len(files)
            file_progress = 1.0 / len(files)
            progress_callback(f"processing_file:{os.path.basename(file_path)}", base_progress)

            tmp_audio = None
            audio_path = file_path
            if os.path.splitext(file_path)[1].lower() in VIDEO_EXTENSIONS:
                progress_callback(f"extracting_audio:{os.path.basename(file_path)}", base_progress)
                tmp_audio = _extract_audio(file_path, ffmpeg_bin)
                audio_path = tmp_audio

            try:
                if diarize:
                    segments = self._run_diarization_pipeline(
                        audio_path, file_path, language,
                        min_speakers, max_speakers,
                        formats, base_progress, file_progress,
                        progress_callback,
                    )
                else:
                    segments = self._run_simple_transcription(
                        audio_path, file_path, language, formats, progress_callback,
                    )
            finally:
                if tmp_audio and os.path.exists(tmp_audio):
                    os.unlink(tmp_audio)

            progress_callback(f"done_file:{os.path.basename(file_path)}", base_progress + file_progress)

        if not self._cancelled:
            progress_callback("all_done", 1.0)

    # ── private ──────────────────────────────────────────────────────────────

    def _load_whisperx_model(self, model_name: str, cb: Callable) -> None:
        import torch
        import whisperx

        device = "cuda" if torch.cuda.is_available() else "cpu"
        compute_type = "float16" if device == "cuda" else "int8"

        if self._model_name != model_name or self._model is None:
            cb(f"loading_model:{model_name}", 0.0)
            self._model = whisperx.load_model(model_name, device, compute_type=compute_type)
            self._model_name = model_name
        self._device = device

    def _run_simple_transcription(
        self, audio_path: str, file_path: str, language: str,
        formats: list[str], cb: Callable,
    ) -> list:
        import whisperx

        audio = whisperx.load_audio(audio_path)
        kwargs = {"batch_size": 8}
        if language:
            kwargs["language"] = language
        result = self._model.transcribe(audio, **kwargs)
        segments = result["segments"]

        stem = os.path.splitext(file_path)[0]
        suffix = f"_{self._model_name}"
        if "txt" in formats:
            _write_txt_simple(segments, f"{stem}{suffix}.txt")
        if "srt" in formats:
            _write_srt(segments, f"{stem}{suffix}.srt", with_speakers=False)
        if "json" in formats:
            _write_json(result, f"{stem}{suffix}.json")
        return segments

    def _run_diarization_pipeline(
        self, audio_path: str, file_path: str, language: str,
        min_speakers: Optional[int], max_speakers: Optional[int],
        formats: list[str], base_progress: float, file_progress: float,
        cb: Callable,
    ) -> list:
        import whisperx
        from whisperx.diarize import DiarizationPipeline, assign_word_speakers

        audio = whisperx.load_audio(audio_path)
        kwargs = {"batch_size": 8}
        if language:
            kwargs["language"] = language
        result = self._model.transcribe(audio, **kwargs)
        detected_lang = result.get("language", language or "fr")

        cb(f"aligning:{os.path.basename(file_path)}", base_progress + file_progress * 0.4)
        model_a, metadata = whisperx.load_align_model(language_code=detected_lang, device=self._device)
        result = whisperx.align(result["segments"], model_a, metadata, audio, self._device)
        del model_a

        cb(f"diarizing:{os.path.basename(file_path)}", base_progress + file_progress * 0.65)
        diarize_kwargs = {}
        if min_speakers:
            diarize_kwargs["min_speakers"] = min_speakers
        if max_speakers:
            diarize_kwargs["max_speakers"] = max_speakers
        diarize_model = DiarizationPipeline(
            model_name="pyannote/speaker-diarization-3.1", device=self._device
        )
        diarize_segments = diarize_model(audio, **diarize_kwargs)
        del diarize_model

        result = assign_word_speakers(diarize_segments, result)
        segments = _rename_speakers(result["segments"])

        stem = os.path.splitext(file_path)[0]
        suffix = f"_{self._model_name}_diarized"
        if "txt" in formats:
            _write_txt_speakers(segments, f"{stem}{suffix}.txt")
        if "srt" in formats:
            _write_srt(segments, f"{stem}{suffix}.srt", with_speakers=True)
        if "json" in formats:
            _write_json(segments, f"{stem}{suffix}.json")
        return segments
