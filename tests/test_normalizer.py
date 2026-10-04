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


# =====================================================================
# Порядковые с суффиксом и единицы измерения
# =====================================================================

def test_ordinal_suffixes():
    n = make()
    out = n.normalize_sentence("В 19-м веке, во 2-й половине, он занял 3-е место.")
    assert "девятнадцатом веке" in out
    assert "второй половине" in out
    assert "третье место" in out
    out2 = n.normalize_sentence("Продана 3-х комнатная квартира со 2-го этажа.")
    assert "трёхкомнатная" in out2
    assert "второго этажа" in out2
    out3 = n.normalize_sentence("За 12-ю неделю — уже 158-х статей.")
    assert "двенадцатую неделю" in out3
    assert "сто пятьдесят восьмых" in out3


def test_measures():
    n = make()
    out = n.normalize_sentence("Багаж 23 кг, путь 10 км, скорость 60 км/ч.")
    assert "двадцать три килограмма" in out
    assert "десять километров" in out
    assert "шестьдесят километров в час" in out
    out2 = n.normalize_sentence("Площадь 100 м², температура −5 °C.")
    assert "сто квадратных метров" in out2
    assert "минус пять градусов Цельсия" in out2
    out3 = n.normalize_sentence("Мощность 5 кВт, ток 12 А, напряжение 220 В.")
    assert "пять киловатт" in out3
    assert "двенадцать ампер" in out3
    assert "двести двадцать вольт" in out3
    out4 = n.normalize_sentence("Файл 12 Гб и 700 Мб.")
    assert "двенадцать гигабайтов" in out4
    assert "семьсот мегабайтов" in out4


def test_roman_case_agreement():
    n = make()
    out = n.normalize_sentence("В XV в. это было правилом, а в XX веке — нет.")
    assert "В пятнадцатом веке" in out
    assert "в двадцатом веке" in out
    out2 = n.normalize_sentence("Глава XVIII кодекса, часть II утратила силу.")
    assert "лава восемнадцатая" in out2  # «Глава восемнадцатая»
    assert "часть вторая" in out2


def test_list_reference_card():
    n = make()
    out = n.normalize_sentence("Данные приведены на л. 5 дела.")
    assert "на листе пять" in out


# =====================================================================
# Даты через точку, версии, подразделы
# =====================================================================

def test_dot_dates():
    n = make()
    out = n.normalize_sentence("Соглашение от 12.03.2021 расторгнуто.")
    assert "от двенадцатого марта две тысячи двадцать первого года" in out
    out2 = n.normalize_sentence("Срок продлён до 01.09, оплата по 31.12.2025.")
    assert "до первого сентября" in out2
    assert "по тридцать первому декабря две тысячи двадцать пятого года" in out2
    out3 = n.normalize_sentence("Постановление от 03.10.26 подписано.")
    assert "третьего октября две тысячи двадцать шестого года" in out3


def test_versions_and_subsections():
    n = make()
    out = n.normalize_sentence("Используйте версию 3.5.1 сборки 2.10.")
    assert "версию три пять один" in out
    assert "сборки два десять" in out
    out2 = n.normalize_sentence("См. п. 3.5 договора и ст. 20.2 кодекса.")
    assert "пункт три пять" in out2
    assert "статья двадцать два" in out2
    out3 = n.normalize_sentence("Сервер 192.168.1.1 недоступен.")
    assert "сто девяносто два" in out3


def test_half_decimals():
    n = make()
    out = n.normalize_sentence("Ущерб 2,5 млн, ставка 12,5%, вес 5,5 кг.")
    assert "два с половиной миллиона" in out
    assert "двенадцать с половиной процентов" in out
    assert "пять с половиной килограмма" in out


def test_legal_redaction_phrases():
    """«в ред.» склоняется, «с изм. и доп.» разворачивается словами."""
    n = make()
    out = n.normalize_sentence("Закон (в ред. ФЗ от 01.09.2024) изменён.")
    assert "в редакции" in out
    out2 = n.normalize_sentence("Кодекс действует (с изм. и доп.) в РФ.")
    assert "с изменениями и дополнениями" in out2


def test_subpoint_and_chain_commas():
    """«подп.» распознаётся; цепочка ссылок читается с запятыми-паузами."""
    n = make()
    out = n.normalize_sentence("см. п. 3 ч. 2 ст. 20.2 КоАП РФ")
    assert "пункт третий, часть вторая, статья двадцать два" in out
    out2 = n.normalize_sentence("подп. «а» п. 3 применяется")
    assert "подпункт а" in out2


def test_percent_ranges():
    """«10-15%» — проценты не теряются, форма по последнему числу."""
    n = make()
    out = n.normalize_sentence("Ставка выросла на 10-15%.")
    assert "десять — пятнадцать процентов" in out
    out2 = n.normalize_sentence("Повысили на 2-3%.")
    assert "два — три процента" in out2


def test_paren_number_dedupe():
    """«100 000 (сто тысяч)» — расшифровка в скобках не читается дважды."""
    n = make()
    out = n.normalize_sentence("Сумма 100 000 (сто тысяч) рублей взыскана.")
    assert out.count("сто тысяч") == 1
    out2 = n.normalize_sentence("Подано 3 (три) заявления.")
    assert out2.count("три") == 1
    # в скобках не число — не трогаем
    out3 = n.normalize_sentence("Суд (первая инстанция) отказал.")
    assert "первая инстанция" in out3


def test_plusminus():
    n = make()
    out = n.normalize_sentence("Допускается отклонение ±3 мм.")
    assert "плюс-минус три" in out


def test_tn_agreement():
    """«т.н.» согласуется с родом следующего слова."""
    n = make()
    out = n.normalize_sentence("Т.к. правила нарушены, т.н. льгота отменена.")
    assert "так называемая льгота" in out
    out2 = n.normalize_sentence("т.н. законность восстановлена.")
    assert "так называемая законность" in out2
    out3 = n.normalize_sentence("т.н. порядок восстановлен.")
    assert "так называемый порядок" in out3


def test_range_case_by_preposition():
    """Падеж чисел в диапазоне — по предлогу: «в … статьях» — предложный."""
    n = make()
    out = n.normalize_sentence("В 158-160 статьях указано.")
    assert "ста пятидесяти восьми" in out
    out2 = n.normalize_sentence("Ставка от 10 до 15% выросла.")
    assert "процент" in out2


def test_gg_year_suffix():
    """«2010-2015 г.г.» — некорректная, но частая форма читается как «гг.»"""
    n = make()
    out = n.normalize_sentence("Практика 2010-2015 г.г. обобщена.")
    assert "годов" in out
    assert "г. г." not in out and "гг." not in out


def test_ps_abbreviation():
    """«P.S.» читается по-русски, а не английскими буквами."""
    n = make()
    out = n.normalize_sentence("Итог подведён. P.S. Дополнение позже.")
    assert "пэ-эс" in out
    out2 = n.normalize_sentence("Итог. PS Дополнение.")
    assert "пэ-эс" in out2


def test_question_rise_segments():
    """Полярный вопрос получает подъём интонации, вопрос со словом — нет."""
    from lektor.config import load_settings
    from lektor.pipeline import Pipeline
    pipe = Pipeline(load_settings())
    utts, _ = pipe._analyze_wrap("Вы согласны с иском?")
    assert any(sg.question_rise for u in utts for sg in u.segments)
    utts2, _ = pipe._analyze_wrap("Кто виновен в этом деле?")
    assert not any(sg.question_rise for u in utts2 for sg in u.segments)
