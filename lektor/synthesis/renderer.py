# -*- coding: utf-8 -*-
"""Рендер: реплики -> аудиофайл. Точные паузы, ровная громкость, темп.

Требование 11: межсинтагменная пауза 150–300 мс, между предложениями
400–600 мс — двигатели дают микро-паузы сами, а точные значения вставляются
здесь, на уровне аудио (не зависят от движка).
"""
from __future__ import annotations

import os
import time
from typing import Callable, Optional

import numpy as np

from ..config import SAMPLE_RATE
from .audio import (WavWriter, normalize_rms, peak_normalize, silence,
                    time_stretch, trim_edges, fade, wav_to_mp3)
from .backends import Utterance


class Renderer:
    def __init__(self, backend, voice: str, speed: float = 1.0,
                 inter_pause_scale: float = 1.0,
                 progress: Callable = None, cancel_event=None,
                 sample_rate: int = SAMPLE_RATE):
        self.backend = backend
        self.voice = voice
        self.speed = speed
        self.inter_pause_scale = inter_pause_scale
        self.progress = progress or (lambda *a, **k: None)
        self.cancel_event = cancel_event
        self.sample_rate = sample_rate

    # ------------------------------------------------------------------
    def render(self, utterances, wav_path: str) -> float:
        """Синтезирует реплики в WAV-файл, возвращает длительность в секундах."""
        writer = WavWriter(wav_path, self.sample_rate)
        total = len(utterances)
        try:
            for i, utt in enumerate(utterances):
                if self.cancel_event is not None and self.cancel_event.is_set():
                    break
                try:
                    chunk = self.backend.synth(utt, self.voice)
                except Exception as e:
                    self.progress(i, total, f"ошибка синтеза: {e}")
                    chunk = np.zeros(0, dtype=np.float32)
                if len(chunk):
                    chunk = trim_edges(chunk, self.sample_rate)
                    chunk = normalize_rms(chunk)
                    if utt.gain_db:
                        chunk = chunk * (10.0 ** (utt.gain_db / 20.0))
                    chunk = peak_normalize(chunk)
                    chunk = fade(chunk, self.sample_rate)
                    if abs(self.speed - 1.0) >= 0.02:
                        chunk = time_stretch(chunk, self.speed, self.sample_rate)
                    writer.write(chunk)
                # пауза после реплики (между предложениями)
                pause_ms = utt.segments[-1].pause_after_ms if utt.segments else 0
                if pause_ms:
                    writer.write(silence(pause_ms * self.inter_pause_scale, self.sample_rate))
                self.progress(i + 1, total, utt.text[:60])
        finally:
            writer.close()
        return writer.duration

    # ------------------------------------------------------------------
    @staticmethod
    def export(wav_path: str, fmt: str = "mp3", bitrate: int = 128) -> str:
        """Конвертирует WAV в итоговый формат. Возвращает путь к файлу."""
        if fmt == "wav":
            return wav_path
        mp3_path = os.path.splitext(wav_path)[0] + ".mp3"
        if wav_to_mp3(wav_path, mp3_path, bitrate):
            try:
                os.unlink(wav_path)
            except Exception:
                pass
            return mp3_path
        return wav_path  # MP3 недоступен — оставляем WAV
