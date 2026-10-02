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
        text = self._dehyphenate(text)
        text = self._remove_noise(text)
        text = self._fix_punct_runs(text)
        text = self._remove_footnote_marks(text)
        main, footnotes = self._split_footnotes(text)
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
        """Надстрочные цифры и ссылки вида [1] у слов."""
        n_before = len(text)
        text = re.sub(f"[{SUPERSCRIPTS}]+", "", text)
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
            if re.match(r"^\d{1,3}[\).\s]\s*\S", s) and not re.match(r"^\d+\s*$", s):
                fn_lines.append(s)
            else:
                break
        if len(fn_lines) >= 2:
            cut = len(lines) - len(fn_lines)
            return "\n".join(lines[:cut]).rstrip(), list(reversed(fn_lines))
        return text, []
