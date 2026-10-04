# -*- coding: utf-8 -*-
"""Членение предложения на синтагмы и расстановка пауз (требования 8, 10–14).

Запятая — вероятностный сигнал, а не команда «сделай паузу» (тр. 8).
Перед паузой строится дерево зависимостей (тр. 9): если запятая разрывает
тесную группу — «глагол + дополнение», «предлог + существительное»,
«не + глагол» — она игнорируется, а событие попадает в отчёт (тр. 30).
Синтагма — минимальная интонационно-смысловая единица (тр. 10).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple

from ..report import Report
from .morphology import analyze
from .syntax import W, TIGHT_RELS

# ---------------------------------------------------------------------------
# Словарные константы
# ---------------------------------------------------------------------------
INTRO_WORDS = {
    "следовательно", "значит", "например", "таким образом", "по существу",
    "во-первых", "во-вторых", "в-третьих", "наконец", "причём", "причем",
    "кстати", "по-видимому", "итак", "впрочем", "однако", "напротив",
    "в общем", "в целом", "короче", "точнее", "бесспорно", "разумеется",
}

SUBORD_CONJS = {
    "который", "которая", "которое", "которые", "которых", "которому",
    "что", "чтобы", "если", "когда", "поскольку", "пока", "хотя",
    "несмотря", "прежде", "как", "будто", "словно", "если", "раз",
}


class Boundary(Enum):
    NONE = "none"       # запятая удалена — слова читаются слитно
    WEAK = "weak"       # запятая сохранена — естественная микро-пауза движка
    MEDIUM = "medium"   # явная пауза между синтагмами (150–300 мс)
    STRONG = "strong"   # конец предложения (400–600 мс)


@dataclass
class Syntagm:
    """Синтагма: группа токенов + граница после неё."""

    words: List[W]
    boundary: Boundary = Boundary.MEDIUM
    reason: str = ""
    pause_ms: int = 0
    pause_override: Optional[int] = None    # SSML <break> пользователя
    contour: str = ""                       # заполняет intonation.py
    focus_id: int = -1                      # заполняет focus.py

    def text(self, spoken: Optional[Dict[int, str]] = None) -> str:
        """Текст синтагмы (spoken: индекс токена -> форма с ударением)."""
        parts = []
        for w in self.words:
            t = (spoken or {}).get(w.id, w.text)
            parts.append(t)
        return join_tokens(parts).strip()


# ---------------------------------------------------------------------------
# Сборка текста из токенов с правильными пробелами
# ---------------------------------------------------------------------------
_NO_SPACE_BEFORE = {",", ".", "!", "?", ";", ":", "…", ")", "»", "%", "!", "?"}
_NO_SPACE_AFTER = {"(", "«"}


def join_tokens(parts: List[str]) -> str:
    out: List[str] = []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        if not out:
            out.append(p)
            continue
        if p[0] in _NO_SPACE_BEFORE:
            out[-1] = out[-1].rstrip() + p
        elif out[-1][-1] in _NO_SPACE_AFTER:
            out.append(p)
        else:
            out.append(p)
    text = " ".join(out)
    return text


# ---------------------------------------------------------------------------
# Сегментатор
# ---------------------------------------------------------------------------
class Segmenter:
    def __init__(self, report: Report, fix_commas: bool = True):
        self.report = report
        self.fix_commas = fix_commas

    # ------------------------------------------------------------------
    def segment(self, words: List[W],
                pause_intra_ms: int = 240, pause_inter_ms: int = 520,
                pause_enum_ms: int = 260,
                forced_breaks: Optional[Dict[int, int]] = None) -> List[Syntagm]:
        """Разбивает предложение на синтагмы.

        forced_breaks: {id_слова: мс} — принудительная пауза ПЕРЕД словом
        (SSML <break time="..."/> пользователя, тр. 13).
        """
        decisions = self._punct_decisions(words)
        syntagms = self._build(words, decisions, forced_breaks or {})
        syntagms = self._mark_enumerations(syntagms)

        for i, s in enumerate(syntagms):
            if s.pause_override:
                s.pause_ms = s.pause_override
            elif s.boundary == Boundary.STRONG:
                s.pause_ms = pause_inter_ms
            elif s.boundary == Boundary.MEDIUM:
                s.pause_ms = pause_enum_ms if s.contour == "enum_continue" else pause_intra_ms
            else:
                s.pause_ms = 0
        return syntagms

    # ------------------------------------------------------------------
    # Решения по знакам препинания
    # ------------------------------------------------------------------
    def _punct_decisions(self, words: List[W]) -> Dict[int, Tuple[Boundary, str]]:
        decisions: Dict[int, Tuple[Boundary, str]] = {}
        for w in words:
            if not w.is_punct:
                continue
            t = w.text
            if t in {",", "،"}:
                decisions[w.id] = self._decide_comma(words, w.id)
            elif t in {";", ":"}:
                decisions[w.id] = (Boundary.MEDIUM, "точка с запятой/двоеточие")
            elif t in {"—", "–", "−"}:
                decisions[w.id] = (Boundary.MEDIUM, "тире")
            elif t in {".", "!", "?", "…"}:
                decisions[w.id] = (Boundary.STRONG, "конец предложения")
            elif t == ")":
                prev = self._near_word(words, w.id, -1)
                if prev is not None and (prev.text.isdigit() or len(prev.text) == 1):
                    decisions[w.id] = (Boundary.MEDIUM, "пункт перечисления")
        return decisions

    def _decide_comma(self, words: List[W], comma_id: int) -> Tuple[Boundary, str]:
        """Решает судьбу одной запятой (тр. 8, 9, 12)."""
        prev = self._near_word(words, comma_id, -1)
        nxt = self._near_word(words, comma_id, +1)
        if prev is None or nxt is None:
            return Boundary.WEAK, ""
        if not self.fix_commas:
            return Boundary.WEAK, ""

        # --- защита тесных групп (тр. 9) --------------------------------
        rel_names = {
            "obj": "глагол и дополнение", "iobj": "глагол и дополнение",
            "obl": "глагол и обстоятельство", "amod": "существительное и определение",
            "nmod": "существительное и его определение", "nummod": "числительное и существительное",
            "case": "предлог и существительное", "appos": "приложение",
            "aux": "вспомогательный глагол", "cop": "связка",
            "det": "определитель и существительное", "advmod": "слово и относящееся к нему наречие",
            "xcomp": "глагол и инфинитив", "compound": "сложное слово",
        }
        if nxt.head == prev.id and nxt.rel in TIGHT_RELS and nxt.rel != "punct":
            why = rel_names.get(nxt.rel, "тесная синтаксическая группа")
            return Boundary.NONE, f"запятая разорвала связь «{why}» ({prev.text} → {nxt.text})"
        if prev.head == nxt.id and prev.rel in TIGHT_RELS and prev.rel != "punct":
            why = rel_names.get(prev.rel, "тесная синтаксическая группа")
            return Boundary.NONE, f"запятая разорвала связь «{why}» ({nxt.text} → {prev.text})"

        if prev.pos == "ADP":
            return Boundary.NONE, "запятая оторвала предлог от его группы"
        if prev.pos == "VERB" and nxt.pos == "PRON" and nxt.case in ("accs", "gent"):
            return Boundary.NONE, f"запятая разорвала связь «глагол + дополнение» ({prev.text} {nxt.text})"
        if prev.lemma in ("не", "ни") or nxt.lemma in ("не", "ни"):
            return Boundary.NONE, "частица «не» не отрывается от своего слова"
        if prev.pos == "NUM" and nxt.pos == "NOUN":
            return Boundary.NONE, "запятая разорвала связь «числительное + существительное»"

        # --- места, где пауза уместна -----------------------------------
        if nxt.pos in ("VERB", "ADJ") and self._is_participle(nxt):
            return Boundary.MEDIUM, "причастный/деепричастный оборот — нормативная пауза"
        if nxt.lemma in SUBORD_CONJS or self._is_intro(nxt):
            return Boundary.MEDIUM, "перед подчинительным союзом или вводным словом"
        if self._is_intro_before(words, comma_id):
            return Boundary.MEDIUM, "после вводного слова или оборота — нормативная пауза"
        # синтаксическое дерево — самый надёжный признак однородности:
        # сосед по запятой связан rel=conj (падежные теги у неоднозначных
        # форм вроде «документы/справки/выписки» часто размечены случайно)
        if nxt.rel == "conj" or prev.rel == "conj":
            return Boundary.MEDIUM, "однородные члены предложения"
        if self._homogeneous(prev, nxt):
            return Boundary.MEDIUM, "однородные члены предложения"
        return Boundary.WEAK, ""

    # ------------------------------------------------------------------
    @staticmethod
    def _near_word(words: List[W], punct_id: int, direction: int) -> Optional[W]:
        idx = punct_id + direction
        while 0 <= idx < len(words):
            w = words[idx]
            if w.is_word:
                return w
            if w.text in {".", "!", "?", ";", ":"}:
                return None
            idx += direction
        return None

    @staticmethod
    def _is_participle(w: W) -> bool:
        p = analyze(w.text)
        return p is not None and p.tag is not None and p.tag.POS in ("PRTF", "PRTS", "GRND")

    @staticmethod
    def _is_intro_before(words: List[W], punct_id: int) -> bool:
        """Вводное слово/обороты, стоящие ПЕРЕД запятой: «Таким образом, …»."""
        forms: List[str] = []
        idx = punct_id - 1
        while idx >= 0 and len(forms) < 3:
            w = words[idx]
            if not w.is_word:
                break
            forms.insert(0, w.text.lower())
            idx -= 1
        if not forms:
            return False
        for k in (3, 2, 1):
            if len(forms) >= k and " ".join(forms[-k:]) in INTRO_WORDS:
                return True
        return forms[-1] in INTRO_WORDS

    @staticmethod
    def _is_intro(w: W) -> bool:
        low = w.lemma.lower()
        if low in INTRO_WORDS:
            return True
        return "-" in low and (low.startswith("во-") or low.startswith("в-"))

    @staticmethod
    def _homogeneous(a: W, b: W) -> bool:
        if a.pos in ("NOUN", "ADJ", "NUM", "VERB", "ADV") and a.pos == b.pos:
            if a.pos in ("NOUN", "ADJ", "NUM"):
                # у неодушевлённых винительный совпадает с именительным:
                # «взыскать неустойку, проценты» — однородные, хоть падежи
                # размечены accs и nomn
                return (a.case == b.case or not a.case or not b.case
                        or {a.case, b.case} <= {"nomn", "accs"})
            return True
        return False

    # ------------------------------------------------------------------
    # Сборка синтагм по точкам разреза
    # ------------------------------------------------------------------
    def _build(self, words: List[W], decisions: Dict[int, Tuple[Boundary, str]],
               forced: Dict[int, int]) -> List[Syntagm]:
        syntagms: List[Syntagm] = []
        current: List[W] = []

        for w in words:
            # запятая с решением NONE — удаляем из текста (тр. 8)
            if w.is_punct and w.text in {",", "،"} and \
                    decisions.get(w.id, (Boundary.WEAK, ""))[0] == Boundary.NONE:
                if current:
                    reason = decisions[w.id][1]
                    if reason:
                        self.report.comma_ignored(self._context(words, w.id), reason)
                continue

            current.append(w)

            cut: Optional[Tuple[Boundary, str]] = None
            override = None
            if w.is_punct and w.id in decisions:
                b, why = decisions[w.id]
                if b in (Boundary.MEDIUM, Boundary.STRONG):
                    cut = (b, why)
            if (w.id + 1) in forced and cut is None:
                cut = (Boundary.MEDIUM, "пауза SSML <break>")
                override = forced[w.id + 1]
            elif (w.id + 1) in forced and cut is not None:
                override = forced[w.id + 1]

            if cut is not None:
                syntagms.append(Syntagm(
                    words=current, boundary=cut[0], reason=cut[1], pause_override=override))
                current = []

        if current:
            syntagms.append(Syntagm(words=current, boundary=Boundary.STRONG,
                                    reason="конец предложения"))
        # последний сегмент всегда закрывает предложение
        if syntagms:
            syntagms[-1].boundary = Boundary.STRONG
        result = [s for s in syntagms if any(w.is_word for w in s.words)]
        # если всё предложение — одна сплошная тесная группа, оставляем целиком
        return result if result else [Syntagm(words=words, boundary=Boundary.STRONG)]

    # ------------------------------------------------------------------
    def _mark_enumerations(self, syntagms: List[Syntagm]) -> List[Syntagm]:
        """Перечисления (тр. 14): ровные паузы и нисходяще-ровная интонация
        на всех элементах, кроме последнего (без интонации завершения)."""
        if len(syntagms) < 2:
            return syntagms
        HOMO = "однородные члены предложения"
        run_start = None
        for i, s in enumerate(syntagms):
            short = len(s.words) <= 18
            medium = s.boundary == Boundary.MEDIUM
            if short and medium:
                if run_start is None:
                    run_start = i
            else:
                if run_start is not None and (
                        i - run_start >= 2
                        or (i - run_start >= 1
                            and syntagms[run_start].reason == HOMO)):
                    for j in range(run_start, i):
                        syntagms[j].contour = "enum_continue"
                run_start = None
        if run_start is not None and (
                len(syntagms) - run_start >= 2
                or (len(syntagms) - run_start >= 1
                    and syntagms[run_start].reason == HOMO)):
            for j in range(run_start, len(syntagms)):
                syntagms[j].contour = "enum_continue"
        return syntagms

    @staticmethod
    def _context(words: List[W], word_id: int, radius: int = 4) -> str:
        lo = max(0, word_id - radius)
        hi = min(len(words), word_id + radius + 1)
        parts = []
        for w in words[lo:hi]:
            parts.append("‖" if w.id == word_id else w.text)
        return " ".join(parts)
