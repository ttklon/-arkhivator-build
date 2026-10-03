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
