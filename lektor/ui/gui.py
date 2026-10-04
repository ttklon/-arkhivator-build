# -*- coding: utf-8 -*-
"""Окно приложения «Лектор» (customtkinter).

Просто вставь текст (или открой файл), выбери голос и нажми «Озвучить» —
получишь MP3 в папке «Аудиолекции» и отчёт о решениях по тексту.
"""
from __future__ import annotations

import os
import queue
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox

import customtkinter as ctk

from ..config import (Settings, load_settings, save_settings, OUTPUT_DIR,
                      USER_DICT_DIR, ENGINE_SILERO, ENGINE_CHATTERBOX, ENGINE_SAPI,
                      APP_DIR, ensure_dirs)

SAMPLE_TEXT = ("Привет! Это проба голоса. Я прочитаю вслух вашу книгу, "
               "статью или документ — спокойно, разборчиво и без интернета.")

ENGINE_LABELS = {
    ENGINE_SILERO: "Silero — быстрый и точный (рекомендую)",
    ENGINE_CHATTERBOX: "Chatterbox HD — самый живой (медленный без NVIDIA)",
    ENGINE_SAPI: "Голоса Windows — запасной",
}


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.settings: Settings = load_settings()
        self.title("Лектор — текст в аудиолекцию")
        self.geometry("1150x740")
        # восстанавливаем размер и положение окна прошлого запуска
        try:
            if self.settings.window and "x" in self.settings.window:
                self.geometry(self.settings.window)
        except Exception:
            pass
        self.minsize(980, 620)
        ctk.set_appearance_mode(self.settings.appearance == "light" and "light" or "dark")
        ctk.set_default_color_theme("blue")

        self._queue: queue.Queue = queue.Queue()
        self._worker: threading.Thread or None = None
        self._cancel = threading.Event()
        self._voices: dict = {}          # engine -> [(id, label)]
        self._preview_file = ""
        self._eta_start = None
        self._eta_frac = 0.0
        self._last_report = ""

        self._build_layout()
        self.after(100, self._poll_queue)
        self.after(200, self._load_engines)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ==================================================================
    # Разметка окна
    # ==================================================================
    def _build_layout(self):
        grid = self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=0)

        # --- левая часть: текст -----------------------------------------
        left = ctk.CTkFrame(self)
        left.grid(row=0, column=0, sticky="nsew", padx=(10, 6), pady=10)
        left.grid_rowconfigure(1, weight=1)
        left.grid_columnconfigure(0, weight=1)

        top = ctk.CTkFrame(left, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 2))
        ctk.CTkLabel(top, text="Текст лекции", font=ctk.CTkFont(size=15, weight="bold")).pack(side="left")
        self.lbl_count = ctk.CTkLabel(top, text="слов: 0", text_color="#8fa3b8")
        self.lbl_count.pack(side="left", padx=10)

        self.om_recent = ctk.CTkOptionMenu(
            top, values=["Недавние"], width=150, command=self._open_recent)
        self.om_recent.pack(side="left", padx=(6, 0))
        self._refresh_recent()

        ctk.CTkButton(top, text="Разметка", width=90,
                      command=self.show_markup).pack(side="right", padx=3)
        ctk.CTkButton(top, text="Открыть файл…", width=110, command=self.open_file).pack(side="right", padx=3)
        ctk.CTkButton(top, text="Пример", width=80, command=self.insert_example).pack(side="right", padx=3)
        ctk.CTkButton(top, text="Очистить", width=80, command=lambda: self.txt.delete("1.0", "end")).pack(side="right", padx=3)

        self.txt = ctk.CTkTextbox(left, font=ctk.CTkFont(size=14), wrap="word")
        self.txt.grid(row=1, column=0, sticky="nsew", padx=8, pady=6)
        self.txt.bind("<KeyRelease>", lambda e: self._update_count())

        hint = ("Поддерживаются: вставка текста, файлы .txt .docx .pdf .fb2 .epub. "
                "Числа, даты, статьи и аббревиатуры озвучиваются словами. "
                "Поддерживается SSML: <break time=\"500ms\"/>, <emphasis>слово</emphasis>.")
        ctk.CTkLabel(left, text=hint, text_color="#8fa3b8", justify="left").grid(
            row=2, column=0, sticky="ew", padx=10, pady=(0, 8))

        # --- правая панель: настройки ------------------------------------
        right = ctk.CTkScrollableFrame(self, width=360)
        right.grid(row=0, column=1, sticky="nsew", padx=(6, 10), pady=10)

        ctk.CTkLabel(right, text="Озвучка", font=ctk.CTkFont(size=15, weight="bold")).pack(anchor="w", pady=(4, 6))

        self.om_engine = ctk.CTkOptionMenu(right, values=["Silero — быстрый и точный (рекомендую)"],
                                           command=self._on_engine_change)
        self.om_engine.pack(fill="x", pady=3)
        self.om_engine.set(ENGINE_LABELS.get(self.settings.engine, ENGINE_LABELS[ENGINE_SILERO]))

        self.om_voice = ctk.CTkOptionMenu(right, values=["(голоса загружаются…)"])
        self.om_voice.pack(fill="x", pady=3)
        ctk.CTkButton(right, text="▶  Прослушать голос", height=28,
                      command=self.preview_voice).pack(fill="x", pady=(2, 8))

        ctk.CTkLabel(right, text="Режим").pack(anchor="w")
        self.om_mode = ctk.CTkOptionMenu(right, values=["Лекция", "Чтение документа"])
        self.om_mode.pack(fill="x", pady=3)
        self.om_mode.set("Лекция" if self.settings.mode == "lecture" else "Чтение документа")

        seg_theme = ctk.CTkSegmentedButton(right, values=["Тёмная", "Светлая"],
                                           command=self._on_theme)
        seg_theme.pack(fill="x", pady=(6, 0))
        seg_theme.set("Светлая" if self.settings.appearance == "light" else "Тёмная")

        self.sl_speed = self._slider(right, "Скорость речи", 0.7, 1.3, self.settings.speed)
        self.sl_intra = self._slider(right, "Паузы внутри предложения", 0.5, 2.0, self.settings.pause_scale)
        self.sl_inter = self._slider(right, "Паузы между предложениями", 0.5, 2.0, self.settings.inter_pause_scale)

        self.sw_fix = ctk.CTkSwitch(right, text="Исправлять запятые по смыслу")
        self.sw_fix.pack(anchor="w", pady=(6, 1))
        self.sw_fix.select() if self.settings.fix_commas else self.sw_fix.deselect()
        self.sw_abbr = ctk.CTkSwitch(right, text="Расшифровывать аббревиатуры (первый раз)")
        self.sw_abbr.pack(anchor="w", pady=1)
        self.sw_abbr.select() if self.settings.expand_abbrevs else self.sw_abbr.deselect()

        ctk.CTkLabel(right, text="Сноски").pack(anchor="w", pady=(8, 0))
        self.om_foot = ctk.CTkOptionMenu(right, values=["пропускать", "читать в конце (тише)"], width=200)
        self.om_foot.pack(anchor="w", pady=3)
        self.om_foot.set("пропускать" if self.settings.footnotes == "skip" else "читать в конце (тише)")

        ctk.CTkLabel(right, text="Формат файла").pack(anchor="w", pady=(8, 0))
        self.om_fmt = ctk.CTkSegmentedButton(right, values=["MP3", "WAV"])
        self.om_fmt.pack(anchor="w", pady=3)
        self.om_fmt.set("MP3" if self.settings.fmt == "mp3" else "WAV")

        self.btn_go = ctk.CTkButton(right, text="▶  ОЗВУЧИТЬ", height=42,
                                    font=ctk.CTkFont(size=15, weight="bold"),
                                    command=self.start_job)
        self.btn_go.pack(fill="x", pady=(14, 4))
        self.progress = ctk.CTkProgressBar(right)
        self.progress.pack(fill="x", pady=2)
        self.progress.set(0)
        self.lbl_status = ctk.CTkLabel(right, text="Готов к работе", text_color="#8fa3b8",
                                       justify="left", anchor="w")
        self.lbl_status.pack(fill="x", pady=2)
        self.btn_cancel = ctk.CTkButton(right, text="Отменить", height=28,
                                        fg_color="#7a3b3b", hover_color="#933",
                                        command=self.cancel_job, state="disabled")
        self.btn_cancel.pack(fill="x", pady=2)

        row_btns = ctk.CTkFrame(right, fg_color="transparent")
        row_btns.pack(fill="x", pady=(8, 2))
        ctk.CTkButton(row_btns, text="Папка с аудио", height=28,
                      command=self.open_folder).pack(side="left", expand=True, fill="x", padx=2)
        ctk.CTkButton(row_btns, text="Отчёт", height=28,
                      command=self.open_last_report).pack(side="left", expand=True, fill="x", padx=2)
        ctk.CTkButton(row_btns, text="Словари", height=28,
                      command=self.open_dicts).pack(side="left", expand=True, fill="x", padx=2)

        self.log = ctk.CTkTextbox(right, height=130, font=ctk.CTkFont(size=12))
        self.log.pack(fill="x", pady=(10, 0))

    def _on_theme(self, label: str):
        mode = "light" if label == "Светлая" else "dark"
        ctk.set_appearance_mode(mode)
        self.settings.appearance = mode
        save_settings(self.settings)

    def _slider(self, parent, label, lo, hi, value):
        ctk.CTkLabel(parent, text=label).pack(anchor="w", pady=(10, 0))
        var = tk.DoubleVar(value=value)
        ctk.CTkSlider(parent, from_=lo, to=hi, variable=var, number_of_steps=20).pack(fill="x")
        return var

    # ==================================================================
    # Фоновая загрузка движков/голосов
    # ==================================================================
    def _load_engines(self):
        def work():
            engines = []
            voices = {}
            try:
                from ..synthesis.silero_backend import SileroBackend
                b = SileroBackend()
                voices[ENGINE_SILERO] = [(v.id, v.label) for v in b.voices()]
                engines.append(ENGINE_SILERO)
                if not b.model_ready():
                    self._queue.put(("log",
                        "Модель Silero не найдена — при озвучке включится запасной "
                        "голос. Запустите install.bat, чтобы её скачать."))
            except Exception:
                pass
            try:
                from ..synthesis.chatterbox_backend import ChatterboxBackend
                if ChatterboxBackend.is_available():
                    b = ChatterboxBackend()
                    voices[ENGINE_CHATTERBOX] = [(v.id, v.label) for v in b.voices()]
                    engines.append(ENGINE_CHATTERBOX)
            except Exception:
                pass
            try:
                from ..synthesis.sapi_backend import SapiBackend
                if SapiBackend.is_available():
                    b = SapiBackend()
                    vs = [(v.id, v.label) for v in b.voices()]
                    if vs:
                        voices[ENGINE_SAPI] = vs
                        engines.append(ENGINE_SAPI)
            except Exception:
                pass
            self._queue.put(("engines", engines, voices))

        threading.Thread(target=work, daemon=True).start()

    def _apply_engines(self, engines, voices):
        self._voices = voices
        labels = [ENGINE_LABELS.get(e, e) for e in engines] or ["Движки не найдены — запустите install.bat"]
        self.om_engine.configure(values=labels)
        cur = ENGINE_LABELS.get(self.settings.engine)
        if cur in labels:
            self.om_engine.set(cur)
        else:
            self.om_engine.set(labels[0])
        self._on_engine_change(self.om_engine.get())

    def _current_engine(self) -> str:
        text = self.om_engine.get()
        for k, v in ENGINE_LABELS.items():
            if v == text:
                return k
        return ENGINE_SILERO

    def _on_engine_change(self, label: str):
        engine = self._current_engine()
        pairs = self._voices.get(engine) or []
        if not pairs:
            self.om_voice.configure(values=["(нет голосов)"])
            self.om_voice.set("(нет голосов)")
            return
        labels = [lbl for _, lbl in pairs]
        self.om_voice.configure(values=labels)
        want = self.settings.voice if engine == self.settings.engine else pairs[0][0]
        for vid, lbl in pairs:
            if vid == want:
                self.om_voice.set(lbl)
                return
        self.om_voice.set(labels[0])

    def _current_voice_id(self) -> str:
        engine = self._current_engine()
        for vid, lbl in self._voices.get(engine, []):
            if lbl == self.om_voice.get():
                return vid
        return ""

    # ==================================================================
    # Сбор настроек из интерфейса
    # ==================================================================
    def _collect_settings(self) -> Settings:
        s = self.settings
        s.engine = self._current_engine()
        s.voice = self._current_voice_id() or s.voice
        s.mode = "lecture" if self.om_mode.get() == "Лекция" else "document"
        s.speed = round(float(self.sl_speed.get()), 2)
        s.pause_scale = round(float(self.sl_intra.get()), 2)
        s.inter_pause_scale = round(float(self.sl_inter.get()), 2)
        s.fix_commas = bool(self.sw_fix.get())
        s.expand_abbrevs = bool(self.sw_abbr.get())
        s.footnotes = "skip" if self.om_foot.get().startswith("пропуск") else "end"
        s.fmt = "mp3" if self.om_fmt.get() == "MP3" else "wav"
        save_settings(s)
        return s

    # ==================================================================
    # Действия
    # ==================================================================
    def show_markup(self):
        """Предпросмотр разметки: ударения, паузы, контуры — без синтеза."""
        text = self.txt.get("1.0", "end").strip()
        if not text:
            messagebox.showinfo("Лектор", "Вставьте текст или откройте файл.")
            return
        settings = self._collect_settings()
        self.lbl_status.configure(text="Разбираю текст…")

        def work():
            try:
                from ..pipeline import Pipeline
                pipe = Pipeline(settings, log=lambda m: self._queue.put(("log", m)))
                res = pipe.dry_run(text, title="Предпросмотр")
                self._queue.put(("markup", res.markup, res.report.render_text()))
            except Exception as e:
                self._queue.put(("markup", None, str(e)))

        threading.Thread(target=work, daemon=True).start()

    def _show_markup_window(self, markup: str, report_text: str):
        win = ctk.CTkToplevel(self)
        win.title("Разметка и отчёт")
        win.geometry("900x640")
        win.attributes("-topmost", True)
        tab = ctk.CTkTabview(win)
        tab.pack(fill="both", expand=True, padx=8, pady=8)
        tab.add("Как будет читаться")
        tab.add("Отчёт")
        t1 = ctk.CTkTextbox(tab.tab("Как будет читаться"),
                            font=ctk.CTkFont(size=14), wrap="word")
        t1.pack(fill="both", expand=True)
        t1.insert("1.0", markup or "(пусто)")
        t2 = ctk.CTkTextbox(tab.tab("Отчёт"), font=ctk.CTkFont(size=13), wrap="word")
        t2.pack(fill="both", expand=True)
        t2.insert("1.0", report_text or "(пусто)")
        self.lbl_status.configure(text="Разметка готова")
        ctk.CTkLabel(win, text="⟦NNN мс⟧ — пауза; «+» — ударение;",
                     text_color="#8fa3b8").pack(pady=(0, 6))

    # ------------------------------------------------------------------
    def _refresh_recent(self):
        items = [os.path.basename(p) for p in self.settings.recent[:8]]
        self.om_recent.configure(values=items or ["Недавние"])
        self.om_recent.set(items[0] if items else "Недавние")

    def _open_recent(self, label: str):
        if label == "Недавние":
            return
        for path in self.settings.recent:
            if os.path.basename(path) == label:
                self._load_file(path)
                return

    def _load_file(self, path: str):
        try:
            from ..textproc.files import read_file
            text = read_file(path)
            self.txt.delete("1.0", "end")
            self.txt.insert("1.0", text)
            self._update_count()
            self._log(f"Открыт файл: {os.path.basename(path)}")
            # запоминаем в недавних (свежие — наверх)
            rec = [p for p in self.settings.recent if p != path]
            rec.insert(0, path)
            self.settings.recent = rec[:8]
            save_settings(self.settings)
            self._refresh_recent()
        except Exception as e:
            messagebox.showerror("Лектор", f"Не удалось открыть файл:\n{e}")

    def open_file(self):
        path = filedialog.askopenfilename(
            title="Открыть текст",
            filetypes=[("Тексты и документы", "*.txt *.docx *.pdf *.fb2 *.epub *.md"),
                       ("Все файлы", "*.*")])
        if not path:
            return
        self._load_file(path)

    def insert_example(self):
        example = os.path.join(APP_DIR, "examples", "пример.txt")
        if os.path.exists(example):
            with open(example, encoding="utf-8") as f:
                self.txt.delete("1.0", "end")
                self.txt.insert("1.0", f.read())
            self._update_count()
        else:
            self._log("Файл примера не найден")

    def open_folder(self):
        ensure_dirs()
        try:
            os.startfile(OUTPUT_DIR)  # noqa: Windows
        except Exception:
            try:
                import subprocess
                subprocess.Popen(["xdg-open", OUTPUT_DIR])
            except Exception:
                pass

    def open_last_report(self):
        if self._last_report and os.path.exists(self._last_report):
            try:
                os.startfile(self._last_report)  # noqa: Windows
                return
            except Exception:
                pass
        # отчёта ещё нет — открываем последний из папки
        try:
            import glob
            reports = sorted(glob.glob(os.path.join(OUTPUT_DIR, "*.отчёт.txt")),
                             key=os.path.getmtime, reverse=True)
            if reports:
                os.startfile(reports[0])  # noqa: Windows
                return
        except Exception:
            pass
        self._log("Отчёта ещё нет — озвучьте текст.")

    def open_dicts(self):
        ensure_dirs()
        try:
            os.startfile(USER_DICT_DIR)  # noqa: Windows
        except Exception:
            pass

    def _update_count(self):
        text = self.txt.get("1.0", "end")
        words = len([w for w in text.split() if any(c.isalpha() for c in w)])
        self.lbl_count.configure(text=f"слов: {words}")

    def _log(self, msg: str):
        self.log.insert("end", msg + "\n")
        self.log.see("end")

    # ==================================================================
    # Прослушивание голоса
    # ==================================================================
    def preview_voice(self):
        settings = self._collect_settings()
        engine = self._current_engine()
        voice = self._current_voice_id()
        self.lbl_status.configure(text="Готовлю пробу голоса…")

        def work():
            try:
                from ..pipeline import build_backend
                from ..synthesis.renderer import Renderer
                from ..synthesis.backends import Segment, Utterance
                backend = build_backend(settings)
                # проба должна звучать как настоящая озвучка —
                # с расставленными ударениями
                try:
                    from ..lingua.stress import StressAssigner
                    from ..report import Report as _R
                    sample = StressAssigner(_R()).stress_sentence(SAMPLE_TEXT)
                except Exception:
                    sample = SAMPLE_TEXT
                utt = Utterance(segments=[Segment(text=sample, pause_after_ms=0)])
                renderer = Renderer(backend, voice)
                base = os.path.join(OUTPUT_DIR, "проба_голоса")
                wav = base + ".wav"
                renderer.render([utt], wav)
                self._queue.put(("preview", wav, None))
            except Exception as e:
                self._queue.put(("preview", None, str(e)))

        threading.Thread(target=work, daemon=True).start()

    def _play_wav(self, path: str):
        try:
            import winsound
            winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC)
        except Exception:
            try:
                import subprocess, sys
                if sys.platform == "darwin":
                    subprocess.Popen(["afplay", path])
                else:
                    subprocess.Popen(["aplay", path])
            except Exception:
                self._log(f"Проба сохранена: {path}")

    # ==================================================================
    # Основная работа
    # ==================================================================
    def start_job(self):
        text = self.txt.get("1.0", "end").strip()
        if not text:
            messagebox.showinfo("Лектор", "Вставьте текст или откройте файл.")
            return
        if self._worker and self._worker.is_alive():
            return
        settings = self._collect_settings()
        self._cancel.clear()
        self.btn_go.configure(state="disabled")
        self.btn_cancel.configure(state="normal")
        self.progress.set(0)
        self._eta_start, self._eta_frac = None, 0.0
        self.lbl_status.configure(text="Запуск…")
        title = text.strip().splitlines()[0][:60] or "лекция"

        def progress(stage: str, frac: float, msg: str):
            self._queue.put(("progress", stage, frac, msg))

        def work():
            try:
                from ..pipeline import Pipeline
                pipe = Pipeline(settings, progress=progress,
                                cancel_event=self._cancel,
                                log=lambda m: self._queue.put(("log", m)))
                res = pipe.run(text, title)
                self._queue.put(("done", res, None))
            except Exception as e:
                self._queue.put(("done", None, str(e)))

        self._worker = threading.Thread(target=work, daemon=True)
        self._worker.start()

    def cancel_job(self):
        self._cancel.set()
        self.lbl_status.configure(text="Останавливаю после текущей реплики…")

    # ==================================================================
    # Очередь событий из фоновых потоков
    # ==================================================================
    def _poll_queue(self):
        try:
            while True:
                item = self._queue.get_nowait()
                kind = item[0]
                if kind == "progress":
                    _, stage, frac, msg = item
                    self.progress.set(frac if frac >= 0 else self.progress.get())
                    if frac > 0:
                        # оценка времени до конца (по темпу продвижения)
                        now = time.monotonic()
                        if self._eta_start is None or frac < (self._eta_frac or 0):
                            self._eta_start, self._eta_frac = now, frac
                        elif frac > (self._eta_frac or 0) and frac > 0.02:
                            rate = (frac - self._eta_frac) / max(0.1, now - self._eta_start)
                            rest = (1.0 - frac) / max(rate, 1e-6)
                            if rest > 20:
                                msg = f"{msg} · осталось ~{int(rest // 60)} мин"
                                self._eta_start, self._eta_frac = now, frac
                    self.lbl_status.configure(text=f"{stage}: {msg}"[:120])
                elif kind == "log":
                    self._log(item[1])
                elif kind == "engines":
                    self._apply_engines(item[1], item[2])
                elif kind == "markup":
                    markup, report_text = item[1], item[2]
                    if markup is None:
                        self.lbl_status.configure(text=f"Разбор не удался: {report_text[:80]}")
                    else:
                        self._show_markup_window(markup, report_text)
                elif kind == "preview":
                    wav, err = item[1], item[2]
                    if err:
                        self.lbl_status.configure(text=f"Проба не удалась: {err[:80]}")
                    else:
                        self.lbl_status.configure(text="Проба голоса…")
                        self._play_wav(wav)
                elif kind == "done":
                    res, err = item[1], item[2]
                    self.btn_go.configure(state="normal")
                    self.btn_cancel.configure(state="disabled")
                    if err:
                        self.lbl_status.configure(text=f"Ошибка: {err[:100]}")
                        messagebox.showerror("Лектор", err)
                        return
                    if res is None or not res.audio_path:
                        self.lbl_status.configure(text="Отменено или пусто")
                        return
                    self.progress.set(1.0)
                    from ..report import fmt_sec
                    mins = fmt_sec(res.duration_sec)
                    self.lbl_status.configure(
                        text=f"Готово! {mins} аудио · {res.report.summary_line()}")
                    self._log(f"Файл: {res.audio_path}")
                    self._log(f"Движок: {res.engine}; голос: {res.voice}")
                    txt_path = os.path.splitext(res.audio_path)[0] + ".отчёт.txt"
                    self._last_report = txt_path
                    self._log(f"Отчёт: {txt_path}")
                    if self.settings.open_folder:
                        self.open_folder()
        except queue.Empty:
            pass
        self.after(120, self._poll_queue)

    def _on_close(self):
        if self._worker and self._worker.is_alive():
            if not messagebox.askyesno(
                    "Лектор",
                    "Сейчас идёт озвучка. Прервать её и выйти?\n"
                    "(несколько секунд на остановку)"):
                return
            self._cancel.set()
            self.lbl_status.configure(text="Останавливаю…")
            self.update_idletasks()
            self._worker.join(timeout=15)
        try:
            self._collect_settings()
            # запоминаем размер и положение окна
            self.settings.window = self.geometry()
            save_settings(self.settings)
        except Exception:
            pass
        self.destroy()


def main() -> int:
    ensure_dirs()
    app = App()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
