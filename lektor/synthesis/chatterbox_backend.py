# -*- coding: utf-8 -*-
"""Движок Chatterbox Multilingual (HD-режим) — самый живой русский голос.

Resemble AI, лицензия MIT, модель 500M. Работает на NVIDIA (6+ ГБ видеопамяти)
или медленно на CPU. Поддерживает клонирование голоса из любого аудиообразца:
достаточно указать файл-образец (10–20 секунд чистой речи).

Разметку ударений «+» не понимает — текст очищается от неё; паузы движок
берёт из пунктуации, точные паузы вставляются на уровне аудио.
"""
from __future__ import annotations

import os
import re
import threading
from typing import List, Optional

import numpy as np

from ..config import SAMPLE_RATE
from .backends import Backend, Segment, Utterance, VoiceDef
from .audio import silence, resample

MAX_CHARS = 280  # рекомендация для стабильной генерации


class ChatterboxBackend(Backend):
    id = "chatterbox"
    label = "Chatterbox HD — самый живой голос"
    supports_stress_marks = False
    needs_gpu = True

    def __init__(self, sample_path: str = "", exaggeration: float = 0.4,
                 cfg_weight: float = 0.3, temperature: float = 0.8, log=print):
        self.sample_path = sample_path if sample_path and os.path.exists(sample_path) else ""
        self.exaggeration = exaggeration
        self.cfg_weight = cfg_weight
        self.temperature = temperature
        self._log = log
        self._model = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    @staticmethod
    def is_available() -> bool:
        try:
            import chatterbox  # noqa
            return True
        except Exception:
            return False

    @staticmethod
    def gpu_ready() -> bool:
        try:
            import torch
            if not torch.cuda.is_available():
                return False
            return torch.cuda.get_device_properties(0).total_memory >= 5 * 1024 ** 3
        except Exception:
            return False

    def voices(self) -> List[VoiceDef]:
        v = [VoiceDef("hd_default", "HD-голос по умолчанию" +
                      (" (клонирован из образца)" if self.sample_path else ""), self.id)]
        return v

    # ------------------------------------------------------------------
    def warm_up(self, voice: str) -> None:
        if self._model is not None:
            return
        with self._lock:
            if self._model is not None:
                return
            import torch
            from chatterbox.mtl_tts import ChatterboxMultilingualTTS
            device = "cuda" if torch.cuda.is_available() else "cpu"
            self._log(f"Chatterbox HD: загрузка модели на {device}…")
            self._model = ChatterboxMultilingualTTS.from_pretrained(device=torch.device(device))

    # ------------------------------------------------------------------
    def prepare_text(self, text: str) -> str:
        text = text.replace("+", "")
        text = re.sub(r"[«»()]", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    # ------------------------------------------------------------------
    def synth(self, utterance: Utterance, voice: str) -> np.ndarray:
        self.warm_up(voice)
        chunks: List[np.ndarray] = []
        for seg in utterance.segments:
            text = self.prepare_text(seg.text)
            if not text:
                continue
            pieces = self._split(text)
            for piece in pieces:
                wav = self._generate(piece)
                if wav is None:
                    continue
                chunks.append(wav)
                chunks.append(silence(60))  # дыхание между кусками
            if seg.pause_after_ms:
                chunks.append(silence(seg.pause_after_ms))
        out = [c for c in chunks if len(c)]
        return np.concatenate(out) if out else np.zeros(0, dtype=np.float32)

    def _split(self, text: str) -> List[str]:
        """Длинные сегменты режем по запятым/пробелам до 280 символов."""
        if len(text) <= MAX_CHARS:
            return [text]
        parts = re.split(r"(?<=[,;:])\s+", text)
        out, cur = [], ""
        for p in parts:
            if len(cur) + len(p) + 1 <= MAX_CHARS:
                cur = (cur + " " + p).strip()
            else:
                if cur:
                    out.append(cur)
                while len(p) > MAX_CHARS:  # сверхдлинный кусок — по словам
                    cut = p.rfind(" ", 0, MAX_CHARS)
                    cut = cut if cut > MAX_CHARS // 2 else MAX_CHARS
                    out.append(p[:cut])
                    p = p[cut:].lstrip()
                cur = p
        if cur:
            out.append(cur)
        return out

    def _generate(self, text: str) -> Optional[np.ndarray]:
        try:
            import torch
            kw = dict(language_id="ru",
                      exaggeration=self.exaggeration,
                      cfg_weight=self.cfg_weight,
                      temperature=self.temperature)
            if self.sample_path:
                kw["audio_prompt_path"] = self.sample_path
            wav = self._model.generate(text, **kw)
            if isinstance(wav, torch.Tensor):
                wav = wav.detach().cpu().numpy().squeeze()
            wav = np.asarray(wav, dtype=np.float32).squeeze()
            sr = int(getattr(self._model, "sr", 24000) or 24000)
            return resample(wav, sr, SAMPLE_RATE)
        except Exception as e:
            self._log(f"Chatterbox: ошибка генерации ({e}); пропускаю фрагмент")
            return None
