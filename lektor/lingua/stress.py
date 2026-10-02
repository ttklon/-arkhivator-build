# -*- coding: utf-8 -*-
"""Словесные ударения (требования 1–7, 28).

Приоритет источников — от самого надёжного к самому слабому:
  1. «ё» в слове — ударение всегда на «ё» (правило русского языка);
  2. пользовательский словарь «словари/ударения.txt» — точные формы и леммы;
  3. встроенный юридический словарь — точные формы и леммы;
  4. словарь омографов — выбор по контексту, иначе нейтральный вариант + отчёт;
  5. ruaccent — нейросетевая расстановка для всех остальных слов;
  6. ничего не найдено — ударение поставит сам движок синтеза (Silero умеет).

Формат разметки — знак «+» ПЕРЕД ударной гласной: «остр+ота», «м+ука».
"""
from __future__ import annotations

import json
import os
import re
import threading
from functools import lru_cache
from typing import Optional

from ..config import USER_DICT_DIR, APP_DIR
from ..report import Report
from .morphology import lemma as morph_lemma
from .tokenizer import split_tokens

VOWELS = "аеёиоуыэюя"
VOWELS_UP = "АЕЁИОУЫЭЮЯ"
_ALL_V = VOWELS + VOWELS_UP

# Односложные служебные слова: не размечаются знаком ударения, чтобы не
# звучали излишне выделенно (разметка полная нужна модели v5_cis_base)
FUNCTION_WORDS = set("""
в во к ко с со у о об от до за на по из над под при про для без сквозь через
и а но да же ли ль бы б уж ведь вот ни не чтоб хоть
я ты мы вы их им ей ему её его ее нас вас нам вам ней них ним
что как этот эта эти тот та те
""".split())

DICT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "dictionaries")


# ---------------------------------------------------------------------------
# Вспомогательные функции работы с разметкой
# ---------------------------------------------------------------------------
def count_vowels(word: str) -> int:
    return sum(1 for c in word if c in _ALL_V)


def stressed_vowel_index(stressed: str) -> Optional[int]:
    """Номер ударной гласной (0-based) в слове со знаком «+».

    «+» стоит ПЕРЕД ударной гласной, значит ударная — первая гласная
    после знака: «пригов+ор» -> 2.
    """
    seen = 0
    for c in stressed:
        if c == "+":
            return seen
        if c in _ALL_V:
            seen += 1
    return None


def place_stress(word: str, vowel_index: int) -> Optional[str]:
    """Вставляет «+» перед гласной с заданным номером, сохраняя регистр."""
    vi = -1
    for i, c in enumerate(word):
        if c in _ALL_V:
            vi += 1
            if vi == vowel_index:
                return word[:i] + "+" + word[i:]
    return None


def transfer_stress(template_stressed: str, word: str) -> Optional[str]:
    """Переносит ударение с образца на другую форму слова (по номеру гласной).

    «пригов+ор» + «приговора» -> «пригов+ора».
    """
    idx = stressed_vowel_index(template_stressed)
    if idx is None or idx >= count_vowels(word):
        return None
    return place_stress(word, idx)


def strip_stress(text: str) -> str:
    """Убирает разметку ударений (для движков, которые её не понимают)."""
    return text.replace("+", "")


def fix_case(template: str, word: str) -> str:
    """Переносит регистр первого символа с исходного слова на результат."""
    if word and template:
        if word[0].isupper() and not template[0].isupper():
            return template[0].upper() + template[1:]
        if word[0].islower() and template[0].isupper() and word.islower() or not word[0].isupper():
            pass
    return template


# ---------------------------------------------------------------------------
# Основной модуль
# ---------------------------------------------------------------------------
class StressAssigner:
    def __init__(self, report: Report, user_dict_dir: str = None):
        self.report = report
        self._lock = threading.Lock()
        self._ruaccent = None
        self._ruaccent_tried = False

        dicts = os.path.join(DICT_DIR)
        self.legal_exact: dict = self._load_json(os.path.join(dicts, "legal_stress.json")).get("слова", {})
        self.homographs: dict = self._load_json(os.path.join(dicts, "homographs.json")).get("омографы", {})

        # леммы словаря (для переноса ударения на формы слова)
        self.legal_lemma: dict = {}
        for k, v in self.legal_exact.items():
            self.legal_lemma.setdefault(morph_lemma(k), (k, v))

        # пользовательские словари
        udir = user_dict_dir or USER_DICT_DIR
        self.user_exact: dict = {}
        self.user_lemma: dict = {}
        self.user_replace: dict = {}
        self._load_user_dicts(udir)

    # -- загрузка словарей --------------------------------------------------
    @staticmethod
    def _load_json(path: str) -> dict:
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _load_user_dicts(self, udir: str) -> None:
        stress_path = os.path.join(udir, "ударения.txt")
        try:
            if os.path.exists(stress_path):
                with open(stress_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#") or "+" not in line:
                            continue
                        key = line.replace("+", "").lower()
                        self.user_exact[key] = line
                        self.user_lemma.setdefault(morph_lemma(key), (key, line))
        except Exception:
            pass
        repl_path = os.path.join(udir, "замены.txt")
        try:
            if os.path.exists(repl_path):
                with open(repl_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#") or "=" not in line:
                            continue
                        k, v = line.split("=", 1)
                        k = k.strip()
                        if k:
                            self.user_replace[k.lower()] = v.strip()
                            self.user_replace[k] = v.strip()
        except Exception:
            pass

    # -- ruaccent (нейросеть, необязательна) ---------------------------------
    def _get_ruaccent(self):
        if self._ruaccent_tried:
            return self._ruaccent
        self._ruaccent_tried = True
        try:
            from ruaccent import RUAccent  # noqa
            acc = RUAccent()
            acc.load()
            self._ruaccent = acc
        except Exception as e:
            self.report.note(
                f"Нейросеть ударений ruaccent недоступна ({type(e).__name__}). "
                "Работают встроенные словари и автоматика движка синтеза.")
        return self._ruaccent

    @lru_cache(maxsize=8192)
    def _ruaccent_sentence(self, text: str) -> str:
        acc = self._get_ruaccent()
        if acc is None:
            return text
        try:
            return acc.put_stress(text, mode="plus")
        except TypeError:
            try:
                return acc.put_stress(text)
            except Exception:
                return text
        except Exception:
            return text

    # -- основная функция -----------------------------------------------------
    def stress_tokens(self, sent_text: str) -> list:
        """Возвращает пары (исходный_токен, форма_для_синтеза) для каждого
        токена предложения. Форма может содержать «+» перед ударной гласной."""
        baseline = self._ruaccent_sentence(sent_text)  # нейросетевой вариант по умолчанию
        tokens = split_tokens(sent_text)
        if not tokens:
            return []

        # базовые ударения от ruaccent: слово -> очередь форм с «+»
        base_forms: dict = {}
        for t in split_tokens(baseline):
            if t.text.isalpha() and "+" in t.text:
                base_forms.setdefault(t.text.replace("+", "").lower(), []).append(t.text)

        pairs: list = []
        word_texts = [t.text.lower() for t in tokens if t.text.isalpha()]
        prev_word = ""
        word_i = -1
        for t in tokens:
            if not t.text.isalpha():
                pairs.append((t.text, t.text))
                continue
            word_i += 1
            low = t.text.lower()
            following = word_texts[word_i + 1: word_i + 4]
            preceding = prev_word
            stressed = self._stress_word(t.text, low, following, preceding, base_forms)
            pairs.append((t.text, stressed or t.text))
            prev_word = low
        return pairs

    def stress_sentence(self, sent_text: str) -> str:
        """Расставляет ударения в предложении, сохраняя пунктуацию и регистр."""
        tokens = split_tokens(sent_text)
        pairs = self.stress_tokens(sent_text)
        if not pairs:
            return sent_text
        return self._rebuild(sent_text, tokens, [p[1] for p in pairs])

    def report_stats_word(self, stressed: str) -> None:
        # фиксация пользовательских ударений для отчёта
        key = strip_stress(stressed).lower()
        if key in self.user_exact or key in self.user_replace:
            self.report.user_stress(stressed)

    def _stress_word(self, word: str, low: str, following: list, preceding: str, base_forms: dict) -> Optional[str]:
        vowels = count_vowels(low)
        if vowels == 0:
            return None

        # 1) «ё» — всегда ударная
        if "ё" in low:
            return place_stress(word, [i for i, c in enumerate(word) if c in _ALL_V].index(
                next(i for i, c in enumerate(word) if c in "ёЁ")))

        # односложные знаменательные слова тоже помечаем: модель v5_cis_base
        # сама ударения не ставит; служебные — не помечаем, иначе звучат
        # излишне выделенно (проверено на слух в открытых проектах)
        if vowels == 1:
            if low in FUNCTION_WORDS or self._pos_of(low) in ("ADP", "CCONJ", "PART", "SCONJ", "PRON"):
                return None
            return place_stress(word, 0)

        # 2) пользовательский словарь (точная форма, затем замены, затем лемма)
        if low in self.user_exact:
            return self._same_case(self.user_exact[low], word)
        if low in self.user_replace:
            return self._same_case(self.user_replace[low], word)
        ul = self.user_lemma.get(morph_lemma(low))
        if ul:
            tr = transfer_stress(ul[1], word)
            if tr:
                return tr

        # 3) юридический словарь (точная форма, затем лемма)
        if low in self.legal_exact:
            return self._same_case(self.legal_exact[low], word)
        ll = self.legal_lemma.get(morph_lemma(low))
        if ll:
            tr = transfer_stress(ll[1], word)
            if tr:
                return tr

        # 4) омографы
        if low in self.homographs:
            return self._resolve_homograph(low, word, following, preceding)

        # 5) вариант ruaccent
        queue = base_forms.get(low)
        if queue:
            form = queue.pop(0)
            return form

        # 6) движок поставит ударение сам
        return None

    def _resolve_homograph(self, low: str, word: str, following: list, preceding: str) -> str:
        entry = self.homographs[low]
        rules = entry.get("правила", [])
        for rule in rules:
            targets = [w.lower() for w in following]
            for base in rule.get("след_слова", []):
                if any(t.startswith(base) for t in targets):
                    return self._same_case(rule["ударение"], word)
            for base in rule.get("пред_слова", []):
                if preceding and preceding.startswith(base):
                    return self._same_case(rule["ударение"], word)
        # контекст не подошёл — нейтральный вариант + запись в отчёт
        self.report.homograph_neutral(word, "… " + (preceding or "") + " " + word + " " + " ".join(following[:2]) + " …")
        return self._same_case(entry.get("по_умолчанию", word), word)

    # -- утилиты ---------------------------------------------------------------
    @staticmethod
    def _pos_of(low: str) -> str:
        from .morphology import pos
        try:
            return pos(low)
        except Exception:
            return "X"

    @staticmethod
    def _same_case(template: str, word: str) -> str:
        if word and template and word[0].isupper() and not template[0].isupper():
            return template[0].upper() + template[1:]
        return template

    @staticmethod
    def _rebuild(original: str, tokens, parts: list) -> str:
        """Собирает строку обратно: между токенами — исходные пробелы."""
        out = []
        pos = 0
        pi = 0
        for t, p in zip(tokens, parts):
            if t.start > pos:
                out.append(original[pos:t.start])
            out.append(p)
            pos = t.end
            pi += 1
        if pos < len(original):
            out.append(original[pos:])
        return "".join(out)
