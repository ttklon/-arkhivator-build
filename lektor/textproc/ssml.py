# -*- coding: utf-8 -*-
"""Поддержка SSML-разметки во входном тексте (требование 13).

Пользователь может вручную управлять паузами и ударениями, не правя код:
  <break time="500ms"/>       — пауза заданной длительности;
  <emphasis>слово</emphasis>  — логическое ударение на слове;
  <prosody rate="slow">…</prosody> — темп фрагмента (slow|medium|fast);
  <prosody pitch="low">…</prosody> — тон фрагмента (low|medium|high).

Разметка извлекается из текста и превращается в директивы для конвейера.
Прочие теги SSML удаляются (с пометкой в отчёт).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional

from ..report import Report


@dataclass
class BreakDirective:
    pos: int                 # позиция (символ) в очищенном тексте
    time_ms: int


@dataclass
class EmphasisDirective:
    word: str
    pos: int


@dataclass
class ProsodyDirective:
    rate: Optional[str] = None
    pitch: Optional[str] = None
    start: int = 0
    end: int = 0


@dataclass
class SSMLResult:
    text: str = ""
    breaks: List[BreakDirective] = field(default_factory=list)
    emphases: List[EmphasisDirective] = field(default_factory=list)
    prosody: List[ProsodyDirective] = field(default_factory=list)
    used: bool = False


_TIME_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(ms|s)?")


def _parse_time(value: str) -> int:
    m = _TIME_RE.match(value or "")
    if not m:
        return 300
    t = float(m.group(1))
    unit = m.group(2) or "ms"
    ms = t * 1000 if unit == "s" else t
    return max(50, min(int(ms), 10000))


_BREAK = re.compile(r'<break\s+time\s*=\s*["\']([^"\']+)["\']\s*/?>', re.IGNORECASE)
_EMPH = re.compile(r"<emphasis>(.*?)</emphasis>", re.IGNORECASE | re.DOTALL)
_PROS = re.compile(r"<prosody([^>]*)>(.*?)</prosody>", re.IGNORECASE | re.DOTALL)
_TAG = re.compile(r"</?[a-zA-Z][a-zA-Z0-9:_-]*(\s[^>]*)?/?>")


def extract_ssml(text: str, report: Report = None) -> SSMLResult:
    """Извлекает поддерживаемые SSML-директивы, возвращает чистый текст.

    Позиции директив отсчитываются в ОЧИЩЕННОМ тексте (без тегов),
    поэтому конвейер может сопоставить их словам предложения.
    """
    res = SSMLResult()
    if "<" not in text:
        res.text = text
        return res

    master = re.compile(
        r"<break\s+time\s*=\s*[\"']([^\"']+)[\"']\s*/?>"
        r"|<emphasis[^>]*>(.*?)</emphasis>"
        r"|<prosody([^>]*)>(.*?)</prosody>",
        re.IGNORECASE | re.DOTALL)

    out: List[str] = []
    pos = 0

    for m in master.finditer(text):
        out.append(text[pos:m.start()])
        cur = sum(map(len, out))
        if m.group(1) is not None:                       # <break time="…"/>
            res.breaks.append(BreakDirective(pos=cur, time_ms=_parse_time(m.group(1))))
            out.append(" ")
            res.used = True
        elif m.group(2) is not None:                     # <emphasis>слово</emphasis>
            inner = m.group(2).strip()
            if inner:
                first = inner.split()[0]
                res.emphases.append(EmphasisDirective(word=first, pos=cur))
                out.append(inner + " ")
                res.used = True
            out.append("")
        else:                                            # <prosody …>…</prosody>
            attrs, inner = m.group(3) or "", m.group(4) or ""
            rate = re.search(r"rate\s*=\s*[\"']([^\"']+)[\"']", attrs)
            pitch = re.search(r"pitch\s*=\s*[\"']([^\"']+)[\"']", attrs)
            if rate or pitch:
                out.append(inner)
                end = sum(map(len, out))
                res.prosody.append(ProsodyDirective(
                    rate=rate.group(1) if rate else None,
                    pitch=pitch.group(1) if pitch else None,
                    start=cur, end=end))
                res.used = True
            else:
                out.append(inner)
        pos = m.end()
    out.append(text[pos:])
    res.text = "".join(out)

    leftovers = _TAG.findall(res.text)
    if leftovers and report is not None:
        names = sorted({t.lower() for t in leftovers})[:8]
        report.add("ssml", "SSML-теги",
                   f"поддержаны break/emphasis/prosody; удалены: {', '.join(names)}",
                   "эти теги движком не поддерживаются")
    res.text = _TAG.sub("", res.text)
    return res
