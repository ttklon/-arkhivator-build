# -*- coding: utf-8 -*-
"""Токенизация: предложения и слова через razdel (правила для русского языка)."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List

from razdel import sentenize, tokenize

# сокращения, после которых razdel зря рвёт предложение:
# «а также л. 5 дела» не должно становиться «…л.» + «5 дела»
_REF_ABBR = re.compile(
    r"(?:^|\s)(?:ст|ст\.ст|ч|п|пп|л|абз|гл|разд|гг|г|тыс|млн|млрд|см|напр|"
    r"им|ред|прим|мин|сек|экз|ед|руб|коп|ул|пр|ш|д|в|вв|т|е|к|стр)\.$",
    re.IGNORECASE)
_INITIAL = re.compile(r"(?:^|\s)[А-ЯЁ]\.$")


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


def _split_headings(s: Sentence) -> List[Sentence]:
    """Строка без завершающего знака + пустая строка — заголовок.

    razdel не рвёт «Введение в право\n\nПраво — …» на два предложения
    (нет точки) — заголовок склеивается с абзацем и теряет свою
    интонацию. Режем по \n\n+, только если «голова» не кончается
    знаком конца/продолжения (одиночные \n не трогаем: жёстко
    свёрстанные PDF-тексты не должны рассыпаться на обрывки).
    """
    if "\n\n" not in s.text:
        return [s]
    out, pos = [], 0
    for m in re.finditer(r"\n\n+", s.text):
        head = s.text[pos:m.start()]
        if head.strip() and not re.search(r"[.!?…:;,]\s*$", head):
            out.append(Sentence(head.rstrip(), s.start + pos,
                                s.start + pos + len(head.rstrip())))
            pos = m.end()
    out.append(Sentence(s.text[pos:], s.start + pos, s.end))
    return [x for x in out if x.text.strip()]


def split_sentences(text: str) -> List[Sentence]:
    """Предложения; разрывы после известных сокращений склеиваем обратно.

    «…по делу л. 5» — «л.» не конец предложения, а часть ссылки;
    «Иванов И. И. Петров» — инициалы, а не границы предложений.
    """
    out: List[Sentence] = []
    for s in sentenize(text):
        sent = Sentence(s.text, s.start, s.stop)
        if out:
            prev = out[-1]
            tail = prev.text.rstrip()
            nxt = sent.text.lstrip()
            merge = False
            if _REF_ABBR.search(tail) and (nxt[:1].isdigit() or nxt[:1].islower()):
                merge = True
            elif _INITIAL.search(tail) and nxt[:1].isupper():
                merge = True
            if merge:
                out[-1] = Sentence(prev.text + sent.text, prev.start, sent.end)
                continue
        out.append(sent)
    # заголовки (строка без знака в конце + пустая строка) — отдельно
    result: List[Sentence] = []
    for s in out:
        result.extend(_split_headings(s))
    return result


def split_tokens(text: str) -> List[Token]:
    return [Token(t.text, t.start, t.stop) for t in tokenize(text)]
