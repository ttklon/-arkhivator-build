# -*- coding: utf-8 -*-
"""Синтаксический анализ: дерево зависимостей через natasha + морфология pymorphy3.

Требование 9: перед синтезом строится дерево зависимостей. Глагол и дополнение,
предлог и существительное, «не» и глагол — тесные группы, которые пауза разрывать
не должна. Здесь готовится «модель слова» (W) с полной разметкой.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import List, Optional

from .morphology import analyze, pos as morph_pos, POS_MAP
from .tokenizer import split_tokens


@dataclass
class W:
    """Слово предложения с полной лингвистической разметкой."""

    text: str
    start: int          # позиция в строке предложения
    end: int
    id: int             # порядковый номер (0-based)
    pos: str = "X"      # часть речи (pymorphy, при сомнении — natasha)
    nat_pos: str = "X"  # часть речи по natasha
    rel: str = "_"      # отношение к голове (UD): obj, obl, amod, ...
    head: int = -1      # индекс слова-головы (-1 — корень)
    lemma: str = ""
    case: str = ""      # падеж (для существительных/прилагательных)
    is_punct: bool = False
    stressed: str = ""  # форма со знаком «+» (заполняет модуль stress)

    @property
    def is_word(self) -> bool:
        return not self.is_punct


# Зависимости, означающие тесную связь двух слов
TIGHT_RELS = {
    "obj", "iobj", "obl", "obl:agent", "obl:tmod", "amod", "nmod",
    "nummod", "appos", "case", "aux", "aux:pass", "cop", "det",
    "neg", "advmod", "xcomp", "ccomp", "mark", "fixed", "goeswith", "compound",
}


class SyntaxAnalyzer:
    """Потокобезопасная обёртка natasha (Segmenter + Morph + Syntax)."""

    _lock = threading.Lock()

    def __init__(self):
        from natasha import Doc, Segmenter, NewsEmbedding, NewsMorphTagger, NewsSyntaxParser
        emb = NewsEmbedding()
        self._doc_cls = Doc
        self._segmenter = Segmenter()
        self._morph_tagger = NewsMorphTagger(emb)
        self._syntax_parser = NewsSyntaxParser(emb)
        self._ok = True

    # ------------------------------------------------------------------
    def analyze_sentence(self, sent_text: str) -> List[W]:
        """Разбирает предложение: токены + морфология + дерево зависимостей."""
        toks = split_tokens(sent_text)
        words: List[W] = []
        for i, t in enumerate(toks):
            w = W(text=t.text, start=t.start, end=t.end, id=i)
            if t.is_word:
                p = analyze(t.text)
                if p is not None:
                    tag = p.tag
                    w.pos = POS_MAP.get(tag.POS, "X") if tag and tag.POS else "X"
                    w.lemma = p.normal_form or t.text.lower()
                    if tag and tag.case:
                        w.case = {"gen1": "gent", "loc1": "loct"}.get(tag.case, tag.case)
            else:
                w.is_punct = True
                w.pos = "PUNCT"
            words.append(w)

        word_count = sum(1 for w in words if w.is_word)
        if word_count >= 2 and self._ok:
            try:
                with self._lock:
                    doc = self._doc_cls(sent_text)
                    doc.segment(self._segmenter)
                    doc.tag_morph(self._morph_tagger)
                    doc.parse_syntax(self._syntax_parser)
                self._merge_natasha(words, doc.tokens)
            except Exception:
                # сбой разбора не должен останавливать озвучку — эвристики продолжат работу
                pass
        return words

    def _merge_natasha(self, words: List[W], nat_tokens) -> None:
        """Переносит разметку natasha на слова (токенизаторы совпадают — razdel)."""
        if len(nat_tokens) != len(words):
            # защита от редких расхождений токенизации
            nat_tokens = self._align(words, nat_tokens)
            if nat_tokens is None:
                return
        for w, t in zip(words, nat_tokens):
            w.nat_pos = getattr(t, "pos", None) or w.nat_pos
            w.rel = getattr(t, "rel", None) or "_"
            head_id = getattr(t, "head_id", None)
            try:
                # id вида '1_3' — предложение 1, токен 3
                w.head = int(str(head_id).split("_")[1]) - 1 if head_id else -1
            except Exception:
                w.head = -1
            if w.pos == "X" and w.nat_pos:
                w.pos = w.nat_pos

    @staticmethod
    def _align(words: List[W], nat_tokens):
        """Жадное выравнивание по текстам токенов."""
        result = []
        it = iter(nat_tokens)
        t = next(it, None)
        for w in words:
            matched = None
            while t is not None and t.text.replace("ё", "е") == w.text.replace("ё", "е"):
                matched = t
                t = next(it, None)
                break
            if matched is None and t is not None and t.text == w.text:
                matched = t
                t = next(it, None)
            result.append(matched)
        return result if all(r is not None for r in result) else None


def find_commas(words: List[W]) -> List[int]:
    """Индексы запятых в предложении."""
    return [w.id for w in words if w.is_punct and w.text in {",", "،", "؛"}]


def words_between(words: List[W], i: int, j: int) -> List[W]:
    return [w for w in words if i <= w.id <= j]
