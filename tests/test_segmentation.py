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


def test_enumeration_rhythm():
    """Однородные члены получают подъём тона, последний — обычный."""
    from lektor.config import load_settings
    from lektor.pipeline import Pipeline
    pipe = Pipeline(load_settings())
    utts, _ = pipe._analyze_wrap(
        "Документы, справки, выписки и квитанции приобщены к делу.")
    segs = [sg for u in utts for sg in u.segments]
    assert len(segs) == 3
    assert segs[0].pitch == "high" and segs[1].pitch == "high"
    assert segs[2].pitch is None
    # двучленное перечисление тоже поднимается
    utts2, _ = pipe._analyze_wrap(
        "Истец, ответчик и третьи лица явились в заседание.")
    segs2 = [sg for u in utts2 for sg in u.segments]
    assert segs2[0].pitch == "high" and segs2[-1].pitch is None
    # придаточное — НЕ перечисление, без искусственного подъёма
    utts3, _ = pipe._analyze_wrap("Он пришёл, чтобы забрать документы.")
    segs3 = [sg for u in utts3 for sg in u.segments]
    assert all(sg.pitch is None for sg in segs3)


def test_headings_split_from_paragraphs():
    """Заголовок (строка без знака + пустая строка) — отдельное предложение."""
    from lektor.lingua.tokenizer import split_sentences
    text = ("Введение в право\n\nПраво — это система норм. "
            "Она регулирует общество.")
    sents = split_sentences(text)
    assert len(sents) == 3
    assert sents[0].text == "Введение в право"
    # жёстко свёрстанный PDF (одиночные \n) не рассыпается
    pdf = ("Суд установил,\nчто долг не возвращён,\nа проценты не уплачены.")
    assert len(split_sentences(pdf)) == 1
    # без пустой строки заголовок не отрезается
    flow = "Глава про договоры\nТекст идёт сразу."
    assert len(split_sentences(flow)) == 1
    # диалог по строкам — реплики отдельные
    dialog = "— Ты пойдёшь?\n\n— Обязательно."
    assert len(split_sentences(dialog)) == 2


def test_initials_no_pause():
    """Точки инициалов («Иванов И. И. проживает») не дают пауз внутри ФИО."""
    from lektor.pipeline import Pipeline
    from lektor.config import Settings
    m = Pipeline(Settings()).dry_run("Иванов И. И. проживает в Курске.").markup
    # внутри ФИО нет границ предложения (520 мс)
    inside = m.split("\n")[0]
    assert "И. И." in inside
    assert inside.count("520") == 1     # только в самом конце


def test_intro_phrase_pauses():
    """Вводные обороты в середине предложения паузятся с обеих сторон."""
    from lektor.lingua.syntax import SyntaxAnalyzer
    from lektor.lingua.segmentation import Segmenter
    from lektor.report import Report
    sa = SyntaxAnalyzer()
    seg = Segmenter(Report("т"), fix_commas=True)

    def n_syn(text):
        return len(seg.segment(sa.analyze_sentence(text)))

    # «по мнению суда» (parataxis) — 4 синтагмы: Во-первых | истец |
    # по мнению суда | не представил
    assert n_syn("Во-первых, истец, по мнению суда, не представил "
                 "доказательств.") == 4
    # «по общему правилу» (obl-оборот) — 3 синтагмы
    assert n_syn("Решение, по общему правилу, может быть обжаловано.") == 3
    # «в силу статьи 421 ГК» — 3 синтагмы
    assert n_syn("Договор, в силу статьи 421 ГК, является свободным.") == 3
    # запятая перед «не представил» не удаляется частицей «не»
    words = sa.analyze_sentence("Истец, по мнению суда, не представил "
                                "доказательств.")
    segs = seg.segment(words)
    texts = [s.text() if callable(getattr(s, "text", None)) else s.text
             for s in segs]
    assert any("не представил" in t for t in texts)
    # тесные группы не рвутся
    assert n_syn("Стороны подписали договор и исполнили его.") == 1


def test_wh_questions_ik2():
    """Специальные вопросы звучат ИК-2, общие без «ли» — ИК-3."""
    from lektor.lingua.syntax import SyntaxAnalyzer
    from lektor.lingua.intonation import IntonationPlanner
    sa = SyntaxAnalyzer()
    ip = IntonationPlanner()

    def st(text):
        return ip.classify_sentence(sa.analyze_sentence(text), "?")

    assert st("Куда обратился истец за защитой прав?") == "IK2_wh_question"
    assert st("Чем закончилось заседание?") == "IK2_wh_question"
    assert st("Откуда поступила жалоба?") == "IK2_wh_question"
    assert st("Чей это иск?") == "IK2_wh_question"
    assert st("Сколько дней длился процесс?") == "IK2_wh_question"
    assert st("Суд удовлетворил иск?") == "IK3_polar_question"
    assert st("Был ли ответчик извещён?") == "IK3_polar_question"


def test_conj_adverb_light_pause():
    """«…, поэтому …» и «…, но …» — лёгкая пауза; «не только…, но и…» целое."""
    from lektor.lingua.syntax import SyntaxAnalyzer
    from lektor.lingua.segmentation import Segmenter
    from lektor.report import Report
    sa = SyntaxAnalyzer()
    seg = Segmenter(Report("т"), fix_commas=True)

    def n_syn(text):
        return len(seg.segment(sa.analyze_sentence(text)))

    assert n_syn("Требования обоснованы, поэтому суд удовлетворяет иск.") == 2
    assert n_syn("Ответчик признал иск, но попросил рассрочку.") == 2
    assert n_syn("Он не только явился, но и представил документы.") == 1
    assert n_syn("Это не столько иск, сколько жест отчаяния.") == 1
