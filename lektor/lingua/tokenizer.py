# -*- coding: utf-8 -*-
"""Токенизация: предложения и слова через razdel (правила для русского языка)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import List

from razdel import sentenize, tokenize


@dataclass
class Sentence:
    text: str
    start: int
    end: int


@dataclass
class Token:
    text: str
    start: int
    end: int

    @property
    def is_word(self) -> bool:
        return any(c.isalpha() for c in self.text)

    @property
    def is_punct(self) -> bool:
        return not self.is_word and not self.text.strip().isdigit()

    @property
    def is_number(self) -> bool:
        return self.text.replace(",", ".").replace(" ", "").replace("\u00a0", ".").replace(".", "", 1).isdigit() and any(c.isdigit() for c in self.text)


def split_sentences(text: str) -> List[Sentence]:
    return [Sentence(s.text, s.start, s.stop) for s in sentenize(text)]


def split_tokens(text: str) -> List[Token]:
    return [Token(t.text, t.start, t.stop) for t in tokenize(text)]
