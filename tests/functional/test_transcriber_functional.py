"""
Tests fonctionnels de app/transcriber.py : scénarios utilisateur complets.

``Transcriber.transcribe`` s'exécute en vrai (lecture du dossier, ffmpeg, écriture des fichiers,
callbacks de progression) ; seuls whisperx, torch, le réseau et ffmpeg sont remplacés par des
faux (voir helpers.py).
"""
import json
import logging

import pytest

import model_setup
import transcriber as T
from helpers import (FakeEngine, ReleaseServer, make_fake_ffmpeg, make_model_zip,
                     populate_model_dir, posix_only, write_media)

THREE_SENTENCES = (
    "[00:00:18.796 --> 00:00:25.000] Premiere phrase.\n"
    "[00:00:25.500 --> 00:00:31.000] Deuxieme phrase ?\n"
    "[00:00:32.000 --> 00:00:43.231] Troisieme.\n"
)
CHUNK_LINE = "[00:00:18.796 --> 00:00:43.231] Premiere phrase. Deuxieme phrase ? Troisieme.\n"


def run(transcriber, path, *, language="", formats=("txt", "srt", "json"), diarize=False,
        min_speakers=None, max_speakers=None, model="base"):
    """Lance ``transcribe`` et renvoie la liste des (code, progression) reçus."""
    received = []
    transcriber.transcribe(
        str(path), model, language, list(formats), diarize, min_speakers, max_speakers,
        lambda code, pct: received.append((code, pct)),
    )
    return received


def codes(received):
    return [code for code, _ in received]


def names(directory):
    return sorted(p.name for p in directory.iterdir())


class TestSimpleMode:
    def test_sentence_level_timestamps(self, monkeypatch, tmp_path):
        """Régression : le mode simple aligne les mots et écrit une ligne par phrase."""
        engine = FakeEngine(monkeypatch)
        (source,) = write_media(tmp_path, "a_fr.wav")
        received = run(T.Transcriber(), source)
        assert (tmp_path / "a_fr_base.txt").read_text(encoding="utf-8") == THREE_SENTENCES
        srt = (tmp_path / "a_fr_base.srt").read_text(encoding="utf-8")
        assert srt.count(" --> ") == 3 and "00:00:25,500 --> 00:00:31,000\nDeuxieme phrase ?" in srt
        data = json.loads((tmp_path / "a_fr_base.json").read_text(encoding="utf-8"))
        assert data["language"] == "fr" and len(data["segments"]) == 3
        assert codes(received) == ["loading_model:base", "processing_file:a_fr.wav", "aligning:a_fr.wav",
                                   "done_file:a_fr.wav", "all_done"]
        assert engine.align_loads == ["fr"] and engine.diarizer_loads == []

    def test_outputs_are_named_after_the_model(self, monkeypatch, tmp_path):
        FakeEngine(monkeypatch)
        (source,) = write_media(tmp_path, "entretien.wav")
        run(T.Transcriber(), source, model="large-v3", formats=["txt"], language="fr")
        assert "entretien_large-v3.txt" in names(tmp_path)

    def test_only_requested_formats_are_written(self, monkeypatch, tmp_path):
        FakeEngine(monkeypatch)
        (source,) = write_media(tmp_path, "a_fr.wav")
        run(T.Transcriber(), source, formats=["srt"])
        assert names(tmp_path) == ["a_fr.wav", "a_fr_base.srt"]

    def test_language_used_for_alignment_is_the_detected_one(self, monkeypatch, tmp_path):
        engine = FakeEngine(monkeypatch)
        (source,) = write_media(tmp_path, "c_en.wav")
        run(T.Transcriber(), source)
        assert engine.align_loads == ["en"] and "language" not in engine.transcribe_calls[0][1]

    def test_forced_language_is_passed_to_whisper(self, monkeypatch, tmp_path):
        engine = FakeEngine(monkeypatch)
        (source,) = write_media(tmp_path, "c_en.wav")
        run(T.Transcriber(), source, language="fr")
        assert engine.transcribe_calls[0][1]["language"] == "fr"
        assert engine.align_loads == ["fr"]

    def test_alignment_failure_falls_back_to_whisper_segments(self, monkeypatch, tmp_path):
        FakeEngine(monkeypatch, align_fail=["xx"])
        (source,) = write_media(tmp_path, "b_xx.wav")
        received = run(T.Transcriber(), source)
        assert (tmp_path / "b_xx_base.txt").read_text(encoding="utf-8") == CHUNK_LINE
        assert "align_unavailable:xx" in codes(received)
        assert codes(received)[-1] == "all_done"   # un repli n'est pas une erreur
        data = json.loads((tmp_path / "b_xx_base.json").read_text(encoding="utf-8"))
        assert data["language"] == "xx" and len(data["segments"]) == 1

    def test_alignment_failure_is_logged_with_its_cause(self, monkeypatch, tmp_path, caplog):
        FakeEngine(monkeypatch, align_fail=["xx"])
        (source,) = write_media(tmp_path, "b_xx.wav")
        with caplog.at_level(logging.WARNING, logger="autotranscript.transcriber"):
            run(T.Transcriber(), source)
        assert "Alignement impossible" in caplog.text and "No default align-model" in caplog.text

    def test_a_later_file_in_a_supported_language_still_gets_aligned(self, monkeypatch, tmp_path):
        """Régression : après l'échec d'une langue, la suivante ne doit pas hériter d'un cache vide."""
        engine = FakeEngine(monkeypatch, align_fail=["xx"])
        write_media(tmp_path, "a_fr.wav", "b_xx.wav", "c_fr.wav")
        received = run(T.Transcriber(), tmp_path)
        assert codes(received).count("align_unavailable:xx") == 1
        assert (tmp_path / "c_fr_base.txt").read_text(encoding="utf-8") == THREE_SENTENCES
        assert engine.align_loads == ["fr", "fr"]

    def test_openai_whisper_fallback_has_chunk_level_timestamps(self, monkeypatch, tmp_path):
        engine = FakeEngine(monkeypatch, openai=True)
        (source,) = write_media(tmp_path, "a_fr.wav")
        received = run(T.Transcriber(), source, formats=["txt"])
        assert (tmp_path / "a_fr_base.txt").read_text(encoding="utf-8") == CHUNK_LINE
        assert not any(code.startswith("aligning") for code in codes(received))
        assert engine.openai_loads == ["base"] and engine.align_loads == []

    def test_diarization_is_ignored_without_whisperx(self, monkeypatch, tmp_path):
        FakeEngine(monkeypatch, openai=True)

        def forbidden(callback=None):
            raise AssertionError("le modèle de diarisation ne doit pas être téléchargé")
        monkeypatch.setattr(model_setup, "ensure_model", forbidden)
        (source,) = write_media(tmp_path, "a_fr.wav")
        run(T.Transcriber(), source, diarize=True, formats=["txt"])
        assert "a_fr_base.txt" in names(tmp_path) and "a_fr_base_diarized.txt" not in names(tmp_path)


class TestFolderHandling:
    def test_folder_is_processed_in_alphabetical_order_and_non_media_is_ignored(self, monkeypatch, tmp_path):
        FakeEngine(monkeypatch)
        write_media(tmp_path, "b_fr.mp3", "a_fr.wav", "notes.txt", "Z_fr.WAV", "image.png")
        received = run(T.Transcriber(), tmp_path, formats=["txt"])
        processed = [c.split(":", 1)[1] for c in codes(received) if c.startswith("processing_file:")]
        assert processed == ["Z_fr.WAV", "a_fr.wav", "b_fr.mp3"]   # ordre des chaînes : majuscules d'abord
        assert not (tmp_path / "notes_base.txt").exists()

    def test_extension_is_case_insensitive(self, monkeypatch, tmp_path):
        FakeEngine(monkeypatch)
        (source,) = write_media(tmp_path, "Interview_fr.MP3")
        assert codes(run(T.Transcriber(), source, formats=["txt"]))[-1] == "all_done"

    def test_subfolders_are_not_explored(self, monkeypatch, tmp_path):
        FakeEngine(monkeypatch)
        (tmp_path / "sous").mkdir()
        write_media(tmp_path / "sous", "a_fr.wav")
        assert codes(run(T.Transcriber(), tmp_path)) == ["no_audio_found"]

    @pytest.mark.parametrize("files", [[], ["notes.txt", "photo.jpg"]])
    def test_nothing_to_transcribe(self, monkeypatch, tmp_path, files):
        engine = FakeEngine(monkeypatch)
        write_media(tmp_path, *files)
        assert run(T.Transcriber(), tmp_path) == [("no_audio_found", 1.0)]
        assert engine.model_loads == []

    def test_progress_never_goes_backwards_nor_above_one(self, monkeypatch, tmp_path):
        FakeEngine(monkeypatch)
        write_media(tmp_path, "a_fr.wav", "b_fr.wav", "c_fr.wav", "d_fr.wav")
        received = run(T.Transcriber(), tmp_path, formats=["txt"])
        percents = [pct for _, pct in received]
        assert percents == sorted(percents) and max(percents) == 1.0
        done = [pct for code, pct in received if code.startswith("done_file:")]
        assert done == pytest.approx([0.25, 0.5, 0.75, 1.0])


class TestDiarization:
    @pytest.fixture
    def ready_model(self, model_setup_dirs):
        populate_model_dir(model_setup_dirs)
        return model_setup_dirs

    def test_batch_with_diarization(self, monkeypatch, tmp_path, ready_model, ui_lang):
        engine = FakeEngine(monkeypatch)
        write_media(tmp_path, "a_fr.wav", "b_fr.wav", "c_en.wav")
        received = run(T.Transcriber(), tmp_path, formats=["txt", "srt", "json"], diarize=True,
                       min_speakers=2, max_speakers=4)

        assert (tmp_path / "a_fr_base_diarized.txt").read_text(encoding="utf-8") == (
            "Locuteur 1 [00:00:18 - 00:00:25] :  Premiere phrase.\n\n"
            "Locuteur 2 [00:00:25 - 00:00:31] : Deuxieme phrase ?\n\n"
            "Locuteur ? [00:00:32 - 00:00:43] : Troisieme.\n\n"
        )
        assert "Locuteur 2 : Deuxieme phrase ?" in (tmp_path / "a_fr_base_diarized.srt").read_text(encoding="utf-8")
        segments = json.loads((tmp_path / "c_en_base_diarized.json").read_text(encoding="utf-8"))
        assert [s.get("speaker") for s in segments] == ["Locuteur 1", "Locuteur 2", "Locuteur ?"]
        assert not [n for n in names(tmp_path) if n.endswith("_base.txt")]   # pas de sortie « simple »

        # chargements : un modèle Whisper, un alignement par langue, une seule pipeline de diarisation
        assert len(engine.model_loads) == 1
        assert engine.align_loads == ["fr", "en"]
        assert engine.diarizer_loads == [(str(ready_model.MODEL_DIR), "cpu")]
        assert all(call == {"min_speakers": 2, "max_speakers": 4} for call in engine.diarize_calls)
        assert codes(received)[-1] == "all_done"

    def test_speaker_labels_follow_the_interface_language(self, monkeypatch, tmp_path, ready_model, ui_lang):
        FakeEngine(monkeypatch)
        ui_lang.load("en")
        (source,) = write_media(tmp_path, "a_fr.wav")
        run(T.Transcriber(), source, diarize=True, formats=["txt"])
        content = (tmp_path / "a_fr_base_diarized.txt").read_text(encoding="utf-8")
        assert "Speaker 1" in content and "Speaker ?" in content and "Locuteur" not in content

    def test_diarization_is_requested_explicitly(self, monkeypatch, tmp_path, ready_model, ui_lang):
        engine = FakeEngine(monkeypatch)
        (source,) = write_media(tmp_path, "a_fr.wav")
        run(T.Transcriber(), source, diarize=False, formats=["txt"])
        assert engine.diarizer_loads == [] and "a_fr_base_diarized.txt" not in names(tmp_path)

    def test_aligner_and_diarizer_are_released_after_each_batch(self, monkeypatch, tmp_path, ready_model, ui_lang):
        engine = FakeEngine(monkeypatch)
        write_media(tmp_path, "a_fr.wav")
        t = T.Transcriber()
        run(t, tmp_path, diarize=True, formats=["txt"])
        assert t._diarizer is None and t._align_model is None
        run(t, tmp_path, diarize=True, formats=["txt"])
        assert len(engine.model_loads) == 1                 # Whisper reste chargé
        assert engine.align_loads == ["fr", "fr"] and len(engine.diarizer_loads) == 2

    def test_alignment_failure_fails_only_that_file(self, monkeypatch, tmp_path, ready_model, ui_lang):
        engine = FakeEngine(monkeypatch, align_fail=["xx"])
        write_media(tmp_path, "a_fr.wav", "b_xx.wav", "c_fr.wav")
        received = run(T.Transcriber(), tmp_path, diarize=True, formats=["txt"])
        errors = [c for c in codes(received) if c.startswith("error:")]
        assert len(errors) == 1 and errors[0].startswith("error:b_xx.wav")
        assert "a_fr_base_diarized.txt" in names(tmp_path) and "c_fr_base_diarized.txt" in names(tmp_path)
        assert "b_xx_base_diarized.txt" not in names(tmp_path)
        assert codes(received)[-1] == "done_with_errors:1/3"
        assert engine.align_loads == ["fr", "fr"]

    def test_model_is_downloaded_before_whisper_is_loaded(self, monkeypatch, tmp_path, model_setup_dirs, ui_lang):
        engine = FakeEngine(monkeypatch)
        server = ReleaseServer(monkeypatch, make_model_zip())
        (source,) = write_media(tmp_path, "a_fr.wav")
        received = codes(run(T.Transcriber(), source, diarize=True, formats=["txt"]))
        assert received.index("diarization_model_ready") < received.index("loading_model:base")
        assert len(server.urls) == 2 and model_setup_dirs.is_model_ready()
        assert engine.diarizer_loads == [(str(model_setup_dirs.MODEL_DIR), "cpu")]

    def test_download_failure_stops_before_any_model_is_loaded(self, monkeypatch, tmp_path, model_setup_dirs, ui_lang):
        engine = FakeEngine(monkeypatch)

        def offline(callback=None):
            raise RuntimeError("Cannot download the diarization model")
        monkeypatch.setattr(model_setup, "ensure_model", offline)
        (source,) = write_media(tmp_path, "a_fr.wav")
        with pytest.raises(RuntimeError, match="Cannot download"):
            run(T.Transcriber(), source, diarize=True)
        assert engine.model_loads == [] and names(tmp_path) == ["a_fr.wav"]

    def test_cancel_while_preparing_the_model(self, monkeypatch, tmp_path, ui_lang):
        engine = FakeEngine(monkeypatch)
        t = T.Transcriber()
        monkeypatch.setattr(model_setup, "ensure_model", lambda callback=None: t.cancel())
        (source,) = write_media(tmp_path, "a_fr.wav")
        assert run(t, source, diarize=True) == []
        assert engine.model_loads == []


class TestBatchRobustness:
    @posix_only
    def test_failing_video_does_not_stop_the_batch(self, monkeypatch, tmp_path, fake_tmpdir):
        FakeEngine(monkeypatch)
        media = tmp_path / "media"
        media.mkdir()
        write_media(media, "a_fr.wav", "bad_fr.mp4", "c_fr.mp3")
        monkeypatch.setattr(T, "_find_ffmpeg", lambda: make_fake_ffmpeg(tmp_path, fail_if_contains="bad"))
        received = run(T.Transcriber(), media, formats=["txt"], language="fr")

        errors = [c for c in codes(received) if c.startswith("error:")]
        assert len(errors) == 1 and errors[0].startswith("error:bad_fr.mp4 — ffmpeg failed")
        assert "a_fr_base.txt" in names(media) and "c_fr_base.txt" in names(media)
        assert "bad_fr_base.txt" not in names(media)
        assert codes(received)[-1] == "done_with_errors:1/3" and "all_done" not in codes(received)
        assert list(fake_tmpdir.iterdir()) == []

    @posix_only
    def test_video_is_transcribed_from_the_extracted_audio(self, monkeypatch, tmp_path, fake_tmpdir):
        engine = FakeEngine(monkeypatch)
        media = tmp_path / "media"
        media.mkdir()
        (video,) = write_media(media, "film.mp4")
        monkeypatch.setattr(T, "_find_ffmpeg", lambda: make_fake_ffmpeg(tmp_path))
        received = run(T.Transcriber(), video, formats=["txt"], language="fr")
        audio_used = engine.transcribe_calls[0][0]
        assert audio_used.endswith(".wav") and audio_used.startswith(str(fake_tmpdir))
        assert "extracting_audio:film.mp4" in codes(received)
        assert "film_base.txt" in names(media)           # la sortie porte le nom de la vidéo
        assert list(fake_tmpdir.iterdir()) == []          # le WAV temporaire est supprimé

    @posix_only
    def test_temporary_audio_is_removed_when_transcription_fails(self, monkeypatch, tmp_path, fake_tmpdir):
        FakeEngine(monkeypatch)
        media = tmp_path / "media"
        media.mkdir()
        (video,) = write_media(media, "boom_fr.mp4")
        monkeypatch.setattr(T, "_find_ffmpeg", lambda: make_fake_ffmpeg(tmp_path))
        t = T.Transcriber()

        def explode(audio, language):
            raise RuntimeError("whisper a planté")
        monkeypatch.setattr(t, "_transcribe", explode)
        received = run(t, video, language="fr")
        assert any(c.startswith("error:boom_fr.mp4 — whisper a planté") for c in codes(received))
        assert list(fake_tmpdir.iterdir()) == []

    def test_every_file_failing(self, monkeypatch, tmp_path):
        FakeEngine(monkeypatch)
        write_media(tmp_path, "a_fr.wav", "b_fr.wav")
        t = T.Transcriber()

        def explode(audio, language):
            raise RuntimeError("panne")
        monkeypatch.setattr(t, "_transcribe", explode)
        received = codes(run(t, tmp_path))
        assert received[-1] == "done_with_errors:2/2"
        assert sum(c.startswith("error:") for c in received) == 2 and "all_done" not in received

    def test_failure_is_logged_with_a_traceback_but_without_the_file_name(self, monkeypatch, tmp_path, caplog):
        FakeEngine(monkeypatch)
        (source,) = write_media(tmp_path, "secret_entretien_fr.wav")
        t = T.Transcriber()

        def explode(audio, language):
            raise RuntimeError("panne")
        monkeypatch.setattr(t, "_transcribe", explode)
        with caplog.at_level(logging.INFO, logger="autotranscript.transcriber"):
            run(t, source)
        assert "Traceback" in caplog.text or "RuntimeError: panne" in caplog.text
        assert "Fichier 1/1 (.wav)" in caplog.text
        assert "secret_entretien" not in caplog.text

    def test_whisper_model_is_reused_between_runs_and_replaced_when_it_changes(self, monkeypatch, tmp_path):
        engine = FakeEngine(monkeypatch)
        (source,) = write_media(tmp_path, "a_fr.wav")
        t = T.Transcriber()
        run(t, source, formats=["txt"])
        run(t, source, formats=["txt"])
        run(t, source, formats=["txt"], model="small")
        assert [m[0] for m in engine.model_loads] == ["base", "small"]


class TestCancellation:
    def test_cancel_after_the_first_file(self, monkeypatch, tmp_path):
        FakeEngine(monkeypatch)
        write_media(tmp_path, "a_fr.wav", "b_fr.wav", "c_fr.wav")
        t, received = T.Transcriber(), []

        def callback(code, pct):
            received.append(code)
            if code.startswith("done_file:"):
                t.cancel()
        t.transcribe(str(tmp_path), "base", "", ["txt"], False, None, None, callback)
        assert "a_fr_base.txt" in names(tmp_path)
        assert "b_fr_base.txt" not in names(tmp_path) and "c_fr_base.txt" not in names(tmp_path)
        assert "all_done" not in received and not any(c.startswith("done_with_errors") for c in received)

    def test_models_are_released_after_a_cancellation(self, monkeypatch, tmp_path, model_setup_dirs, ui_lang):
        FakeEngine(monkeypatch)
        populate_model_dir(model_setup_dirs)
        write_media(tmp_path, "a_fr.wav", "b_fr.wav")
        t = T.Transcriber()

        def callback(code, pct):
            if code.startswith("done_file:"):
                t.cancel()
        t.transcribe(str(tmp_path), "base", "", ["txt"], True, None, None, callback)
        assert t._diarizer is None and t._align_model is None

    def test_a_new_run_starts_clean_after_a_cancellation(self, monkeypatch, tmp_path):
        FakeEngine(monkeypatch)
        write_media(tmp_path, "a_fr.wav", "b_fr.wav")
        t = T.Transcriber()
        t.cancel()
        received = codes(run(t, tmp_path, formats=["txt"]))
        assert received[-1] == "all_done" and "b_fr_base.txt" in names(tmp_path)
