# -*- coding: utf-8 -*-
"""Очистка текста: списки, сноски, маркеры (тр. 26)."""
from lektor.textproc.cleaner import Cleaner
from lektor.report import Report


def make(footnotes="skip"):
    return Cleaner(Report(), footnotes=footnotes)


def test_numbered_list_at_end_not_lost():
    """Критично: список в конце документа не должен пропадать как «сноска»."""
    c = make()
    out = c.clean("Основные принципы:\n1. Законность.\n2. Справедливость.\n3. Гуманизм.")
    assert "Законность" in out
    assert "Справедливость" in out
    assert "Гуманизм" in out


def test_numbered_marker_read_as_ordinal():
    c = make()
    out = c.clean("Принципы:\n1. Законность.\n2. Справедливость.")
    assert "Первое — Законность" in out
    assert "Второе — Справедливость" in out


def test_letter_markers():
    c = make()
    out = c.clean("Требования:\nа) объяснить;\nб) прекратить.")
    assert "Пункт а — объяснить" in out
    assert "Пункт б — прекратить" in out


def test_bullets_stripped():
    c = make()
    out = c.clean("В договоре:\n- срок;\n- цена.")
    assert "- срок" not in out
    assert "срок" in out and "цена" in out


def test_dialogue_dash_kept():
    c = make()
    out = c.clean("— Привет, — сказал он.\n— Здравствуй.")
    assert "— Привет" in out


def test_real_footnotes_still_detected():
    """Настоящие сноски («1 Слово…» с пробелом) по-прежнему отделяются."""
    c = make()
    out = c.clean("Текст основной части.\n\n1 Первая заметка про источники.\n2 Вторая заметка.")
    assert "заметка" not in out        # в режиме skip сноски убраны
    c2 = make(footnotes="end")
    out2 = c2.clean("Текст основной части.\n\n1 Первая заметка про источники.\n2 Вторая заметка.")
    assert "Первая заметка" in out2  # читаются в конце


def test_windows_line_endings_and_bom():
    """CRLF из файлов Windows и BOM не ломают абзацы и разметку."""
    c = make()
    out = c.clean("\ufeffПервый абзац.\r\nВторой абзац.\r\n\r\nТретий.")
    assert "\r" not in out
    assert "\ufeff" not in out
    assert "Первый абзац." in out and "Третий." in out


def test_invisible_chars_removed():
    c = make()
    out = c.clean("Сло\u200bво с невид\u00adимыми симв\u200dолами.")
    assert "\u200b" not in out and "\u00ad" not in out


def test_internet_dash():
    c = make()
    out = c.clean("Это -- важный момент, а это - тоже.")
    assert "—" in out
    assert "--" not in out
    # дефис внутри слова не трогаем
    out2 = c.clean("какой-то пункт по-прежнему читается слитно.")
    assert "какой-то" in out2 and "по-прежнему" in out2


def test_ascii_quotes_to_guillemets():
    """Парные ASCII-кавычки превращаются в «ёлочки»."""
    c = make()
    out = c.clean('Он сказал "довольно" и ушёл.')
    assert "«довольно»" in out
    assert '"' not in out
    # уже типографские кавычки не трогаем
    out2 = c.clean("Он сказал «довольно» и ушёл.")
    assert "«довольно»" in out2


def test_ascii_quotes_keep_ssml():
    """Кавычки внутри SSML-тегов не превращаются в ёлочки."""
    c = make()
    out = c.clean('Фраза <break time="700ms"/> продолжается. Он сказал "довольно".')
    assert 'time="700ms"' in out
    assert "«довольно»" in out
    # пара кавычек через тег не разваливается
    out2 = c.clean('Он сказал "слова <emphasis>жирно</emphasis> дальше" и ушёл.')
    assert out2.count("«") == 1 and out2.count("»") == 1


def test_superscript_units_not_footnotes():
    """«м²», «см³», «м/с²» — единицы, а не сноски: cleaner не должен
    вырезать из них надстрочные цифры (нормализатор читает их словами)."""
    from lektor.textproc.cleaner import Cleaner
    from lektor.report import Report
    c = Cleaner(Report())
    assert c.clean("Площадь 100 м² и 30 см³.") == "Площадь 100 м² и 30 см³."
    assert c.clean("Ускорение 9,8 м/с².") == "Ускорение 9,8 м/с²."
    assert c.clean("Поле 5 км² и 10 мм².") == "Поле 5 км² и 10 мм²."
    # настоящие сноски после слов — удаляются
    assert c.clean("Сноска¹ и ещё² тут.") == "Сноска и ещё тут."


def test_single_line_not_colontitle():
    """Однострочный ввод «ст. 158» — это текст, а не колонтитул «ст. 158 из 200»."""
    from lektor.textproc.cleaner import Cleaner
    from lektor.report import Report
    c = Cleaner(Report())
    assert c.clean("ст. 158") == "ст. 158"
    assert c.clean("158") == "158"
    # в многострочном тексте номера страниц по-прежнему выкидываются
    multi = "Текст документа.\n12\n13\nЕщё текст."
    assert c.clean(multi) == "Текст документа.\nЕщё текст."
