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


# =====================================================================
# Дополнения итерации «идеала»: суммы, адреса, дроби, номера, телефоны
# =====================================================================

def test_amounts_agreement():
    n = make()
    out = n.normalize_sentence("Компания заплатила 5 млн рублей, из них 2 тыс. — штраф.")
    assert "пять миллионов рублей" in out
    assert "две тысячи" in out            # не «два тысяч»
    out2 = n.normalize_sentence("С общества взыскано 1,5 млрд руб.")
    assert "полтора миллиарда рублей" in out2
    out3 = n.normalize_sentence("С 5 млн голосов.")
    assert "С пятью миллионами голосов" in out3


def test_city_and_address():
    n = make()
    out = n.normalize_sentence("г. Москва, ул. Ленина, д. 5.")
    assert "город Москва" in out
    assert "улица Ленина" in out
    assert "дом пять" in out


def test_year_abbreviation():
    n = make()
    out = n.normalize_sentence("В 2006 г. закон принят.")
    assert "две тысячи шестом году" in out
    assert "г." not in out


def test_years_range_gg():
    n = make()
    out = n.normalize_sentence("В 2010-2015 гг. практика изменилась.")
    assert "две тысячи десятом — две тысячи пятнадцатом годах" in out
    assert "гг" not in out


def test_fractions():
    n = make()
    out = n.normalize_sentence("Доля составляет 1/2, у соседа 3/4 и 2/3, у них 5/8.")
    assert "одна вторая" in out
    assert "три четверти" in out
    assert "две трети" in out
    assert "пять восьмых" in out


def test_long_numbers_digit_by_digit():
    n = make()
    out = n.normalize_sentence("ИНН 7707083893 указан верно.")
    assert "семь семь ноль семь" in out
    assert "миллиард" not in out and "миллион" not in out


def test_court_case_number():
    n = make()
    out = n.normalize_sentence("Дело № 2-123/2021 рассмотрено.")
    assert "номер два — сто двадцать три — две тысячи двадцать первый" in out
    assert "от двух до" not in out


def test_phones():
    n = make()
    out = n.normalize_sentence("Звоните: +7 926 123-45-67.")
    assert "плюс семь" in out
    assert "девять два шесть" in out
    assert "от девяноста" not in out


def test_digit_group_code():
    n = make()
    out = n.normalize_sentence("Код 123-45-67 устарел.")
    assert "один два три" in out
    assert "от ста двадцати" not in out
