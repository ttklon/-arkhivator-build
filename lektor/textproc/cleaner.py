# -*- coding: utf-8 -*-
"""Очистка текста от «шума» юридических документов (требование 26).

Убирает: номера страниц, колонтитулы, повторяющиеся служебные строки,
маркеры сносок, ссылки URL, «!!!»/«???», лишние пробелы. Сноски либо
пропускаются, либо переносятся в конец с маркером «Сноска» и читаются
тише — режим задаётся настройкой.
"""
from __future__ import annotations

import re
from collections import Counter
from typing import List, Tuple

from ..report import Report

SUPERSCRIPTS = "¹²³⁴⁵⁶⁷⁸⁹⁰⁺"


class Cleaner:
    def __init__(self, report: Report, footnotes: str = "skip"):
        """footnotes: 'skip' — убрать сноски, 'end' — прочитать в конце."""
        self.report = report
        self.footnotes = footnotes

    def clean(self, text: str) -> str:
        # нормальный вид текста: BOM, CRLF из файлов Windows,
        # невидимые символы после копирования с сайтов
        text = text.replace("\ufeff", "")
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        text = re.sub(r"[\u200b\u200c\u200d\u00ad]", "", text)
        # парные ASCII-кавычки -> «ёлочки» (в русских текстах "..." — брак
        # вёрстки после копирования из Word/интернета);
        # ВНУТРИ тегов <...> кавычки не трогаем (SSML: time="700ms")
        text = self._fix_ascii_quotes(text)
        # интернет-тире: «слово -- слово» и «слово - слово» -> «слово — слово»
        text = re.sub(r"\s--+\s", " — ", text)
        text = re.sub(r"(?<=[а-яёА-ЯЁ»])\s-\s(?=[а-яёА-ЯЁ«])", " — ", text)
        text = self._dehyphenate(text)
        text = self._remove_noise(text)
        text = self._fix_punct_runs(text)
        text = self._remove_footnote_marks(text)
        main, footnotes = self._split_footnotes(text)
        text = self._lists(main if (self.footnotes == "end" or not footnotes) else text)
        if self.footnotes == "end" and footnotes:
            self.report.footnote(f"перенесены в конец ({len(footnotes)} шт.), читаются тише", "")
            text = main.rstrip() + "\n\nСноски.\n" + "\n".join(footnotes)
        elif footnotes:
            self.report.footnote(f"пропущены ({len(footnotes)} шт.)", "")
            text = main
        return text.strip()

    # ------------------------------------------------------------------
    @staticmethod
    def _dehyphenate(text: str) -> str:
        """Склейка переносов: «суде-\nбного» -> «судебного»."""
        return re.sub(r"([а-яё])[-–]\s*\n\s*([а-яё])", r"\1\2", text, flags=re.IGNORECASE)

    def _fix_ascii_quotes(self, text: str) -> str:
        """'"...' -> «...»: парные ASCII-кавычки становятся ёлочками.

        Теги <...> пропускаем целиком — кавычки атрибутов SSML священны.
        Состояние открыт/закрыт переносится через теги, чтобы пара
        "слова <b>жирно</b>" не развалилась.
        """
        if '"' not in text:
            return text
        parts = re.split(r"(<[^>]*>)", text)
        opening = [True]

        def flip(seg: str) -> str:
            if '"' not in seg:
                return seg
            out = []
            for ch in seg:
                if ch == '"':
                    out.append("«" if opening[0] else "»")
                    opening[0] = not opening[0]
                else:
                    out.append(ch)
            return "".join(out)

        for i, part in enumerate(parts):
            if len(part) > 2 and part.startswith("<") and part.endswith(">"):
                continue
            parts[i] = flip(part)
        return "".join(parts)

    def _remove_noise(self, text: str) -> str:
        lines = text.splitlines()
        cleaned: List[str] = []
        for line in lines:
            s = line.strip()
            # номера страниц и служебные строки
            if re.fullmatch(r"\d{1,4}([—–-]\d{1,4})?", s):
                continue
            if re.fullmatch(r"(стр|ст|с)\.?\s*\d+( из \d+)?", s, re.IGNORECASE):
                continue
            if re.fullmatch(r"[—–\-_=•·.\s]+", s):
                continue
            if re.match(r"^https?://\S+$", s):
                self.report.footnote("убрана ссылка", s[:60])
                continue
            s = re.sub(r"https?://\S+", "", s)
            s = s.replace("\u00a0", " ")
            cleaned.append(line.rstrip())
        # повторяющиеся колонтитулы (>= 3 повторов короткой строки без знаков конца)
        counter = Counter(re.sub(r"\s+", " ", l).strip().lower() for l in cleaned if 3 < len(l.strip()) <= 70)
        repeated = {t for t, c in counter.items() if c >= 3 and not re.search(r"[.!?…»]$", t)}
        if repeated:
            self.report.footnote(
                f"удалены повторяющиеся колонтитулы: {', '.join(sorted(repeated)[:5])}", "")
            cleaned = [l for l in cleaned
                       if re.sub(r"\s+", " ", l).strip().lower() not in repeated]
        return "\n".join(cleaned)

    @staticmethod
    def _fix_punct_runs(text: str) -> str:
        text = re.sub(r"([!])\1+", r"\1", text)
        text = re.sub(r"([?])\1+", r"\1", text)
        text = re.sub(r"([.,;:])([.,;:])+", r"\1", text)
        text = re.sub(r"[ \t]+", " ", text)
        return re.sub(r"\n{3,}", "\n\n", text)

    def _remove_footnote_marks(self, text: str) -> str:
        """Надстрочные цифры и ссылки вида [1] у слов.

        Но ²/³ после м/см/км/мм — это квадратные/кубические единицы
        («100 м²», «30 см³»), их оставляем: нормализатор читает их
        словами («сто квадратных метров»).
        """
        n_before = len(text)
        text = re.sub(f"(?<![а-яёА-ЯЁ])[{SUPERSCRIPTS}]+", "", text)
        # после буквы — удаляем, КРОМЕ единиц с квадратом/кубом:
        # «м²», «см³», «км²», «мм²», «га», а также «м/с²» (там ² стоит
        # после «с», перед которой слэш)
        text = re.sub(r"(?<=[а-яёА-ЯЁ])"
                      r"(?<!м)(?<!см)(?<!км)(?<!мм)(?<!га)(?<!/с)"
                      r"(?<!М)(?<!СМ)(?<!КМ)(?<!ММ)(?<!ГА)"
                      f"[{SUPERSCRIPTS}]+", "", text)
        text = re.sub(r"\s?\[\d{1,3}\]", "", text)
        if len(text) != n_before:
            self.report.footnote("убраны маркеры сносок в тексте", "")
        return text

    def _split_footnotes(self, text: str) -> Tuple[str, List[str]]:
        """Отделяет блок сносок в конце документа (строки «1 …», «2 …»)."""
        lines = text.splitlines()
        i = len(lines)
        fn_lines: List[str] = []
        while i > 0:
            i -= 1
            s = lines[i].strip()
            if not s:
                continue
            if re.match(r"^\d{1,3}\s+\S", s) and not re.match(r"^\d+\s*$", s):
                fn_lines.append(s)
            else:
                break
        if len(fn_lines) >= 2:
            cut = len(lines) - len(fn_lines)
            # список после строки с двоеточием («Принципы:» + пункты) —
            # это не сноски
            prev = next((l.strip() for l in reversed(lines[:cut]) if l.strip()), "")
            if not prev.endswith(":"):
                return "\n".join(lines[:cut]).rstrip(), list(reversed(fn_lines))
        return text, []

    # ------------------------------------------------------------------
    def _lists(self, text: str) -> str:
        """Маркеры списков — словами, чтобы звучало как у чтеца.

        «1. Законность.» -> «Первое — законность.»
        «а) объяснить;»   -> «Пункт а — объяснить;»
        «- текст»         -> «текст» (маркер-тире убирается)
        Без этого номера пунктов приклеивались к предыдущему предложению
        и читались как «принципы один».
        """
        from ..lingua import numerals

        num_rx = re.compile(r"^(\d{1,2})[.)]\s+(.+)$")
        let_rx = re.compile(r"^([а-яё])[)\]]\s+(.+)$")
        bullet_rx = re.compile(r"^[-\u2022\u00b7\u2023\u25aa\u2013]\s+(.+)$")
        listish = re.compile(
            r"^(?:\d{1,2}[.)]\s|[а-яё][)\]]\s|[-\u2022\u00b7\u2023\u25aa\u2013]\s)")

        orig = text.splitlines()
        lines = list(orig)
        changed = False
        for idx, line in enumerate(orig):
            s = line.strip()
            m = num_rx.match(s)
            if m:
                n = int(m.group(1))
                rest = m.group(2)
                # контекст списка: предыдущая строка кончается двоеточием
                # или рядом есть ещё пункт (контекст — по ИСХОДНЫМ строкам)
                prev = next((l.strip() for l in reversed(orig[:idx]) if l.strip()), "")
                nxt = next((l.strip() for l in orig[idx + 1:] if l.strip()), "")
                if prev.endswith(":") or listish.match(nxt) or listish.match(prev):
                    ordinal = " ".join(numerals.ordinal_words(n, "n"))
                    lines[idx] = ordinal[0].upper() + ordinal[1:] + " — " + rest
                    changed = True
                continue
            m = let_rx.match(s)
            if m:
                prev = next((l.strip() for l in reversed(orig[:idx]) if l.strip()), "")
                nxt = next((l.strip() for l in orig[idx + 1:] if l.strip()), "")
                if prev.endswith(":") or listish.match(nxt) or listish.match(prev):
                    lines[idx] = "Пункт " + m.group(1) + " — " + m.group(2)
                    changed = True
                continue
            m = bullet_rx.match(s)
            if m and not s.startswith("\u2014"):  # «—» в начале — диалог, не трогаем
                lines[idx] = m.group(1)
                changed = True
        if changed:
            self.report.footnote("маркеры списков прочитаны словами", "")
        return "\n".join(lines)
