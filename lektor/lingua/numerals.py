# -*- coding: utf-8 -*-
"""Числа словами: количественные, порядковые, годы, деньги, дроби.

Требования 24 и 25: «статья 159 часть 2 пункт "в"» должно читаться как
«статья сто пятьдесят девять, часть вторая, пункт вэ», а даты и номера
законов — без «проглатывания» и с правильным грамматическим согласованием.

Все функции возвращают список слов (nominative), которые дальше при
необходимости склоняются через pymorphy3 (см. morphology.inflect_word).
"""
from __future__ import annotations

ONES = {1: "один", 2: "два", 3: "три", 4: "четыре", 5: "пять", 6: "шесть",
        7: "семь", 8: "восемь", 9: "девять"}
ONES_F = {1: "одна", 2: "две"}
TEENS = {10: "десять", 11: "одиннадцать", 12: "двенадцать", 13: "тринадцать",
         14: "четырнадцать", 15: "пятнадцать", 16: "шестнадцать",
         17: "семнадцать", 18: "восемнадцать", 19: "девятнадцать"}
TENS = {2: "двадцать", 3: "тридцать", 4: "сорок", 5: "пятьдесят",
        6: "шестьдесят", 7: "семьдесят", 8: "восемьдесят", 9: "девяносто"}
HUNDREDS = {1: "сто", 2: "двести", 3: "триста", 4: "четыреста", 5: "пятьсот",
            6: "шестьсот", 7: "семьсот", 8: "восемьсот", 9: "девятьсот"}

# Порядковые: основа + тип окончания (m/f/n/pl)
_ENDINGS = {
    "hard": ("ый", "ая", "ое", "ые"),
    "oy": ("ой", "ая", "ое", "ые"),
    "soft": ("ий", "ья", "ье", "ьи"),  # третий / третья / третье / третьи
}
_ORD_ONES = {1: ("перв", "hard"), 2: ("втор", "oy"), 3: ("трет", "soft"),
             4: ("четвёрт", "hard"), 5: ("пят", "hard"), 6: ("шест", "oy"),
             7: ("седьм", "oy"), 8: ("восьм", "oy"), 9: ("девят", "hard")}
_ORD_TEENS = {10: "десят", 11: "одиннадцат", 12: "двенадцат", 13: "тринадцат",
              14: "четырнадцат", 15: "пятнадцат", 16: "шестнадцат",
              17: "семнадцат", 18: "восемнадцат", 19: "девятнадцат"}
_ORD_TENS = {2: "двадцат", 3: "тридцат", 4: "сороков", 5: "пятидесят",
             6: "шестидесят", 7: "семидесят", 8: "восьмидесят", 9: "девяност"}
_ORD_HUNDREDS = {1: "сот", 2: "двухсот", 3: "трёхсот", 4: "четырёхсот",
                 5: "пятисот", 6: "шестисот", 7: "семисот", 8: "восьмисот",
                 9: "девятисот"}

# Родительные «соединительные» основы для составных порядковых (2000 -> двухтысячный)
_GEN_ONES = {1: "одно", 2: "двух", 3: "трёх", 4: "четырёх", 5: "пяти",
             6: "шести", 7: "семи", 8: "восьми", 9: "девяти"}
_GEN_TEENS = {11: "одиннадцати", 12: "двенадцати", 13: "тринадцати",
              14: "четырнадцати", 15: "пятнадцати", 16: "шестнадцати",
              17: "семнадцати", 18: "восемнадцати", 19: "девятнадцати"}
_GEN_TENS = {2: "двадцати", 3: "тридцати", 4: "сорока", 5: "пятидесяти",
             6: "шестидесяти", 7: "семидесяти", 8: "восьмидесяти", 9: "девяноста"}
_GEN_HUNDREDS = {1: "сто", 2: "двухсот", 3: "трёхсот", 4: "четырёхсот",
                 5: "пятисот", 6: "шестисот", 7: "семисот", 8: "восьмисот",
                 9: "девятисот"}

_BIG = (
    (10**12, ("триллион", "триллиона", "триллионов")),
    (10**9, ("миллиард", "миллиарда", "миллиардов")),
    (10**6, ("миллион", "миллиона", "миллионов")),
    (10**3, ("тысяча", "тысячи", "тысяч")),
)

_GENDERS = ("m", "f", "n", "p")


def plural(n: int, f1: str, f2: str, f3: str) -> str:
    """Форма существительного после числительного: 1 рубль, 2 рубля, 5 рублей."""
    n = abs(n) % 100
    if 11 <= n <= 14:
        return f3
    n %= 10
    if n == 1:
        return f1
    if 2 <= n <= 4:
        return f2
    return f3


def _agree(stem: str, kind: str, gender: str) -> str:
    return stem + _ENDINGS[kind][ _GENDERS.index(gender) ]


def cardinal_words(n: int, gender: str = "m") -> list[str]:
    """Число словами в именительном падеже: 159 -> ['сто','пятьдесят','девять']."""
    if n < 0:
        return ["минус"] + cardinal_words(-n, gender)
    if n == 0:
        return ["ноль"]
    parts: list[str] = []
    rest = n
    for base, forms in _BIG:
        count, rest = divmod(rest, base)
        if count:
            # «двадцать одна тысяча»: согласование с feminine-словом «тысяча»
            parts.extend(cardinal_words(count, "f" if base == 10**3 else "m"))
            parts.append(plural(count, *forms))
    h, r = divmod(rest, 100)
    if h:
        parts.append(HUNDREDS[h])
    if 10 <= r < 20:
        parts.append(TEENS[r])
    else:
        t, u = divmod(r, 10)
        if t:
            parts.append(TENS[t])
        if u:
            parts.append(ONES_F[u] if (gender == "f" and u in ONES_F) else ONES[u])
    return parts


def _last_component(n: int) -> int:
    """Последний значимый разрядный блок: 915->15, 905->5, 910->10, 900->900."""
    h, r = divmod(n % 1000, 100)
    if h == 0 and r == 0:
        return 0
    if r == 0:
        return h * 100
    if 10 <= r < 20:
        return r
    if r % 10 == 0:
        return r
    return r % 10


# реестр порождённых порядковых (м. р.): слово -> (основа, тип окончания)
_ORD_REGISTRY: dict = {}

# падежные окончания мужского рода ( pymorphy путает «седьмой» с ж. родом)
_MASC_CASE = {
    "hard": {"nomn": "ый", "gent": "ого", "gen1": "ого", "datv": "ому",
             "accs": "ый", "ablt": "ым", "loct": "ом", "loc1": "ом", "voct": "ый"},
    "oy":   {"nomn": "ой", "gent": "ого", "gen1": "ого", "datv": "ому",
             "accs": "ой", "ablt": "ым", "loct": "ом", "loc1": "ом", "voct": "ой"},
    "soft": {"nomn": "ий", "gent": "ьего", "gen1": "ьего", "datv": "ьему",
             "accs": "ий", "ablt": "ьем", "loct": "ьем", "loc1": "ьем", "voct": "ий"},
}


def ordinal_inflect_word(word: str, case: str):
    """Надёжное склонение порождённых нами порядковых («седьмой» -> «седьмого»)."""
    reg = _ORD_REGISTRY.get(word)
    if reg is None:
        return None
    stem, kind = reg
    endings = _MASC_CASE[kind]
    return stem + endings.get(case, endings["nomn"])


def ordinal_word(component: int, gender: str = "m") -> str:
    """Порядковое числительное для разрядного блока: 5 -> 'пятый' (ж: 'пятая')."""
    if 1 <= component <= 9:
        stem, kind = _ORD_ONES[component]
    elif 10 <= component <= 19:
        stem, kind = _ORD_TEENS[component], "hard"
    elif component in (20, 30, 40, 50, 60, 70, 80, 90):
        kind = "oy" if component == 40 else "hard"
        stem = _ORD_TENS[component // 10]
    elif component % 100 == 0 and 1 <= component // 100 <= 9:
        stem, kind = _ORD_HUNDREDS[component // 100], "hard"
    else:
        raise ValueError(f"не порядковый блок: {component}")
    w = _agree(stem, kind, gender)
    if gender == "m":
        _ORD_REGISTRY[w] = (stem, kind)
    return w


def _scale_ordinal(n: int, gender: str) -> str:
    """Круглые тысячи/миллионы: 2000 -> двухтысячный, 10^6 -> миллионный."""
    for base, suffix in ((10**9, "миллиардн"), (10**6, "миллионн"), (10**3, "тысячн")):
        if n % base == 0:
            k = n // base
            if k == 1:
                return _agree(suffix, "hard", gender)
            prefix = _gen_join(k)
            return _agree(prefix + suffix, "hard", gender)
    raise ValueError(n)


def _gen_join(k: int) -> str:
    """Соединительная основа: 21 -> 'двадцатиодно', 900 -> 'девятисот'."""
    parts: list[str] = []
    h, r = divmod(k, 100)
    if h:
        parts.append(_GEN_HUNDREDS[h])
    if 10 <= r < 20:
        parts.append(_GEN_TEENS[r])
    else:
        t, u = divmod(r, 10)
        if t:
            parts.append(_GEN_TENS[t])
        if u:
            parts.append(_GEN_ONES[u])
    return "".join(parts)


def ordinal_words(n: int, gender: str = "m") -> list[str]:
    """Порядковое числительное: 159 (ж) -> ['сто','пятьдесят','девятая'].

    Правило русского языка: порядковым является только последний компонент,
    предыдущие разряды читаются количественными («сто пятьдесят девятая»).
    """
    if n < 0:
        return ["минус"] + ordinal_words(-n, gender)
    if n == 0:
        return [_agree("нулев", "hard", gender)]
    if n >= 1000 and n % 1000 == 0:
        return [_scale_ordinal(n, gender)]
    last = _last_component(n)
    if last == 0:  # например, 1 000 000 — не кратен только 1000
        return [_scale_ordinal(n, gender)]
    prefix = n - last
    words = cardinal_words(prefix) if prefix else []
    words.append(ordinal_word(last, gender))
    if words[:2] == ["одна", "тысяча"]:  # «тысяча девяностый», не «одна тысяча …»
        words = ["тысяча"] + words[2:]
    return words


def year_words(year: int, case: str = "nomn") -> list[str]:
    """Год словами: 2006 -> «две тысячи шестой»; падеж склоняет последнее слово.

    «от 27 июля 2006 года» -> «две тысячи шестого» (gent),
    «в 2006 году»          -> «две тысячи шестом» (loct).
    """
    y = int(year)
    if 1000 <= y < 2000:
        rest = y - 1000
        words = ["тысяча"] + (ordinal_words(rest) if rest else [])
    elif 2000 <= y < 3000:
        rest = y - 2000
        if rest == 0:
            words = [_agree("двухтысячн", "hard", "m")]
        else:
            words = ["две", "тысячи"] + ordinal_words(rest)
    else:
        words = ordinal_words(y)
        # «одна тысяча» -> «тысяча»
        if words[:2] == ["одна", "тысяча"]:
            words = ["тысяча"] + words[2:]
    return _inflect_last(words, case)


def _inflect_last(words: list[str], case: str) -> list[str]:
    if case in ("nomn", "", None) or not words:
        return words
    from .morphology import inflect_word
    inflected = ordinal_inflect_word(words[-1], case) or inflect_word(words[-1], {case})
    return words[:-1] + [inflected] if inflected else words


def inflect_words(words: list[str], case: str, last_only: bool = False) -> list[str]:
    """Склоняет слова числительного.

    ['сто','пятьдесят','девять'] + gent -> ста пятидесяти девяти.
    Для порядковых (last_only=True) склоняется только последнее слово:
    «двадцать седьмой» + gent -> «двадцать седьмого».
    """
    if case in ("nomn", "", None) or not words:
        return words
    from .morphology import inflect_word
    out = []
    for i, w in enumerate(words):
        if last_only and i != len(words) - 1:
            out.append(w)
            continue
        if last_only:
            # составное порядковое: склоняем только последнее слово по таблице
            tw = ordinal_inflect_word(w, case)
            if tw:
                out.append(tw)
                continue
        out.append(inflect_word(w, {case}) or w)
    return out


def decimal_words(int_part: int, frac: str, gender: str = "m") -> list[str]:
    """Дробное число: 1,5 -> «полтора»; 2,5 -> «два с половиной»; 3,14 -> «три целых четырнадцать сотых»."""
    frac = frac.rstrip("0")
    if not frac:
        return cardinal_words(int_part, gender)
    if frac == "5" and int_part == 1:
        return ["полторы"] if gender == "f" else ["полтора"]
    if frac == "5" and int_part >= 2:
        # «пять с половиной», «двенадцать с половиной» — а не
        # «пять целых пять десятых»
        return cardinal_words(int_part, gender) + ["с", "половиной"]
    denominators = {1: ("десятая", "десятых", "десятых"),
                    2: ("сотая", "сотых", "сотых"),
                    3: ("тысячная", "тысячных", "тысячных"),
                    4: ("десятитысячная", "десятитысячных", "десятитысячных")}
    d = denominators.get(len(frac))
    if not d:
        return cardinal_words(int_part, gender) + ["запятая"] + list(frac)
    frac_n = int(frac)
    words = cardinal_words(int_part, gender)
    words.append("целая" if int_part % 10 == 1 and int_part % 100 != 11 else "целых")
    words.extend(cardinal_words(frac_n, "f"))
    words.append(plural(frac_n, *d))
    return words


def rubles_words(n: int) -> list[str]:
    return cardinal_words(n) + [plural(n, "рубль", "рубля", "рублей")]


def kopecks_words(n: int) -> list[str]:
    return cardinal_words(n, "f") + [plural(n, "копейка", "копейки", "копеек")]


def percent_words(n: int) -> list[str]:
    return cardinal_words(n) + [plural(n, "процент", "процента", "процентов")]


def hours_minutes(h: int, m: int) -> list[str]:
    words = cardinal_words(h) + [plural(h, "час", "часа", "часов")]
    if m:
        words.extend(cardinal_words(m, "f") + [plural(m, "минута", "минуты", "минут")])
    return words
