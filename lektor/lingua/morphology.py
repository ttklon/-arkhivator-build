# -*- coding: utf-8 -*-
"""Морфология русского языка на pymorphy3: часть речи, падеж, лемма, согласование.

Требование 1: ударение и грамматика зависят от ФОРМЫ слова, поэтому вся логика
работает с конкретными словоформами и их морфологической разметкой.
"""
from __future__ import annotations

import threading
from functools import lru_cache

import pymorphy3

_morph = None
_lock = threading.Lock()

# Части речи pymorphy -> универсальные метки
POS_MAP = {
    "NOUN": "NOUN", "ADJF": "ADJ", "ADJS": "ADJ", "COMP": "ADJ",
    "VERB": "VERB", "INFN": "VERB", "PRTF": "ADJ", "PRTS": "ADJ",
    "GRND": "VERB", "NUMR": "NUM", "ADVB": "ADV", "NPRO": "PRON",
    "PRED": "ADV", "PREP": "ADP", "CONJ": "CCONJ", "PRCL": "PART", "INTJ": "INTJ",
}

CASES = ("nomn", "gent", "datv", "accs", "ablt", "loct", "voct", "gen1", "loc1")
GENDERS = ("masc", "femn", "neut", "ms-f")


def get_morph() -> pymorphy3.MorphAnalyzer:
    global _morph
    if _morph is None:
        with _lock:
            if _morph is None:
                _morph = pymorphy3.MorphAnalyzer()
    return _morph


@lru_cache(maxsize=300000)
def cached_parse(word: str):
    """Разбор словоформы (кэшируется: в юридических текстах много повторов)."""
    return get_morph().parse(word)


def analyze(word: str):
    """Лучший разбор словоформы (безопасен для любых строк).

    Числительные предпочитаются омонимам («сто» — числительное, а не СТО)."""
    if not word or not any(c.isalpha() for c in word):
        return None
    try:
        parses = cached_parse(word.lower().strip("«»\"'"))
        if not parses:
            return None
        for p in parses:
            if p.tag and p.tag.POS == "NUMR":
                return p
        return parses[0]
    except Exception:
        return None


def pos(word: str) -> str:
    p = analyze(word)
    return POS_MAP.get(getattr(p, "tag", None) and p.tag.POS, "X") if p else "X"


def lemma(word: str) -> str:
    p = analyze(word)
    return p.normal_form if p else word.lower()


def inflect_word(word: str, gram: frozenset | set) -> str | None:
    """Склоняет слово к заданному набору граммем (например, {'gent'})."""
    p = analyze(word)
    if not p:
        return None
    try:
        inf = p.inflect(gram)
        return inf.word if inf else None
    except Exception:
        return None


def word_case(word: str) -> str | None:
    p = analyze(word)
    if p and p.tag and p.tag.case:
        # нормализуем редко встречающиеся варианты к базовым падежам;
        # str() избавляет от спец-типа граммемы pymorphy3
        c = str(p.tag.case)
        return {"gen1": "gent", "loc1": "loct", "loc2": "loct",
                "gen2": "gent", "acc2": "accs"}.get(c, c)
    return None


def is_content(word: str) -> bool:
    """Знаменательное слово (может нести логическое ударение — тр. 16)."""
    return pos(word) in ("NOUN", "ADJ", "VERB", "ADV", "NUM", "PROPN", "INTJ")


# Удобные описания падежей для отчётов
CASE_NAMES = {
    "nomn": "именительный", "gent": "родительный", "datv": "дательный",
    "accs": "винительный", "ablt": "творительный", "loct": "предложный",
}
