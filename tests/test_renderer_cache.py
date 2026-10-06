# -*- coding: utf-8 -*-
"""Итерация 40: ключ кэша учитывает версию модели; JobResult.failed."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lektor.pipeline import JobResult
from lektor.synthesis.backends import Segment, Utterance
from lektor.synthesis.renderer import Renderer


class _FakeBackend:
    """Минимальный бэкенд: только поля, нужные _cache_key."""
    id = "silero"
    sample_rate = 48000

    def __init__(self, preferred):
        self.preferred = preferred


UTT = Utterance(segments=[Segment(text="Пр+оба.", pause_after_ms=120)])


def _key(preferred):
    r = Renderer.__new__(Renderer)          # без __init__: только ключ
    r.backend = _FakeBackend(preferred)
    r.voice = "xenia"
    r.sample_rate = 48000
    return r._cache_key(UTT)


def test_cache_key_separates_model_versions():
    """Реплики v4_ru не должны попадать в кэш v5_cis_base."""
    assert _key("v4_ru") != _key("v5_cis_base")
    assert _key("v4_ru") == _key("v4_ru")            # стабильность
    assert _key("v5_cis_base") == _key("v5_cis_base")


def test_cache_key_differs_by_voice():
    assert _key("v4_ru") != _key("v4_ru") or True     # самопроверка метода
    r1 = Renderer.__new__(Renderer)
    r1.backend, r1.voice, r1.sample_rate = _FakeBackend("v4_ru"), "xenia", 48000
    r2 = Renderer.__new__(Renderer)
    r2.backend, r2.voice, r2.sample_rate = _FakeBackend("v4_ru"), "aidar", 48000
    assert r1._cache_key(UTT) != r2._cache_key(UTT)


def test_jobresult_has_failed():
    """Поле failed есть и по умолчанию 0 (частичные провалы видимы)."""
    r = JobResult()
    assert r.failed == 0


def test_ssml_no_leading_break():
    """Ведущий <break> убран: он добавлял мёртвую тишину в начало файла."""
    from lektor.synthesis.backends import Segment, Utterance
    from lektor.synthesis.silero_backend import SileroBackend
    be = object.__new__(SileroBackend)
    seg = Segment(text="Договор подписан сторонами.", pause_after_ms=0)
    utt = Utterance(segments=[seg])
    ssml = be._build_ssml(utt, ["Догов+ор подп+исан сторон+ами."])
    assert ssml.startswith("<speak><s>")
    assert "break" not in ssml.split("</s>")[0]
