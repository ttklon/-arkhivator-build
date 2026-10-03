# -*- coding: utf-8 -*-
"""Рендер: реплики -> аудиофайл. Точные паузы, ровная громкость, темп.

Требование 11: межсинтагменная пауза 150–300 мс, между предложениями
400–600 мс — двигатели дают микро-паузы сами, а точные значения вставляются
здесь, на уровне аудио (не зависят от движка).
"""
from __future__ import annotations

import hashlib
import os
from typing import Callable, Optional

import numpy as np

from ..config import CACHE_DIR, SAMPLE_RATE
from .audio import (WavWriter, normalize_rms, peak_normalize, silence,
                    time_stretch, trim_edges, fade, wav_to_mp3)
from .backends import Utterance


class Renderer:
    def __init__(self, backend, voice: str, speed: float = 1.0,
                 inter_pause_scale: float = 1.0,
                 progress: Callable = None, cancel_event=None,
                 sample_rate: int = SAMPLE_RATE, cache_dir: str = None):
        self.backend = backend
        self.voice = voice
        self.speed = speed
        self.inter_pause_scale = inter_pause_scale
        self.progress = progress or (lambda *a, **k: None)
        self.cancel_event = cancel_event
        self.sample_rate = sample_rate
        # кэш на диск: повторная сборка того же текста почти мгновенна
        self.cache_dir = cache_dir if cache_dir is not None else CACHE_DIR
        self.cache_hits = 0
        self.cache_misses = 0

    # ------------------------------------------------------------------
    def _cache_key(self, utt: Utterance) -> str:
        parts = [self.backend.id, self.voice, f"{self.sample_rate}"]
        for sg in utt.segments:
            parts.append("|".join([sg.text, str(sg.pause_after_ms),
                                   str(sg.rate), str(sg.pitch),
                                   str(sg.emphasize_word), str(sg.question_rise)]))
        raw = "\x1f".join(parts).encode("utf-8")
        return hashlib.sha1(raw).hexdigest()

    def _synth_cached(self, utt: Utterance) -> np.ndarray:
        if not self.cache_dir:
            return self.backend.synth(utt, self.voice)
        try:
            os.makedirs(self.cache_dir, exist_ok=True)
        except Exception:
            return self.backend.synth(utt, self.voice)
        path = os.path.join(self.cache_dir, self._cache_key(utt) + ".npy")
        if os.path.exists(path):
            try:
                data = np.load(path)
                self.cache_hits += 1
                self.progress(-1, -1, "из кэша")
                return data
            except Exception:
                pass
        data = self.backend.synth(utt, self.voice)
        self.cache_misses += 1
        try:
            np.save(path, data)
        except Exception:
            pass
        return data

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
                    chunk = self._synth_cached(utt)
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
