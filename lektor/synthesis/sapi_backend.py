# -*- coding: utf-8 -*-
"""Запасной движок: встроенные голоса Windows (SAPI через pyttsx3).

Качество ниже Silero, зато работает всегда и без загрузок — если основные
движки недоступны, озвучка всё равно состоится.
"""
from __future__ import annotations

import os
import re
import tempfile
from typing import List, Optional

import numpy as np

from ..config import SAMPLE_RATE
from .backends import Backend, Utterance, VoiceDef
from .audio import silence, read_wav, resample


class SapiBackend(Backend):
    id = "sapi"
    label = "Голоса Windows (запасной)"
    supports_stress_marks = False

    def __init__(self, rate: int = 0, log=print):
        self.rate = rate  # -50..50, ускорение/замедление SAPI
        self._log = log

    @staticmethod
    def is_available() -> bool:
        try:
            import pyttsx3  # noqa
            return os.name == "nt"
        except Exception:
            return False

    def voices(self) -> List[VoiceDef]:
        try:
            import pyttsx3
            eng = pyttsx3.init()
            out = []
            for v in eng.getProperty("voices"):
                name = getattr(v, "name", "") or v.id
                langs = " ".join(str(x) for x in (getattr(v, "languages", []) or []))
                if "ru" in name.lower() or "ru" in langs.lower() or "рус" in name.lower():
                    out.append(VoiceDef(v.id, name, self.id))
            if not out:
                # русских голосов нет: даём любые, но честно помечаем —
                # иначе английский голос прочтёт русский текст с акцентом
                out = []
                for v in eng.getProperty("voices")[:6]:
                    name = getattr(v, "name", "") or v.id
                    out.append(VoiceDef(
                        v.id, f"{name} (не русский — читать будет плохо)",
                        self.id))
            return out
        except Exception:
            return []

    def warm_up(self, voice: str) -> None:
        pass

    def prepare_text(self, text: str) -> str:
        return re.sub(r"\s+", " ", text.replace("+", "")).strip()

    def synth(self, utterance: Utterance, voice: str) -> np.ndarray:
        import pyttsx3
        chunks: List[np.ndarray] = []
        for seg in utterance.segments:
            text = self.prepare_text(seg.text)
            if not text:
                continue
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
                tmp = tf.name
            try:
                eng = pyttsx3.init()
                if voice:
                    eng.setProperty("voice", voice)
                if self.rate:
                    eng.setProperty("rate", 175 + self.rate)
                eng.save_to_file(text, tmp)
                eng.runAndWait()
                eng.stop()
                data, sr = read_wav(tmp)
                if len(data):
                    chunks.append(resample(data, sr, SAMPLE_RATE))
            except Exception as e:
                self._log(f"SAPI: ошибка ({e})")
            finally:
                try:
                    os.unlink(tmp)
                except Exception:
                    pass
            if seg.pause_after_ms:
                chunks.append(silence(seg.pause_after_ms))
        out = [c for c in chunks if len(c)]
        return np.concatenate(out) if out else np.zeros(0, dtype=np.float32)
