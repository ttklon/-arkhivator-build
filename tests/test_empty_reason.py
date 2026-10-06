# -*- coding: utf-8 -*-
"""Итерация 41: внятная причина, когда аудио не создано."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lektor.config import load_settings
from lektor.pipeline import Pipeline


def _run(text, tmp):
    return Pipeline(load_settings()).run(text, "пусто", str(tmp))


def test_only_punctuation_gives_reason(tmp_path):
    """Знаки без слов: любая из двух причин — но не пустое молчание."""
    res = _run("!!! ??? ... ,,, ;;; ::: ((()))", tmp_path)
    assert not res.audio_path
    assert res.empty_reason
    assert ("не осталось" in res.empty_reason
            or "предложения" in res.empty_reason)


def test_whitespace_only_gives_reason(tmp_path):
    res = _run("   \n\t  \n\n", tmp_path)
    assert not res.audio_path
    assert res.empty_reason


def test_normal_text_has_no_empty_reason(tmp_path):
    res = _run("Первое предложение. Второе предложение.", tmp_path)
    assert res.audio_path
    assert res.empty_reason == ""
