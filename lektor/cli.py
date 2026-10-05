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
import os
import sys
import time

from .config import load_settings, save_settings, Settings, OUTPUT_DIR


def main(argv=None) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    p = argparse.ArgumentParser(
        prog="lektor",
        description="«Лектор» — текст в аудиолекцию (полностью офлайн).")
    from . import __version__
    p.add_argument("--version", action="version",
                   version="Лектор " + __version__,
                   help="показать версию и выйти")
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
    p.add_argument("--no-cache", action="store_true",
                   help="не использовать дисковый кэш синтеза")
    p.add_argument("--doctor", action="store_true",
                   help="самодиагностика: зависимости, словари, модель, проба синтеза")
    p.add_argument("--chapters", action="store_true",
                   help="разбить аудио на части по заголовкам текста")

    a = p.parse_args(argv)
    settings = load_settings()

    if a.doctor:
        return doctor()

    if a.list_voices:
        from .pipeline import build_backend
        backend = build_backend(settings)
        if backend is None:
            print("Движки недоступны: запустите install.bat")
            return 1
        for v in backend.voices():
            print(f"{v.engine}\t{v.id}\t{v.label}")
        return 0

    # пакетный режим: на входе папка — озвучиваем все поддерживаемые файлы
    if a.input and not a.text and os.path.isdir(a.input):
        return batch(a, settings)

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

    t_start = [None]

    def progress(stage: str, frac: float, msg: str) -> None:
        if not a.quiet and frac >= 0:
            bar = "#" * int(frac * 24)
            tail = ""
            if t_start[0] is None and frac > 0.02:
                t_start[0] = time.monotonic()
            if t_start[0] is not None and 0.05 < frac < 1.0:
                elapsed = time.monotonic() - t_start[0]
                rest = elapsed / frac * (1.0 - frac)
                if rest > 20:
                    tail = f"  · осталось ~{int(round(rest / 60))} мин"
            print(f"\r  [{stage}] {bar:<24} {int(frac * 100):>3}%  {msg[:48]}{tail}",
                  end="")

    from .pipeline import Pipeline
    pipe = Pipeline(settings, progress=progress,
                    cache=not a.no_cache)

    if a.markup:
        res = pipe.dry_run(text, title)
        print(res.markup)
        print("\n===== ОТЧЁТ =====")
        print(res.report.render_text())
        return 0

    if a.chapters:
        settings.chapters = True

    # -o: файл (.mp3/.wav) или папка
    out_dir = out_path = None
    if a.output:
        if a.output.lower().endswith((".mp3", ".wav")):
            out_path = a.output
            settings.fmt = os.path.splitext(a.output)[1][1:].lower()
        else:
            out_dir = a.output

    try:
        res = pipe.run(text, title, out_dir=out_dir, out_path=out_path)
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


def doctor() -> int:
    """Самодиагностика: что стоит, чего не хватает, что делать."""
    from . import __version__
    print(f"Лектор {__version__} — самодиагностика")
    print("=" * 52)
    import importlib
    fails = []

    def dep(name, module, fix, optional=False):
        try:
            importlib.import_module(module)
            print(f"  [ ОК ] {name}")
        except Exception as e:
            print(f"  [{'НЕТ'}] {name} — {str(e)[:48]}")
            if not optional:
                fails.append(fix)

    print("Обязательные модули:")
    dep("torch (нейросети)", "torch",
        "pip install torch --index-url https://download.pytorch.org/whl/cpu")
    dep("silero-stress (ударения)", "silero_stress", "pip install silero-stress")
    dep("razdel (токенизация)", "razdel", "pip install razdel")
    dep("pymorphy3 (морфология)", "pymorphy3", "pip install pymorphy3")
    dep("natasha (синтаксис)", "natasha", "pip install natasha")
    dep("numpy (аудио)", "numpy", "pip install numpy")
    dep("lameenc (MP3)", "lameenc", "pip install lameenc")

    print("Форматы файлов (необязательные):")
    dep("PyMuPDF (PDF)", "fitz", "pip install PyMuPDF", optional=True)
    dep("python-docx (Word)", "docx", "pip install python-docx", optional=True)
    dep("BeautifulSoup (HTML/EPUB)", "bs4", "pip install beautifulsoup4", optional=True)

    print("Словари:")
    from .config import APP_DIR, MODELS_DIR, OUTPUT_DIR, ensure_dirs
    dicts = os.path.join(APP_DIR, "lektor", "dictionaries")
    for d in ("homographs.json", "legal_stress.json",
              "abbreviations.json", "letters.json"):
        p = os.path.join(dicts, d)
        exists = os.path.exists(p)
        valid = exists
        if exists:
            # файл может быть побит при копировании — проверяем, что JSON
            # разбирается (иначе программа молча работает без словаря)
            try:
                import json as _json
                with open(p, "r", encoding="utf-8") as f:
                    _json.load(f)
            except Exception:
                valid = False
        if not exists:
            print(f"  [НЕТ] {d}")
            fails.append("переустановите приложение — словари отсутствуют")
        elif not valid:
            print(f"  [НЕТ] {d} — файл повреждён (не разбирается)")
            fails.append(f"восстановите файл {d} (переустановите приложение)")
        else:
            print(f"  [ ОК ] {d}")

    print("Модель голоса Silero:")
    ensure_dirs()
    model = None
    for mid in ("v5_cis_base", "v5_5_ru", "v4_ru"):
        if os.path.exists(os.path.join(MODELS_DIR, mid + ".pt")):
            model = mid
            break
    if model:
        print(f"  [ ОК ] {model}.pt")
    else:
        print("  [НЕТ] модель не скачана — запустите install.bat")
        fails.append("запустите install.bat (скачает модель Silero)")

    print("Проба ударений:")
    try:
        from .lingua.stress import StressAssigner
        from .report import Report
        marked = StressAssigner(Report()).stress_sentence(
            "Приговор суда вступил в законную силу.")
        ok = "+" in marked
        print(f"  [{' ОК ' if ok else 'НЕТ'}] {marked[:60]}")
        if not ok:
            fails.append("silero-stress не размечает текст (см. выше)")
    except Exception as e:
        print(f"  [НЕТ] {str(e)[:60]}")
        fails.append("исправьте ошибки модулей выше")

    if model and not fails:
        print("Проба синтеза:")
        try:
            from .synthesis.silero_backend import SileroBackend
            from .synthesis.backends import Segment, Utterance
            b = SileroBackend(log=lambda m: None)
            audio = b.synth(Utterance(segments=[
                Segment(text="Прив+ет! Всё раб+отает.", pause_after_ms=0)]), "xenia")
            import numpy as np, wave
            wav = os.path.join(OUTPUT_DIR, "Диагностика.wav")
            with wave.open(wav, "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(48000)
                w.writeframes((np.asarray(audio).clip(-1, 1) * 32767)
                              .astype("<i2").tobytes())
            print(f"  [ ОК ] {len(audio) / 48000:.1f} с — послушайте {wav}")
        except Exception as e:
            print(f"  [НЕТ] {str(e)[:60]}")

    print("=" * 52)
    if fails:
        print("ЧТО СДЕЛАТЬ:")
        for f in dict.fromkeys(fails):
            print(f"  • {f}")
        return 1
    print("Всё готово к озвучке.")
    return 0


def batch(a, settings) -> int:
    """Озвучить все текстовые файлы папки по очереди."""
    from .textproc.files import SUPPORTED
    files = sorted(
        f for f in os.listdir(a.input)
        if os.path.splitext(f)[1].lower() in SUPPORTED
        and not f.startswith("~$"))
    if not files:
        print(f"В папке нет поддерживаемых файлов ({', '.join(SUPPORTED)}).")
        return 2
    print(f"Пакетная озвучка: {len(files)} файл(ов) из {a.input}")
    ok = 0
    from .pipeline import Pipeline
    # один конвейер на всю папку: словари и морфология грузятся один раз
    pipe = Pipeline(settings, log=print)
    for i, name in enumerate(files, 1):
        path = os.path.join(a.input, name)
        print(f"\n[{i}/{len(files)}] {name}")
        try:
            src = read_any(path)
            if not src.strip():
                print("  пропущен: текста нет (пустой файл или PDF-скан)")
                continue
            res = pipe.run(src, os.path.splitext(name)[0])
            if res.audio_path:
                ok += 1
                if getattr(res, "audio_paths", None):
                    print(f"  готово: {len(res.audio_paths)} частей")
                else:
                    print(f"  готово: {os.path.basename(res.audio_path)}")
            else:
                print("  аудио не создано")
        except Exception as e:
            print(f"  ошибка: {e}")
    print(f"\nГотово: {ok} из {len(files)} файлов.")
    return 0 if ok == len(files) else (0 if ok else 3)


def read_any(path: str) -> str:
    from .textproc.files import read_file
    return read_file(path)


if __name__ == "__main__":
    raise SystemExit(main())
