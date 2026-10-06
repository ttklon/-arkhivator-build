# -*- coding: utf-8 -*-
"""Итерация 39: устойчивость Silero — быстрый отказ без модели и
перебор зеркал при скачивании (без сети, всё на моках)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from lektor.synthesis.silero_backend import (
    MODEL_MIRRORS, SileroBackend, download_model)


class _FailFast:
    """Utterance-заглушка (не нужна для warm_up, но пригодится synth)."""


def test_warmup_fail_is_cached(monkeypatch, tmp_path):
    """Ошибка загрузки модели запоминается: вторая реплика не лезет в сеть."""
    import torch
    calls = {"n": 0}

    def boom(*a, **kw):
        calls["n"] += 1
        raise IOError("нет сети")

    monkeypatch.setattr(torch.hub, "load", boom)
    b = SileroBackend(models_dir=str(tmp_path), log=lambda m: None)
    assert not b.model_ready()
    with pytest.raises(RuntimeError) as e1:
        b.warm_up("xenia")
    assert "Модель голоса не загрузилась" in str(e1.value)
    assert calls["n"] == 1                       # одна попытка, не три
    with pytest.raises(RuntimeError) as e2:
        b.warm_up("xenia")
    assert str(e2.value) == str(e1.value)        # та же ошибка, без сети
    assert calls["n"] == 1                       # повторной загрузки НЕ было


def test_download_model_all_mirrors_fail(monkeypatch, tmp_path):
    """Если оба зеркала недоступны — внятная ошибка со всеми адресами."""
    import urllib.request
    from lektor.synthesis import silero_backend as sb
    calls = {"n": 0}

    def boom(url, path, reporthook=None):
        calls["n"] += 1
        raise IOError(f"сервер {url} недоступен")

    monkeypatch.setattr(urllib.request, "urlretrieve", boom)
    monkeypatch.setattr(sb, "MODELS_DIR", str(tmp_path))
    with pytest.raises(RuntimeError) as e:
        download_model(log=lambda m: None)
    assert "зеркала" in str(e.value)
    for url in MODEL_MIRRORS:
        assert url in str(e.value)               # видно, что именно не ответило
    assert calls["n"] == len(MODEL_MIRRORS)      # попробовали все
    assert not os.path.exists(str(tmp_path) + "/v5_cis_base.pt.part")


def test_mirrors_list_sane():
    """Основное зеркало — models.silero.ai, запасное — GitHub."""
    assert MODEL_MIRRORS[0].startswith("https://models.silero.ai/")
    assert any("github.com" in u for u in MODEL_MIRRORS)
