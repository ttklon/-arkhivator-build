# -*- coding: utf-8 -*-
"""Аудио-слой: потоковая запись WAV, экспорт MP3, нормализация громкости,
обрезка тишины, плавные стыки, ресемплинг, плавное изменение темпа (WSOLA).
"""
from __future__ import annotations

import os
import wave
from typing import Optional

import numpy as np

from ..config import SAMPLE_RATE


# ---------------------------------------------------------------------------
# WAV (потоковая запись 16 бит, моно)
# ---------------------------------------------------------------------------
class WavWriter:
    def __init__(self, path: str, sample_rate: int = SAMPLE_RATE):
        self.path = path
        self.sample_rate = sample_rate
        self.frames = 0
        self._f = wave.open(path, "wb")
        self._f.setnchannels(1)
        self._f.setsampwidth(2)
        self._f.setframerate(sample_rate)

    def write(self, chunk: np.ndarray) -> None:
        if chunk is None or len(chunk) == 0:
            return
        pcm = np.clip(chunk, -1.0, 1.0)
        self._f.writeframes((pcm * 32767.0).astype(np.int16).tobytes())
        self.frames += len(chunk)

    @property
    def duration(self) -> float:
        return self.frames / self.sample_rate

    def close(self) -> None:
        try:
            self._f.close()
        except Exception:
            pass


def id3v2_tag(meta: dict) -> bytes:
    """ID3v2.3-тег с кириллицей (UTF-16) — плееры покажут название и автора."""
    def frame(fid: str, text: str) -> bytes:
        payload = b"\x01" + text.encode("utf-16")   # 1 = UTF-16 c BOM
        size = len(payload).to_bytes(4, "big")
        return fid.encode("ascii") + size + b"\x00\x00" + payload

    frames = b""
    if meta.get("title"):
        frames += frame("TIT2", str(meta["title"]))
    if meta.get("artist"):
        frames += frame("TPE1", str(meta["artist"]))
    if meta.get("album"):
        frames += frame("TALB", str(meta["album"]))
    if meta.get("year"):
        frames += frame("TYER", str(meta["year"]))
    if meta.get("genre"):
        frames += frame("TCON", str(meta["genre"]))
    if not frames:
        return b""
    n = len(frames)
    syncsafe = bytes([(n >> 21) & 0x7F, (n >> 14) & 0x7F, (n >> 7) & 0x7F, n & 0x7F])
    return b"ID3" + bytes([3, 0, 0]) + syncsafe + frames


class Mp3Writer:
    """Потоковая запись MP3 (моно) — большие книги не требуют
    промежуточного WAV на много гигабайт."""

    def __init__(self, path: str, sample_rate: int = SAMPLE_RATE, bitrate: int = 128,
                 meta: dict = None):
        import lameenc
        self.path = path
        self.sample_rate = sample_rate
        self.frames = 0
        self._enc = lameenc.Encoder()
        self._enc.set_bit_rate(bitrate)
        self._enc.set_in_sample_rate(sample_rate)
        self._enc.set_channels(1)
        self._enc.set_quality(2)
        self._f = open(path, "wb")
        if meta:
            try:
                self._f.write(id3v2_tag(meta))
            except Exception:
                pass

    def write(self, chunk: np.ndarray) -> None:
        if chunk is None or len(chunk) == 0:
            return
        pcm = np.clip(chunk, -1.0, 1.0)
        data = (pcm * 32767.0).astype(np.int16).tobytes()
        self._f.write(self._enc.encode(data))
        self.frames += len(chunk)

    @property
    def duration(self) -> float:
        return self.frames / self.sample_rate

    def close(self) -> None:
        try:
            self._f.write(self._enc.flush())
            self._f.close()
        except Exception:
            pass


def read_wav(path: str) -> tuple[np.ndarray, int]:
    with wave.open(path, "rb") as f:
        sr = f.getframerate()
        n = f.getnframes()
        data = np.frombuffer(f.readframes(n), dtype=np.int16).astype(np.float32) / 32767.0
    return data, sr


# ---------------------------------------------------------------------------
# MP3 (lameenc, потоково из WAV-файла)
# ---------------------------------------------------------------------------
def wav_to_mp3(wav_path: str, mp3_path: str, bitrate: int = 128,
               meta: dict = None) -> bool:
    try:
        import lameenc
    except ImportError:
        return False
    try:
        with wave.open(wav_path, "rb") as f:
            sr, ch, sw = f.getframerate(), f.getnchannels(), f.getsampwidth()
            enc = lameenc.Encoder()
            enc.set_bit_rate(bitrate)
            enc.set_in_sample_rate(sr)
            enc.set_channels(ch)
            enc.set_quality(2)
            with open(mp3_path, "wb") as out:
                if meta:
                    try:
                        out.write(id3v2_tag(meta))
                    except Exception:
                        pass
                while True:
                    raw = f.readframes(sr * ch)  # по ~1 секунде
                    if not raw:
                        break
                    out.write(enc.encode(raw))
                out.write(enc.flush())
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Обработка звука
# ---------------------------------------------------------------------------
def silence(ms: float, sample_rate: int = SAMPLE_RATE) -> np.ndarray:
    n = int(sample_rate * ms / 1000.0)
    return np.zeros(max(0, n), dtype=np.float32)


def rms(chunk: np.ndarray) -> float:
    if len(chunk) == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(chunk.astype(np.float64)))))


def normalize_rms(chunk: np.ndarray, target: float = 0.075) -> np.ndarray:
    """Приводит фрагмент к целевой средней громкости (ровный голос лекции)."""
    r = rms(chunk)
    if r < 1e-5:
        return chunk
    gain = target / r
    if gain > 8.0:
        gain = 8.0
    return (chunk * gain).astype(np.float32)


def peak_normalize(chunk: np.ndarray, ceiling: float = 0.94) -> np.ndarray:
    peak = float(np.max(np.abs(chunk))) if len(chunk) else 0.0
    if peak > ceiling:
        return (chunk * (ceiling / peak)).astype(np.float32)
    return chunk


def trim_edges(chunk: np.ndarray, sample_rate: int = SAMPLE_RATE,
               thresh: float = 0.004, pad_ms: int = 20) -> np.ndarray:
    """Обрезает тишину в начале и конце фрагмента (движки её добавляют сами)."""
    if len(chunk) == 0:
        return chunk
    win = int(sample_rate * 0.02)
    if len(chunk) <= win * 2:
        return chunk
    abs_chunk = np.abs(chunk)
    n = len(chunk)
    lo = 0
    while lo < n - win and float(np.max(abs_chunk[lo:lo + win])) < thresh:
        lo += win // 2
    hi = n
    while hi > win and float(np.max(abs_chunk[hi - win:hi])) < thresh:
        hi -= win // 2
    pad = int(sample_rate * pad_ms / 1000)
    lo = max(0, lo - pad)
    hi = min(n, hi + pad)
    if hi - lo < int(sample_rate * 0.05):
        return chunk
    return chunk[lo:hi].copy()


def fade(chunk: np.ndarray, sample_rate: int = SAMPLE_RATE, ms: float = 6.0) -> np.ndarray:
    n = int(sample_rate * ms / 1000)
    if len(chunk) <= 2 * n or n == 0:
        return chunk
    env = np.linspace(0.0, 1.0, n, dtype=np.float32)
    out = chunk.copy()
    out[:n] *= env
    out[-n:] *= env[::-1]
    return out


def resample(chunk: np.ndarray, src_sr: int, dst_sr: int = SAMPLE_RATE) -> np.ndarray:
    if src_sr == dst_sr or len(chunk) == 0:
        return chunk.astype(np.float32)
    try:
        from scipy.signal import resample_poly
        from math import gcd
        g = gcd(int(src_sr), int(dst_sr))
        return resample_poly(chunk, dst_sr // g, src_sr // g).astype(np.float32)
    except Exception:
        t = np.linspace(0.0, len(chunk) - 1, int(len(chunk) * dst_sr / src_sr))
        return np.interp(t, np.arange(len(chunk)), chunk).astype(np.float32)


# ---------------------------------------------------------------------------
# Изменение темпа без изменения высоты тона (WSOLA) — требование 21
# ---------------------------------------------------------------------------
def time_stretch(chunk: np.ndarray, rate: float, sample_rate: int = SAMPLE_RATE) -> np.ndarray:
    """rate > 1 — быстрее, rate < 1 — медленнее (например, 0.9 = на 10 % медленнее)."""
    if abs(rate - 1.0) < 0.02 or len(chunk) < sample_rate // 4:
        return chunk
    rate = max(0.5, min(2.0, rate))
    frame = int(0.040 * sample_rate)          # 40 мс
    overlap = frame // 2
    hop_out = frame - overlap
    hop_in = int(round(hop_out * rate))

    n_out = int(len(chunk) / rate) + frame
    out = np.zeros(n_out, dtype=np.float32)
    win = np.hanning(frame).astype(np.float32)

    pos_in, pos_out = 0, 0
    prev_tail: Optional[np.ndarray] = None
    while pos_in + frame < len(chunk) and pos_out + frame < n_out:
        seg = chunk[pos_in:pos_in + frame]
        if prev_tail is not None:
            # WSOLA: ищем лучшее совмещение с хвостом предыдущего кадра
            tail_len = overlap
            target = prev_tail[:tail_len]
            best_off = 0
            best_score = -1e18
            search = seg[: tail_len * 2] if len(seg) >= tail_len * 2 else seg
            for off in range(0, max(1, len(search) - tail_len), tail_len // 8 or 1):
                cand = search[off:off + tail_len]
                if len(cand) < tail_len:
                    break
                score = float(np.dot(cand, target))
                if score > best_score:
                    best_score, best_off = score, off
            seg = chunk[pos_in + best_off: pos_in + best_off + frame]
            if len(seg) < frame:
                break
        frame_out = seg * win
        if pos_out == 0:
            out[0:frame] = frame_out
        else:
            out[pos_out:pos_out + overlap] = np.maximum(
                out[pos_out:pos_out + overlap], 0)  # хвост уже записан
            out[pos_out + overlap: pos_out + frame] += frame_out[overlap:]
        prev_tail = seg
        pos_in += hop_in
        pos_out += hop_out

    result = out[:pos_out + frame]
    peak = float(np.max(np.abs(result))) if len(result) else 0.0
    if peak > 0.95:
        result *= 0.95 / peak
    return result.astype(np.float32)
