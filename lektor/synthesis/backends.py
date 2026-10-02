# -*- coding: utf-8 -*-
"""Базовый интерфейс движка синтеза + реестр.

Каждый движок получает список сегментов (текст + пауза после + акценты)
и возвращает аудио float32 48 кГц. Движки взаимозаменяемы (тр. 27).
"""
from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np

from ..config import SAMPLE_RATE


@dataclass
class Segment:
    """Отрезок речи внутри одной реплики: текст + параметры просодии."""

    text: str
    pause_after_ms: int = 0          # пауза ПОСЛЕ сегмента
    emphasize_word: Optional[str] = None  # слово с логическим ударением
    rate: Optional[str] = None       # slow | fast | None (тр. 21)
    pitch: Optional[str] = None      # low | None
    final: bool = True               # последний сегмент реплики (тон завершения)

    def __len__(self):
        return len(self.text)


@dataclass
class Utterance:
    """Реплика (обычно предложение): сегменты + общая громкость."""

    segments: List[Segment] = field(default_factory=list)
    gain_db: float = 0.0             # например, -4 для сносок (тр. 26)

    @property
    def text(self) -> str:
        return " ".join(s.text for s in self.segments)


@dataclass
class VoiceDef:
    id: str
    label: str
    engine: str


class Backend(ABC):
    id: str = "?"
    label: str = "?"
    supports_stress_marks: bool = True   # понимает ли «+» перед ударной гласной
    needs_gpu: bool = False

    @abstractmethod
    def voices(self) -> List[VoiceDef]:
        ...

    @abstractmethod
    def warm_up(self, voice: str) -> None:
        """Загрузка модели (ленивая, один раз)."""
        ...

    @abstractmethod
    def synth(self, utterance: Utterance, voice: str) -> np.ndarray:
        """Реплика -> аудио float32 @ 48 кГц (включая внутренние паузы)."""
        ...

    def prepare_text(self, text: str) -> str:
        """Финальная подготовка текста для конкретного движка."""
        return text

    def describe(self) -> str:
        return self.label
