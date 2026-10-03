# -*- coding: utf-8 -*-
"""Логическое ударение (требования 15, 16, 17).

Логическое ударение не отражено в тексте — оно определяется смыслом.
Нейтральное правило: ударение ближе к концу синтагмы, но не на служебном
слове (тр. 15). Ставится на существительных, реже на глаголах, когда глагол —
смысловой центр; не ставится на прилагательных и местоимениях без контраста
(тр. 16). Противопоставления («не административной, а уголовной») выделяют
слово, вводящее контраст (тр. 17).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

from .syntax import W

# Маркеры противопоставления и выделения (тр. 17)
CONTRAST_PREV = {"не", "ни"}                 # «не административной» — выделяем следующее слово
CONTRAST_STARTERS = {"только", "именно", "даже", "лишь", "как", "прежде всего", "главным образом"}
CONTRAST_CONJ = {"а", "но", "однако", "зато", "либо", "или"}

POS_WEIGHTS = {
    "NOUN": 3.0, "PROPN": 3.0,
    "VERB": 2.2, "ADV": 1.4, "NUM": 1.2,
    "ADJ": 0.6,           # прилагательные — только при контрасте (тр. 16)
    "PRON": 0.0, "ADP": 0.0, "CCONJ": 0.0, "PART": 0.0, "PUNCT": 0.0, "SCONJ": 0.0,
}


@dataclass
class Focus:
    word_id: int = -1
    reason: str = ""


class FocusFinder:
    def __init__(self, term_lemmas: Optional[set] = None):
        """term_lemmas — леммы юридического словаря: термины несут смысл."""
        self.term_lemmas = term_lemmas or set()

    def find(self, words: List[W]) -> Focus:
        """Ищет слово с логическим ударением в синтагме."""
        content = [w for w in words if w.is_word]
        if not content:
            return Focus()

        # 1) контрастивное ударение (тр. 17)
        contrast = self._contrast(content)
        if contrast is not None:
            return contrast

        # 2) нейтральное правило (тр. 15, 16)
        best, best_score, reason = -1, -1.0, ""
        n = len(content)
        has_noun = any(w.pos in ("NOUN", "PROPN") for w in content)
        for i, w in enumerate(content):
            weight = POS_WEIGHTS.get(w.pos, 0.3)
            if weight <= 0:
                continue
            if w.pos == "VERB" and has_noun:
                weight *= 0.7  # глагол — реже (тр. 16)
            if w.pos == "ADJ":
                weight *= 0.5
            # юридический термин — смысловой центр
            if w.lemma in self.term_lemmas:
                weight += 1.5
            # длинные слова чаще информативнее
            weight += min(len(w.text), 14) / 30.0
            # ближе к концу синтагмы (тр. 15), но не последнее служебное
            position = i / max(1, n - 1)
            weight += 0.6 * position
            if weight > best_score:
                best, best_score = w.id, weight
                reason = "нейтральное правило (смысловой центр ближе к концу синтагмы)"
        return Focus(word_id=best, reason=reason)

    # ------------------------------------------------------------------
    def _contrast(self, words: List[W]) -> Optional[Focus]:
        """«не X, а Y», «только X», «именно X» — ударение на контрастном слове."""
        for i, w in enumerate(words):
            low = w.lemma.lower()
            # «не + слово» перед запятой и союзом «а/но» -> контраст на X
            if low in CONTRAST_PREV and i + 1 < len(words):
                nxt = words[i + 1]
                if nxt.pos in ("NOUN", "ADJ", "VERB", "ADV"):
                    # ищем «а»/«но» дальше — усиливает уверенность
                    return Focus(word_id=nxt.id, reason="контрастивное ударение («не X, а Y»)")
            if low in CONTRAST_STARTERS and i + 1 < len(words):
                nxt = words[i + 1]
                if nxt.pos in ("NOUN", "PROPN", "VERB", "ADJ", "NUM"):
                    return Focus(word_id=nxt.id, reason=f"выделение по маркеру «{w.text}»")
            # «X, а Y» — контраст на Y
            if low in CONTRAST_CONJ and i + 1 < len(words):
                nxt = words[i + 1]
                if nxt.pos in ("NOUN", "ADJ", "VERB", "ADV", "NUM") and i >= 1:
                    prev = words[i - 1]
                    if prev.pos in ("NOUN", "ADJ", "VERB", "ADV", "NUM"):
                        return Focus(word_id=nxt.id, reason="противопоставление (союз «а/но»)")
        return None
