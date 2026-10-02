# -*- coding: utf-8 -*-
"""Загрузка моделей при установке (python -m lektor.download_models).

Скачивает:
  — модель Silero v5_cis_base (29 русских голосов, MIT, ~130 МБ);
  — при желании модели ruaccent (нейросеть ударений, ~100 МБ);
  — при желании веса Chatterbox HD (нужна NVIDIA, ~1 ГБ).

После установки программа работает полностью офлайн.
"""
from __future__ import annotations

import argparse
import os
import sys
import urllib.request

from .config import MODELS_DIR

SILERO_URLS = {
    "v5_cis_base": "https://models.silero.ai/models/tts/ru/v5_cis_base.pt",
    "v5_5_ru": "https://models.silero.ai/models/tts/ru/v5_5_ru.pt",
    "v4_ru": "https://models.silero.ai/models/tts/ru/v4_ru.pt",
}


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


def download_silero(which: str = "v5_cis_base") -> bool:
    os.makedirs(MODELS_DIR, exist_ok=True)
    url = SILERO_URLS[which]
    path = os.path.join(MODELS_DIR, which + ".pt")
    if _download(url, path):
        # быстрая проверка целостности
        try:
            import torch
            import io
            with open(path, "rb") as f:
                buf = io.BytesIO(f.read())
            model = torch.package.PackageImporter(buf).load_pickle("tts_models", "model")
            model.to(torch.device("cpu"))
            audio = model.apply_tts(text="Пров+ерка.", speaker="ru_alexandr" if which == "v5_cis_base" else "xenia",
                                    sample_rate=48000, put_accent=False, put_yo=False)
            print(f"  самопроверка синтеза: {'ок, ' + str(len(audio)) + ' сэмплов' if audio is not None and len(audio) > 1000 else 'пусто!'}")
            return True
        except Exception as e:
            print(f"  модель скачалась, но самопроверка не прошла: {e}")
            return False
    return False


def warm_ruaccent() -> bool:
    try:
        from ruaccent import RUAccent
        acc = RUAccent()
        acc.load()
        print("  ruaccent: " + acc.put_stress("Проверка ударений: договор, приговор.", mode="plus"))
        return True
    except Exception as e:
        print(f"  ruaccent недоступен ({e}) — программа будет использовать встроенные словари.")
        return False


def warm_chatterbox() -> bool:
    try:
        import torch
        from chatterbox.mtl_tts import ChatterboxMultilingualTTS
        device = "cuda" if torch.cuda.is_available() else "cpu"
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
    p.add_argument("--ruaccent", action="store_true", help="только нейросеть ударений")
    p.add_argument("--model", default="v5_cis_base", choices=list(SILERO_URLS))
    a = p.parse_args(argv)

    ok = True
    if a.chatterbox:
        ok = warm_chatterbox() and ok
    elif a.ruaccent:
        ok = warm_ruaccent() and ok
    elif a.all:
        ok = download_silero(a.model) and ok
        ok = warm_ruaccent() and ok
        ok = warm_chatterbox() and ok
    else:
        ok = download_silero(a.model) and ok
        ok = warm_ruaccent() and ok
    print("Итог:", "готово" if ok else "были проблемы (см. выше)")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
