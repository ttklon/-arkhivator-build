# -*- coding: utf-8 -*-
"""Интонационные контуры и темп (требования 18–21).

Определено 24 типа мелодических кривых на базе системы ИК русского языка
(ИК-1…ИК-7) плюс служебные типы для вводности, обращений, перечислений и
цитат. Каждый тип задаёт параметры, которые движок синтеза получает через
SSML (prosody rate/pitch) и точные паузы.

Юридическая интонация (тр. 20): ровный уверенный тон, без эмоциональных
всплесков — контуры ИК-5/ИК-6 используются ограниченно.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from .syntax import W

# 24 контура (тр. 18)
CONTOURS = {
    # ключ: (описание, rate, pitch, множитель паузы после)
    "IK1_statement":        ("утверждение", None, None, 1.0),
    "IK1_heading":          ("заголовок", "slow", "low", 1.2),
    "IK2_wh_question":      ("вопрос с вопросительным словом", None, None, 1.0),
    "IK2_imperative":       ("побуждение, приказ", None, None, 1.0),
    "IK2_appeal":           ("обращение", None, None, 1.1),
    "IK3_polar_question":   ("вопрос без вопросительного слова", None, None, 1.0),
    "IK3_continuation":     ("незавершённость внутри предложения", None, None, 0.8),
    "IK3_incomplete":       ("обрыв, недосказанность", None, None, 0.9),
    "IK4_open_question":    ("незавершённый вопрос при сопоставлении", None, None, 1.0),
    "IK4_topic":            ("тема перед двоеточием", None, None, 0.9),
    "IK5_completion":       ("завершённость с усилением", None, None, 1.0),
    "IK5_exclamation":      ("восклицание", None, None, 1.0),
    "IK6_emphasis":         ("подчёркивание, контраст", "slow", None, 1.15),
    "IK7_negation":         ("отрицание-противопоставление", None, None, 1.0),
    "parenthesis":          ("вводность", None, None, 0.9),
    "address":              ("обращение отдельной синтагмой", None, None, 1.1),
    "enum_continue":        ("перечисление, продолжение", None, "high", 0.9),
    "enum_final":           ("перечисление, конец", None, None, 1.0),
    "quote_open":           ("начало цитаты", None, None, 0.9),
    "quote_close":          ("конец цитаты", None, None, 1.0),
    "list_item_continue":   ("пункт списка, продолжение", None, None, 0.9),
    "list_item_final":      ("пункт списка, последний", None, None, 1.0),
    "conditional":          ("условная придаточная", None, None, 0.9),
    "relative":             ("определительная придаточная", None, None, 0.9),
}

QUESTION_WORDS = {"ли", "разве", "неужели", "как", "что", "где", "когда", "почему",
                  "зачем", "сколько", "какой", "какая", "какое", "какие", "кто", "кого",
                  "кому", "который", "которая", "которое", "которые"}
WH_WORDS = {"как", "что", "где", "когда", "почему", "зачем", "сколько", "какой",
            "какая", "какое", "какие", "кто", "кого", "кому", "который", "которая",
            "которое", "которые"}


@dataclass
class Intonation:
    contour: str
    rate: Optional[str] = None
    pitch: Optional[str] = None
    pause_factor: float = 1.0
    final_punct: str = "."      # знак в конце синтагмы для движка
    label: str = ""


class IntonationPlanner:
    """Классифицирует предложения и назначает контуры синтагмам."""

    def classify_sentence(self, words: List[W], final_punct: str) -> str:
        """Тип предложения по знаку в конце и содержанию."""
        if final_punct == "?":
            first_words = {w.lemma.lower() for w in words[:4] if w.is_word}
            if first_words & WH_WORDS or any(w.lemma.lower() in WH_WORDS for w in words[: min(6, len(words))]):
                return "IK2_wh_question"
            return "IK3_polar_question"
        if final_punct == "!":
            # побуждение (императив) или восклицание
            for w in words:
                p = _imperative(w)
                if p:
                    return "IK2_imperative"
            return "IK5_exclamation"
        # точка или её отсутствие
        for w in words:
            if _imperative(w):
                return "IK2_imperative"
        if final_punct in ("", ":"):
            return "IK1_heading" if len(words) <= 8 else "IK4_topic"
        return "IK1_statement"

    def assign(self, syntagms, sentence_type: str) -> List[SyntagmPlan]:
        """Назначает контуры синтагмам предложения."""
        plans: List[SyntagmPlan] = []
        n = len(syntagms)
        for i, s in enumerate(syntagms):
            is_last = i == n - 1
            if getattr(s, "contour", "") in ("enum_continue",):
                contour = "enum_continue" if not is_last else "enum_final"
            elif is_last:
                contour = sentence_type if sentence_type != "IK1_heading" else "IK1_heading"
            else:
                # незавершённость: ровный или слегка восходящий тон (тр. 19)
                first = next((w for w in s.words if w.is_word), None)
                if first is not None and first.lemma.lower() in QUESTION_WORDS:
                    contour = "IK4_open_question"
                else:
                    contour = "IK3_continuation"
            desc, rate, pitch, pf = CONTOURS.get(contour, CONTOURS["IK1_statement"])
            plans.append(SyntagmPlan(
                contour=contour, rate=rate, pitch=pitch, pause_factor=pf,
                final_punct="?" if sentence_type.startswith(("IK2_wh", "IK3_polar")) and is_last else ".",
                label=desc,
            ))
        return plans


@dataclass
class SyntagmPlan:
    contour: str
    rate: Optional[str] = None
    pitch: Optional[str] = None
    pause_factor: float = 1.0
    final_punct: str = "."
    label: str = ""


def _imperative(w: W) -> bool:
    from .morphology import analyze
    if not w.is_word or w.pos != "VERB":
        return False
    p = analyze(w.text)
    try:
        return p is not None and p.tag and p.tag.mood == "impr"
    except Exception:
        return False
