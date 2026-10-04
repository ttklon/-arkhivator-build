# -*- coding: utf-8 -*-
"""Числа словами (требование 24)."""
from lektor.lingua import numerals as N


def test_cardinal():
    assert N.cardinal_words(159) == ["сто", "пятьдесят", "девять"]
    assert N.cardinal_words(2006) == ["две", "тысячи", "шесть"]
    assert N.cardinal_words(21) == ["двадцать", "один"]
    assert N.cardinal_words(21000) == ["двадцать", "одна", "тысяча"]
    assert N.cardinal_words(0) == ["ноль"]
    assert N.cardinal_words(1000000) == ["один", "миллион"]
    assert N.cardinal_words(2, "f") == ["две"]


def test_ordinal():
    assert N.ordinal_words(2, "f") == ["вторая"]
    assert N.ordinal_words(159, "f") == ["сто", "пятьдесят", "девятая"]
    assert N.ordinal_words(159, "m") == ["сто", "пятьдесят", "девятый"]
    assert N.ordinal_words(27, "m") == ["двадцать", "седьмой"]
    assert N.ordinal_words(2006, "m") == ["две", "тысячи", "шестой"]
    assert N.ordinal_words(2000, "m") == ["двухтысячный"]
    assert N.ordinal_words(1990, "m") == ["тысяча", "девятьсот", "девяностый"]
    assert N.ordinal_words(25, "m") == ["двадцать", "пятый"]
    assert N.ordinal_words(40, "m") == ["сороковой"]
    assert N.ordinal_words(3, "n") == ["третье"]


def test_year_cases():
    assert N.year_words(2006, "gent") == ["две", "тысячи", "шестого"]
    assert N.year_words(2006, "loct") == ["две", "тысячи", "шестом"]
    assert N.year_words(1990, "gent") == ["тысяча", "девятьсот", "девяностого"]


def test_money_and_plural():
    assert N.plural(1, "рубль", "рубля", "рублей") == "рубль"
    assert N.plural(2, "рубль", "рубля", "рублей") == "рубля"
    assert N.plural(5, "рубль", "рубля", "рублей") == "рублей"
    assert N.plural(11, "рубль", "рубля", "рублей") == "рублей"
    assert " ".join(N.rubles_words(1000)) == "одна тысяча рублей"
    assert " ".join(N.percent_words(10)) == "десять процентов"


def test_decimals():
    assert N.decimal_words(1, "5") == ["полтора"]
    assert N.decimal_words(1, "5", "f") == ["полторы"]
    assert " ".join(N.decimal_words(0, "5")) == "ноль целых пять десятых"
    assert " ".join(N.decimal_words(3, "14")).startswith("три целых")


def test_inflect_words():
    words = N.inflect_words(["сто", "пятьдесят", "девять"], "gent")
    assert words == ["ста", "пятидесяти", "девяти"]
