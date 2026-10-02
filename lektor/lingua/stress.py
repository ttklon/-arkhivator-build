# -*- coding: utf-8 -*-
"""Ударения: ПОЛНАЯ разметка каждого слова для Silero v5_cis_base.

Модель v5_cis_base сама ударения не ставит — так задумано (см.
snakers4/silero-models: «v5_cis_base models assume that proper stress
should be added for each word, i.e. к+ошка»). Слово без знака «+» модель
читает безударным, и речь превращается в кашу. Поэтому этот модуль
гарантирует знак ударения каждому слову, у которого больше одной гласной.

Приоритет источников:
  1. словарь пользователя (словари/ударения.txt, замены.txt) — высший;
  2. юридический словарь (dictionaries/legal_stress.json) + перенос по лемме;
  3. омографы по контексту (dictionaries/homographs.json);
  4. silero-stress — нейросеть Silero (4 млн слов, омографы в контексте,
     модели внутри pip-пакета, интернет не нужен);
  5. ruaccent — если silero-stress не завёлся;
  6. правило «ё» (ударная всегда; в сложных словах — последняя);
  7. эвристика «первая гласная» — чтобы слово не осталось безударным.

Односложные служебные слова знак не получают (иначе звучат выделенно —
проверено на слух в проекте audiobook-ru); «что/как/где/кто» — НЕ служебные,
их знак нужен. Клитики «-то/-ка/-таки» склеиваются с основным словом.
"""
from __future__ import annotations

import json
import os
import re
import threading
from functools import lru_cache
from typing import Optional

from ..config import USER_DICT_DIR
from ..report import Report
from .morphology import lemma as morph_lemma
from .tokenizer import split_tokens

VOWELS = "аеёиоуыэюя"
VOWELS_UP = "АЕЁИОУЫЭЮЯ"
_ALL_V = VOWELS + VOWELS_UP

DICT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "dictionaries")

# Односложные служебные слова: БЕЗ знака ударения. Список выверен на слух
# (audiobook-ru): помеченный предлог звучит как логическое выделение.
# Внимание: «он/она/оно/они», «что/как/где/кто» сюда НЕ входят — им знак нужен.
FUNCTION_WORDS = set("""
в во к ко с со у о об от до за на по из над под при про для без сквозь чрез через
и а но да же ли ль бы б уж ведь ну вот вон ни не чтоб хоть
я ты мы вы их им ей ему его её его нас вас нам вам ней них ним
""".split())

# постфиксы, которые пишутся через дефис: склеиваем для естественного чтения
CLITIC_HYPHEN = re.compile(r"(?<=[А-Яа-яЁё])-(то|ка|таки)(?![+А-Яа-яЁё])",
                           re.IGNORECASE)

WORD_RE = re.compile(r"[А-Яа-яЁёA-Za-z]+(?:[+-][А-Яа-яЁёA-Za-z]+)*")


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


def mark_first_vowel(word: str) -> str:
    """Эвристика: знак перед первой гласной (крайняя мера, см. докстринг)."""
    out = place_stress(word, 0)
    return out if out is not None else word


def mark_yo(word: str) -> str:
    """Знак перед ПОСЛЕДНЕЙ «ё».

    «ё» всегда ударная, но Silero с выключенной своей расстановкой этого
    не знает: слово с «ё» без знака уходит в синтез безударным и читается
    через «е» («извёстка» -> «известка»). В сложных словах ударная обычно
    вторая часть («трёхколёсный» -> «трёхкол+ёсный»).
    """
    i = word.lower().rfind("ё")
    if i < 0:
        return word
    if i > 0 and word[i - 1] == "+":
        return word
    return word[:i] + "+" + word[i:]


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


def glue_clitics(text: str) -> str:
    """«кто-то» -> «кто-то» для чтения: дефис перед безударным постфиксом
    убирается, чтобы синтез не делал паузу внутри слова."""
    return CLITIC_HYPHEN.sub(r"\1", text)


def fix_case(template: str, word: str) -> str:
    """Переносит регистр первого символа с исходного слова на результат.

    Учитывает ведущий «+»: «+это» при оригинале «Это» -> «+Это»."""
    if word and template and word[0].isupper() and not template[:1].isupper():
        if template.startswith("+"):
            return "+" + template[1].upper() + template[2:] if len(template) > 1 else template
        return template[0].upper() + template[1:]
    return template


# ---------------------------------------------------------------------------
# Основной модуль
# ---------------------------------------------------------------------------
# silero-stress грузит .pt при первом обращении — кэшируем на процесс,
# чтобы каждое новое окно/конвейер не перечитывал модель заново
_GLOBAL_ACCENTOR: dict = {}


class StressAssigner:
    def __init__(self, report: Report, user_dict_dir: str = None):
        self.report = report
        self._lock = threading.Lock()

        # нейросеть ударений: silero-stress (основная), ruaccent (запасная)
        self._accentor = None          # silero-stress
        self._accentor_tried = False
        self._ruaccent = None          # ruaccent
        self._ruaccent_tried = False
        self._word_cache: dict = {}    # слово -> помеченная форма
        self.heuristic_count = 0       # слов с предположительным ударением

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

    # -- silero-stress: нейросеть ударений от Silero --------------------------
    def _get_accentor(self):
        """silero-stress: 4 млн слов, модели внутри pip-пакета, офлайн."""
        if self._accentor_tried:
            return self._accentor
        self._accentor_tried = True
        try:
            from silero_stress import load_accentor
            acc = load_accentor("ru")
            # пробный вызов — убеждаемся, что модель реально работает
            probe = acc("проверка")
            if probe and "+" in probe:
                self._accentor = acc
                return acc
            self.report.note("silero-stress ответил без разметки — проверяю ruaccent.")
        except Exception as e:
            self.report.note(f"silero-stress недоступен ({type(e).__name__}).")
        return None

    # -- ruaccent: запасная нейросеть -----------------------------------------
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
                f"Нейросети ударений недоступны ({type(e).__name__}). "
                "Слова вне словарей получат предположительное ударение "
                "(первая гласная) — при странном звучании слова добавьте "
                "его в словари/ударения.txt.")
        return self._ruaccent

    @lru_cache(maxsize=4096)
    def _accent_sentence(self, text: str) -> str:
        """Полный нейросетевой вариант предложения с разметкой."""
        acc = self._get_accentor()
        if acc is not None:
            try:
                return str(acc(text))
            except Exception:
                pass
        ra = self._get_ruaccent()
        if ra is not None:
            try:
                return ra.put_stress(text, mode="plus")
            except TypeError:
                try:
                    return ra.put_stress(text)
                except Exception:
                    return text
            except Exception:
                return text
        return text

    def _accent_word(self, word: str) -> str:
        """Нейросеть по одному слову (для слов, пропущенных в разметке фразы)."""
        low = word.lower()
        if low in self._word_cache:
            return self._word_cache[low]
        out = low
        acc = self._get_accentor()
        if acc is not None:
            try:
                s = str(acc(low))
                s = re.sub(r"[^А-Яа-яЁё+]", "", s)
                if "+" in s:
                    out = s
            except Exception:
                pass
        if out == low:
            ra = self._get_ruaccent()
            if ra is not None:
                try:
                    s = ra.put_stress(low, mode="plus")
                    if "+" in s:
                        out = s
                except Exception:
                    pass
        self._word_cache[low] = out
        return out

    # -- основная функция -----------------------------------------------------
    def stress_tokens(self, sent_text: str) -> list:
        """Пары (исходный_токен, форма_для_синтеза) для каждого токена.

        ГАРАНТИЯ: каждое слово с 2+ гласными получает «+» (модель v5_cis_base
        безударные слова читает кашей).
        """
        tokens = split_tokens(sent_text)
        if not tokens:
            return []

        baseline = self._accent_sentence(sent_text)
        if baseline == sent_text:
            base_forms = {}          # нейросеть недоступна или не размечает
        else:
            # razdel рвёт слова со знаком «+» на куски, поэтому базовую
            # разметку разбираем пословно: ключ — чистая форма, значение —
            # форма со знаком (несколько вхождений -> очередь)
            base_forms: dict = {}
            for w in baseline.split():
                form = w.strip(".,!?;:()«»\"'…—")
                if "+" not in form:
                    continue
                key = form.replace("+", "").lower()
                if key and any(c.isalpha() for c in key):
                    base_forms.setdefault(key, []).append(form)

        word_texts = [t.text.lower() for t in tokens if t.text.isalpha()]
        prev_word = ""
        word_i = -1
        pairs: list = []
        for i, t in enumerate(tokens):
            if not t.text.isalpha():
                pairs.append((t.text, t.text))
                continue
            word_i += 1
            low = t.text.lower()
            following = word_texts[word_i + 1: word_i + 4]
            preceding = prev_word
            base_form = (base_forms.get(low) or [None])[0]
            stressed = self._stress_word(t.text, low, following, preceding, base_form)
            pairs.append((t.text, stressed))
            prev_word = low
        return pairs

    def stress_sentence(self, sent_text: str) -> str:
        """Расставляет ударения в предложении, сохраняя пунктуацию и регистр."""
        tokens = split_tokens(sent_text)
        pairs = self.stress_tokens(sent_text)
        if not pairs:
            return sent_text
        return self._rebuild(sent_text, tokens, [p[1] for p in pairs])

    # ------------------------------------------------------------------
    def _stress_word(self, word: str, low: str, following: list,
                     preceding: str, base_form: Optional[str]) -> str:
        """Итоговая форма слова со знаком ударения (или без — для служебных)."""
        vowels = count_vowels(low)
        if vowels == 0:
            return word

        # односложные: служебные — без знака, остальные — со знаком
        if vowels == 1:
            if low in FUNCTION_WORDS:
                return word
            form = self._dict_or_base(word, low, following, preceding, base_form)
            if form and "+" in form:
                return self._finalize(form, word)
            return self._finalize(mark_first_vowel(word), word)

        # многосложные — полная цепочка источников
        form = self._dict_or_base(word, low, following, preceding, base_form)
        if form and "+" in form:
            return self._finalize(form, word)

        # перезапрос нейросети по одному слову
        solo = self._accent_word(low)
        if "+" in solo:
            return self._finalize(fix_case(solo, word), word)

        # правило «ё»
        if "ё" in low:
            return self._finalize(mark_yo(word), word)

        # крайняя мера: первая гласная (чтобы слово не осталось безударным)
        self.heuristic_count += 1
        return self._finalize(mark_first_vowel(word), word)

    def _dict_or_base(self, word: str, low: str, following: list,
                      preceding: str, base_form: Optional[str]) -> Optional[str]:
        """Словари (пользователь > юр) > омограф-правила > нейросеть фразы."""
        # 1) пользовательский словарь
        if low in self.user_exact:
            self.report.user_stress(self.user_exact[low])
            return self._same_case(self.user_exact[low], word)
        if low in self.user_replace:
            self.report.user_stress(self.user_replace[low])
            return self._same_case(self.user_replace[low], word)
        ul = self.user_lemma.get(morph_lemma(low))
        if ul:
            tr = transfer_stress(ul[1], word)
            if tr:
                return tr

        # 2) юридический словарь
        if low in self.legal_exact:
            return self._same_case(self.legal_exact[low], word)
        ll = self.legal_lemma.get(morph_lemma(low))
        if ll:
            tr = transfer_stress(ll[1], word)
            if tr:
                return tr

        # 3) омографы: только сработавшее конкретное правило (ключи словаря:
        # «ударение» + «след_слова»/«пред_слова»); нейтральный вариант — ниже,
        # потому что нейросеть в контексте обычно точнее дефолта
        if low in self.homographs:
            hit = self._homograph_rule(low, word, following, preceding)
            if hit is not None:
                return hit

        # 4) нейросетевой вариант из разбора всей фразы (контекст!)
        if base_form and "+" in base_form:
            return self._same_case(base_form, word)
        return None

    def _finalize(self, form: str, original: str) -> str:
        """Пост-проверки: «ё» обязана иметь знак; клитики склеиваются."""
        low = form.lower()
        if "ё" in low:
            # знак должен стоять перед последней «ё»
            i = low.rfind("ё")
            if i == 0 or form[i - 1] != "+":
                form = mark_yo(strip_stress(form))
        form = fix_case(form, original)
        form = glue_clitics(form)
        return form

    # ------------------------------------------------------------------
    def _homograph_rule(self, low: str, word: str, following: list,
                        preceding: str) -> Optional[str]:
        """Конкретное правило омографа по соседним словам; None — не сработало.

        Ключи словаря: «ударение» + «след_слова»/«пред_слова» (основы слов).
        """
        entry = self.homographs[low]
        for rule in entry.get("правила", []):
            reading = rule.get("ударение")
            if not reading:
                continue
            nxt = [w.lower() for w in following if w]
            for key in rule.get("след_слова", []):
                if any(t.startswith(key) for t in nxt):
                    self.report.homograph_resolved(
                        word, reading, " ".join([word] + following[:2]),
                        f"перед «{key}…»")
                    return self._same_case(reading, word)
            if preceding:
                for key in rule.get("пред_слова", []):
                    if preceding.startswith(key):
                        self.report.homograph_resolved(
                            word, reading, " ".join([preceding, word]),
                            f"после «{key}…»")
                        return self._same_case(reading, word)
        return None


    # -- утилиты ---------------------------------------------------------------
    @staticmethod
    def _same_case(template: str, word: str) -> str:
        if word and template and word[0].isupper() and not template[:1].isupper():
            if template.startswith("+"):
                return "+" + template[1].upper() + template[2:] if len(template) > 1 else template
            return template[0].upper() + template[1:]
        return template

    @staticmethod
    def _rebuild(original: str, tokens, parts: list) -> str:
        """Собирает предложение из новых форм, сохраняя пробелы и пунктуацию."""
        out = []
        pos = 0
        for t, p in zip(tokens, parts):
            if t.start > pos:
                out.append(original[pos:t.start])
            out.append(p)
            pos = t.end
        if pos < len(original):
            out.append(original[pos:])
        return "".join(out)
