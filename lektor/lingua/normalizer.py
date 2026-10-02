# -*- coding: utf-8 -*-
"""Нормализация текста перед синтезом (требования 23, 24, 25, 7).

Превращает «письменный» текст в «устный»:
  «ст. 159 ч. 2 п. „в“»        -> «статья сто пятьдесят девять, часть вторая, пункт вэ»
  «от 27 июля 2006 года №149-ФЗ» -> «от двадцать седьмого июля две тысячи шестого года номер сто сорок девять фэ-зэ»
  «УК РФ» (первый раз)          -> «Уголовный кодекс Российской Федерации, далее — УК РФ»
  «1000 руб.», «10%», «12:30»  -> «одна тысяча рублей», «десять процентов», «двенадцать часов тридцать минут»

Каждое преобразование фиксируется в отчёте.
"""
from __future__ import annotations

import re
from typing import Optional, Tuple

from ..report import Report
from . import numerals
from .morphology import analyze, pos, inflect_word, word_case
from .tokenizer import split_tokens

MONTHS = "январ\\w*|феврал\\w*|март\\w*|апрел\\w*|ма[йя]\\w*|июн\\w*|июл\\w*|август\\w*|сентябр\\w*|октябр\\w*|ноябр\\w*|декабр\\w*"
MONTHS_RE = re.compile(r"(январ\w*|феврал\w*|март\w*|апрел\w*|ма[йя]\w*|июн\w*|июл\w*|август\w*|сентябр\w*|октябр\w*|ноябр\w*|декабр\w*)")

# ---------------------------------------------------------------------------
# Справочники статейных сокращений (тр. 24)
# base: (полная форма для разворота, род, тип числительного)
# ---------------------------------------------------------------------------
ARTICLE_WORDS = {
    "ст": ("статья", "f", "card"),
    "статья": (None, "f", "card"), "статьи": (None, "f", "card"),
    "статьёй": (None, "f", "card"), "статьей": (None, "f", "card"),
    "статью": (None, "f", "card"),
    "ч": ("часть", "f", "ord"),
    "часть": (None, "f", "ord"), "части": (None, "f", "ord"),
    "частью": (None, "f", "ord"), "частью": (None, "f", "ord"),
    "п": ("пункт", "m", "ord"),
    "пункт": (None, "m", "ord"), "пункта": (None, "m", "ord"),
    "пунктом": (None, "m", "ord"), "пункту": (None, "m", "ord"), "пункты": (None, "m", "ord"),
    "пп": ("подпункт", "m", "ord"),
    "подпункт": (None, "m", "ord"), "подпункта": (None, "m", "ord"), "подпунктом": (None, "m", "ord"),
    "абз": ("абзац", "m", "ord"),
    "абзац": (None, "m", "ord"), "абзаца": (None, "m", "ord"), "абзацем": (None, "m", "ord"),
    "гл": ("глава", "f", "card"),
    "глава": (None, "f", "card"), "главы": (None, "f", "card"), "главой": (None, "f", "card"),
    "разд": ("раздел", "m", "card"),
    "раздел": (None, "m", "card"), "раздела": (None, "m", "card"), "разделом": (None, "m", "card"),
}

LETTERS_FILE = None  # загружается в __init__

PREP_CASES = {
    # предлог -> типичный падеж (используется как подсказка)
    "от": "gent", "до": "gent", "без": "gent", "для": "gent", "около": "gent",
    "у": "gent", "из": "gent", "возле": "gent", "после": "gent", "кроме": "gent",
    "к": "datv", "по": "datv", "благодаря": "datv",
    "перед": "ablt", "над": "ablt", "под": "ablt", "между": "ablt",
    "о": "loct", "об": "loct", "в": "loct", "на": "loct", "при": "loct",
}


def _load_json(path):
    import json, os
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


class TextNormalizer:
    def __init__(self, report: Report, expand_abbrevs: bool = True, dict_dir: str = None):
        self.report = report
        self.expand_abbrevs = expand_abbrevs
        import os
        base = dict_dir or os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "dictionaries")
        ab = _load_json(os.path.join(base, "abbreviations.json"))
        self.abbrs = ab.get("сокращения", {})
        self.shorts = ab.get("мелкие", {})
        letters = _load_json(os.path.join(base, "letters.json"))
        self.letter_names = letters.get("русские", {})
        self.expanded: set = set()   # аббревиатуры, уже расшифрованные (тр. 23)

    # ==================================================================
    def normalize_sentence(self, text: str) -> str:
        text = self._shorts(text)
        text = self._articles(text)          # ст. 159 ч. 2 п. «в»
        text = self._law_numbers(text)       # №149-ФЗ
        text = self._dates(text)             # 27 июля 2006 года, в 2006 году
        text = self._roman(text)             # XX век, глава XVIII
        text = self._ranges(text)            # 158-160
        text = self._money_time_percent(text)
        text = self._numbers(text)           # остальные числа с согласованием
        text = self._abbreviations(text)     # УК РФ и пр. (тр. 7, 23)
        text = re.sub(r"\s+([.,;:!?…])", r"\1", text)
        return re.sub(r"\s+", " ", text).strip()

    # ==================================================================
    # 1. Мелкие сокращения
    def _shorts(self, text: str) -> str:
        for k in sorted(self.shorts, key=len, reverse=True):
            v = self.shorts[k]
            text = re.sub(r"(?<![\w.])" + re.escape(k) + r"(?![\w.])",
                          lambda m, v=v: " " + v + " ", text, flags=re.IGNORECASE)
        return re.sub(r"\s+", " ", text).strip()

    # ==================================================================
    # 2. Статьи, части, пункты (тр. 24)
    _REF_WORD = r"(?:ст|статья|статьи|статьёй|статьей|статью|ч|часть|части|частью|п|пп|пункт|пункта|пунктом|пункту|пункты|подпункт|подпункта|подпунктом|абз|абзац|абзаца|абзацем|гл|глава|главы|главой|разд|раздел|раздела|разделом)"
    _REF_ITEM = r"(?:\d+|[«\"'][а-яё][»\"']|[а-яё])(?=[)\]},.;:!?…\s»]|$)"

    def _articles(self, text: str) -> str:
        # после слова ссылки обязателен конец слова («ст.», «статья », но не «по»)
        rx = re.compile(r"\b(" + self._REF_WORD + r")(?:\.|(?=\s))\s*(" + self._REF_ITEM + r")",
                        re.IGNORECASE)
        out = []
        pos = 0
        last_end = -1
        insert_comma = False
        for m in rx.finditer(text):
            if m.start() < pos:
                continue
            word, value = m.group(1), m.group(2)
            key = word.lower().rstrip(".")
            entry = ARTICLE_WORDS.get(key)
            if entry is None:
                continue
            full, gender, numtype = entry
            prefix = full if full else word.lower()
            quote = value.startswith(("«", '"', "'"))
            value_clean = value.strip("«»\"'")

            # падеж по предлогу перед ссылкой: «по ч. 2» -> «по части второй»
            before = text[max(0, m.start() - 14):m.start()].lower().rstrip()
            case = "nomn"
            for prep, pc in PREP_CASES.items():
                if before.endswith(" " + prep) or before == prep:
                    if word_case(word) != "nomn":
                        case = word_case(word)
                    else:
                        case = pc
                    break
            if case != "nomn":
                from .morphology import inflect_word
                inflected = inflect_word(prefix, {case})
                if inflected:
                    prefix = inflected

            if value_clean.isdigit():
                n = int(value_clean)
                if numtype == "card":
                    words = numerals.cardinal_words(n)
                    if case != "nomn":
                        words = numerals.inflect_words(words, case)
                    spoken = " ".join(words)
                else:
                    if case == "nomn":
                        case = word_case(word) or "nomn"
                    spoken = " ".join(numerals.ordinal_words(n, gender)) \
                        if case == "nomn" else " ".join(numerals.inflect_words(
                            numerals.ordinal_words(n, gender), case, last_only=True))
                reading = f"{prefix} {spoken}"
            elif len(value_clean) == 1 and value_clean.lower() in self.letter_names:
                name = self.letter_names[value_clean.lower()]
                reading = f"{prefix} {name}"
            else:
                continue

            if insert_comma and m.start() == last_end + 1:
                out.append(", ")
            out.append(text[pos:m.start()])
            out.append(reading)
            pos = m.end()
            last_end = m.end()
            # запятая между частями ссылки: «статья 159, часть 2, пункт „в“»
            insert_comma = True
            self.report.number_normalized(m.group(0), reading)
        out.append(text[pos:])
        result = "".join(out)
        return re.sub(r"\s+", " ", result)

    # ==================================================================
    # 3. Номера законов
    def _law_numbers(self, text: str) -> str:
        def law_repl(m):
            n = int(m.group(1))
            reading = " ".join(numerals.cardinal_words(n)) + " фэ-зэ"
            self.report.number_normalized(m.group(0), reading)
            return " " + reading + " "

        text = re.sub(r"(\d{1,3})\s*[-–—]\s*ФЗ\b", law_repl, text)
        text = re.sub(r"№\s*(\d{1,4})\b",
                      lambda m: " номер " + " ".join(numerals.cardinal_words(int(m.group(1)))) + " ", text)
        return re.sub(r"\s+", " ", text).strip()

    # ==================================================================
    # 4. Даты (тр. 25)
    def _dates(self, text: str) -> str:
        # «27 июля 2006 года» / «27 июля»
        def day_repl(m):
            day = int(m.group(1))
            case = "nomn"
            before = text[max(0, m.start() - 12):m.start()].lower()
            for prep in ("от", "до", "с", "по", "перед", "после", "без"):
                if before.rstrip().endswith(prep):
                    case = "gent"
                    break
            words = numerals.ordinal_words(day, "m")
            spoken = " ".join(words if case == "nomn"
                              else numerals.inflect_words(words, case, last_only=True))
            self.report.number_normalized(m.group(0), m.group(2) + " " + spoken)
            return " " + spoken + " " + m.group(2) + " "

        text = re.sub(r"\b(\d{1,2})\s+(" + MONTHS + r")", day_repl, text)

        # «в 2006 году» -> предложный; «с 2006 года» -> родительный
        def year_repl(m):
            year = int(m.group(2))
            prep_raw = m.group(1) or ""
            prep = prep_raw.lower()
            if m.group(3) and m.group(3).lower().startswith("год"):  # «году»
                case = "loct" if prep in ("в", "во", "на") else "gent"
            else:  # «2006 год» / «по 2008 год»
                case = {"по": "accs", "к": "datv", "с": "gent", "от": "gent",
                        "до": "gent", "в": "accs"}.get(prep, "nomn")
            words = numerals.year_words(year, case)
            spoken = " ".join(words)
            self.report.number_normalized(m.group(0), spoken + " " + (m.group(3) or ""))
            return " " + (prep_raw + " " if prep else "") + spoken + " " + (m.group(3) or "") + " "

        text = re.sub(r"\b(в|во|на|с|от|до|по|к)?\s*(\d{4})\s*(год[ауе]?\w*|г\.)",
                      year_repl, text, flags=re.IGNORECASE)
        text = re.sub(r"\s+([.,;:!?…])", r"\1", text)
        return re.sub(r"\s+", " ", text).strip()

    # ==================================================================
    # 5. Римские цифры
    def _roman(self, text: str) -> str:
        def roman_val(ch):
            return {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}.get(ch, 0)

        def roman_to_int(s):
            total = 0
            prev = 0
            for ch in reversed(s):
                v = roman_val(ch)
                total = total - v if v < prev else total + v
                prev = max(prev, v)
            return total if total > 0 else None

        def repl(m):
            n = roman_to_int(m.group(1))
            if not n or n > 3999:
                return m.group(0)
            reading = " ".join(numerals.ordinal_words(n, "m"))
            self.report.number_normalized(m.group(0), reading)
            return " " + reading + " "

        return re.sub(r"\b([IVXLCDM]{1,8})\b(?=\s*(?:век|века|веком|часть|частей|глав|раздел))",
                      repl, text)

    # ==================================================================
    # 6. Диапазоны: «158-160» -> «от ста пятидесяти восьми до ста шестидесяти»
    def _ranges(self, text: str) -> str:
        def repl(m):
            a, b = int(m.group(1)), int(m.group(2))
            if a >= b or b > 10 ** 9:
                return m.group(0)
            wa = numerals.inflect_words(numerals.cardinal_words(a), "gent")
            wb = numerals.inflect_words(numerals.cardinal_words(b), "gent")
            reading = "от " + " ".join(wa) + " до " + " ".join(wb)
            self.report.number_normalized(m.group(0), reading)
            return " " + reading + " "

        return re.sub(r"(?<![\w-])(\d{1,4})\s*[-–—]\s*(\d{1,4})(?![\w-])", repl, text)

    # ==================================================================
    # 7. Деньги, проценты, время
    def _money_time_percent(self, text: str) -> str:
        def money_repl(m):
            n = int(m.group(1).replace(" ", "").replace("\u00a0", ""))
            cur = m.group(2).lower().rstrip(".")
            if cur in ("₽", "р", "руб", "рубль", "рубля", "рублей"):
                reading = " ".join(numerals.rubles_words(n))
            elif cur.startswith("коп"):
                reading = " ".join(numerals.kopecks_words(n))
            else:
                reading = " ".join(numerals.cardinal_words(n)) + " " + m.group(2).rstrip(".")
            self.report.number_normalized(m.group(0), reading)
            return " " + reading + " "

        text = re.sub(r"(\d[\d\u00a0 ]*)\s*(₽|рублей|рубля|рубль|руб\.?|р\.|копейки|копеек|коп\.?)",
                      money_repl, text)

        def pct_repl(m):
            n = m.group(1).replace(",", ".")
            try:
                if "." in n:
                    ip, fr = n.split(".", 1)
                    words = numerals.decimal_words(int(ip), fr)
                else:
                    words = numerals.percent_words(int(n))
                reading = " ".join(words)
            except Exception:
                return m.group(0)
            self.report.number_normalized(m.group(0), reading)
            return " " + reading + " "

        text = re.sub(r"(\d+(?:[.,]\d+)?)\s*%", pct_repl, text)

        def time_repl(m):
            h, mi = int(m.group(1)), int(m.group(2))
            if h > 23 or mi > 59:
                return m.group(0)
            reading = " ".join(numerals.hours_minutes(h, mi))
            self.report.number_normalized(m.group(0), reading)
            return " " + reading + " "

        text = re.sub(r"\b(\d{1,2}):(\d{2})\b", time_repl, text)
        return re.sub(r"\s+", " ", text).strip()

    # ==================================================================
    # 8. Остальные числа — с грамматическим согласованием
    def _numbers(self, text: str) -> str:
        rx = re.compile(r"(\d{1,3}(?:[\s\u00a0]\d{3})+|\d+)(?:[.,](\d+))?")

        def repl(m):
            raw = m.group(0)
            try:
                ip = int(m.group(1).replace(" ", "").replace("\u00a0", ""))
            except ValueError:
                return raw
            frac = m.group(2)
            # падеж: по форме следующего существительного, если перед числом предлог
            case = "nomn"
            before = text[:m.start()].rstrip()
            prev_word = before.split()[-1].lower() if before.split() else ""
            p = analyze(prev_word)
            if p is not None and p.tag and p.tag.POS == "PREP":
                # ищем существительное после числа
                after = text[m.end():].lstrip()
                for tok in split_tokens(after)[:3]:
                    if tok.is_word:
                        nc = word_case(tok.text)
                        if nc:
                            case = nc
                        break
                    if tok.text in {",", ".", ";"}:
                        break
            if frac:
                words = numerals.decimal_words(ip, frac)
            else:
                words = numerals.cardinal_words(ip)
            if case != "nomn" and not frac:
                words = numerals.inflect_words(words, case)
            reading = " ".join(words)
            self.report.number_normalized(raw.replace("\u00a0", " "), reading)
            return " " + reading + " "

        return re.sub(r"\s+", " ", rx.sub(repl, text)).strip()

    # ==================================================================
    # 9. Аббревиатуры (тр. 7, 23)
    def _abbreviations(self, text: str) -> str:
        tokens = split_tokens(text)
        if not tokens:
            return text
        out = []
        i = 0
        n = len(tokens)
        pos = 0
        while i < n:
            t = tokens[i]
            up = t.text.upper().rstrip(".")
            key = up
            entry = self.abbrs.get(key)
            if entry is None and t.text.upper() in self.abbrs:
                entry = self.abbrs[t.text.upper()]

            if entry is not None:
                will_tail = (key in {"УК", "УПК", "ГК", "ГПК", "АПК", "ТК", "ЖК"}
                             and i + 1 < n
                             and tokens[i + 1].text.upper() in {"РФ", "РСФСР"})
                reading = self._abbr_reading(entry, t.text, text, tokens, i,
                                             tail_rf=will_tail)
                out.append(text[pos:t.start])
                out.append(reading)
                pos = t.end
                i += 1
                # «УК РФ»: хвост «РФ» либо уже расшифрован в полной форме,
                # либо читается по буквам
                if will_tail:
                    nt = tokens[i]
                    expanding = self.expand_abbrevs and key in self.expanded
                    if not expanding:
                        tail = " эр эф" if nt.text.upper() == "РФ" else " эр эс эс эф эс эр"
                        out.append(text[pos:nt.start])
                        out.append(tail)
                    pos = nt.end
                    i += 1
                continue
            i += 1

        out.append(text[pos:])
        result = "".join(out)

        # Неизвестные аббревиатуры из заглавных букв — читаем по буквам (тр. 7)
        def unknown(m):
            word = m.group(0)
            if word.upper() in self.abbrs or word.lower() in self.abbrs:
                return word
            p = analyze(word.lower())
            known_word = p is not None and p.score > 0.3 and p.tag.POS not in ("NPRO",)
            if known_word or len(word) > 6 or not word.isupper():
                return word
            letters = [self.letter_names.get(c.lower(), c) for c in word.lower()]
            reading = " ".join(letters)
            self.report.number_normalized(word, reading)
            return " " + reading + " "

        result = re.sub(r"\b[А-ЯЁ]{2,6}\b", unknown, result)
        return re.sub(r"\s+", " ", result).strip()

    def _abbr_reading(self, entry: dict, token_text: str, text: str, tokens, i: int,
                      tail_rf: bool = False) -> str:
        """Чтение аббревиатуры: расшифровка при первом употреблении или краткое чтение."""
        key = token_text.upper().rstrip(".")
        full = entry.get("полностью")
        known = entry.get("известное", False)
        reading = entry.get("чтение", [])
        short = " ".join(reading) if isinstance(reading, list) else str(reading)

        if (full and self.expand_abbrevs and not known and key not in self.expanded):
            self.expanded.add(key)
            # падеж из контекста: предыдущее слово — предлог, либо разбор самого токена
            case = self._context_case(tokens, i)
            phrase = self._inflect_full(full, case)
            self.report.abbreviation_expanded(key, phrase)
            display = short + (" эр эф" if tail_rf else "")
            return phrase + ", далее — " + display
        self.report.abbreviation_reading(key, short)
        return " " + short + " "

    @staticmethod
    def _short_display(key: str, reading) -> str:
        r = " ".join(reading) if isinstance(reading, list) else str(reading)
        return r

    @staticmethod
    def _context_case(tokens, i: int) -> str:
        for j in range(i - 1, max(-1, i - 4), -1):
            t = tokens[j]
            if not t.is_word:
                if t.text in {",", ".", ";"}:
                    break
                continue
            p = analyze(t.text)
            if p is not None and p.tag and p.tag.POS == "PREP":
                return PREP_CASES.get(p.normal_form, "nomn")
            break
        return "nomn"

    @staticmethod
    def _inflect_full(full: list, case: str) -> str:
        """Склоняет первую фразу полного названия к падежу, хвост не трогает."""
        if not full:
            return ""
        head = full[0]
        if case != "nomn":
            words = []
            for w in head:
                inf = inflect_word(w, {case})
                words.append(inf if inf else w)
            head = words
        phrases = [" ".join(head)] + [" ".join(p) for p in full[1:]]
        return " ".join(phrases)
