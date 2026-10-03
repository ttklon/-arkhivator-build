# -*- coding: utf-8 -*-
"""Командная строка: python -m lektor [файл] [опции]

Примеры:
  python -m lektor лекция.txt                       # -> Аудиолекции/*.mp3
  python -m lektor закон.pdf -o закон.mp3 --voice baya
  python -m lektor текст.txt --markup               # только разметка и отчёт
  python -m lektor --list-voices                    # доступные голоса
"""
from __future__ import annotations

import argparse
import sys

from .config import load_settings, save_settings, Settings, OUTPUT_DIR


def main(argv=None) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    p = argparse.ArgumentParser(
        prog="lektor",
        description="«Лектор» — текст в аудиолекцию (полностью офлайн).")
    p.add_argument("input", nargs="?", help="файл .txt/.docx/.pdf/.fb2/.epub или «-» для stdin")
    p.add_argument("-t", "--text", help="текст прямо из аргумента")
    p.add_argument("-o", "--output", help="итоговый файл (mp3/wav) или папка")
    p.add_argument("--engine", choices=["silero", "chatterbox", "sapi"])
    p.add_argument("--voice", help="имя голоса (см. --list-voices)")
    p.add_argument("--mode", choices=["lecture", "document"], help="режим озвучки")
    p.add_argument("--speed", type=float, help="0.7..1.3 — множитель темпа")
    p.add_argument("--format", choices=["mp3", "wav"])
    p.add_argument("--markup", action="store_true",
                   help="не синтезировать: показать разметку и отчёт")
    p.add_argument("--list-voices", action="store_true")
    p.add_argument("--no-fix-commas", action="store_true",
                   help="не исправлять запятые по синтаксису")
    p.add_argument("--no-expand-abbrevs", action="store_true",
                   help="не расшифровывать аббревиатуры")
    p.add_argument("--open", action="store_true", help="открыть папку с результатом")
    p.add_argument("--quiet", action="store_true")

    a = p.parse_args(argv)
    settings = load_settings()

    if a.list_voices:
        from .pipeline import build_backend
        backend = build_backend(settings)
        if backend is None:
            print("Движки недоступны: запустите install.bat")
            return 1
        for v in backend.voices():
            print(f"{v.engine}\t{v.id}\t{v.label}")
        return 0

    # сбор текста
    text = ""
    title = "текст"
    if a.text:
        text, title = a.text, "текст из аргумента"
    elif a.input and a.input != "-":
        from .textproc.files import read_file, detect_title
        try:
            text = read_file(a.input)
            title = detect_title(a.input, text)
        except Exception as e:
            print(f"Не удалось прочитать файл: {e}")
            return 2
    else:
        text = sys.stdin.read()
        title = "текст из stdin"

    if not text.strip():
        print("Пустой текст.")
        return 2

    # настройки из аргументов
    if a.engine:
        settings.engine = a.engine
    if a.voice:
        settings.voice = a.voice
    if a.mode:
        settings.mode = a.mode
    if a.speed:
        settings.speed = max(0.5, min(1.5, a.speed))
    if a.format:
        settings.fmt = a.format
    if a.no_fix_commas:
        settings.fix_commas = False
    if a.no_expand_abbrevs:
        settings.expand_abbrevs = False

    def progress(stage: str, frac: float, msg: str) -> None:
        if not a.quiet:
            bar = "#" * int(frac * 24)
            print(f"\r  [{stage}] {bar:<24} {int(frac * 100):>3}%  {msg[:48]}", end="")

    from .pipeline import Pipeline
    pipe = Pipeline(settings, progress=progress)

    if a.markup:
        res = pipe.dry_run(text, title)
        print(res.markup)
        print("\n===== ОТЧЁТ =====")
        print(res.report.render_text())
        return 0

    try:
        res = pipe.run(text, title)
    except Exception as e:
        print(f"\nОшибка: {e}")
        return 3

    if not a.quiet:
        print()
    if res.audio_path:
        if not a.quiet:
            from .report import fmt_sec
            print(f"Готово: {res.audio_path}")
            print(f"Движок: {res.engine}; голос: {res.voice}; "
                  f"аудио {fmt_sec(res.duration_sec)}")
            print(f"Отчёт: {res.report.summary_line()}")
        if a.open:
            import os
            folder = os.path.dirname(os.path.abspath(res.audio_path))
            try:
                os.startfile(folder)  # noqa: Windows
            except Exception:
                try:
                    import subprocess
                    subprocess.Popen(["xdg-open", folder])
                except Exception:
                    pass
        return 0
    print("Аудио не создано (проверьте текст и настройки).")
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
