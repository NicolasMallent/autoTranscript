import json
import os
import queue
import threading
import tkinter as tk
import webbrowser
from tkinter import filedialog, messagebox

import customtkinter as ctk

import i18n as i18n_mod
from transcriber import Transcriber

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CONFIG_PATH = os.path.join(os.path.expanduser("~"), ".autotranscript", "config.json")
_REPO_URL = "https://github.com/NicolasMallent/autoTranscript"

_AUTHORS = [
    "Cécile de Hosson (UPCité - LDAR)",
    "Sylviane Pompéï (UPCité - LDAR)",
    "Pierre Andrieu (UPCité - LDAR)",
]
_CONTRIBUTOR = "Nicolas Mallent (Ingénieur R&D Robotique)"
_VERSION = "2.0.0"

WHISPER_LANGUAGES = {
    "whisper_lang_french": "French",
    "whisper_lang_english": "English",
    "whisper_lang_auto": "auto",
}


def _load_models() -> list[dict]:
    path = os.path.join(_BASE_DIR, "models.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _load_config() -> dict:
    if os.path.exists(_CONFIG_PATH):
        with open(_CONFIG_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {"lang": "fr", "last_model": "base", "last_folder": ""}


def _save_config(cfg: dict) -> None:
    os.makedirs(os.path.dirname(_CONFIG_PATH), exist_ok=True)
    with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


class App(ctk.CTk):
    def __init__(self):
        super().__init__()

        self._config = _load_config()
        i18n_mod.load(self._config.get("lang", "fr"))
        self._models = _load_models()
        self._transcriber = Transcriber()
        self._queue: queue.Queue = queue.Queue()
        self._running = False
        self._selected_path = tk.StringVar(value="")

        ctk.set_appearance_mode("system")
        ctk.set_default_color_theme("blue")

        self.title("AutoTranscript")
        self.minsize(620, 540)
        self.resizable(True, True)

        self._build_ui()
        self._poll_queue()

    def _build_ui(self):
        self._tabview = ctk.CTkTabview(self)
        self._tabview.pack(fill="both", expand=True, padx=12, pady=12)

        self._tab_transcription = self._tabview.add(i18n_mod.t("tab_transcription"))
        self._tab_settings = self._tabview.add(i18n_mod.t("tab_settings"))
        self._tab_about = self._tabview.add(i18n_mod.t("tab_about"))

        self._build_transcription_tab(self._tab_transcription)
        self._build_settings_tab(self._tab_settings)
        self._build_about_tab(self._tab_about)

    def _build_transcription_tab(self, parent):
        parent.columnconfigure(1, weight=1)

        row = 0

        # --- Mode file/folder ---
        self._mode_var = tk.StringVar(value="file")
        ctk.CTkLabel(parent, text="").grid(row=row, column=0, pady=(8, 0))
        row += 1

        mode_frame = ctk.CTkFrame(parent, fg_color="transparent")
        mode_frame.grid(row=row, column=0, columnspan=3, sticky="w", padx=12)
        self._rb_file = ctk.CTkRadioButton(
            mode_frame,
            text=i18n_mod.t("mode_file"),
            variable=self._mode_var,
            value="file",
            command=self._on_mode_change,
        )
        self._rb_file.pack(side="left", padx=(0, 16))
        self._rb_folder = ctk.CTkRadioButton(
            mode_frame,
            text=i18n_mod.t("mode_folder"),
            variable=self._mode_var,
            value="folder",
            command=self._on_mode_change,
        )
        self._rb_folder.pack(side="left")
        row += 1

        # --- Path selector ---
        path_frame = ctk.CTkFrame(parent, fg_color="transparent")
        path_frame.grid(row=row, column=0, columnspan=3, sticky="ew", padx=12, pady=(6, 0))
        path_frame.columnconfigure(0, weight=1)

        self._path_entry = ctk.CTkEntry(path_frame, textvariable=self._selected_path, state="readonly")
        self._path_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))

        self._select_btn = ctk.CTkButton(
            path_frame, text=i18n_mod.t("select_file"), width=140, command=self._on_select
        )
        self._select_btn.grid(row=0, column=1)
        row += 1

        # --- Model ---
        ctk.CTkLabel(parent, text=i18n_mod.t("model_label")).grid(
            row=row, column=0, sticky="w", padx=12, pady=(14, 0)
        )
        model_ids = [m["id"] for m in self._models]
        model_labels = [
            f"{m['id']}  ({m['size']}) — {m[i18n_mod.current_lang()]}" for m in self._models
        ]
        default_model = self._config.get("last_model", "base")
        default_idx = model_ids.index(default_model) if default_model in model_ids else 1
        self._model_var = tk.StringVar(value=model_labels[default_idx])
        self._model_combo = ctk.CTkComboBox(
            parent, values=model_labels, variable=self._model_var, state="readonly", width=380
        )
        self._model_combo.grid(row=row, column=1, columnspan=2, sticky="w", padx=12, pady=(14, 0))
        row += 1

        # --- Whisper language ---
        ctk.CTkLabel(parent, text=i18n_mod.t("language_label")).grid(
            row=row, column=0, sticky="w", padx=12, pady=(10, 0)
        )
        lang_keys = list(WHISPER_LANGUAGES.keys())
        lang_labels = [i18n_mod.t(k) for k in lang_keys]
        self._whisper_lang_var = tk.StringVar(value=lang_labels[0])
        self._lang_combo = ctk.CTkComboBox(
            parent, values=lang_labels, variable=self._whisper_lang_var, state="readonly", width=220
        )
        self._lang_combo.grid(row=row, column=1, sticky="w", padx=12, pady=(10, 0))
        row += 1

        # --- Output formats ---
        ctk.CTkLabel(parent, text=i18n_mod.t("output_format_label")).grid(
            row=row, column=0, sticky="nw", padx=12, pady=(10, 0)
        )
        fmt_frame = ctk.CTkFrame(parent, fg_color="transparent")
        fmt_frame.grid(row=row, column=1, columnspan=2, sticky="w", padx=12, pady=(10, 0))
        self._fmt_txt = tk.BooleanVar(value=True)
        self._fmt_json = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(fmt_frame, text=i18n_mod.t("format_txt"), variable=self._fmt_txt).pack(
            side="left", padx=(0, 16)
        )
        ctk.CTkCheckBox(fmt_frame, text=i18n_mod.t("format_json"), variable=self._fmt_json).pack(
            side="left"
        )
        row += 1

        # --- Transcribe button ---
        btn_frame = ctk.CTkFrame(parent, fg_color="transparent")
        btn_frame.grid(row=row, column=0, columnspan=3, pady=(16, 4))
        self._transcribe_btn = ctk.CTkButton(
            btn_frame, text=i18n_mod.t("transcribe_button"), width=160, command=self._on_transcribe
        )
        self._transcribe_btn.pack(side="left", padx=8)
        self._cancel_btn = ctk.CTkButton(
            btn_frame,
            text=i18n_mod.t("cancel_button"),
            width=120,
            fg_color="gray40",
            hover_color="gray30",
            command=self._on_cancel,
            state="disabled",
        )
        self._cancel_btn.pack(side="left", padx=8)
        row += 1

        # --- Progress bar ---
        self._progress = ctk.CTkProgressBar(parent)
        self._progress.set(0)
        self._progress.grid(row=row, column=0, columnspan=3, sticky="ew", padx=12, pady=(8, 4))
        row += 1

        # --- Log area ---
        self._log = ctk.CTkTextbox(parent, height=120, state="disabled", wrap="word")
        self._log.grid(row=row, column=0, columnspan=3, sticky="nsew", padx=12, pady=(0, 8))
        parent.rowconfigure(row, weight=1)
        row += 1

        self._log_append(i18n_mod.t("log_ready"))

    def _build_settings_tab(self, parent):
        parent.columnconfigure(1, weight=1)

        ctk.CTkLabel(parent, text=i18n_mod.t("settings_language_label")).grid(
            row=0, column=0, sticky="w", padx=16, pady=(20, 0)
        )
        self._ui_lang_var = tk.StringVar(
            value=i18n_mod.t(
                "settings_language_fr" if i18n_mod.current_lang() == "fr" else "settings_language_en"
            )
        )
        lang_options = [i18n_mod.t("settings_language_fr"), i18n_mod.t("settings_language_en")]
        ctk.CTkComboBox(
            parent,
            values=lang_options,
            variable=self._ui_lang_var,
            state="readonly",
            width=160,
            command=self._on_lang_change,
        ).grid(row=0, column=1, sticky="w", padx=16, pady=(20, 0))

    def _build_about_tab(self, parent):
        frame = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        frame.pack(fill="both", expand=True, padx=16, pady=12)

        ctk.CTkLabel(frame, text="AutoTranscript", font=ctk.CTkFont(size=22, weight="bold")).pack(
            anchor="w", pady=(0, 2)
        )
        ctk.CTkLabel(frame, text=f"v{_VERSION}", font=ctk.CTkFont(size=12)).pack(anchor="w")
        ctk.CTkLabel(
            frame, text=i18n_mod.t("about_description"), wraplength=500, justify="left"
        ).pack(anchor="w", pady=(12, 0))

        ctk.CTkLabel(
            frame, text=i18n_mod.t("about_authors_title"), font=ctk.CTkFont(weight="bold")
        ).pack(anchor="w", pady=(16, 4))
        for author in _AUTHORS:
            ctk.CTkLabel(frame, text=f"• {author}").pack(anchor="w")

        ctk.CTkLabel(
            frame, text=i18n_mod.t("about_contributor_title"), font=ctk.CTkFont(weight="bold")
        ).pack(anchor="w", pady=(12, 4))
        ctk.CTkLabel(frame, text=f"• {_CONTRIBUTOR}").pack(anchor="w")

        ctk.CTkLabel(
            frame, text=i18n_mod.t("about_repo"), font=ctk.CTkFont(weight="bold")
        ).pack(anchor="w", pady=(16, 4))
        link = ctk.CTkLabel(
            frame, text=_REPO_URL, text_color=("#1a73e8", "#4da6ff"), cursor="hand2"
        )
        link.pack(anchor="w")
        link.bind("<Button-1>", lambda _: webbrowser.open(_REPO_URL))

    # --- helpers ---

    def _log_append(self, message: str) -> None:
        self._log.configure(state="normal")
        self._log.insert("end", message + "\n")
        self._log.see("end")
        self._log.configure(state="disabled")

    def _on_mode_change(self) -> None:
        mode = self._mode_var.get()
        self._select_btn.configure(
            text=i18n_mod.t("select_file" if mode == "file" else "select_folder")
        )
        self._selected_path.set("")

    def _on_select(self) -> None:
        if self._mode_var.get() == "file":
            audio_types = " ".join(f"*{e}" for e in sorted({".mp3", ".wav", ".m4a", ".ogg", ".flac", ".aac", ".mp4", ".mkv", ".avi", ".mov", ".webm"}))
            path = filedialog.askopenfilename(
                title=i18n_mod.t("file_dialog_title"),
                filetypes=[("Audio / Vidéo", audio_types), ("Tous les fichiers", "*.*")],
            )
        else:
            path = filedialog.askdirectory(title=i18n_mod.t("folder_dialog_title"))
        if path:
            self._selected_path.set(path)
            self._config["last_folder"] = os.path.dirname(path) if os.path.isfile(path) else path
            _save_config(self._config)

    def _selected_model_id(self) -> str:
        label = self._model_var.get()
        return label.split()[0]

    def _selected_whisper_lang(self) -> str:
        label = self._whisper_lang_var.get()
        for key, value in WHISPER_LANGUAGES.items():
            if i18n_mod.t(key) == label:
                return "" if value == "auto" else value
        return ""

    def _selected_formats(self) -> list[str]:
        formats = []
        if self._fmt_txt.get():
            formats.append("txt")
        if self._fmt_json.get():
            formats.append("json")
        return formats

    def _on_transcribe(self) -> None:
        path = self._selected_path.get()
        if not path:
            messagebox.showwarning("AutoTranscript", i18n_mod.t("error_no_input"))
            return
        formats = self._selected_formats()
        if not formats:
            messagebox.showwarning("AutoTranscript", i18n_mod.t("error_no_format"))
            return

        model_id = self._selected_model_id()
        self._config["last_model"] = model_id
        _save_config(self._config)

        self._running = True
        self._transcribe_btn.configure(state="disabled")
        self._cancel_btn.configure(state="normal")
        self._progress.set(0)

        def _run():
            try:
                self._transcriber.transcribe(
                    path,
                    model_id,
                    self._selected_whisper_lang(),
                    formats,
                    lambda msg, pct: self._queue.put((msg, pct)),
                )
            except Exception as exc:
                self._queue.put((f"error:{exc}", 0.0))
            finally:
                self._queue.put(("_done_", 1.0))

        threading.Thread(target=_run, daemon=True).start()

    def _on_cancel(self) -> None:
        self._transcriber.cancel()

    def _on_lang_change(self, _=None) -> None:
        label = self._ui_lang_var.get()
        lang = "fr" if label == i18n_mod.t("settings_language_fr") else "en"
        self._config["lang"] = lang
        _save_config(self._config)
        i18n_mod.load(lang)
        self._rebuild_ui()

    def _rebuild_ui(self) -> None:
        self._tabview.destroy()
        self._build_ui()

    def _poll_queue(self) -> None:
        try:
            while True:
                msg, pct = self._queue.get_nowait()
                if msg == "_done_":
                    self._running = False
                    self._transcribe_btn.configure(state="normal")
                    self._cancel_btn.configure(state="disabled")
                elif msg.startswith("loading_model:"):
                    model = msg.split(":", 1)[1]
                    self._log_append(i18n_mod.t("log_loading_model", model=model))
                elif msg.startswith("processing_file:"):
                    fname = msg.split(":", 1)[1]
                    self._log_append(i18n_mod.t("log_processing_file", file=fname))
                elif msg.startswith("extracting_audio:"):
                    fname = msg.split(":", 1)[1]
                    self._log_append(i18n_mod.t("log_extracting_audio", file=fname))
                elif msg.startswith("done_file:"):
                    fname = msg.split(":", 1)[1]
                    self._log_append(i18n_mod.t("log_done_file", file=fname))
                elif msg == "all_done":
                    self._log_append(i18n_mod.t("log_all_done"))
                elif msg == "no_audio_found":
                    self._log_append(i18n_mod.t("log_no_audio_found"))
                elif msg.startswith("error:"):
                    err = msg.split(":", 1)[1]
                    self._log_append(i18n_mod.t("log_error", error=err))
                self._progress.set(pct)
        except queue.Empty:
            pass
        self.after(100, self._poll_queue)
