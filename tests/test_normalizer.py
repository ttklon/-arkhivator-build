# -*- coding: utf-8 -*-
"""Нормализация текста (требования 23, 24, 25)."""
from lektor.lingua.normalizer import TextNormalizer
from lektor.report import Report


def make():
    return TextNormalizer(Report(), expand_abbrevs=True)


def test_article_reference():
    n = make()
    out = n.normalize_sentence("Наказание предусмотрено ч. 2 п. «в» ст. 159 УК РФ.")
    assert "часть вторая" in out
    assert "пункт вэ" in out
    assert "статья сто пятьдесят девять" in out


def test_law_number():
    n = make()
    out = n.normalize_sentence("Федеральный закон № 149-ФЗ подписан.")
    assert "номер сто сорок девять фэ-зэ" in out


def test_dates():
    n = make()
    out = n.normalize_sentence("Федеральный закон от 27 июля 2006 года.")
    assert "двадцать седьмого июля" in out
    assert "две тысячи шестого года" in out
    out2 = n.normalize_sentence("В 2006 году закон принят.")
    assert "две тысячи шестом году" in out2


def test_money_percent_time():
    n = make()
    out = n.normalize_sentence("Ущерб 1 500 000 рублей, уклонение 10%, заседание в 12:30.")
    assert "миллион пятьсот тысяч рублей" in out
    assert "десять процентов" in out
    assert "двенадцать часов тридцать минут" in out


def test_abbreviation_first_use():
    n = make()
    out = n.normalize_sentence("Статья 158 УК РФ запрещает кражу.")
    assert "Уголовный кодекс Российской Федерации" in out
    assert "далее" in out
    # второй раз — уже кратко
    out2 = n.normalize_sentence("Статья 159 УК РФ запрещает мошенничество.")
    assert "Уголовный кодекс" not in out2


def test_ranges():
    n = make()
    out = n.normalize_sentence("Статьи 158-160 применяются вместе.")
    assert "от ста пятидесяти восьми до ста шестидесяти" in out


def test_shorts():
    n = make()
    out = n.normalize_sentence("Взыскание руб., коп., т.д. и т.п.")
    assert "рублей" in out and "копеек" in out
    assert "так далее" in out and "тому подобное" in out


def test_russian_number_agreement():
    n = make()
    out = n.normalize_sentence("Допрос проведён с 3 свидетелями и 2 понятого.")
    assert "с тремя свидетелями" in out or "с тремя" in out
    assert "двумя" in out or "два" in out
