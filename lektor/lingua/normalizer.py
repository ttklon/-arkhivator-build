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
    "подп": ("подпункт", "m", "ord"),
    "подпункт": (None, "m", "ord"), "подпункта": (None, "m", "ord"), "подпунктом": (None, "m", "ord"),
    "абз": ("абзац", "m", "ord"),
    "абзац": (None, "m", "ord"), "абзаца": (None, "m", "ord"), "абзацем": (None, "m", "ord"),
    "л": ("лист", "m", "card"),
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
    "с": "ablt", "со": "ablt",
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
        text = self._paren_dedupe(text)     # 100 000 (сто тысяч) -> 100 000
        text = self._shorts(text)
        text = self._articles(text)          # ст. 159 ч. 2 п. «в»
        text = self._law_numbers(text)       # №149-ФЗ, дело № 2-123/2021
        text = self._roman(text)             # XX век, глава XVIII
        text = self._phones(text)            # +7 926 123-45-67 — поцифрово
        text = self._digit_groups(text)      # коды вида 123-45-67 — поцифрово
        text = self._ordinals(text)          # 19-й, 2-я, 158-х -> порядковые
        text = self._ranges(text)            # 158-160, 2010-2015 годов
        text = self._fractions(text)         # 1/2 -> «одна вторая»
        text = self._dot_dates(text)         # 12.03.2021 -> «двенадцатого марта …»
        text = self._dates(text)             # 27 июля 2006 года, в 2006 году
        text = self._amounts(text)           # 5 млн, 2 тыс. (согласование)
        text = self._measures(text)          # 5 кг, 60 км/ч, 100 м², −5 °C
        text = self._money_time_percent(text)
        text = self._numbers(text)           # остальные числа с согласованием
        text = self._abbreviations(text)     # УК РФ и пр. (тр. 7, 23)
        text = re.sub(r"\s+([.,;:!?…])", r"\1", text)
        text = re.sub(r"«\s+", "«", text)
        text = re.sub(r"\s+»", "»", text)
        return re.sub(r"\s+", " ", text).strip()

    # ==================================================================
    # 0. Дубли чисел в скобках: «100 000 (сто тысяч) рублей» —
    #    расшифровка словами не читается дважды
    _NUM_NF = {
        "один": 1, "два": 2, "три": 3, "четыре": 4, "пять": 5, "шесть": 6,
        "семь": 7, "восемь": 8, "девять": 9, "десять": 10, "одиннадцать": 11,
        "двенадцать": 12, "тринадцать": 13, "четырнадцать": 14, "пятнадцать": 15,
        "шестнадцать": 16, "семнадцать": 17, "восемнадцать": 18,
        "девятнадцать": 19, "двадцать": 20, "тридцать": 30, "сорок": 40,
        "пятьдесят": 50, "шестьдесят": 60, "семьдесят": 70, "восемьдесят": 80,
        "девяносто": 90, "сто": 100, "двести": 200, "триста": 300,
        "четыреста": 400, "пятьсот": 500, "шестьсот": 600, "семьсот": 700,
        "восемьсот": 800, "девятьсот": 900, "тысяча": 1000,
        "миллион": 10 ** 6, "миллиард": 10 ** 9, "триллион": 10 ** 12,
    }

    def _words_to_int(self, words: str):
        """«сто тысяч» -> 100000; None, если это не число словами."""
        from .morphology import analyze
        total, cur = 0, 0
        for tok in words.split():
            p = analyze(tok)
            nf = p.normal_form if p else tok
            v = self._NUM_NF.get(nf)
            if v is None:
                return None
            if v < 1000:
                cur += v
            else:
                total += (cur or 1) * v
                cur = 0
        return total + cur

    def _paren_dedupe(self, text: str) -> str:
        def repl(m):
            digits = int(re.sub(r"[\s\u00a0]", "", m.group(1)))
            if self._words_to_int(m.group(2)) == digits:
                self.report.number_normalized(
                    m.group(0).strip(),
                    m.group(1).strip() + " (расшифровка в скобках пропущена)")
                return " " + m.group(1) + " "
            return m.group(0)
        return re.sub(r"(?<![\w-])(\d[\d\u00a0 ]{0,18}?)\s*\(([а-яё][а-яё \\-]{2,80})\)",
                      repl, text)

    # ==================================================================
    # 1. Мелкие сокращения
    # сокращения, чувствительные к регистру: «в.» = век, но «В.» = вольты
    _CASE_SENSITIVE_SHORTS = {"в.", "вв."}

    def _shorts(self, text: str) -> str:
        # «±3 мм» читается словами; оставляем знак только в разметке
        text = text.replace("±", " плюс-минус ")
        # «т.н. льгота» -> «так называемая льгота» (согласование по роду)
        def _tn(m):
            from .morphology import analyze, inflect_word
            nxt = m.group(1)
            p = analyze(nxt)
            grams = set()
            if p and p.tag:
                if p.tag.gender in ("masc", "femn", "neut"):
                    grams.add(p.tag.gender)
                if p.tag.number == "plur":
                    grams.add("plur")
            word = inflect_word("называемый", grams) if grams else None
            return "так " + (word or "называемый") + " " + nxt
        text = re.sub(r"(?<![\w.])т\.?\s?н\.?(?![\w.])\s+([а-яё][а-яё-]*)",
                      _tn, text, flags=re.IGNORECASE)
        for k in sorted(self.shorts, key=len, reverse=True):
            v = self.shorts[k]
            flags = 0 if k in self._CASE_SENSITIVE_SHORTS else re.IGNORECASE
            text = re.sub(r"(?<![\w.])" + re.escape(k) + r"(?![\w.])",
                          lambda m, v=v: " " + v + " ", text, flags=flags)
        return re.sub(r"\s+", " ", text).strip()

    # ==================================================================
    # 2. Статьи, части, пункты (тр. 24)
    _REF_WORD = r"(?:ст|статья|статьи|статьёй|статьей|статью|ч|часть|части|частью|п|пп|подп|пункт|пункта|пунктом|пункту|пункты|подпункт|подпункта|подпунктом|абз|абзац|абзаца|абзацем|л|лист|листа|листу|гл|глава|главы|главой|разд|раздел|раздела|разделом)"
    _REF_ITEM = (r"(?:\d+(?:\.\d+)+"      # цепочка «20.2», «3.5.1» — подраздел
                 r"|\d+|[«\"'][а-яё][»\"']|[а-яё])"
                 r"(?=[)\]},;:!?…\s»]|$|\.(?!\d))")

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

            # падеж по предлогу непосредственно перед ссылкой:
            # «по ч. 2» -> «по части второй»; внутри цепочки ссылок
            # («по ч. 2 ст. 159») предлог относится только к первой
            before = ("".join(out) + text[pos:m.start()]).lower().rstrip()
            case = "nomn"
            for prep, pc in PREP_CASES.items():
                if before.endswith(" " + prep) or before == prep:
                    own = word_case(word)
                    if own and own != "nomn":
                        case = own
                    else:
                        case = pc
                    break
            if case != "nomn":
                from .morphology import inflect_word
                inflected = inflect_word(prefix, {case})
                if inflected:
                    prefix = inflected

            if re.fullmatch(r"\d+(?:\.\d+)+", value_clean):
                # подраздел: «ст. 20.2» -> «статья двадцать два»,
                # «п. 3.5.1» -> «пункт три пять один» (по группам)
                spoken = " ".join(
                    " ".join(numerals.cardinal_words(int(g)))
                    for g in value_clean.split("."))
                reading = f"{prefix} {spoken}"
            elif value_clean.isdigit():
                n = int(value_clean)
                if numtype == "card":
                    # номер-обозначение читается именительным:
                    # «на листе пять», «по статье сто пятьдесят девять»
                    words = numerals.cardinal_words(n)
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

        # номера судебных дел: «№ 2-123/2021» — «номер два — сто двадцать
        # три — две тысячи двадцать первый» (не «от двух до ста двадцати»)
        def case_repl(m):
            wa = " ".join(numerals.cardinal_words(int(m.group(1))))
            wb = " ".join(numerals.cardinal_words(int(m.group(2))))
            tail = ""
            if m.group(3):
                y = int(m.group(3))
                if 1000 <= y <= 2100:
                    tail = " — " + " ".join(numerals.ordinal_words(y, "m"))
                else:
                    tail = " — " + " ".join(numerals.cardinal_words(y))
            reading = f"номер {wa} — {wb}{tail}"
            self.report.number_normalized(m.group(0), reading)
            return " " + reading + " "

        text = re.sub(r"(?:№|\bномер\b)\s*(\d{1,4})\s*[-–—]\s*(\d{1,5})"
                      r"(?:\s*/\s*(\d{2,4}))?(?!\d)", case_repl, text)
        text = re.sub(r"№\s*(\d{1,4})\b",
                      lambda m: " номер " + " ".join(numerals.cardinal_words(int(m.group(1)))) + " ", text)
        return re.sub(r"\s+", " ", text).strip()

    # ==================================================================
    # 4. Даты (тр. 25)
    def _dates(self, text: str) -> str:
        # адресные сокращения: «г. Москва» -> «город Москва», «ул. Ленина,
        # д. 5» -> «улица Ленина, дом пять» (но «2006 г.» — это год!)
        def addr_repl(m):
            if re.search(r"\d{4}\s*$", text[max(0, m.start() - 12):m.start()]):
                return m.group(0)  # перед нами год — «в 2006 г.»
            return {"г": "город ", "ул": "улица ", "пр": "проспект ",
                    "ш": "шоссе ", "д": "дом "}[m.group(1).lower()]

        text = re.sub(r"\b(г|ул|пр|ш|д)\.\s*(?=[А-ЯЁ0-9])", addr_repl, text)

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
            # «2010-2015»: второй год — часть диапазона, он уже прочитан
            if m.start() > 0 and text[m.start() - 1] in "-–—":
                return m.group(0)
            year = int(m.group(2))
            prep_raw = m.group(1) or ""
            prep = prep_raw.lower()
            g3 = (m.group(3) or "").strip()
            if g3.lower().startswith("год") or g3 in ("г.", "г"):
                case = "loct" if prep in ("в", "во", "на") else "gent"
                if g3 in ("г.", "г"):  # «в 2006 г.» = «в 2006 году»
                    g3 = {"loct": "году", "gent": "года", "datv": "году",
                          "accs": "год", "nomn": "год",
                          "ablt": "годом"}.get(case, "года")
            else:  # «2006 год» / «по 2008 год»
                case = {"по": "accs", "к": "datv", "с": "gent", "от": "gent",
                        "до": "gent", "в": "accs"}.get(prep, "nomn")
            words = numerals.year_words(year, case)
            spoken = " ".join(words)
            self.report.number_normalized(m.group(0), spoken + " " + g3)
            return " " + (prep_raw + " " if prep else "") + spoken + \
                (" " + g3 if g3 else "") + " "

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
            word = m.group(2)
            low = word.lower()
            gender = "f" if low.startswith(("глав", "част")) else "m"
            # падеж — по форме следующего слова («в XVIII веке» -> предложный)
            case = word_case(word) or "nomn"
            if case == "nomn":
                before = text[:m.start()].rstrip().lower().split()
                prep = before[-1] if before else ""
                if prep in ("в", "во", "на"):
                    case = "loct"
                elif prep in ("с", "со", "от", "до", "без"):
                    case = "gent"
            words = numerals.ordinal_words(n, gender)
            if case != "nomn":
                words = numerals.inflect_words(words, case, last_only=True)
                w_inf = inflect_word(word, {case})
                if w_inf:
                    word = w_inf
            reading = " ".join(words) + " " + word
            self.report.number_normalized(m.group(0), reading)
            return " " + reading + " "

        text = re.sub(r"\b([IVXLCDM]{1,8})\b\s+"
                      r"(век\w*|часть\w*|част\w*|глав\w*|раздел\w*)",
                      repl, text)

        # обратный порядок: «часть II», «главе XVIII», «том III»
        def repl_back(m):
            word, roman = m.group(1), m.group(2)
            n = roman_to_int(roman)
            if not n or n > 3999:
                return m.group(0)
            low = word.lower()
            gender = "f" if low.startswith(("глав", "част")) else "m"
            # «том» омонимично (предложный падеж) — как название тома
            # читаем именительным: «том третий»
            case = {"том": "nomn"}.get(low, word_case(word) or "nomn")
            words = numerals.ordinal_words(n, gender)
            if case != "nomn":
                words = numerals.inflect_words(words, case, last_only=True)
            reading = word + " " + " ".join(words)
            self.report.number_normalized(m.group(0), reading)
            return " " + reading + " "

        return re.sub(r"\b([Чч]аст\w*|[Гг]лав\w*|[Тт]ом\w*|[Рр]аздел\w*)\s+([IVXLCDM]{1,8})\b",
                      repl_back, text)

    # ==================================================================
    # 5а. Телефоны: «+7 926 123-45-67» -> «плюс семь, девять два шесть…»
    DIGIT_NAMES = {"0": "ноль", "1": "один", "2": "два", "3": "три", "4": "четыре",
                   "5": "пять", "6": "шесть", "7": "семь", "8": "восемь", "9": "девять"}

    def _digits_spoken(self, digits: str) -> str:
        return " ".join(self.DIGIT_NAMES.get(ch, ch) for ch in digits)

    def _phones(self, text: str) -> str:
        def repl(m):
            code = m.group(1)
            code_word = ("плюс семь" if code == "+7"
                         else "восемь" if code == "8" else "семь")
            groups = [m.group(i) for i in (3, 5, 7, 9)]
            parts = [code_word] + [self._digits_spoken(g) for g in groups if g]
            reading = ", ".join(parts)
            self.report.number_normalized(m.group(0), reading)
            return " " + reading + " "

        rx = (r"(?<![\d+])(\+7|8|7)([\s(\u2013\u2014-]*)(\d{3})"
              r"([\s)\u2013\u2014-]+)(\d{3})([\s\u2013\u2014-]*)"
              r"(\d{2})([\s\u2013\u2014-]*)(\d{2})(?!\d)")
        return re.sub(rx, lambda m: repl(m), text)

    # ==================================================================
    # 5б. Группы цифр с тире: «123-45-67» — поцифрово (это код, не диапазон)
    def _digit_groups(self, text: str) -> str:
        def repl(m):
            digits = re.sub(r"\D", "", m.group(0))
            if not 6 <= len(digits) <= 12:
                return m.group(0)
            reading = ", ".join(self._digits_spoken(g)
                                for g in re.findall(r"\d+", m.group(0)))
            self.report.number_normalized(m.group(0), reading)
            return " " + reading + " "

        rx = r"(?<![\d/.])(?:\d{2,4}[\s\u2013\u2014-]+){2,}\d{2,4}(?![\d/.])"
        return re.sub(rx, lambda m: repl(m), text)

    # ==================================================================
    # 5в. Порядковые с суффиксом: «19-й», «2-я», «158-х», «в 3-м»
    _ORD_SUFFIX = {
        "й": ("m", "nomn"), "го": ("m", "gent"), "му": ("m", "datv"),
        "ти": ("m", "gent"),
        "м": ("m", None),    # предложный после «в/на/о», иначе творительный
        "я": ("f", "nomn"), "ю": ("f", "accs"),
        "е": ("n", "nomn"),
        "х": ("pl", "gent"), "ми": ("pl", "ablt"),
    }

    def _ordinals(self, text: str) -> str:
        def repl(m):
            n = int(m.group(1))
            suf = m.group(2).lower()
            gender, case = self._ORD_SUFFIX.get(suf, ("m", "nomn"))
            if case is None:
                before = text[:m.start()].rstrip().lower().split()
                prep = before[-1] if before else ""
                case = "loct" if prep in ("в", "во", "на", "о", "об", "при", "по") \
                    else "ablt"
            # «3-х комнатная» -> «трёхкомнатная» (слитно, одним словом)
            if suf in ("х", "ти") and m.group(3):
                num_part = "".join(numerals.inflect_words(
                    numerals.cardinal_words(n), "gent"))
                reading = num_part + m.group(3)
                self.report.number_normalized(m.group(0).strip(), reading)
                return " " + reading + " "
            words = numerals.ordinal_words(n, "m" if gender == "pl" else gender)
            if gender == "pl":
                words[-1] = inflect_word(words[-1], {"plur"}) or words[-1]
            if case and case != "nomn":
                words = numerals.inflect_words(words, case, last_only=True)
            reading = " ".join(words)
            self.report.number_normalized(m.group(0), reading)
            return " " + reading + " "

        rx = (r"(?<![\d\w])(\d{1,4})\s*[-–—]\s*"
              r"(й|го|му|ти|м|я|ю|е|х|ми)(?![а-яё\w-])\s*(комнат\w*)?")
        return re.sub(rx, lambda m: repl(m), text)

    # ==================================================================
    # 6б. Единицы измерения: «23 кг», «60 км/ч», «100 м²», «−5 °C»
    _MEASURES = {
        "кг": (("килограмм", "килограмма", "килограммов"), "m"),
        "г": (("грамм", "грамма", "граммов"), "m"),
        "мг": (("миллиграмм", "миллиграмма", "миллиграммов"), "m"),
        "т": (("тонна", "тонны", "тонн"), "f"),
        "км": (("километр", "километра", "километров"), "m"),
        "м": (("метр", "метра", "метров"), "m"),
        "см": (("сантиметр", "сантиметра", "сантиметров"), "m"),
        "мм": (("миллиметр", "миллиметра", "миллиметров"), "m"),
        "л": (("литр", "литра", "литров"), "m"),
        "мл": (("миллилитр", "миллилитра", "миллилитров"), "m"),
        "гб": (("гигабайт", "гигабайта", "гигабайтов"), "m"),
        "мб": (("мегабайт", "мегабайта", "мегабайтов"), "m"),
        "кб": (("килобайт", "килобайта", "килобайтов"), "m"),
        "тб": (("терабайт", "терабайта", "терабайтов"), "m"),
        "гц": (("герц", "герца", "герц"), "m"),
        "мгц": (("мегагерц", "мегагерца", "мегагерц"), "m"),
        "кгц": (("килогерц", "килогерца", "килогерц"), "m"),
        "вт": (("ватт", "ватта", "ватт"), "m"),
        "квт": (("киловатт", "киловатта", "киловатт"), "m"),
        "в": (("вольт", "вольта", "вольт"), "m"),
        "а": (("ампер", "ампера", "ампер"), "m"),
        "град": (("градус", "градуса", "градусов"), "m"),
    }

    def _measures(self, text: str) -> str:
        # температура: «−5 °C» -> «минус пять градусов Цельсия»
        def temp_repl(m):
            sign = m.group(1) or ""
            raw = m.group(2).replace(",", ".")
            scale = (m.group(3) or "").upper()
            n = float(raw) if "." in raw else int(raw)
            words = numerals.cardinal_words(int(n)) if float(n).is_integer() \
                else numerals.decimal_words(int(raw.split(".")[0]), raw.split(".")[1])
            unit = self._plural_unit(int(n) if float(n).is_integer() else 5,
                                     self._MEASURES["град"][0])
            sign_word = {"−": "минус ", "–": "минус ", "-": "минус ",
                         "+": "плюс "}.get(sign, "")
            reading = (sign_word + " ".join(words) + " " + unit
                       + (" Цельсия" if scale == "C" or scale == "С"
                          else " Фаренгейта" if scale == "F" else ""))
            self.report.number_normalized(m.group(0).strip(), reading)
            return " " + reading + " "

        text = re.sub(r"([\u2212\u2013+-]?)\s*(\d+(?:[.,]\d+)?)\s*°\s*([CFСF]?)",
                      temp_repl, text)

        # единицы после числа
        def unit_repl(m):
            raw = m.group(1).replace(",", ".")
            unit_raw = m.group(2)
            key = unit_raw.lower().split("/")[0]
            # квадратные метры: «м²», «м2», «кв. м» (но не «кВт»!)
            if key in ("м²", "м2", "м^2") or re.fullmatch(r"кв\.?\s*м", key):
                return " " + self._square_meters(raw, m.group(0)) + " "
            forms, gender = self._MEASURES[key]
            if "." in raw:
                ip, fr = raw.split(".", 1)
                words = numerals.decimal_words(int(ip), fr) + [forms[1]]
            else:
                n = int(raw)
                words = numerals.cardinal_words(n, gender) + [self._plural_unit(n, forms)]
            # «60 км/ч» -> «шестьдесят километров в час»
            if unit_raw.endswith("/ч") or unit_raw.endswith("/час"):
                words.append("в час")
            reading = " ".join(words)
            self.report.number_normalized(m.group(0), reading)
            return " " + reading + " "

        # многобуквенные единицы — без учёта регистра («кг», «Гб», «кВт»);
        # «В.» (вольт) не должен превращаться в «век» — это делает _shorts
        rx_multi = re.compile(
            r"(\d+(?:[.,]\d+)?)\s*(км/час|км/ч|м\u00b2|м2|м\^2|кв\.?\s*м|"
            r"кг|мг|км|см|мм|мл|гб|мб|кб|тб|гц|мгц|кгц|квт|вт)"
            r"(?![а-яёА-ЯЁa-zA-Z])", re.IGNORECASE)
        # одиночные строчные («5 г», «10 м») и заглавные («220 В», «12 А»)
        rx_single_lo = re.compile(
            r"(\d+(?:[.,]\d+)?)\s*([гтмл])(?![а-яёА-ЯЁa-zA-Z])")
        rx_single_up = re.compile(
            r"(\d+(?:[.,]\d+)?)\s*([ВА])(?![а-яёА-ЯЁa-zA-Z])")
        text = rx_multi.sub(lambda m: unit_repl(m), text)
        text = rx_single_lo.sub(lambda m: unit_repl(m), text)
        return rx_single_up.sub(lambda m: unit_repl(m), text)

    def _square_meters(self, raw: str, orig: str) -> str:
        n = int(raw.replace(",", "").replace(".", "")) if "." not in raw and "," not in raw \
            else int(float(raw.replace(",", ".")))
        words = numerals.cardinal_words(n)
        if 11 <= n % 100 <= 14 or n % 10 not in (1,):
            unit = "квадратных " + self._plural_unit(n, ("метр", "метра", "метров"))
        else:
            unit = "квадратный метр"
        reading = " ".join(words) + " " + unit
        self.report.number_normalized(orig, reading)
        return reading

    # ==================================================================
    # 6. Дроби: «1/2» -> «одна вторая», «3/4» -> «три четверти»
    _FRAC_SPECIAL_1 = {2: "вторая", 3: "треть", 4: "четверть"}
    _FRAC_SPECIAL_FEW = {3: "трети", 4: "четверти"}
    _FRAC_PL = {2: "вторых", 3: "третьих", 4: "четвёртых", 5: "пятых",
                6: "шестых", 7: "седьмых", 8: "восьмых", 9: "девятых",
                10: "десятых", 11: "одиннадцатых", 12: "двенадцатых",
                13: "тринадцатых", 14: "четырнадцатых", 15: "пятнадцатых",
                16: "шестнадцатых", 17: "семнадцатых", 18: "восемнадцатых",
                19: "девятнадцатых", 20: "двадцатых", 30: "тридцатых",
                40: "сороковых", 50: "пятидесятых", 100: "сотых",
                1000: "тысячных"}

    def _fractions(self, text: str) -> str:
        def repl(m):
            n, d = int(m.group(1)), int(m.group(2))
            if n == 0 or d == 0 or d == 1:
                return m.group(0)
            if n == 1:
                if d in self._FRAC_SPECIAL_1:
                    denom = self._FRAC_SPECIAL_1[d]
                else:
                    ow = numerals.ordinal_words(d, "f")
                    denom = ow[-1]
                reading = "одна " + denom
            elif 2 <= n % 100 <= 4 and not 11 <= n % 100 <= 14:
                if d in self._FRAC_SPECIAL_FEW:
                    denom = self._FRAC_SPECIAL_FEW[d]
                else:
                    denom = self._denom_pl(d)
                reading = " ".join(numerals.cardinal_words(n, "f")) + " " + denom
            else:
                reading = " ".join(numerals.cardinal_words(n, "f")) + " " + self._denom_pl(d)
            self.report.number_normalized(m.group(0), reading)
            return " " + reading + " "

        return re.sub(r"(?<![\d/])(?<![\d][.,])(\d{1,4})\s*/\s*(\d{1,4})"
                      r"(?![\d/])(?![.,]\d)",
                      lambda m: repl(m), text)

    def _denom_pl(self, d: int) -> str:
        if d in self._FRAC_PL:
            return self._FRAC_PL[d]
        ow = numerals.ordinal_words(d, "f")
        inf = inflect_word(ow[-1], {"gent", "plur"})
        return inf or (ow[-1] + "ых")

    # ==================================================================
    # 6. Диапазоны: «158-160» -> «от ста пятидесяти восьми до ста шестидесяти»
    def _ranges(self, text: str) -> str:
        def repl(m):
            a, b = int(m.group(1)), int(m.group(2))
            if a >= b or b > 10 ** 9:
                return m.group(0)
            # цепочка групп «123-45-67» — это код, а не диапазон
            # (обычно уже разобран раньше, здесь — страховка)
            if re.match(r"\s*[-–—]\s*\d", text[m.end():]) or \
                    re.search(r"\d\s*[-–—]\s*$", text[:m.start()]):
                return m.group(0)
            year_word = (m.group(3) or "").strip()  # «годах», «гг.» и т.п.
            if year_word in ("гг.", "гг") and 1000 <= a <= 2100:
                # «в 2010-2015 гг.» -> «годах»; «практика 2010-2015 гг.» ->
                # «годов» (родительный, как после существительного)
                prep = text[max(0, m.start() - 10):m.start()].strip().lower()
                if prep.endswith(("в", "во", "на")):
                    year_word = "годах"
                elif prep.endswith(("с", "со", "до", "от", "по")):
                    year_word = "годов"
                else:
                    year_word = "годов"
            if year_word and 1000 <= a <= 2100 and 1000 <= b <= 2100:
                # диапазон лет: «в 2010-2015 годах» -> порядковые в падеже
                # слова «год»: «в две тысячи десятом — две тысячи пятнадцатом годах»
                case = word_case(year_word.strip()) or "nomn"
                wa = numerals.inflect_words(numerals.ordinal_words(a, "m"), case, last_only=True)
                wb = numerals.inflect_words(numerals.ordinal_words(b, "m"), case, last_only=True)
                reading = " ".join(wa) + " — " + " ".join(wb) + " " + year_word.strip()
                self.report.number_normalized(m.group(0), reading)
                return " " + reading + " "
            # «10-15%» — проценты в диапазоне («выросла на 10-15%»)
            if m.group(4):
                before = text[:m.start()].rstrip().rsplit(" ", 1)[-1].lower()
                wa0 = numerals.cardinal_words(a)
                wb0 = numerals.cardinal_words(b)
                if before in ("в", "во", "на", "с", "к", "по", "при", "для"):
                    reading = " ".join(wa0) + " — " + " ".join(wb0)
                else:
                    reading = ("от " + " ".join(wa0) +
                               " до " + " ".join(wb0))
                b10, b100 = b % 10, b % 100
                pword = ("процента" if 2 <= b10 <= 4 and b100 not in (12, 13, 14)
                         else "процентов")
                reading += " " + pword
                self.report.number_normalized(m.group(0), reading)
                return " " + reading + " "
            wa = numerals.cardinal_words(a)
            wb = numerals.cardinal_words(b)
            # перед диапазоном уже есть предлог («в 158-160 статьях») —
            # не добавляем свой «от … до …»; падеж чисел — по предлогу:
            # «в/во» — предложный, «на» — винительный, «к/по» — дательный
            before = text[:m.start()].rstrip().rsplit(" ", 1)[-1].lower()
            if before in ("в", "во", "на", "с", "к", "по", "при", "для"):
                if before in ("в", "во"):
                    case = "loct"
                elif before == "на":
                    case = "accs"
                elif before in ("к", "по"):
                    case = "datv"
                else:
                    case = "gent"
                wa = numerals.inflect_words(wa, case)
                wb = numerals.inflect_words(wb, case)
                reading = " ".join(wa) + " — " + " ".join(wb)
            else:
                wa = numerals.inflect_words(wa, "gent")
                wb = numerals.inflect_words(wb, "gent")
                reading = "от " + " ".join(wa) + " до " + " ".join(wb)
            self.report.number_normalized(m.group(0), reading)
            return " " + reading + " "

        return re.sub(r"(?<![\w-])(\d{1,4})\s*[-–—]\s*(\d{1,4})(?![\w-])"
                      r"(\s+(?:год\w*|гг\.?|г\.))?(\s*%)?",
                      lambda m: repl(m), text)

    # ==================================================================
    # 6а. Круглые единицы: «5 млн», «2 тыс.», «1,5 млрд руб.» — со-
    # согласованием («две тысячи», а не «два тысяч»)
    _UNITS = {
        "тыс": (("тысяча", "тысячи", "тысяч"), "f"),
        "млн": (("миллион", "миллиона", "миллионов"), "m"),
        "млрд": (("миллиард", "миллиарда", "миллиардов"), "m"),
    }

    @staticmethod
    def _plural_unit(n: int, forms) -> str:
        if 11 <= n % 100 <= 14:
            return forms[2]
        return forms[0] if n % 10 == 1 else forms[1] if n % 10 in (2, 3, 4) else forms[2]

    def _amounts(self, text: str) -> str:
        def repl(m):
            raw = m.group(1).replace(",", ".")
            unit_key = m.group(2).lower().rstrip(".")
            forms, gender = self._UNITS[unit_key]
            cur = (m.group(3) or "").lower().rstrip(".")
            # падеж по предлогу: «с 5 млн» -> «с пятью миллионами»
            case = "nomn"
            before = text[:m.start()].rstrip().split()
            if before:
                pw = before[-1].lower()
                if pw in PREP_CASES:
                    case = PREP_CASES[pw]
            if "." in raw:
                ip, fr = raw.split(".", 1)
                # «полтора миллиарда» — ед. число; при склонении — мн.:
                # «с полутора миллиардами»
                base = forms[1] if case == "nomn" else forms[2]
                words = numerals.decimal_words(int(ip), fr) + [base]
            else:
                n = int(raw)
                words = numerals.cardinal_words(n, gender) + [self._plural_unit(n, forms)]
            if case != "nomn":
                # единица измерения — во множественном числе:
                # «с двумя тысячами», а не «с двумя тысячей»
                head = numerals.inflect_words(words[:-1], case)
                unit_inf = (inflect_word(words[-1], {"plur", case})
                            or inflect_word(words[-1], {case}) or words[-1])
                words = head + [unit_inf]
            reading = " ".join(words)
            if cur.startswith("руб"):
                reading += " рублей"   # после «тысяча/миллион» — всегда род. падеж мн. ч.
            elif cur.startswith("коп"):
                reading += " копеек"
            self.report.number_normalized(m.group(0), reading)
            return " " + reading + " "

        rx = (r"(\d+(?:[.,]\d+)?)\s*(тыс\.?|млн\.?|млрд\.?)"
              r"\s*((?:руб|коп)\.?(?![а-яёА-ЯЁ]))?")
        return re.sub(rx, lambda m: repl(m), text)

    # ==================================================================
    # 6в. Даты через точку: «12.03.2021» -> «двенадцатого марта
    # две тысячи двадцать первого года»; «01.09» -> «первого сентября».
    # Не дата: пункты «п. 3.5» и версии «3.5.1».
    _MONTHS_GEN = ["", "января", "февраля", "марта", "апреля", "мая", "июня",
                   "июля", "августа", "сентября", "октября", "ноября", "декабря"]

    def _dot_dates(self, text: str) -> str:
        def repl(m):
            d, mo = int(m.group(1)), int(m.group(2))
            has_year = m.group(3) is not None
            if not (1 <= d <= 31 and 1 <= mo <= 12):
                return m.group(0)
            # «версия 2.10», «сборка 3.5» — не дата
            wbefore = text[max(0, m.start() - 14):m.start()].lower().rstrip()
            if re.search(r"(?:верси|сборк|релиз|обновлени|build|v)[а-яё]*$", wbefore):
                return m.group(0)
            if not has_year:
                # без года похоже на дату только при двузначных частях
                # («01.09», «31.12», «12.03»); «3.5» — версия или пункт
                if not (len(m.group(1)) == 2 or len(m.group(2)) == 2 or d > 12):
                    return m.group(0)
                # «п. 3.5» — номер пункта, а не дата
                if re.search(r"(?:п|пп|ст|ч|абз|подп|разд|гл|пункт|часть|"
                             r"статья|раздел|глава)\.?\s*$", wbefore):
                    return m.group(0)
            case = "nomn"
            before_w = text[:m.start()].rstrip().lower().split()
            prep = before_w[-1] if before_w else ""
            if prep in ("от", "до", "с", "со", "перед", "после", "без", "около"):
                case = "gent"
            elif prep in ("по", "к"):
                case = "datv"
            day_words = numerals.ordinal_words(d, "m")
            if case != "nomn":
                day_words = numerals.inflect_words(day_words, case, last_only=True)
            reading = " ".join(day_words) + " " + self._MONTHS_GEN[mo]
            if has_year:
                y = int(m.group(3))
                if y < 100:
                    y += 2000 if y < 51 else 1900
                if 1000 <= y <= 2100:
                    reading += " " + " ".join(numerals.year_words(y, "gent")) + " года"
                else:
                    reading += " " + " ".join(numerals.cardinal_words(y)) + " года"
            self.report.number_normalized(m.group(0), reading)
            return " " + reading + " "

        rx = r"(?<![\d.])(\d{1,2})\.(\d{1,2})(?:\.(\d{4}|\d{2}))?(?!\d)(?!\.\d)"
        text = re.sub(rx, lambda m: repl(m), text)

        # «п. 3.5», «ст. 20.2» — номер подраздела: «пункт три пять»
        def subsec_repl(m):
            # группы читаются числами: «3.5» -> «три пять», «20.2» -> «двадцать два»
            spoken = " ".join(
                " ".join(numerals.cardinal_words(int(g)))
                for g in m.group(2).split("."))
            # «п.» -> «пункт», «ст.» -> «статья»
            key = m.group(1).lower().rstrip(".")
            entry = ARTICLE_WORDS.get(key)
            word = (entry[0] if entry and entry[0] else m.group(1)).lower()
            reading = word + " " + spoken
            self.report.number_normalized(m.group(1) + " " + m.group(2), reading)
            return " " + reading + " "

        text = re.sub(r"((?:п|пп|подп|ст|ч|абз|разд|гл|пункт\w*|часть\w*|"
                      r"статья\w*|раздел\w*|глава\w*)\.?)\s+"
                      r"(\d{1,2}(?:\.\d{1,2}){1,3})(?![\d.])",
                      subsec_repl, text, flags=re.IGNORECASE)

        # оставшиеся цепочки «3.5.1», «192.168.1.1», «версия 2.10» —
        # читаем поцифрово, а не как даты или десятичные
        def chain_repl(m):
            # «2.10» -> «два десять», «192.168.1.1» -> «сто девяносто два …»
            reading = " ".join(
                " ".join(numerals.cardinal_words(int(g)))
                for g in m.group(1).split("."))
            self.report.number_normalized(m.group(0), reading)
            return " " + reading + " "

        text = re.sub(r"(?<![\d.])(\d{1,3}(?:\.\d{1,3})+)(?!\d)(?!\.\d)",
                      chain_repl, text)
        return text

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
                    fr = fr.rstrip("0") or "0"
                    words = numerals.decimal_words(int(ip), fr)
                    if words[-2:] == ["с", "половиной"] or words[0] == "полтора":
                        words.append("процента" if words[0] in ("полтора",) or
                                     int(ip) % 10 in (2, 3, 4) and int(ip) % 100 not in (12, 13, 14)
                                     else "процентов")
                    else:
                        words.append("процента" if int(fr) in (2, 3, 4) else "процентов")
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
            digits = m.group(1).replace(" ", "").replace("\u00a0", "")
            # длинные номера (ИНН, счёта) — поцифрово: «семь семь ноль…»,
            # а не «семь миллиардов семьсот семь миллионов…»
            if not frac:
                window = text[max(0, m.start() - 16):m.start()].upper()
                id_ctx = re.search(r"(ИНН|ОГРН\w*|СНИЛС|КПП|БИК)\s*[:№]?\s*$", window)
                if len(digits) >= 7 or (len(digits) in (5, 6) and id_ctx):
                    reading = self._digits_spoken(digits)
                    self.report.number_normalized(raw.replace("\u00a0", " "), reading)
                    return " " + reading + " "
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
                # автор уже расшифровал сам («…кодекса…, далее — ГК РФ»):
                # не добавляем вторую расшифровку, читаем кратко
                window = text[max(0, t.start - 60):t.start].lower()
                already = "далее" in window or "введено обозначение" in window
                if already:
                    short = " ".join(entry.get("чтение", [])) \
                        if isinstance(entry.get("чтение"), list) else str(entry.get("чтение", t.text))
                    out.append(text[pos:t.start])
                    out.append(" " + short + " ")
                    pos = t.end
                    i += 1
                    continue
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
