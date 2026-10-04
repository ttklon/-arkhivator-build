# -*- coding: utf-8 -*-
"""Движок Silero TTS — основной: быстрый, офлайн, точные ударения через «+».

Использует модели v5 (v5_cis_base — 29 русских голосов, лицензия MIT) или
v4_ru (5 голосов, CC BY-NC-SA — для личного обучения бесплатно).
Поддерживает SSML: <break time="..."/>, <prosody rate/pitch> — через них
реализуются точные паузы и темп (тр. 11, 21).

Модель не умеет сама ставить ударения в v5_cis_base — поэтому конвейер
помечает ударения знаком «+» сам (модуль lingua.stress).
"""
from __future__ import annotations

import os
import re
import threading
from typing import List, Optional
from xml.sax.saxutils import escape

import numpy as np

from ..config import MODELS_DIR, SAMPLE_RATE
from .backends import Backend, Segment, Utterance, VoiceDef

SILERO_URLS = {
    "v5_cis_base": "https://models.silero.ai/models/tts/ru/v5_cis_base.pt",
    "v5_5_ru": "https://models.silero.ai/models/tts/ru/v5_5_ru.pt",
    "v4_ru": "https://models.silero.ai/models/tts/ru/v4_ru.pt",
}

VOICES_RU = [
    ("xenia", "Ксения — женский"),
    ("baya", "Бая — женский"),
    ("kseniya", "Ксения (v3) — женский"),
    ("aidar", "Айдар — мужской"),
    ("eugene", "Евгений — мужской"),
]

VOICES_CIS = [
    ("ru_alexandr", "Александр — мужской"),
    ("ru_bogdan", "Богдан — мужской"),
    ("ru_dmitriy", "Дмитрий — мужской"),
    ("ru_eduard", "Эдуард — мужской"),
    ("ru_igor", "Игорь — мужской"),
    ("ru_marat", "Марат — мужской"),
    ("ru_roman", "Роман — мужской"),
    ("ru_gamat", "Гамат — мужской"),
    ("ru_safarhuja", "Сафархуджа — мужской"),
    ("ru_kejilgan", "Кежилган — мужской, в возрасте"),
    ("ru_albina", "Альбина — женский"),
    ("ru_aigul", "Айгуль — женский"),
    ("ru_alfia", "Альфия — женский"),
    ("ru_alfia2", "Альфия 2 — женский"),
    ("ru_ekaterina", "Екатерина — женский"),
    ("ru_karina", "Карина — женский"),
    ("ru_nurgul", "Нургуль — женский"),
    ("ru_oksana", "Оксана — женский"),
    ("ru_ramilia", "Рамиля — женский"),
    ("ru_saida", "Саида — женский"),
    ("ru_vika", "Вика — женский"),
    ("ru_zara", "Зара — женский"),
    ("ru_zhadyra", "Жадыра — женский"),
    ("ru_zhazira", "Жазира — женский"),
    ("ru_zinaida", "Зинаида — женский"),
    ("ru_kermen", "Кермен — женский"),
    ("ru_miyau", "Мияу"),
    ("ru_onaoy", "Онаой"),
    ("ru_sibday", "Сибдей"),
]

# Латиница -> кириллица (в алфавите модели латинских букв нет)
LATIN_MAP = {
    "a": "а", "b": "б", "c": "ц", "d": "д", "e": "е", "f": "ф", "g": "г",
    "h": "х", "i": "и", "j": "дж", "k": "к", "l": "л", "m": "м", "n": "н",
    "o": "о", "p": "п", "q": "кью", "r": "р", "s": "с", "t": "т", "u": "у",
    "v": "в", "w": "в", "x": "кс", "y": "й", "z": "з",
}

# алфавит модели: строчные И заглавные русские буквы, «+», пунктуация
BAD_CHARS = re.compile(
    r"[^абвгдеёжзийклмнопрстуфхцчшщъыьэюяАБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ\+ ,.!?\-…:;()«»]")


def translit(text: str) -> str:
    """Приблизительная транслитерация латиницы (редкие заимствования)."""
    def repl(m):
        w = m.group(0)
        out = []
        for ch in w:
            low = ch.lower()
            mapped = LATIN_MAP.get(low, "")
            if not mapped:
                out.append(ch)
            elif ch.isupper():
                out.append(mapped[0].upper() + mapped[1:])
            else:
                out.append(mapped)
        return "".join(out)

    return re.sub(r"[A-Za-z]{2,}", repl, text)


class SileroBackend(Backend):
    id = "silero"
    label = "Silero (быстрый и точный)"
    supports_stress_marks = True

    def __init__(self, models_dir: str = None, preferred: str = None, log=print):
        self.models_dir = models_dir or MODELS_DIR
        self._log = log
        self._model = None
        self._model_id: Optional[str] = None
        self._lock = threading.Lock()
        # какая модель доступна локально
        self.available = self._detect_models()
        self.preferred = preferred if preferred in self.available else (
            self.available[0] if self.available else None)

    # ------------------------------------------------------------------
    def _detect_models(self) -> List[str]:
        found = []
        for mid in ("v5_cis_base", "v5_5_ru", "v4_ru"):
            if os.path.exists(os.path.join(self.models_dir, mid + ".pt")):
                found.append(mid)
        return found

    def model_ready(self) -> bool:
        return bool(self.available)

    def voices(self) -> List[VoiceDef]:
        if self.preferred == "v5_cis_base":
            return [VoiceDef(v, label, self.id) for v, label in VOICES_CIS]
        return [VoiceDef(v, label, self.id) for v, label in VOICES_RU]

    # ------------------------------------------------------------------
    def warm_up(self, voice: str) -> None:
        if self._model is not None:
            return
        with self._lock:
            if self._model is not None:
                return
            import torch
            torch.set_grad_enabled(False)
            path = os.path.join(self.models_dir, (self.preferred or "v5_cis_base") + ".pt")
            if os.path.exists(path):
                with open(path, "rb") as f:
                    import io
                    buf = io.BytesIO(f.read())
                model = torch.package.PackageImporter(buf).load_pickle("tts_models", "model")
            else:
                # скачивание через torch.hub (нужен интернет, только один раз)
                mid = self.preferred or "v5_cis_base"
                model, _ = torch.hub.load(
                    repo_or_dir="snakers4/silero-models", model="silero_tts",
                    language="ru", speaker=mid, trust_repo=True, verbose=False)
            model.to(torch.device("cpu"))
            n = max(1, (os.cpu_count() or 2) // 2)
            try:
                torch.set_num_threads(n)
            except Exception:
                pass
            self._model = model
            self._model_id = self.preferred

    # ------------------------------------------------------------------
    def prepare_text(self, text: str) -> str:
        text = translit(text)
        # символы, которых нет в алфавите модели
        text = BAD_CHARS.sub(" ", text)
        text = re.sub(r"[«»()]", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    # ------------------------------------------------------------------
    def synth(self, utterance: Utterance, voice: str) -> np.ndarray:
        self.warm_up(voice)
        try:
            return self._synth_try(utterance, voice, use_ssml=True)
        except Exception:
            # SSML не разобрался — читаем простым текстом
            try:
                return self._synth_try(utterance, voice, use_ssml=False)
            except Exception:
                # слишком длинно — режем на части
                return self._synth_split(utterance, voice)

    def _synth_split(self, utterance: Utterance, voice: str) -> np.ndarray:
        parts = []
        for seg in utterance.segments:
            one = Utterance(segments=[Segment(text=seg.text, pause_after_ms=seg.pause_after_ms,
                                              final=seg.final)])
            try:
                parts.append(self._synth_try(one, voice, use_ssml=False))
                parts.append(np.zeros(int(SAMPLE_RATE * seg.pause_after_ms / 1000), dtype=np.float32))
            except Exception:
                continue
        return np.concatenate(parts) if parts else np.zeros(0, dtype=np.float32)

    # ------------------------------------------------------------------
    def _synth_try(self, utterance: Utterance, voice: str, use_ssml: bool) -> np.ndarray:
        import torch
        texts = [self.prepare_text(s.text) for s in utterance.segments]
        texts = [t for t in texts if t]
        if not texts:
            return np.zeros(0, dtype=np.float32)
        own = any("+" in t for t in texts)  # наша разметка ударений

        kw = dict(speaker=voice, sample_rate=SAMPLE_RATE,
                  put_accent=not own, put_yo=not own)
        if (self._model_id or "").startswith("v5"):
            kw.update(put_stress_homo=not own, put_yo_homo=not own,
                      stress_single_vowel=not own)

        if not use_ssml or all(s.pause_after_ms == 0 for s in utterance.segments):
            audio = self._call(text=" ".join(texts), **kw)
            return audio.numpy().astype(np.float32)

        ssml = self._build_ssml(utterance, texts)
        audio = self._call(ssml_text=ssml, **kw)
        return audio.numpy().astype(np.float32)

    def _call(self, **kwargs):
        """Вызов apply_tts с совместимостью параметров v4/v5."""
        try:
            return self._model.apply_tts(**kwargs)
        except TypeError:
            # старая модель не знает v5-параметров
            for k in ("put_stress_homo", "put_yo_homo", "stress_single_vowel"):
                kwargs.pop(k, None)
            return self._model.apply_tts(**kwargs)

    # ------------------------------------------------------------------
    def _build_ssml(self, utterance: Utterance, texts: List[str]) -> str:
        """SSML для Silero v5: разгон, паузы-брейки, просодия (тр. 11, 21)."""
        parts = ['<speak><break time="300ms"/>']
        segs = utterance.segments
        for i, (seg, text) in enumerate(zip(segs, texts)):
            inner = escape(text)
            # логическое ударение: тон выше + замедление (тр. 15–17),
            # формат проверен на слух в проекте audiobook-ru
            if seg.emphasize_word:
                word = escape(self.prepare_text(seg.emphasize_word))
                if word and word in inner:
                    inner = inner.replace(
                        word, f'<prosody pitch="x-high" rate="slow">{word}</prosody>', 1)
            # ИК-3: вопрос без вопросительного слова держится только на
            # подъёме тона — оборачиваем последнее слово (проверено на слух
            # в audiobook-ru: подъём без замедления)
            if seg.question_rise:
                words_list = inner.split(" ")
                if len(words_list) >= 1:
                    # «Подтверждаете ли вы…» — подъём на слове ПЕРЕД «ли»
                    # (смысловой глагол), как в живой речи; обычный полярный
                    # вопрос — подъём на последнем слове
                    li = next((i for i, w in enumerate(words_list)
                               if w.strip(".,!?;:…«»").lower() == "ли"), None)
                    idx = li - 1 if (li is not None and li > 0) \
                        else len(words_list) - 1
                    target = words_list[idx]
                    if target.strip(".,!?;:…«»"):
                        words_list[idx] = \
                            f'<prosody pitch="x-high">{target}</prosody>'
                        inner = " ".join(words_list)
            attrs = ""
            if seg.rate:
                attrs += f' rate="{seg.rate}"'
            if seg.pitch:
                attrs += f' pitch="{seg.pitch}"'
            if attrs:
                inner = f"<prosody{attrs}>{inner}</prosody>"
            parts.append(f"<s>{inner}</s>")
            if i < len(segs) - 1 and seg.pause_after_ms:
                parts.append(f'<break time="{int(seg.pause_after_ms)}ms"/>')
        parts.append("</speak>")
        return "".join(parts)
