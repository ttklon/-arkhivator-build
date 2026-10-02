# -*- coding: utf-8 -*-
"""Отчёт об озвучке (требование 30).

Логирует все решения, где программа поступила не «буквально по пунктуации»:
запятые, проигнорированные как паузы, омографы, расшифровки аббревиатур,
преобразованные числа и т.д. Отчёт сохраняется рядом с аудиофайлом
(.txt для человека и .json для программной обработки).
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Optional


@dataclass
class Event:
    kind: str          # comma | homograph | abbr | number | user_stress | footnote | ssml | note
    title: str         # короткое описание для человека
    context: str = ""  # цитата из текста
    reason: str = ""   # обоснование решения


KIND_TITLES = {
    "comma": "Запятые, скорректированные по синтаксису",
    "homograph": "Омографы",
    "abbr": "Аббревиатуры",
    "number": "Числа, даты и номера",
    "user_stress": "Пользовательские ударения",
    "footnote": "Сноски и служебный текст",
    "ssml": "SSML-разметка",
    "note": "Примечания",
}


class Report:
    def __init__(self, title: str = "Озвучка"):
        self.title = title
        self.started = datetime.now()
        self.events: list[Event] = []
        self.stats: dict = {
            "слов": 0,
            "предложений": 0,
            "синтагм": 0,
            "длительность_аудио_сек": 0.0,
            "время_сборки_сек": 0.0,
        }

    # -- добавление событий -------------------------------------------------
    def add(self, kind: str, title: str, context: str = "", reason: str = "") -> Event:
        ev = Event(kind, title, context, reason)
        self.events.append(ev)
        return ev

    def comma_ignored(self, context: str, reason: str) -> None:
        self.add("comma", "Запятая проигнорирована как пауза", context, reason)

    def comma_weakened(self, context: str, reason: str) -> None:
        self.add("comma", "Пауза после запятой ослаблена", context, reason)

    def homograph_neutral(self, word: str, context: str) -> None:
        self.add("homograph", f"Омограф «{word}» — выбран нейтральный вариант",
                 context, "контекст неоднозначен, слово стоит проверить")

    def homograph_resolved(self, word: str, reading: str, context: str, rule: str = "контекст") -> None:
        self.add("homograph", f"Омограф «{word}» читается как «{reading}»", context, rule)

    def abbreviation_expanded(self, abbr: str, full: str) -> None:
        self.add("abbr", f"«{abbr}» расшифровано при первом упоминании", full)

    def abbreviation_reading(self, abbr: str, reading: str) -> None:
        self.add("abbr", f"Аббревиатура «{abbr}» читается как «{reading}»")

    def number_normalized(self, original: str, reading: str) -> None:
        self.add("number", f"«{original}» читается как «{reading}»")

    def user_stress(self, word: str) -> None:
        self.add("user_stress", f"Ударение из словаря пользователя: «{word}»")

    def footnote(self, action: str, context: str) -> None:
        self.add("footnote", f"Сноска: {action}", context)

    def note(self, text: str) -> None:
        self.add("note", "Примечание", text)

    # -- итоги ---------------------------------------------------------------
    def counts(self) -> dict:
        c: dict = {}
        for e in self.events:
            c[e.kind] = c.get(e.kind, 0) + 1
        return c

    def finish(self, audio_seconds: float, gen_seconds: float) -> None:
        self.stats["длительность_аудио_сек"] = round(audio_seconds, 1)
        self.stats["время_сборки_сек"] = round(gen_seconds, 1)

    def summary_line(self) -> str:
        c = self.counts()
        parts = []
        if c.get("comma"):
            parts.append(f"запятых скорректировано: {c['comma']}")
        if c.get("homograph"):
            parts.append(f"омографов: {c['homograph']}")
        if c.get("abbr"):
            parts.append(f"аббревиатур: {c['abbr']}")
        if c.get("number"):
            parts.append(f"чисел и дат: {c['number']}")
        if c.get("user_stress"):
            parts.append(f"пользовательских ударений: {c['user_stress']}")
        return "; ".join(parts) if parts else "все знаки препинания соответствовали синтаксису"

    def render_text(self) -> str:
        self.stats["время_сборки_сек"] = self.stats.get("время_сборки_сек") or round(
            (datetime.now() - self.started).total_seconds(), 1)
        lines = [f"ОТЧЁТ ОБ ОЗВУЧКЕ — «{self.title}»",
                 f"Дата: {self.started.strftime('%d.%m.%Y %H:%M')}", ""]
        s = self.stats
        lines.append("Статистика: "
                     f"слов {s.get('слов', 0)}, предложений {s.get('предложений', 0)}, "
                     f"синтагм {s.get('синтагм', 0)}; "
                     f"аудио {fmt_sec(s.get('длительность_аудио_сек', 0))}, "
                     f"сборка {fmt_sec(s.get('время_сборки_сек', 0))}.")
        lines.append(f"Решения по тексту: {self.summary_line()}.")
        lines.append("")
        counts = self.counts()
        if not counts:
            lines.append("Ничего необычного: текст озвучен как написан.")
        for kind, title in KIND_TITLES.items():
            events = [e for e in self.events if e.kind == kind]
            if not events:
                continue
            lines.append(f"== {title} ({len(events)}) ==")
            shown = events[:60]
            for i, e in enumerate(shown, 1):
                line = f"{i}. {e.title}"
                if e.reason and e.reason != e.title:
                    line += f" — {e.reason}"
                if e.context:
                    line += f"\n     …{e.context}…"
                lines.append(line)
            if len(events) > len(shown):
                lines.append(f"… и ещё {len(events) - len(shown)}.")
            lines.append("")
        return "\n".join(lines)

    def save(self, audio_base_path: str) -> tuple[Optional[str], Optional[str]]:
        """Пишет отчёт рядом с аудиофайлом: <имя>.отчёт.txt и <имя>.отчёт.json"""
        txt_path = None
        json_path = None
        try:
            base = os.path.splitext(audio_base_path)[0]
            txt_path = base + ".отчёт.txt"
            with open(txt_path, "w", encoding="utf-8") as f:
                f.write(self.render_text())
            json_path = base + ".отчёт.json"
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump({
                    "title": self.title,
                    "stats": self.stats,
                    "summary": self.summary_line(),
                    "events": [asdict(e) for e in self.events],
                }, f, ensure_ascii=False, indent=1)
        except Exception:
            pass
        return txt_path, json_path


def fmt_sec(sec: float) -> str:
    sec = int(round(sec))
    m, s = divmod(sec, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h} ч {m} мин"
    if m:
        return f"{m} мин {s} с"
    return f"{s} с"
