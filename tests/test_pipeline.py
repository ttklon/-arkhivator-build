# -*- coding: utf-8 -*-
"""Сквозной прогон конвейера без нейросетей (dry-run + стаб-движок)."""
import os

import numpy as np
import pytest

from lektor.config import Settings, load_settings, ensure_dirs
from lektor.pipeline import Pipeline
from lektor.report import Report
from lektor.synthesis.backends import Backend, Segment, Utterance, VoiceDef
from lektor.synthesis.renderer import Renderer

TEXT = """
Лекция: освобождение от уголовной ответственности

Привет. Освободи, меня от уголовной ответственности — так, с лишней запятой, пишут в прошениях.

Дело возбуждено по ч. 2 ст. 159 УК РФ. Федеральный закон от 27 июля 2006 года № 149-ФЗ устанавливает:
а) порядок;
б) права.

Приговор, приговору, эксперт, осуждённый.
"""


class StubBackend(Backend):
    id = "stub"
    label = "Стаб (синусоида для тестов)"
    supports_stress_marks = True

    def voices(self):
        return [VoiceDef("stub", "Стаб-голос", self.id)]

    def warm_up(self, voice):
        pass

    def prepare_text(self, text):
        return text

    def synth(self, utterance: Utterance, voice: str) -> np.ndarray:
        parts = []
        sr = 48000
        for seg in utterance.segments:
            dur = 0.06 + len(seg.text) * 0.003
            t = np.linspace(0.0, 1.0, int(sr * dur), dtype=np.float32)
            parts.append((0.25 * np.sin(2 * np.pi * 200 * t)).astype(np.float32))
            if seg.pause_after_ms:
                parts.append(np.zeros(int(sr * seg.pause_after_ms / 1000), np.float32))
        return np.concatenate(parts) if parts else np.zeros(0, np.float32)


def test_dry_run_markup_and_report(tmp_path):
    settings = load_settings()
    pipe = Pipeline(settings)
    res = pipe.dry_run(TEXT, title="Проверка")
    assert res.markup, "разметка должна быть непустой"
    from lektor.lingua.stress import strip_stress
    plain = strip_stress(res.markup)
    # нормализация чисел и статей
    assert "статья сто пятьдесят девять" in plain
    assert "часть вторая" in plain or "части второй" in plain
    assert "двадцать седьмого июля" in plain
    assert "две тысячи шестого года" in plain
    # расшифровка УК РФ при первом упоминании
    assert "Уголовный кодекс Российской Федерации" in plain
    # вредная запятая исправлена и попала в отчёт
    assert any(e.kind == "comma" for e in res.report.events)
    joined = " ".join(plain.split("\n"))
    assert "Освободи, меня" not in joined
    # ударения расставлены
    assert "+" in res.markup


def test_render_to_wav_and_mp3(tmp_path):
    settings = load_settings()
    pipe = Pipeline(settings)
    pipe.report = Report("тест")
    from lektor.textproc.cleaner import Cleaner
    from lektor.textproc import ssml as ssml_mod
    clean = Cleaner(pipe.report, "skip").clean(TEXT)
    ssml_res = ssml_mod.extract_ssml(clean, pipe.report)
    utts, _ = pipe._analyze(ssml_res.text, ssml_res)
    assert utts

    wav = str(tmp_path / "out.wav")
    r = Renderer(StubBackend(), "stub", speed=1.0)
    dur = r.render(utts, wav)
    assert os.path.exists(wav) and dur > 1.0

    from lektor.synthesis.audio import wav_to_mp3
    mp3 = str(tmp_path / "out.mp3")
    ok = wav_to_mp3(wav, mp3)
    if ok:
        assert os.path.getsize(mp3) > 1000


def test_speed_stretch_no_crash(tmp_path):
    from lektor.synthesis.audio import time_stretch, silence
    data = 0.3 * np.sin(np.linspace(0, 100, 48000 * 2).astype(np.float32))
    for rate in (0.9, 1.0, 1.15):
        out = time_stretch(data.astype(np.float32), rate)
        assert len(out) > 1000


def test_ssml_breaks_respected(tmp_path):
    settings = load_settings()
    pipe = Pipeline(settings)
    text = "Первая часть фразы <break time=\"700ms\"/> вторая часть фразы."
    res = pipe.dry_run(text, title="SSML")
    import re as _re
    pauses = [int(x) for x in _re.findall(r"⟦(\d+) мс⟧", res.markup)]
    # брейк пользователя даёт паузу ~700 мс (плюс возможный акцент до +70 мс)
    assert any(650 <= p <= 780 for p in pauses), pauses
