# -*- coding: utf-8 -*-
"""Аудио-слой: потоковый MP3, рендер сразу в MP3, чистка кэша."""
import os

import numpy as np

from lektor.synthesis.audio import Mp3Writer, silence
from lektor.synthesis.backends import Segment, Utterance, VoiceDef
from lektor.synthesis.backends import Backend
from lektor.synthesis.renderer import Renderer


class SineBackend(Backend):
    id = "sine"
    label = "Синус для тестов"
    supports_stress_marks = True

    def voices(self):
        return [VoiceDef("sine", "Синус", self.id)]

    def warm_up(self, voice):
        pass

    def prepare_text(self, text):
        return text

    def synth(self, utterance: Utterance, voice: str) -> np.ndarray:
        sr = 24000
        n = sum(len(s.text) for s in utterance.segments) * 100 + 2400
        t = np.linspace(0.0, 1.0, n, dtype=np.float32)
        return (0.3 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)


def _utt(text="проверка"):
    return [Utterance(segments=[Segment(text=text, pause_after_ms=100)])]


def test_mp3_writer_smoke(tmp_path):
    path = str(tmp_path / "out.mp3")
    w = Mp3Writer(path, sample_rate=24000)
    t = np.linspace(0.0, 1.0, 24000, dtype=np.float32)
    w.write((0.5 * np.sin(2 * np.pi * 440 * t)).astype(np.float32))
    w.write(silence(200, 24000))
    dur = w.duration
    w.close()
    assert os.path.exists(path)
    assert os.path.getsize(path) > 2000
    assert 1.0 < dur < 1.4
    with open(path, "rb") as f:
        head = f.read(3)
    # mp3-поток: ID3-тег или синхробайт кадра
    assert head[:3] == b"ID3" or head[0] == 0xFF


def test_renderer_direct_mp3(tmp_path):
    path = str(tmp_path / "direct.mp3")
    r = Renderer(SineBackend(), "sine", sample_rate=24000,
                 cache_dir=str(tmp_path / "cache"))
    dur = r.render(_utt("проверка поточного вывода в mp3"), path)
    assert os.path.exists(path)
    assert os.path.getsize(path) > 2000
    assert dur > 0.1
    assert not os.path.exists(str(tmp_path / "direct.wav"))


def test_renderer_cache_roundtrip(tmp_path):
    cache = str(tmp_path / "cache")
    calls = [0]

    class Counting(SineBackend):
        def synth(self, utterance, voice):
            calls[0] += 1
            return super().synth(utterance, voice)

    r1 = Renderer(Counting(), "sine", sample_rate=24000, cache_dir=cache)
    r1.render(_utt(), str(tmp_path / "a.wav"))
    assert calls[0] == 1
    r2 = Renderer(Counting(), "sine", sample_rate=24000, cache_dir=cache)
    r2.render(_utt(), str(tmp_path / "b.wav"))
    assert calls[0] == 1          # второй раз — из кэша
    assert r2.cache_hits == 1


def test_cache_prune(tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    # 3 «старых» файла по ~600 КБ
    old = []
    for i in range(3):
        p = cache / f"old{i}.npy"
        np.save(p, np.zeros(150_000, dtype=np.float32))
        old.append(p)
    r = Renderer(SineBackend(), "sine", sample_rate=24000, cache_dir=str(cache))
    r._prune_cache(hard_limit_mb=1, keep_mb=0)
    assert not old[0].exists() and not old[1].exists()


class BrokenBackend(SineBackend):
    id = "broken"

    def synth(self, utterance, voice):
        raise RuntimeError("модель не загрузилась")


def test_render_all_failed_raises(tmp_path):
    """Полный отказ синтеза — ошибка, а не «аудио из одних пауз»."""
    import pytest
    from lektor.synthesis.backends import Utterance, Segment
    path = str(tmp_path / "тишина.mp3")
    r = Renderer(BrokenBackend(), "sine", sample_rate=24000)
    utts = [Utterance(segments=[Segment(text=f"слово {i}", pause_after_ms=300)])
            for i in range(5)]
    with pytest.raises(RuntimeError):
        r.render(utts, path)
    assert not os.path.exists(path)
    assert r.failed == 3  # ранний выход после трёх неудач подряд


def test_render_partial_failure_keeps_file(tmp_path):
    """Частичный отказ — файл создаётся, счётчик ошибок доступен."""
    from lektor.synthesis.backends import Utterance, Segment

    class HalfBroken(SineBackend):
        def __init__(self):
            self.calls = 0

        def synth(self, utterance, voice):
            self.calls += 1
            if self.calls > 2:
                raise RuntimeError("сбой")
            return super().synth(utterance, voice)

    path = str(tmp_path / "частичный.wav")
    r = Renderer(HalfBroken(), "sine", sample_rate=24000,
                 cache_dir=str(tmp_path / "cache"))
    utts = [Utterance(segments=[Segment(text=f"различная реплика {i}",
                                        pause_after_ms=100)])
            for i in range(4)]
    dur = r.render(utts, path)  # не должно поднимать ошибку
    assert os.path.exists(path)
    assert r.failed == 2
    assert dur > 0.1


def test_mp3_id3_tags(tmp_path):
    """MP3 несёт ID3-тег: плееры покажут название и автора (кириллица)."""
    path = str(tmp_path / "tagged.mp3")
    w = Mp3Writer(path, sample_rate=24000,
                  meta={"title": "Лекция о договоре", "artist": "Лектор",
                        "album": "Аудиолекции", "year": "2026"})
    t = np.linspace(0.0, 1.0, 12000, dtype=np.float32)
    w.write((0.4 * np.sin(2 * np.pi * 330 * t)).astype(np.float32))
    w.close()
    data = open(path, "rb").read()
    assert data[:3] == b"ID3"
    # размер тега (synchsafe) корректен, за тегом идут mp3-кадры
    size = ((data[6] & 0x7F) << 21) | ((data[7] & 0x7F) << 14) | \
           ((data[8] & 0x7F) << 7) | (data[9] & 0x7F)
    assert 10 + size < len(data)
    assert b"\xff" in data[10 + size: 10 + size + 4]
    # кириллица в заголовке (UTF-16)
    assert "Лекция о договоре".encode("utf-16") in data
    assert b"TIT2" in data and b"TPE1" in data


def test_prune_cache(tmp_path, monkeypatch):
    """Кэш синтеза не растёт бесконечно: самые старые файлы удаляются."""
    import os
    import time
    from lektor.synthesis import renderer
    monkeypatch.setattr(renderer, "CACHE_DIR", str(tmp_path))
    for i in range(4):
        p = tmp_path / f"old{i}.npy"
        p.write_bytes(b"x" * 100)          # 4 x 100 байт
        ts = time.time() - 86400 * (10 - i)  # чем меньше i, тем старше
        os.utime(p, (ts, ts))
    removed = renderer.prune_cache(0.0002)   # лимит ~200 байт
    files = list(tmp_path.glob("old*.npy"))
    assert removed == 2 and len(files) == 2
    # самые СТАРЫЕ удалены
    assert all(f.stat().st_mtime > time.time() - 86400 * 9 for f in files)
