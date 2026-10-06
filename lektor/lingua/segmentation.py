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
CONJ_ADVERBS = {"поэтому", "потому", "следовательно", "значит",
                "притом", "причём", "зато"}

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
                prev = self._near_word(words, w.id, -1)
                # точка после одиночной заглавной буквы — инициал
                # («Иванов И. И. проживает»): ФИО читается слитно,
                # без паузы между инициалами
                if t == "." and prev is not None and len(prev.text) == 1 \
                        and prev.text[0].isupper():
                    decisions[w.id] = (Boundary.WEAK, "инициал (И. И.)")
                else:
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

        # --- вводный оборот важнее «тесных групп» ----------------------
        # obl-группа, окаймлённая запятыми, — это оборот, а не тесная
        # группа («Решение, по общему правилу, может быть обжаловано»)
        if prev is not None and prev.rel == "obl" and (
                self._closes_parataxis(words, comma_id)
                or self._closes_adp_intro(words, comma_id)):
            return Boundary.MEDIUM, "после вводного оборота — нормативная пауза"

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
        if prev.pos == "NUM" and nxt.pos == "NOUN":
            return Boundary.NONE, "запятая разорвала связь «числительное + существительное»"

        # --- места, где пауза уместна -----------------------------------
        if nxt.pos in ("VERB", "ADJ") and self._is_participle(nxt):
            return Boundary.MEDIUM, "причастный/деепричастный оборот — нормативная пауза"
        # вводный оборот: запятая открывает/закрывает parataxis-поддерево
        # («истец, по мнению суда, не представил» — пауза с обеих сторон)
        if self._opens_parataxis(words, comma_id) \
                or self._opens_adp_intro(words, comma_id):
            return Boundary.MEDIUM, "перед вводным оборотом — нормативная пауза"
        if self._closes_parataxis(words, comma_id) \
                or self._closes_adp_intro(words, comma_id):
            return Boundary.MEDIUM, "после вводного оборота — нормативная пауза"
        if nxt.lemma in SUBORD_CONJS or self._is_intro(nxt):
            return Boundary.MEDIUM, "перед подчинительным союзом или вводным словом"
        # наречные союзы и «но»: лёгкая пауза, как у чтеца
        # («…, поэтому суд…», «…, но попросил…»); «не только…, но и…»
        # не рвём
        if nxt.lemma in CONJ_ADVERBS or (
                nxt.lemma == "но" and not self._only_correlation(words, comma_id)):
            return Boundary.MEDIUM, "перед сочинительным союзом — лёгкая пауза"
        if self._is_intro_before(words, comma_id):
            return Boundary.MEDIUM, "после вводного слова или оборота — нормативная пауза"
        # «не/ни» не отрывается от своего слова — но только если это
        # действительно его частица, а не начало сказуемого после оборота
        if (prev.lemma in ("не", "ни") or nxt.lemma in ("не", "ни")) \
                and not self._starts_predicate_after_intro(words, comma_id):
            return Boundary.NONE, "частица «не» не отрывается от своего слова"
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
    def _syn_head_chain(words: List[W], w: W) -> list:
        """Цепочка голов слова (id) до корня."""
        chain = []
        cur = w
        seen = set()
        while cur is not None and cur.id not in seen:
            seen.add(cur.id)
            chain.append(cur.id)
            if cur.head < 0:
                break
            nxt = words[cur.head] if cur.head < len(words) else None
            cur = nxt if (nxt is not None and not nxt.is_punct) else None
        return chain

    def _opens_parataxis(self, words: List[W], comma_id: int) -> bool:
        """Запятая открывает вводный оборот: следующее слово принадлежит
        parataxis-поддереву, а не главному сказуемому."""
        nxt = self._near_word(words, comma_id, 1)
        if nxt is None:
            return False
        chain = self._syn_head_chain(words, nxt)
        # слово само parataxis или подчинено parataxis (кроме корня)
        for wid in chain[:-1]:
            w = words[wid]
            if w.rel == "parataxis":
                return True
        return nxt.rel == "parataxis"

    def _closes_parataxis(self, words: List[W], comma_id: int) -> bool:
        """Запятая закрывает вводный оборот: предыдущее слово — в
        parataxis-поддереве, следующее — вне его (возвращаемся к корню)."""
        prev = self._near_word(words, comma_id, -1)
        nxt = self._near_word(words, comma_id, 1)
        if prev is None or nxt is None:
            return False
        pchain = self._syn_head_chain(words, prev)
        nchain = self._syn_head_chain(words, nxt)
        if pchain and pchain[-1] == prev.id and prev.head < 0:
            return False
        in_intro = any(words[wid].rel == "parataxis" for wid in pchain[:-1])             or prev.rel == "parataxis"
        in_main = not any(words[wid].rel == "parataxis" for wid in nchain[:-1]) \
            and nxt.rel != "parataxis"
        return in_intro and in_main

    @staticmethod
    def _adp_intro_flank(words: List[W], comma_id: int, forward: bool) -> bool:
        """«..., по общему правилу, может быть …» — группа с предлогом
        между парой запятых, не содержащая корня, а за закрывающей
        запятой — сказуемое. forward=True ищет открывающую запятую."""
        # соседнее по направлению слово
        w = None
        idx = comma_id + (1 if forward else -1)
        while 0 <= idx < len(words):
            if words[idx].is_word:
                w = words[idx]
                break
            if words[idx].text in {".", "!", "?", ";", ":"}:
                return False
            idx += (1 if forward else -1)
        if w is None:
            return False
        if forward and w.pos != "ADP":
            return False
        # пройти группу до противоположной запятой
        step = 1 if forward else -1
        idx2 = comma_id + step
        group = []
        closing = None
        while 0 <= idx2 < len(words):
            t = words[idx2]
            if t.is_punct and t.text == ",":
                closing = idx2
                break
            if t.is_punct and t.text in {".", "!", "?", ";", ":"}:
                return False
            if t.is_word:
                group.append(t)
            idx2 += step
        if closing is None or not group:
            return False
        # в группе не должно быть корня предложения
        if any(g.head < 0 for g in group):
            return False
        # слово за закрывающей запятой (для forward) или перед
        # открывающей (для backward) — сказуемое корня
        anchor_idx = closing + (1 if forward else -1)
        anchor = None
        while 0 <= anchor_idx < len(words):
            t = words[anchor_idx]
            if t.is_word:
                anchor = t
                break
            if t.text in {".", "!", "?", ";", ":"}:
                break
            anchor_idx += (1 if forward else -1)
        if anchor is None:
            return False
        # anchor — root или зависит от root (не/быть/…)
        cur = anchor
        hops = 0
        while cur is not None and hops < 4:
            if cur.head < 0:
                return cur.pos in ("VERB", "AUX", "ADJ")   # краткое причастие
            cur = words[cur.head] if cur.head < len(words) else None
            hops += 1
        return False

    def _opens_adp_intro(self, words: List[W], comma_id: int) -> bool:
        return self._adp_intro_flank(words, comma_id, forward=True)

    def _closes_adp_intro(self, words: List[W], comma_id: int) -> bool:
        return self._adp_intro_flank(words, comma_id, forward=False)

    @staticmethod
    def _only_correlation(words: List[W], comma_id: int) -> bool:
        """«не только X, но и Y» / «не столько X, сколько Y» — пауза
        перед «но»/«сколько» не нужна (единая конструкция)."""
        back = 0
        idx = comma_id - 1
        while idx >= 0 and back < 3:
            w = words[idx]
            if w.is_word:
                if w.lemma in ("только", "сколько", "столь", "настолько"):
                    return True
                back += 1
            idx -= 1
        return False

    @staticmethod
    def _starts_predicate_after_intro(words: List[W], punct_id: int) -> bool:
        """«…, не представил» после запятой — начало сказуемого, «не»
        здесь не чья-то частица, и запятую удалять нельзя."""
        idx = punct_id + 1
        while idx < len(words) and not words[idx].is_word:
            if words[idx].text in {".", "!", "?", ";", ":"}:
                return False
            idx += 1
        w = words[idx] if idx < len(words) else None
        if w is None or w.lemma not in ("не", "ни"):
            return False
        idx += 1
        while idx < len(words) and not words[idx].is_word:
            idx += 1
        nxt = words[idx] if idx < len(words) else None
        if nxt is None:
            return False
        return nxt.pos in ("VERB", "PRTF", "PRTS", "GRND", "INFN")

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
                # case может быть строкой, объектом pymorphy или пустым —
                # приводим к строке (у неодушевлённых винительный
                # совпадает с именительным: «неустойку, проценты»)
                ac = str(a.case or "")
                bc = str(b.case or "")
                return (ac == bc or not ac or not bc
                        or {ac, bc} <= {"nomn", "accs"})
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
