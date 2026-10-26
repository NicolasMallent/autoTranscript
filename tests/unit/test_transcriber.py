"""Tests unitaires de app/transcriber.py."""
import json
import platform
import sys
import types

import pytest

import transcriber as T
from helpers import FakeEngine, make_fake_ffmpeg, populate_model_dir, posix_only

SEGMENTS = [
    {"start": 0.0, "end": 6.24, "text": " Dans le bouquin, non."},
    {"start": 6.5, "end": 11.1, "text": "Exactement."},
]


class TestSplitHms:
    @pytest.mark.parametrize("seconds, expected", [
        (0, (0, 0, 0, 0)),
        (6.24, (0, 0, 6, 240)),
        (59.9996, (0, 1, 0, 0)),          # jamais « 60 » dans un champ
        (3599.9996, (1, 0, 0, 0)),
        (3661.5, (1, 1, 1, 500)),
        (0.0004, (0, 0, 0, 0)),
        (86400, (24, 0, 0, 0)),
    ])
    def test_split(self, seconds, expected):
        assert T._split_hms(seconds) == expected

    def test_accepts_integers_and_floats_alike(self):
        assert T._split_hms(5) == T._split_hms(5.0)


class TestTimeFormats:
    def test_txt_format(self):
        assert T._float_to_time(6.24) == "00:00:06.240"
        assert T._float_to_time(59.9996) == "00:01:00.000"

    def test_srt_format_uses_a_comma(self):
        assert T._srt_timestamp(3661.5) == "01:01:01,500"

    def test_clock_format_has_no_milliseconds(self):
        assert T._format_hms(3725.2) == "01:02:05"
        assert T._format_hms(1.5) == "00:00:01"

    def test_more_than_99_hours(self):
        assert T._float_to_time(360000) == "100:00:00.000"


class TestRenameSpeakers:
    def test_numbers_speakers_in_order_of_first_appearance(self, ui_lang):
        raw = [{"speaker": "SPEAKER_05", "text": "a"}, {"speaker": "SPEAKER_01", "text": "b"},
               {"speaker": "SPEAKER_05", "text": "c"}]
        assert [s["speaker"] for s in T._rename_speakers(raw)] == ["Locuteur 1", "Locuteur 2", "Locuteur 1"]

    def test_segment_without_speaker_is_not_a_new_speaker(self, ui_lang):
        raw = [{"speaker": "A", "text": "1"}, {"text": "2"}, {"speaker": "B", "text": "3"}]
        assert [s["speaker"] for s in T._rename_speakers(raw)] == ["Locuteur 1", "Locuteur ?", "Locuteur 2"]

    def test_none_speaker_is_treated_as_missing(self, ui_lang):
        assert T._rename_speakers([{"speaker": None, "text": "x"}])[0]["speaker"] == "Locuteur ?"

    def test_only_unknown_segments(self, ui_lang):
        result = T._rename_speakers([{"text": "a"}, {"text": "b"}])
        assert [s["speaker"] for s in result] == ["Locuteur ?", "Locuteur ?"]

    def test_empty_list(self, ui_lang):
        assert T._rename_speakers([]) == []

    def test_input_is_not_modified_and_other_keys_are_kept(self, ui_lang):
        raw = [{"speaker": "SPEAKER_00", "text": "a", "start": 1.0}]
        result = T._rename_speakers(raw)
        assert raw[0]["speaker"] == "SPEAKER_00"
        assert result[0]["start"] == 1.0 and result[0] is not raw[0]

    def test_labels_follow_the_interface_language(self, ui_lang):
        ui_lang.load("en")
        result = T._rename_speakers([{"speaker": "A", "text": "x"}, {"text": "y"}])
        assert [s["speaker"] for s in result] == ["Speaker 1", "Speaker ?"]


class TestWriters:
    def test_txt_simple_one_line_per_segment(self, tmp_path):
        out = tmp_path / "out.txt"
        T._write_txt_simple(SEGMENTS, str(out))
        assert out.read_text(encoding="utf-8") == (
            "[00:00:00.000 --> 00:00:06.240] Dans le bouquin, non.\n"
            "[00:00:06.500 --> 00:00:11.100] Exactement.\n"
        )

    def test_txt_simple_empty(self, tmp_path):
        out = tmp_path / "out.txt"
        T._write_txt_simple([], str(out))
        assert out.read_text() == ""

    def test_txt_simple_keeps_accents(self, tmp_path):
        out = tmp_path / "out.txt"
        T._write_txt_simple([{"start": 0, "end": 1, "text": "  été à Noël  "}], str(out))
        assert out.read_text(encoding="utf-8").endswith("] été à Noël\n")

    def test_txt_speakers_format(self, tmp_path):
        out = tmp_path / "out.txt"
        T._write_txt_speakers(
            [{"start": 0.0, "end": 6.9, "text": "Bonjour.", "speaker": "Locuteur 1"}], str(out))
        # Les secondes sont tronquées (6,9 s → 00:00:06), comme sur une horloge
        assert out.read_text(encoding="utf-8") == "Locuteur 1 [00:00:00 - 00:00:06] : Bonjour.\n\n"

    def test_txt_speakers_requires_the_speaker_key(self, tmp_path):
        with pytest.raises(KeyError):
            T._write_txt_speakers([{"start": 0, "end": 1, "text": "x"}], str(tmp_path / "o.txt"))

    def test_srt_numbering_and_layout(self, tmp_path):
        out = tmp_path / "out.srt"
        T._write_srt(SEGMENTS, str(out), with_speakers=False)
        assert out.read_text(encoding="utf-8") == (
            "1\n00:00:00,000 --> 00:00:06,240\nDans le bouquin, non.\n\n"
            "2\n00:00:06,500 --> 00:00:11,100\nExactement.\n\n"
        )

    def test_srt_speaker_prefix(self, tmp_path):
        out = tmp_path / "out.srt"
        segments = [{"start": 0, "end": 1, "text": "Oui.", "speaker": "Locuteur 2"},
                    {"start": 1, "end": 2, "text": "Non."}]
        T._write_srt(segments, str(out), with_speakers=True)
        content = out.read_text(encoding="utf-8")
        assert "Locuteur 2 : Oui." in content and "\nNon.\n" in content

    def test_srt_ignores_speakers_when_not_requested(self, tmp_path):
        out = tmp_path / "out.srt"
        T._write_srt([{"start": 0, "end": 1, "text": "Oui.", "speaker": "L1"}], str(out), with_speakers=False)
        assert "L1" not in out.read_text()

    def test_srt_empty(self, tmp_path):
        out = tmp_path / "out.srt"
        T._write_srt([], str(out), with_speakers=True)
        assert out.read_text() == ""

    @pytest.mark.parametrize("data", [{"a": 1}, [1, 2]])
    def test_json_roundtrip(self, tmp_path, data):
        out = tmp_path / "out.json"
        T._write_json(data, str(out))
        assert json.loads(out.read_text(encoding="utf-8")) == data

    def test_json_does_not_escape_accents(self, tmp_path):
        out = tmp_path / "out.json"
        T._write_json({"texte": "é"}, str(out))
        assert "é" in out.read_text(encoding="utf-8")


class TestWriteOutputs:
    def test_writes_every_requested_format_next_to_the_source(self, tmp_path):
        source = tmp_path / "interview.mp3"
        T._write_outputs(SEGMENTS, {"raw": True}, str(source), "_base", ["txt", "srt", "json"], False)
        assert sorted(p.name for p in tmp_path.iterdir()) == [
            "interview_base.json", "interview_base.srt", "interview_base.txt"]
        assert json.loads((tmp_path / "interview_base.json").read_text()) == {"raw": True}

    def test_only_requested_formats(self, tmp_path):
        T._write_outputs(SEGMENTS, {}, str(tmp_path / "a.wav"), "_x", ["srt"], False)
        assert [p.name for p in tmp_path.iterdir()] == ["a_x.srt"]

    def test_no_format_writes_nothing(self, tmp_path):
        T._write_outputs(SEGMENTS, {}, str(tmp_path / "a.wav"), "_x", [], False)
        assert list(tmp_path.iterdir()) == []

    def test_unknown_format(self, tmp_path):
        with pytest.raises(KeyError):
            T._write_outputs(SEGMENTS, {}, str(tmp_path / "a.wav"), "_x", ["pdf"], False)

    def test_with_speakers_uses_the_speaker_layout(self, tmp_path):
        segments = [{"start": 0, "end": 1, "text": "Oui.", "speaker": "Locuteur 1"}]
        T._write_outputs(segments, segments, str(tmp_path / "a.wav"), "_d", ["txt", "srt"], True)
        assert (tmp_path / "a_d.txt").read_text(encoding="utf-8").startswith("Locuteur 1 [")
        assert "Locuteur 1 : Oui." in (tmp_path / "a_d.srt").read_text(encoding="utf-8")

    def test_json_receives_the_raw_data_not_the_segments(self, tmp_path):
        T._write_outputs(SEGMENTS, "BRUT", str(tmp_path / "a.wav"), "_x", ["json"], False)
        assert json.loads((tmp_path / "a_x.json").read_text()) == "BRUT"

    def test_source_name_with_dots_and_spaces(self, tmp_path):
        T._write_outputs(SEGMENTS, {}, str(tmp_path / "test video v2.final.mp4"), "_base", ["txt"], False)
        assert (tmp_path / "test video v2.final_base.txt").exists()


class TestFindFfmpeg:
    @pytest.mark.parametrize("system, binary", [("Linux", "ffmpeg"), ("Windows", "ffmpeg.exe")])
    def test_bundled_binary_is_preferred(self, tmp_path, monkeypatch, system, binary):
        monkeypatch.setattr(platform, "system", lambda: system)
        monkeypatch.setattr(T, "BASE_DIR", tmp_path)
        bundled = tmp_path / "ffmpeg" / system.lower() / binary
        bundled.parent.mkdir(parents=True)
        bundled.write_bytes(b"")
        assert T._find_ffmpeg() == str(bundled)

    def test_falls_back_to_path(self, tmp_path, monkeypatch):
        monkeypatch.setattr(T, "BASE_DIR", tmp_path)
        assert T._find_ffmpeg() == "ffmpeg"

    def test_empty_bundled_folder_does_not_count(self, tmp_path, monkeypatch):
        monkeypatch.setattr(platform, "system", lambda: "Linux")
        monkeypatch.setattr(T, "BASE_DIR", tmp_path)
        (tmp_path / "ffmpeg" / "linux").mkdir(parents=True)
        assert T._find_ffmpeg() == "ffmpeg"


@posix_only
class TestExtractAudio:
    def test_success_returns_an_existing_wav(self, tmp_path, fake_tmpdir):
        ffmpeg = make_fake_ffmpeg(tmp_path)
        result = T._extract_audio("/data/film.mp4", ffmpeg)
        assert result.endswith(".wav") and open(result, "rb").read() == b"RIFF"

    def test_failure_raises_and_removes_the_temporary_file(self, tmp_path, fake_tmpdir):
        ffmpeg = make_fake_ffmpeg(tmp_path, fail_always=True)
        with pytest.raises(RuntimeError, match="exit code 1"):
            T._extract_audio("/data/film.mp4", ffmpeg)
        assert list(fake_tmpdir.iterdir()) == []

    def test_error_message_has_the_stderr_tail_without_the_input_path(self, tmp_path, fake_tmpdir):
        ffmpeg = make_fake_ffmpeg(tmp_path, fail_always=True)
        with pytest.raises(RuntimeError) as info:
            T._extract_audio("/secret/dir/entretien.mp4", ffmpeg)
        message = str(info.value)
        assert "Invalid data found" in message and "<input>" in message
        assert "entretien" not in message and "/secret" not in message

    def test_chained_exception_does_not_leak_the_command_line(self, tmp_path, fake_tmpdir):
        ffmpeg = make_fake_ffmpeg(tmp_path, fail_always=True)
        with pytest.raises(RuntimeError) as info:
            T._extract_audio("/secret/dir/entretien.mp4", ffmpeg)
        assert info.value.__cause__ is None and info.value.__suppress_context__

    def test_stderr_is_limited_to_the_last_five_lines(self, tmp_path, fake_tmpdir):
        script = tmp_path / "noisy-ffmpeg"
        script.write_text('#!/bin/sh\nfor i in 1 2 3 4 5 6 7 8; do echo "ligne $i" >&2; done\nexit 3\n')
        script.chmod(0o755)
        with pytest.raises(RuntimeError) as info:
            T._extract_audio("/x/a.mp4", str(script))
        message = str(info.value)
        assert "ligne 8" in message and "ligne 4" in message and "ligne 3" not in message

    def test_missing_ffmpeg(self, tmp_path, fake_tmpdir):
        with pytest.raises(RuntimeError, match="not found"):
            T._extract_audio("/x/a.mp4", str(tmp_path / "absent"))
        assert list(fake_tmpdir.iterdir()) == []


class TestLoadModel:
    def test_first_load_on_cpu(self, monkeypatch):
        engine = FakeEngine(monkeypatch)
        messages = []
        T.Transcriber()._load_model("base", lambda m, p: messages.append((m, p)))
        assert engine.model_loads == [("base", "cpu", "int8")]
        assert messages == [("loading_model:base", 0.0)]

    def test_gpu_uses_float16(self, monkeypatch):
        engine = FakeEngine(monkeypatch, cuda=True)
        T.Transcriber()._load_model("base", lambda m, p: None)
        assert engine.model_loads == [("base", "cuda", "float16")]

    def test_same_model_is_not_reloaded(self, monkeypatch):
        engine = FakeEngine(monkeypatch)
        t, messages = T.Transcriber(), []
        t._load_model("base", lambda m, p: messages.append(m))
        t._load_model("base", lambda m, p: messages.append(m))
        assert len(engine.model_loads) == 1 and messages == ["loading_model:base"]

    def test_other_model_replaces_the_first_and_frees_gpu_memory(self, monkeypatch):
        engine = FakeEngine(monkeypatch, cuda=True)
        t = T.Transcriber()
        t._load_model("base", lambda m, p: None)
        t._load_model("small", lambda m, p: None)
        assert [m[0] for m in engine.model_loads] == ["base", "small"]
        assert engine.cuda_empty_cache_calls == 1

    def test_openai_whisper_fallback(self, monkeypatch):
        engine = FakeEngine(monkeypatch, openai=True)
        T.Transcriber()._load_model("base", lambda m, p: None)
        assert engine.openai_loads == ["base"] and engine.model_loads == []


class TestTranscribeKwargs:
    def _run(self, monkeypatch, language, **engine_options):
        engine = FakeEngine(monkeypatch, **engine_options)
        t = T.Transcriber()
        t._load_model("base", lambda m, p: None)
        t._transcribe("audio_fr.wav", language)
        return engine.transcribe_calls[-1][1]

    def test_whisperx_with_language(self, monkeypatch):
        assert self._run(monkeypatch, "fr") == {"language": "fr", "batch_size": 8}

    def test_whisperx_auto_detection_has_no_language(self, monkeypatch):
        assert self._run(monkeypatch, "") == {"batch_size": 8}

    def test_openai_whisper_has_no_batch_size(self, monkeypatch):
        assert self._run(monkeypatch, "en", openai=True) == {"language": "en"}


class TestAlignModelCache:
    def test_same_language_is_loaded_once(self, monkeypatch):
        engine = FakeEngine(monkeypatch)
        t = T.Transcriber()
        first = t._get_align_model("fr")
        assert t._get_align_model("fr") == first
        assert engine.align_loads == ["fr"]

    def test_language_change_reloads(self, monkeypatch):
        engine = FakeEngine(monkeypatch)
        t = T.Transcriber()
        t._get_align_model("fr")
        t._get_align_model("en")
        assert engine.align_loads == ["fr", "en"]

    def test_failed_load_raises(self, monkeypatch):
        FakeEngine(monkeypatch, align_fail=["xx"])
        with pytest.raises(ValueError, match="xx"):
            T.Transcriber()._get_align_model("xx")

    def test_failed_load_does_not_leave_a_stale_cache(self, monkeypatch):
        """Après l'échec d'une langue, la langue précédente doit être rechargée, pas servie à vide."""
        engine = FakeEngine(monkeypatch, align_fail=["xx"])
        t = T.Transcriber()
        t._get_align_model("fr")
        with pytest.raises(ValueError):
            t._get_align_model("xx")
        model, metadata = t._get_align_model("fr")
        assert model is not None and metadata is not None
        assert engine.align_loads == ["fr", "fr"]


class TestTryAlign:
    def _call(self, transcriber, result, language=""):
        messages = []
        aligned = transcriber._try_align(result, "audio_fr.wav", language, "/x/a.wav", 0.0, 1.0,
                                         lambda code, pct: messages.append(code))
        return aligned, messages

    def test_success_returns_the_aligned_sentences_with_the_language(self, monkeypatch):
        FakeEngine(monkeypatch)
        aligned, messages = self._call(T.Transcriber(), {"segments": [{"text": "x"}], "language": "fr"})
        assert aligned["language"] == "fr" and len(aligned["segments"]) == 3
        assert messages == ["aligning:a.wav"]

    def test_failure_returns_the_original_result_untouched(self, monkeypatch):
        FakeEngine(monkeypatch, align_error=LookupError("punkt_tab"))
        result = {"segments": [{"text": "x"}], "language": "fr"}
        aligned, messages = self._call(T.Transcriber(), result)
        assert aligned is result
        assert messages == ["aligning:a.wav", "align_unavailable:fr"]

    def test_model_failure_is_also_a_fallback(self, monkeypatch):
        FakeEngine(monkeypatch, align_fail=["xx"])
        result = {"segments": [], "language": "xx"}
        aligned, messages = self._call(T.Transcriber(), result)
        assert aligned is result and messages[-1] == "align_unavailable:xx"

    def test_requested_language_is_used_when_the_result_has_none(self, monkeypatch):
        FakeEngine(monkeypatch, align_error=RuntimeError("panne"))
        _, messages = self._call(T.Transcriber(), {"segments": []}, language="en")
        assert messages[-1] == "align_unavailable:en"


class TestReleaseDiarizationModels:
    def test_releases_everything_and_frees_gpu_memory(self, monkeypatch, model_setup_dirs):
        engine = FakeEngine(monkeypatch, cuda=True)
        populate_model_dir(model_setup_dirs)
        t = T.Transcriber()
        t._get_align_model("fr")
        t._get_diarizer()
        t._release_diarization_models()
        assert t._align_model is None and t._align_lang is None and t._diarizer is None
        assert engine.cuda_empty_cache_calls == 1

    def test_nothing_to_release_does_nothing(self, monkeypatch):
        engine = FakeEngine(monkeypatch, cuda=True)
        T.Transcriber()._release_diarization_models()
        assert engine.cuda_empty_cache_calls == 0

    def test_diarizer_is_loaded_once(self, monkeypatch, model_setup_dirs):
        engine = FakeEngine(monkeypatch)
        populate_model_dir(model_setup_dirs)
        t = T.Transcriber()
        assert t._get_diarizer() is t._get_diarizer()
        assert len(engine.diarizer_loads) == 1


class TestLoadDiarizationPipeline:
    def test_missing_model(self, model_setup_dirs):
        with pytest.raises(RuntimeError, match="not found"):
            T.Transcriber()._load_diarization_pipeline(object)

    def test_loads_from_the_local_folder(self, model_setup_dirs):
        populate_model_dir(model_setup_dirs)
        calls = []

        class Pipeline:
            def __init__(self, model_name, device):
                calls.append((model_name, device))

        t = T.Transcriber()
        t._device = "cuda"
        assert isinstance(t._load_diarization_pipeline(Pipeline), Pipeline)
        assert calls == [(str(model_setup_dirs.MODEL_DIR), "cuda")]

    def test_loading_error_is_wrapped_and_chained(self, model_setup_dirs):
        populate_model_dir(model_setup_dirs)

        class Broken:
            def __init__(self, model_name, device):
                raise OSError("poids illisibles")

        with pytest.raises(RuntimeError, match="Cannot load") as info:
            T.Transcriber()._load_diarization_pipeline(Broken)
        assert isinstance(info.value.__cause__, OSError)


class TestFreeMemory:
    def test_without_torch_loaded(self, monkeypatch):
        monkeypatch.delitem(sys.modules, "torch", raising=False)
        T.Transcriber._free_memory()  # ne doit ni lever ni importer torch
        assert "torch" not in sys.modules

    def test_empties_the_gpu_cache_when_cuda_is_available(self, monkeypatch):
        engine = FakeEngine(monkeypatch, cuda=True)
        T.Transcriber._free_memory()
        assert engine.cuda_empty_cache_calls == 1

    def test_does_not_touch_the_cache_without_cuda(self, monkeypatch):
        engine = FakeEngine(monkeypatch, cuda=False)
        T.Transcriber._free_memory()
        assert engine.cuda_empty_cache_calls == 0


def test_cancel_sets_the_flag():
    t = T.Transcriber()
    assert t._cancelled is False
    t.cancel()
    assert t._cancelled is True


def test_extension_sets_are_consistent():
    assert T.AUDIO_EXTENSIONS.isdisjoint(T.VIDEO_EXTENSIONS)
    assert T.ALL_EXTENSIONS == T.AUDIO_EXTENSIONS | T.VIDEO_EXTENSIONS
    assert all(ext.startswith(".") and ext == ext.lower() for ext in T.ALL_EXTENSIONS)
