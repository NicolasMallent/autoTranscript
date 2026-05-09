import datetime
import json
import os
import platform
import subprocess
import sys
import tempfile
from typing import Callable

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


def _float_to_time(time_float: float) -> str:
    delta = datetime.timedelta(seconds=time_float)
    hours, remainder = divmod(delta.total_seconds(), 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{int(hours):02}:{int(minutes):02}:{seconds:06.3f}"


def _extract_audio(video_path: str, ffmpeg_bin: str) -> str:
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp.close()
    subprocess.run(
        [ffmpeg_bin, "-y", "-i", video_path, "-vn", "-ar", "16000", "-ac", "1", tmp.name],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return tmp.name


def _write_txt(segments: list, output_path: str) -> None:
    with open(output_path, "w", encoding="utf-8") as f:
        for segment in segments:
            start = _float_to_time(segment["start"])
            end = _float_to_time(segment["end"])
            text = (
                segment["text"]
                .replace("... ", "...\n")
                .replace(". ", ".\n")
                .replace("! ", "!\n")
                .replace("? ", "?\n")
            )
            f.write(f"\n[{start} --> {end}]{text}")


def _write_json(result: dict, output_path: str) -> None:
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)


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
        progress_callback: Callable[[str, float], None],
    ) -> None:
        import whisper

        self._cancelled = False
        ffmpeg_bin = _find_ffmpeg()

        if self._model_name != model_name or self._model is None:
            progress_callback(f"loading_model:{model_name}", 0.0)
            self._model = whisper.load_model(model_name)
            self._model_name = model_name

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

        options = {"task": "transcribe", "verbose": False}
        if language and language != "auto":
            options["language"] = language

        for i, file_path in enumerate(files):
            if self._cancelled:
                break

            progress_callback(f"processing_file:{os.path.basename(file_path)}", i / len(files))

            tmp_audio = None
            audio_path = file_path
            ext = os.path.splitext(file_path)[1].lower()

            if ext in VIDEO_EXTENSIONS:
                progress_callback(f"extracting_audio:{os.path.basename(file_path)}", i / len(files))
                tmp_audio = _extract_audio(file_path, ffmpeg_bin)
                audio_path = tmp_audio

            try:
                result = self._model.transcribe(audio_path, **options)
            finally:
                if tmp_audio and os.path.exists(tmp_audio):
                    os.unlink(tmp_audio)

            stem = os.path.splitext(file_path)[0]

            if "txt" in formats:
                _write_txt(result["segments"], f"{stem}_{model_name}.txt")
            if "json" in formats:
                _write_json(result, f"{stem}_{model_name}.json")

            progress_callback(f"done_file:{os.path.basename(file_path)}", (i + 1) / len(files))

        if not self._cancelled:
            progress_callback("all_done", 1.0)
