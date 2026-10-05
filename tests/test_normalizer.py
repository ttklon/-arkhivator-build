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
    # цепочка ссылок читается по-цитатному: «статьи сто пятьдесят
    # восемь — сто шестьдесят», а не «от ста пятидесяти восьми…»
    assert "статьи сто пятьдесят восемь — сто шестьдесят" in out


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


def test_dimensions_with_h():
    """«30х40 см» — размеры читаются с «на», а не буквой «х»."""
    n = make()
    out = n.normalize_sentence("Плитка размером 30х40 см уложена.")
    assert "тридцать на сорок" in out
    out2 = n.normalize_sentence("Размер 25x35 мм.")
    assert "двадцать пять на тридцать пять" in out2


def test_time_ranges():
    """«10:00-13:00» — диапазон времени, а не развалившийся номер."""
    n = make()
    out = n.normalize_sentence("Приём: 10:00-13:00 и 14:00-17:00.")
    assert "с десяти до тринадцати часов" in out
    assert "с четырнадцати до семнадцати часов" in out
    out2 = n.normalize_sentence("Обед 13:00-14:30.")
    assert "с тринадцати часов" in out2 and "тридцати минут" in out2


def test_time_case_by_preposition():
    """«с 9:00» — родительный, «к 12:00» — дательный, «в 12:30» — как было."""
    n = make()
    out = n.normalize_sentence("Магазин работает с 9:00 до 18:00.")
    assert "с девяти часов" in out and "до восемнадцати часов" in out
    out2 = n.normalize_sentence("Пик к 12:00.")
    assert "к двенадцати часам" in out2


def test_address_parts():
    """«корп.», «кв.», «эт.» разворачиваются; «кв. м» не ломается."""
    n = make()
    out = n.normalize_sentence("Адрес: ул. Ленина, д. 5, корп. 2, кв. 17, 3 эт.")
    for w in ("улица", "дом пять", "корпус два", "квартира семнадцать",
              "третий этаж"):
        assert w in out, (w, out)
    out2 = n.normalize_sentence("Квартира 45 кв. м.")
    assert "квадратных метров" in out2
    out3 = n.normalize_sentence("Офис на 3 этаже здания.")
    assert "на третьем этаже" in out3


def test_mister_abbreviation():
    """«г-н Иванов» — «господин Иванов», «г-жа» — «госпожа»."""
    n = make()
    out = n.normalize_sentence("Г-н Иванов обратился в суд.")
    assert "господин Иванов" in out
    out2 = n.normalize_sentence("Г-жа Петрова ответчик.")
    assert "госпожа Петрова" in out2


def test_plural_number_sign():
    """«№№ 1, 2» — «номера один, два», а не «номер номер»."""
    n = make()
    out = n.normalize_sentence("Открыты дела №№ 1, 2 и 3.")
    assert "номера" in out
    assert "номер номер" not in out


def test_usa_abbreviation():
    """«США» читается по буквам, а не как слово «сша»."""
    n = make()
    out = n.normalize_sentence("Практика США учтена.")
    assert "эс шэ а" in out


def test_money_with_kopecks():
    """«100 000,50 руб.» — сумма с копейками, а не развалившийся хвост."""
    n = make()
    out = n.normalize_sentence("Взыскать 100 000,50 руб. с ответчика.")
    assert "сто тысяч рублей пятьдесят копеек" in out
    out2 = n.normalize_sentence("Долг 1 500 000,00 руб. погашен.")
    assert "один миллион пятьсот тысяч рублей" in out2
    assert "ноль" not in out2


def test_human_numbers_with_spaces():
    """«2 500 000» с разделителями — человеческое число, не номер счёта."""
    n = make()
    out = n.normalize_sentence("Прибыль 2 500 000 направлена в фонд.")
    assert "два миллиона пятьсот тысяч" in out
    # ИНН без пробелов — по-прежнему поцифрово
    out2 = n.normalize_sentence("ИНН 770123456789 присвоен.")
    assert "семь семь ноль" in out2


def test_hyphen_compound_words():
    """«3-летний» -> «трёхлетний», «25-летие» -> «двадцатипятилетие»."""
    n = make()
    out = n.normalize_sentence("Установлен 3-летний срок давности.")
    assert "трёхлетний" in out
    out2 = n.normalize_sentence("Отмечается 25-летие закона.")
    assert "двадцатипятилетие" in out2
    out3 = n.normalize_sentence("Квартира 1-комнатная куплена.")
    assert "однокомнатная" in out3
    # «3-х комнатная» (через пробел) не сломалось
    out4 = n.normalize_sentence("Куплена 3-х комнатная квартира.")
    assert "трёхкомнатная" in out4


def test_article_number_ranges():
    """«ст. 159-161» — диапазон статей читается в цитатной форме."""
    n = make()
    out = n.normalize_sentence("Действия квалифицированы по ст. 159-161 УК РФ.")
    assert "статье сто пятьдесят девять — сто шестьдесят один" in out


def test_technical_units():
    """л.с., об/мин, кВт·ч, куб. м, м³."""
    n = make()
    assert "лошадиных сил" in n.normalize_sentence("Двигатель 150 л.с. установлен.")
    assert "оборотов в минуту" in n.normalize_sentence("Вал вращается 3000 об/мин.")
    assert "киловатт-часов" in n.normalize_sentence("Расход 250 кВт·ч в месяц.")
    assert "кубических метров" in n.normalize_sentence("Заказано 12 куб. м бетона.")
    assert "кубических метров" in n.normalize_sentence("Объём 25 м³.")
    # «кв. м» не сломался
    assert "квадратных метров" in n.normalize_sentence("Квартира 45 кв. м.")


def test_time_hours_minutes_form():
    """«в 12 ч. 30 мин.» — время, а не «часть тридцатая»."""
    n = make()
    out = n.normalize_sentence("Заседание в 12 ч. 30 мин. начнётся.")
    assert "двенадцать часов тридцать минут" in out
    assert "часть" not in out
    out2 = n.normalize_sentence("Собрание с 10 ч. до 14 ч. идёт.")
    assert "с десяти часов до четырнадцати часов" in out2
    # «ст. 5 ч. 2» — это часть статьи, а не часы
    out3 = n.normalize_sentence("См. ст. 5 ч. 2 закона.")
    assert "часть вторая" in out3      # «час» внутри «часть» — не часы


def test_according_to_dative():
    """«Согласно ст. 5» — дательный падеж: «согласно статье»."""
    n = make()
    out = n.normalize_sentence("Согласно ст. 5 закона требования законны.")
    assert "статье" in out


def test_geo_abbreviations():
    """пос./пер./лит. разворачиваются; обл. согласуется с прилагательным."""
    n = make()
    out = n.normalize_sentence("Адрес: пос. Иванова, пер. Слесарный, 5.")
    assert "посёлок Иванова" in out and "переулок Слесарный" in out
    out2 = n.normalize_sentence("Офис в Московской обл., г. Одинцово.")
    assert "Московской области" in out2
    out3 = n.normalize_sentence("Заявление из Тверской обл. рассмотрено.")
    assert "Тверской области" in out3
    out4 = n.normalize_sentence("Корпус лит. А построен.")
    assert "литера" in out4


def test_and_or_slash():
    """«и/или» читается слитно «и или», без паузы."""
    n = make()
    out = n.normalize_sentence("Продавец и/или покупатель подписывают.")
    assert "и или" in out


def test_date_with_year_suffix():
    """«от 21.01.2025 г.» — без двойного «года»; «г. Москва» — город."""
    n = make()
    out = n.normalize_sentence("Приказ от 21.01.2025 г. подписан.")
    assert "двадцать пятого года подписан" in out
    assert out.count("года") == 1
    out2 = n.normalize_sentence("Закон от 12.03.2021 года действует.")
    assert out2.count("года") == 1
    out3 = n.normalize_sentence("Отпуск с 01.09.2024 г. по 30.06.2025 г. оформлен.")
    assert "четвёртого года по тридцатому июня" in out3


def test_year_range_with_po():
    """«с 2020 по 2024 год» — оба года порядковые."""
    n = make()
    out = n.normalize_sentence("За период с 2020 по 2024 год проверено.")
    assert "с две тысячи двадцатого по две тысячи двадцать четвёртый год" in out


def test_comparison_genitive():
    """«не более 3 лет» — родительный падеж."""
    n = make()
    out = n.normalize_sentence("Срок не более 3 лет установлен.")
    assert "не более трёх лет" in out
    out2 = n.normalize_sentence("Не менее 2 лет действует.")
    assert "двух лет" in out2
    out3 = n.normalize_sentence("Свыше 100 дел рассмотрено.")
    assert "ста дел" in out3


def test_technical_designations():
    """«Т-34», «Су-27», «ФЗ-152» — дефис не звучит паузой."""
    n = make()
    out = n.normalize_sentence("Танк Т-34 сохранился, самолёт Су-27 тоже.")
    assert "тридцать четыре" in out and "двадцать семь" in out
    # «Г-н Иванов» не сломался (дефис с маленькой буквы)
    out2 = n.normalize_sentence("Г-н Иванов обратился.")
    assert "господин" in out2


def test_plus_after_number():
    """«18+» читается «восемнадцать плюс», «+7 …» не трогается."""
    n = make()
    out = n.normalize_sentence("Материал 18+ помечен.")
    assert "восемнадцать плюс" in out


def test_gent_context_constructions():
    """«в течение 10 дней», «в силу ст. 61» — родительный падеж."""
    n = make()
    out = n.normalize_sentence("В течение 10 дней ответчик возразил.")
    assert "десяти дней" in out
    out2 = n.normalize_sentence("По истечении 30 суток срок истёк.")
    assert "тридцати суток" in out2
    out3 = n.normalize_sentence("В рамках 3 программ финансирование выделено.")
    assert "трёх программ" in out3
    out4 = n.normalize_sentence("В случае 2 отказов спор передаётся в суд.")
    assert "двух отказов" in out4


def test_legal_phrase_article_case():
    """«в силу ст. 61» -> «в силу статьи…» (родительный)."""
    n = make()
    out = n.normalize_sentence("В силу ст. 61 ГПК РФ обстоятельства установлены.")
    assert "силу статьи" in out
    out2 = n.normalize_sentence("Иск подан в порядке ст. 131 ГПК РФ.")
    assert "в порядке статьи" in out2


def test_half_units():
    """«0,5 часа» -> «полчаса», «0,5 суток» -> «полсуток» (тр. 24)."""
    n = make()
    out = n.normalize_sentence("Подождите 0,5 часа и 0,5 суток.")
    assert "полчаса" in out and "полсуток" in out
    assert "ноль целых" not in out
    out2 = n.normalize_sentence("Срок 0,5 года, то есть 0,5 лет.")
    assert out2.count("полгода") == 2
    out3 = n.normalize_sentence("Объём 0,5 литра и рост 0,5 процента.")
    assert "пол-литра" in out3 and "полпроцента" in out3


def test_half_percent():
    """«0,5%» -> «полпроцента» — живая форма без «ноль целых»."""
    n = make()
    out = n.normalize_sentence("Инфляция 0,5% и ещё 0,50%.")
    assert out.count("полпроцента") == 2
    assert "процентов" not in out


def test_kopecks_padding():
    """«100 000,5 руб.» — это 50 копеек, а не 5 (разряд дроби)."""
    n = make()
    out = n.normalize_sentence("Заплатили 100 000,5 руб. и 2,5 рубля.")
    assert "пятьдесят копеек" in out
    assert "пять копеек" not in out
    out2 = n.normalize_sentence("Сумма 100 000,05 руб.")
    assert "пять копеек" in out2


def test_money_word_boundaries():
    """«с 1,5 рублями» — валюта не вырезается из середины слова."""
    n = make()
    out = n.normalize_sentence("С 1,5 рублями в кармане.")
    assert "полутора рублями" in out
    assert " копеек ми " not in out and not out.endswith("ми")


def test_amounts_no_word_tear():
    """«1,5 тысячи» — «тыс» не вырезается из слова «тысячи»."""
    n = make()
    out = n.normalize_sentence("Сумма 1,5 тысячи рублей.")
    assert "полторы тысячи" in out
    assert " ячи" not in out and "ячи " not in out.split("рублей")[0][-3:]
    out2 = n.normalize_sentence("Цена 5 тыс.руб. без НДС.")
    assert "пять тысяч рублей" in out2


def test_fraction_gender():
    """«1,5 минуты» -> «полторы минуты» (женский род)."""
    n = make()
    out = n.normalize_sentence("Через 1,5 минуты и 2,5 тысячи шагов.")
    assert "полторы минуты" in out
    assert "две с половиной тысячи" in out


def test_accs_prepositions():
    """«через 5 километров» -> «через пять километров» (винительный)."""
    n = make()
    out = n.normalize_sentence("Через 5 километров пути и за 10 дней.")
    assert "ерез пять километров" in out
    assert "а десять дней" in out
    out2 = n.normalize_sentence("На 5 страницах и в 5 шагах.")
    assert "на пяти страницах" in out2.lower() and "в пяти шагах" in out2.lower()
    out3 = n.normalize_sentence("Через 1,5 часа пришёл ответ.")
    assert "через полтора часа" in out3.lower()


def test_fraction_inflection():
    """«от 2,5 километров» -> «от двух с половиной километров»."""
    n = make()
    out = n.normalize_sentence("Отрезок от 2,5 километров до 3.")
    assert "от двух с половиной километров" in out.lower()
    out2 = n.normalize_sentence("Без 2,5 процентов запаса.")
    assert "без двух с половиной процентов" in out2.lower()


def test_dot_fractions_with_units():
    """«0.5 часа» (с точкой) — дробь, а не версия; единицы разворачиваются."""
    n = make()
    out = n.normalize_sentence("2.5 млн рублей и 1.5 тыс. единиц.")
    assert "два с половиной миллиона рублей" in out
    assert "полторы тысячи единиц" in out
    out2 = n.normalize_sentence("3.5 м ткани и 7.5 вольт.")
    assert "три с половиной метра" in out2
    assert "семь с половиной вольт" in out2
    out3 = n.normalize_sentence("0.5 часа ожидания.")
    assert "полчаса" in out3
    assert "ноль пять" not in out3


def test_version_context():
    """«Python 3.10» — версия, а не дата; без контекста — дата."""
    n = make()
    out = n.normalize_sentence("Python 2.7 и 3.10.")
    assert "два семь" in out and "три десять" in out
    assert "октября" not in out
    out2 = n.normalize_sentence("Версия 2.10 вышла, сборка 3.5.1 готова.")
    assert "два десять" in out2 and "три пять один" in out2
    out3 = n.normalize_sentence("Дело от 2.10 подано.")
    assert "второго октября" in out3


def test_half_measure_units():
    """«0,5 кг» -> «полкилограмма» — и для точечной дроби тоже."""
    n = make()
    out = n.normalize_sentence("0,5 кг и 0.5 л воды.")
    assert "полкилограмма" in out and "пол-литра" in out
    assert "ноль целых" not in out
    out2 = n.normalize_sentence("0,5 км/ч и 0.5 В.")
    assert "полкилометра в час" in out2 and "полвольта" in out2


def test_quarter_units():
    """«0,25 часа» -> «четверть часа», «0,75 литра» -> «три четверти литра»."""
    n = make()
    out = n.normalize_sentence("Подожди 0,25 часа, это займёт 0,75 литра.")
    assert "четверть часа" in out
    assert "три четверти литра" in out
    assert "ноль целых" not in out


def test_quarter_units_inflected():
    """Четверти склоняются по предлогу («около четверти», «с четвертью»)."""
    n = make()
    out = n.normalize_sentence("Около 0,25 суток и с 0,25 часа пути.").lower()
    assert "около четверти суток" in out
    assert "с четвертью часа" in out
    out2 = n.normalize_sentence("Около 0,75 метра ткани.").lower()
    assert "около трёх четвертей метра" in out2


def test_quarter_percent():
    """«0,25%» -> «четверть процента», «0,75%» -> «три четверти процента»."""
    n = make()
    out = n.normalize_sentence("Рост 0,25% и падение 0,75%.").lower()
    assert "четверть процента" in out
    assert "три четверти процента" in out


def test_fractional_square_meters():
    """«2,5 м²» — дробь не обрубается до целого («два с половиной…»)."""
    n = make()
    out = n.normalize_sentence("Площадь 2,5 м² и объём 3,5 м³.")
    assert "два с половиной квадратных метров" in out
    assert "три с половиной кубических метров" in out
    out2 = n.normalize_sentence("Комната 21,2 м².")
    assert "двадцать одна целая две десятых" in out2


def test_half_amounts():
    """«0,5 тыс.» -> «полтысячи», «0,5 млн» -> «полмиллиона» (с падежами)."""
    n = make()
    out = n.normalize_sentence("Сумма 0,5 тыс. рублей и 0,5 млн.")
    assert "полтысячи рублей" in out
    assert "полмиллиона" in out
    assert "ноль целых" not in out
    out2 = n.normalize_sentence("Около 0,5 тыс. и с 0,5 млрд на счету.").lower()
    assert "около полутысячи" in out2
    assert "с полумиллиардом" in out2


def test_quarter_percent_inflected():
    """«в пределах 0,25%» -> «в пределах четверти процента»."""
    n = make()
    out = n.normalize_sentence("В пределах 0,25% и от 0,75% нормы.")
    assert "в пределах четверти процента" in out.lower()
    assert "от трёх четвертей процента" in out.lower()
    out2 = n.normalize_sentence("В рамках 0,25% допуска.")
    assert "в рамках четверти процента" in out2.lower()


def test_gent_context_quarters_and_amounts():
    """«в течение 0,25 года» -> «в течение четверти года» (родительный)."""
    n = make()
    out = n.normalize_sentence("В течение 0,25 года и по истечении 0,25 суток.")
    assert "в течение четверти года" in out.lower()
    assert "по истечении четверти суток" in out.lower()
    out2 = n.normalize_sentence("Не более 1,5 тыс. и свыше 0,5 млн руб.")
    assert "не более полутора тысяч" in out2.lower()
    assert "свыше полумиллиона" in out2.lower()


def test_new_abbreviations():
    """ДТП/СМЭ/ЖКХ читаются по буквам; ОВД/КТС разворачиваются при первом упоминании."""
    n = make()
    out = n.normalize_sentence("Оформлено ДТП, услуги ЖКХ оплачены.")
    assert "дэ тэ пэ" in out
    assert "жэ ка ха" in out
    out2 = n.normalize_sentence("ОВД уведомлён, НПА изучен.")
    assert "орган внутренних дел" in out2
    assert "нормативно-правовой акт" in out2
    assert "далее" in out2


def test_compound_shorts():
    """«т. е.», «т. к.», «в т. ч.» — слова, а не разорванные паузой обрывки."""
    from lektor.lingua.normalizer import TextNormalizer
    from lektor.report import Report
    n = TextNormalizer(Report())
    assert n.normalize_sentence("Кража, т. е. тайное хищение.") == \
        "Кража, то есть тайное хищение."
    assert n.normalize_sentence("Он оправдан, т. к. нет состава.") == \
        "Он оправдан, так как нет состава."
    assert n.normalize_sentence("В т. ч. и мы.").lower() == "в том числе и мы."
    assert n.normalize_sentence("И т. д. и т. п.") == "И так далее и тому подобное"
    assert n.normalize_sentence("Т. о., состав отсутствует.").lower() == \
        "таким образом, состав отсутствует."


def test_city_case_after_preposition():
    """«в г. Москве» -> «в городе Москве»: падеж слова «город» — от предлога."""
    from lektor.lingua.normalizer import TextNormalizer
    from lektor.report import Report
    n = TextNormalizer(Report())
    assert n.normalize_sentence("Проживает в г. Москве.") == \
        "Проживает в городе Москве."
    assert n.normalize_sentence("Прибыл из г. Курска.") == \
        "Прибыл из города Курска."
    assert n.normalize_sentence("К г. Туле подъезжаем.") == "К городу Туле подъезжаем."
    assert n.normalize_sentence("Рядом с г. Обнинском.") == "Рядом с городом Обнинском."
    # без предлога — именительный, как и раньше
    assert n.normalize_sentence("г. Москва — столица.") == "город Москва — столица."
    # год и грамм не должны превратиться в город
    assert "году" in n.normalize_sentence("В 2010 г. он родился.")
    assert "граммов" in n.normalize_sentence("Масса 100 г.")


def test_street_case_after_preposition():
    """«на ул. Ленина» -> «на улице Ленина» — падеж от предлога, не именительный."""
    from lektor.lingua.normalizer import TextNormalizer
    from lektor.report import Report
    n = TextNormalizer(Report())
    assert n.normalize_sentence("На ул. Ленина, д. 5 он жил.") == \
        "На улице Ленина, дом 5 он жил.".replace("5", "пять")
    assert n.normalize_sentence("По ул. Мира идут.") == "По улице Мира идут."
    assert n.normalize_sentence("В г. Москве, на пр. Вернадского.") == \
        "В городе Москве, на проспекте Вернадского."
    # адрес-перечисление без предлогов — именительный, как и раньше
    assert n.normalize_sentence("г. Москва, ул. Тверская, д. 7.") == \
        "город Москва, улица Тверская, дом семь."


def test_i_pr_short():
    """«и пр.» читается «и прочие» (а не остаётся «пр.»)."""
    from lektor.lingua.normalizer import TextNormalizer
    from lektor.report import Report
    n = TextNormalizer(Report())
    assert n.normalize_sentence("Расторжение, убытки и пр. последствия.") == \
        "Расторжение, убытки и прочие последствия."


def test_tom_volume():
    """«т. 3» — том (не буква «тэ» и не тонна)."""
    from lektor.lingua.normalizer import TextNormalizer
    from lektor.report import Report
    n = TextNormalizer(Report())
    assert n.normalize_sentence("Материалы в т. 2 изъяты.") == "Материалы в том 2 изъяты.".replace("2", "два")
    # тонна после числа — по-прежнему тонна
    assert "тонн" in n.normalize_sentence("Масса 5 т.")


def test_list_dela():
    """«л.д.» — лист дела с падежом от предлога, не «лист дэ»."""
    from lektor.lingua.normalizer import TextNormalizer
    from lektor.report import Report
    n = TextNormalizer(Report())
    out = n.normalize_sentence("На л.д. 55 имеется договор.")
    assert "листе дела" in out and "дэ" not in out
    assert "договор" in out


def test_measure_dot_not_sentence_end():
    """«в 5 т. содержится» — точка сокращения меры не рвёт фразу."""
    from lektor.lingua.normalizer import TextNormalizer
    from lektor.report import Report
    n = TextNormalizer(Report())
    out = n.normalize_sentence("В 5 т. содержится правило.")
    assert out == "В 5 тонн содержится правило.".replace("5 тонн", "пять тонн")
    # конец предложения — точка сохраняется
    assert n.normalize_sentence("Масса 5 т.").endswith("пять тонн.")
    # тире после меры — продолжение фразы
    assert "килограмма — это" in n.normalize_sentence("Проверка: 3 кг. — это вес.")
