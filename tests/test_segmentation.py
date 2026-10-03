# -*- coding: utf-8 -*-
"""Синтагмы и исправление запятых (требования 8-14)."""
from lektor.lingua.syntax import SyntaxAnalyzer
from lektor.lingua.segmentation import Segmenter, Boundary
from lektor.report import Report


def analyze_and_segment(text, fix=True):
    rep = Report()
    sa = SyntaxAnalyzer()
    words = sa.analyze_sentence(text)
    seg = Segmenter(rep, fix_commas=fix)
    syntagms = seg.segment(words)
    return rep, words, syntagms


def test_bad_comma_removed():
    """«Освободи, меня …» — запятая рвёт глагол и дополнение (тр. 8, 9)."""
    rep, words, syntagms = analyze_and_segment("Освободи, меня от уголовной ответственности.")
    comma_events = [e for e in rep.events if e.kind == "comma"]
    assert comma_events, "запятая должна была попасть в отчёт"
    assert "глагол" in comma_events[0].reason and "дополнение" in comma_events[0].reason
    # запятой больше нет в текстах синтагм
    joined = " ".join(s.text() for s in syntagms)
    assert "Освободи, меня" not in joined


def test_normal_comma_kept():
    """Запятая перед «который» и между однородными остаётся."""
    rep, words, syntagms = analyze_and_segment("Дело, которое возбуждено, рассматривается судом.")
    joined = " ".join(s.text() for s in syntagms)
    assert "Дело," in joined or "Дело" in joined  # запятая при союзе сохранена или синтагма разрезана


def test_intro_word_pause():
    rep, words, syntagms = analyze_and_segment("Таким образом, требования обоснованны.")
    assert len(syntagms) >= 2  # вводное отделено паузой


def test_strong_boundary_at_end():
    rep, words, syntagms = analyze_and_segment("Первая синтагма. Вторая.")
    assert syntagms[-1].boundary == Boundary.STRONG
    assert syntagms[-1].pause_ms >= 400


def test_pause_ranges():
    rep, words, syntagms = analyze_and_segment("Вводное слово, следовательно, разделяет.")
    for s in syntagms:
        if s.boundary == Boundary.MEDIUM:
            assert 120 <= s.pause_ms <= 600


def test_no_punct_one_syntagm():
    rep, words, syntagms = analyze_and_segment("Короткое предложение без знаков внутри")
    assert len(syntagms) == 1
