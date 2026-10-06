# -*- coding: utf-8 -*-
"""Загрузка и проверка моделей при установке (python -m lektor.download_models).

Проверяет/скачивает:
  — модель Silero v5_cis_base (29 русских голосов, MIT, ~130 МБ);
  — silero-stress — нейросеть ударений (модели уже внутри pip-пакета,
    здесь только проверяем, что она работает);
  — при желании ruaccent (запасная нейросеть ударений);
  — при желании веса Chatterbox HD (лучше с NVIDIA; на CPU медленно).

В конце прогоняет самопроверку синтеза и сохраняет пробный WAV —
его можно сразу послушать.
"""
from __future__ import annotations

import argparse
import os
import sys
import urllib.request

from .config import MODELS_DIR, OUTPUT_DIR, ensure_dirs

SILERO_URLS = {
    "v5_cis_base": "https://models.silero.ai/models/tts/ru/v5_cis_base.pt",
    "v5_5_ru": "https://models.silero.ai/models/tts/ru/v5_5_ru.pt",
    "v4_ru": "https://models.silero.ai/models/tts/ru/v4_ru.pt",
}

PROBE_TEXT = ("Прив+ет! +Это проб+а г+олоса. Пригов+ор, экспер+т, "
              "дактилоскоп+ия, осужд+ённый.")

FULL_PROBE = ("Привет! Это проверка установки. Суд вынес приговор по делу "
              "о хищении: осуждённый освобождён по амнистии.")


def _mirrors(which: str):
    """Основной сайт Silero + запасное зеркало на GitHub (LFS)."""
    return [
        SILERO_URLS[which],
        f"https://github.com/snakers4/silero-models/raw/master/"
        f"files/model_urls/{'ru_' if which != 'v4_ru' else ''}{which}.pt",
    ]


def _download(url: str, path: str) -> bool:
    if os.path.exists(path) and os.path.getsize(path) > 10_000_000:
        print(f"  уже скачано: {path}")
        return True
    print(f"  качаю {url}")
    try:
        def hook(n, bs, total):
            if total > 0:
                done = min(n * bs, total)
                pct = int(done * 100 / total)
                sys.stdout.write(f"\r    {pct:>3}%  {done // 1024 // 1024} МБ")
                sys.stdout.flush()

        tmp = path + ".part"
        urllib.request.urlretrieve(url, tmp, reporthook=hook)
        os.replace(tmp, path)
        print(f"\r    готово: {os.path.getsize(path) // 1024 // 1024} МБ          ")
        return True
    except Exception as e:
        print(f"\n    не удалось: {e}")
        try:
            os.unlink(path + ".part")
        except Exception:
            pass
        return False


def check_silero_stress() -> bool:
    """silero-stress обязателен: без него v5_cis_base читает безударной кашей."""
    try:
        from silero_stress import load_accentor
        acc = load_accentor("ru")
        out = str(acc("Проверка ударений: договор, приговор, эксперт."))
        print(f"  silero-stress: {out}")
        if "+" not in out:
            print("  ВНИМАНИЕ: silero-stress ответил без разметки!")
            return False
        return True
    except Exception as e:
        print(f"  silero-stress недоступен: {e}")
        print("  Без него слова будут читаться безударными! Переустановите:")
        print("      .venv\\Scripts\\python.exe -m pip install silero-stress")
        return False


def download_silero(which: str = "v5_cis_base") -> bool:
    os.makedirs(MODELS_DIR, exist_ok=True)
    path = os.path.join(MODELS_DIR, which + ".pt")
    ok = any(_download(url, path) for url in _mirrors(which))
    if not ok:
        # последнее зеркало уже печатало свою ошибку; подсказка
        print("  Проверьте интернет и запустите установку ещё раз,")
        print("  либо скачайте модель кнопкой в окне программы.")
        return False
    # самопроверка: синтез + сохранение пробного файла
    try:
        import io

        import torch
        with open(path, "rb") as f:
            buf = io.BytesIO(f.read())
        model = torch.package.PackageImporter(buf).load_pickle("tts_models", "model")
        model.to(torch.device("cpu"))
        speaker = "ru_alexandr" if which == "v5_cis_base" else "xenia"
        audio = model.apply_tts(text=PROBE_TEXT, speaker=speaker,
                                sample_rate=48000, put_accent=False, put_yo=False)
        n = len(audio) if audio is not None else 0
        if n < 1000:
            print(f"  самопроверка синтеза: пусто ({n} сэмплов)!")
            return False
        ensure_dirs()
        probe = os.path.join(OUTPUT_DIR, "Проверка установки.wav")
        import wave

        with wave.open(probe, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(48000)
            import numpy as np
            pcm = (audio.numpy().clip(-1, 1) * 32767).astype("<i2")
            w.writeframes(pcm.tobytes())
        secs = n / 48000
        print(f"  самопроверка синтеза: ок, {secs:.1f} с аудио")
        print(f"  ПРОСЛУШАЙТЕ ФАЙЛ: {probe}")
        # полная проверка: та же фраза через весь конвейер (ударения, паузы)
        try:
            import numpy as np
            from .lingua.stress import StressAssigner
            from .report import Report
            from .synthesis.backends import Segment, Utterance
            from .synthesis.silero_backend import SileroBackend
            marked = StressAssigner(Report()).stress_sentence(FULL_PROBE)
            if "+" not in marked:
                print("  ВНИМАНИЕ: разметка ударений не работает — голос будет безударным!")
                return False
            backend = SileroBackend(models_dir=MODELS_DIR, preferred=which,
                                     log=lambda m: None)
            backend._model = model  # модель уже загружена выше
            backend._model_id = which
            audio2 = backend.synth(
                Utterance(segments=[Segment(text=marked, pause_after_ms=0)]),
                speaker)
            if audio2 is None or len(audio2) < 48000:
                print("  ВНИМАНИЕ: синтез с разметкой не удался!")
                return False
            probe2 = os.path.join(OUTPUT_DIR, "Проверка полной озвучки.wav")
            with wave.open(probe2, "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(48000)
                pcm = (np.asarray(audio2).clip(-1, 1) * 32767).astype("<i2")
                w.writeframes(pcm.tobytes())
            print(f"  полная проверка конвейера: ок — {probe2}")
        except Exception as e:
            print(f"  полная проверка конвейера не прошла: {e}")
            return False
        return True
    except Exception as e:
        print(f"  модель скачалась, но самопроверка не прошла: {e}")
        return False


def warm_ruaccent() -> bool:
    try:
        from ruaccent import RUAccent
        acc = RUAccent()
        acc.load()
        print("  ruaccent: " + acc.put_stress("Проверка ударений: договор, приговор.", mode="plus"))
        return True
    except Exception as e:
        print(f"  ruaccent недоступен ({e}) — не страшно, silero-stress основной.")
        return False


def warm_chatterbox() -> bool:
    try:
        import torch
        from chatterbox.mtl_tts import ChatterboxMultilingualTTS
        device = "cuda" if torch.cuda.is_available() else "cpu"
        if device == "cpu":
            print("  ВНИМАНИЕ: NVIDIA не найдена — Chatterbox будет работать на CPU")
            print("  (медленно, ~в 5–10 раз дольше реального времени).")
        print(f"  загружаю Chatterbox HD на {device} (первый раз ~1 ГБ)…")
        ChatterboxMultilingualTTS.from_pretrained(device=torch.device(device))
        return True
    except Exception as e:
        print(f"  Chatterbox HD недоступен: {e}")
        return False


def main(argv=None) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser()
    p.add_argument("--all", action="store_true", help="всё, включая HD-движок")
    p.add_argument("--chatterbox", action="store_true", help="только HD-движок")
    p.add_argument("--ruaccent", action="store_true", help="только запасная нейросеть ударений")
    p.add_argument("--model", default="v5_cis_base", choices=list(SILERO_URLS))
    a = p.parse_args(argv)

    ok = True
    if a.chatterbox:
        ok = warm_chatterbox() and ok
    elif a.ruaccent:
        ok = warm_ruaccent() and ok
    elif a.all:
        ok = check_silero_stress() and ok
        ok = download_silero(a.model) and ok
        ok = warm_ruaccent() and ok
        ok = warm_chatterbox() and ok
    else:
        ok = check_silero_stress() and ok
        ok = download_silero(a.model) and ok
        ok = warm_ruaccent() and ok
    print("Итог:", "готово" if ok else "были проблемы (см. выше)")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
