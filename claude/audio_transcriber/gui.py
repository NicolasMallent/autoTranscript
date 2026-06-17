"""
Interface graphique de l'application (Tkinter).
"""
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText
from typing import Optional

import config
import engine
import model_setup


class TranscriptionApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Transcription audio avec identification des locuteurs")
        self.root.geometry("780x620")
        self.root.minsize(620, 480)

        self.audio_path: Optional[str] = None
        self.segments: list = []
        self.message_queue: queue.Queue = queue.Queue()
        self.is_running = False

        self._build_widgets()
        self._poll_queue()

    # ------------------------------------------------------------------ UI

    def _build_widgets(self) -> None:
        padding = {"padx": 10, "pady": 6}

        # --- Sélection du fichier ---
        file_frame = ttk.LabelFrame(self.root, text="Fichier audio")
        file_frame.pack(fill="x", **padding)

        self.file_label = ttk.Label(file_frame, text="Aucun fichier sélectionné", foreground="grey")
        self.file_label.pack(side="left", padx=10, pady=10, fill="x", expand=True)

        ttk.Button(file_frame, text="Choisir un fichier…", command=self._choose_file).pack(
            side="right", padx=10, pady=10
        )

        # --- Options ---
        options_frame = ttk.LabelFrame(self.root, text="Options")
        options_frame.pack(fill="x", **padding)

        ttk.Label(options_frame, text="Précision du modèle :").grid(row=0, column=0, sticky="w", padx=10, pady=6)
        self.model_size_var = tk.StringVar(value=config.DEFAULT_WHISPER_MODEL)
        ttk.Combobox(
            options_frame,
            textvariable=self.model_size_var,
            values=config.WHISPER_MODEL_SIZES,
            state="readonly",
            width=12,
        ).grid(row=0, column=1, sticky="w", padx=10, pady=6)

        ttk.Label(options_frame, text="Langue :").grid(row=0, column=2, sticky="w", padx=10, pady=6)
        self.language_var = tk.StringVar(value="Détection automatique")
        ttk.Combobox(
            options_frame,
            textvariable=self.language_var,
            values=list(config.LANGUAGES.keys()),
            state="readonly",
            width=18,
        ).grid(row=0, column=3, sticky="w", padx=10, pady=6)

        ttk.Label(options_frame, text="Nombre de locuteurs (si connu) :").grid(
            row=1, column=0, columnspan=2, sticky="w", padx=10, pady=6
        )
        speakers_frame = ttk.Frame(options_frame)
        speakers_frame.grid(row=1, column=2, columnspan=2, sticky="w", padx=10, pady=6)
        self.min_speakers_var = tk.StringVar()
        self.max_speakers_var = tk.StringVar()
        ttk.Label(speakers_frame, text="min").pack(side="left")
        ttk.Spinbox(speakers_frame, from_=0, to=20, width=4, textvariable=self.min_speakers_var).pack(
            side="left", padx=(4, 12)
        )
        ttk.Label(speakers_frame, text="max").pack(side="left")
        ttk.Spinbox(speakers_frame, from_=0, to=20, width=4, textvariable=self.max_speakers_var).pack(
            side="left", padx=4
        )

        # --- Action ---
        action_frame = ttk.Frame(self.root)
        action_frame.pack(fill="x", **padding)

        self.start_button = ttk.Button(action_frame, text="Transcrire", command=self._start_transcription)
        self.start_button.pack(side="left")

        self.status_label = ttk.Label(action_frame, text="Prêt.")
        self.status_label.pack(side="left", padx=12)

        self.progress_bar = ttk.Progressbar(self.root, mode="determinate", maximum=100)
        self.progress_bar.pack(fill="x", **padding)

        # --- Résultats ---
        result_frame = ttk.LabelFrame(self.root, text="Résultat")
        result_frame.pack(fill="both", expand=True, **padding)

        self.result_text = ScrolledText(result_frame, wrap="word", state="disabled")
        self.result_text.pack(fill="both", expand=True, padx=8, pady=8)

        export_frame = ttk.Frame(self.root)
        export_frame.pack(fill="x", **padding)

        self.export_txt_button = ttk.Button(
            export_frame, text="Exporter en .txt", command=self._export_txt, state="disabled"
        )
        self.export_txt_button.pack(side="left")

        self.export_srt_button = ttk.Button(
            export_frame, text="Exporter en .srt", command=self._export_srt, state="disabled"
        )
        self.export_srt_button.pack(side="left", padx=8)

    # ------------------------------------------------------------- Actions

    def _choose_file(self) -> None:
        path = filedialog.askopenfilename(
            title="Choisir un fichier audio",
            filetypes=[
                ("Fichiers audio", "*.wav *.mp3 *.m4a *.flac *.ogg *.wma *.aac"),
                ("Tous les fichiers", "*.*"),
            ],
        )
        if path:
            self.audio_path = path
            self.file_label.config(text=Path(path).name, foreground="black")

    def _start_transcription(self) -> None:
        if self.is_running:
            return
        if not self.audio_path:
            messagebox.showwarning("Fichier manquant", "Choisis d'abord un fichier audio.")
            return

        self.is_running = True
        self.start_button.config(state="disabled")
        self.export_txt_button.config(state="disabled")
        self.export_srt_button.config(state="disabled")
        self._set_result_text("")
        self.progress_bar["value"] = 0

        min_speakers = int(self.min_speakers_var.get()) if self.min_speakers_var.get().strip() else None
        max_speakers = int(self.max_speakers_var.get()) if self.max_speakers_var.get().strip() else None
        language_code = config.LANGUAGES.get(self.language_var.get(), "")
        whisper_model_size = self.model_size_var.get()

        thread = threading.Thread(
            target=self._run_pipeline,
            args=(self.audio_path, whisper_model_size, language_code, min_speakers, max_speakers),
            daemon=True,
        )
        thread.start()

    def _run_pipeline(
        self,
        audio_path: str,
        whisper_model_size: str,
        language_code: str,
        min_speakers: Optional[int],
        max_speakers: Optional[int],
    ) -> None:
        def progress_callback(message: str, fraction: float) -> None:
            self.message_queue.put(("progress", message, fraction))

        try:
            progress_callback("Préparation du modèle de diarisation…", 0.0)
            model_dir = model_setup.ensure_model(progress_callback=progress_callback)

            segments = engine.transcribe_and_diarize(
                audio_path=audio_path,
                model_dir=model_dir,
                whisper_model_size=whisper_model_size,
                language=language_code,
                min_speakers=min_speakers,
                max_speakers=max_speakers,
                progress_callback=progress_callback,
            )
            self.message_queue.put(("done", segments))
        except Exception as exc:  # noqa: BLE001 - on veut afficher toute erreur à l'utilisateur
            self.message_queue.put(("error", str(exc)))

    def _poll_queue(self) -> None:
        try:
            while True:
                item = self.message_queue.get_nowait()
                kind = item[0]
                if kind == "progress":
                    _, message, fraction = item
                    self.status_label.config(text=message)
                    self.progress_bar["value"] = max(0, min(100, fraction * 100))
                elif kind == "done":
                    _, segments = item
                    self._on_transcription_done(segments)
                elif kind == "error":
                    _, error_message = item
                    self._on_transcription_error(error_message)
        except queue.Empty:
            pass
        self.root.after(100, self._poll_queue)

    def _on_transcription_done(self, segments: list) -> None:
        self.segments = segments
        self._set_result_text(engine.segments_to_text(segments))
        self.status_label.config(text="Terminé.")
        self.progress_bar["value"] = 100
        self.start_button.config(state="normal")
        self.export_txt_button.config(state="normal")
        self.export_srt_button.config(state="normal")
        self.is_running = False

    def _on_transcription_error(self, error_message: str) -> None:
        self.status_label.config(text="Erreur.")
        self.start_button.config(state="normal")
        self.is_running = False
        messagebox.showerror("Erreur pendant la transcription", error_message)

    # ------------------------------------------------------------- Export

    def _set_result_text(self, text: str) -> None:
        self.result_text.config(state="normal")
        self.result_text.delete("1.0", "end")
        self.result_text.insert("1.0", text)
        self.result_text.config(state="disabled")

    def _export_txt(self) -> None:
        self._export(engine.segments_to_text(self.segments), default_ext=".txt", file_type=("Fichier texte", "*.txt"))

    def _export_srt(self) -> None:
        self._export(engine.segments_to_srt(self.segments), default_ext=".srt", file_type=("Sous-titres", "*.srt"))

    def _export(self, content: str, default_ext: str, file_type: tuple) -> None:
        path = filedialog.asksaveasfilename(defaultextension=default_ext, filetypes=[file_type])
        if not path:
            return
        Path(path).write_text(content, encoding="utf-8")
        messagebox.showinfo("Export terminé", f"Fichier enregistré : {path}")


def run() -> None:
    root = tk.Tk()
    TranscriptionApp(root)
    root.mainloop()
