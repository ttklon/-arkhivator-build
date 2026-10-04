# -*- coding: utf-8 -*-
"""Ударения (требования 1-7, 28)."""
from lektor.lingua.stress import StressAssigner, strip_stress
from lektor.report import Report


def make(tmp_path=None):
    if tmp_path:
        import os
        d = tmp_path / "словари"
        d.mkdir(exist_ok=True)
        (d / "ударения.txt").write_text("остр+ота\nтвор+ог\n", encoding="utf-8")
        (d / "замены.txt").write_text("эстоппель = эстопп+эль\n", encoding="utf-8")
        return StressAssigner(Report(), user_dict_dir=str(d))
    return StressAssigner(Report())


def test_stress_marks_format():
    s = make()
    out = s.stress_sentence("Приговор по делу.")
    assert "пригов+ор" in out.lower()


def test_yo_rule():
    s = make()
    out = s.stress_sentence("Осуждённый дал показания.")
    assert "+ё" in out


def test_lemma_transfer():
    s = make()
    out = s.stress_sentence("Экспертиза по приговору.")
    assert "пригов+ору" in out.lower()


def test_monosyllabic_content_word_marked():
    s = make()
    out = s.stress_sentence("Суд вынес приговор.")
    assert "с+уд" in out.lower() or "С+уд" in out


def test_function_word_not_marked():
    s = make()
    out = s.stress_sentence("Он был в доме и в саду."
                            .replace(" и в саду", ""))
    # предлоги и частицы не выделяются (знаменательные односложные — выделяются)
    assert " в+ " not in out and " в+." not in out


def test_homograph_context():
    s = make()
    out = s.stress_sentence("Навесной замок открыт.")
    assert "зам+ок" in out.lower()
    out2 = s.stress_sentence("Средневековый замок разрушен.")
    assert "з+амок" in out2.lower()


def test_user_dict(tmp_path):
    s = make(tmp_path)
    out = s.stress_sentence("Острота вопроса и эстоппель.")
    assert "остр+ота" in out.lower()
    assert "эстопп+эль" in out


def test_strip():
    assert strip_stress("пригов+ор, м+ука") == "приговор, мука"


def test_full_marking_guarantee():
    """ГЛАВНОЕ: v5_cis_base требует знак ударения у КАЖДОГО многосложного
    слова — без него слово читается безударной кашей."""
    s = make()
    for text in ["Привет, это проверка голоса.",
                 "Уголовное дело возбуждено по факту хищения.",
                 "Экспертиза назначена, ходатайство удовлетворено."]:
        out = s.stress_sentence(text)
        for w in out.split():
            plain = w.strip(".,!?;:()«»\"'…—").replace("+", "")
            if any(c.isalpha() for c in plain) and sum(
                    c in "аеёиоуыэюяАЕЁИОУЫЭЮЯ" for c in plain) >= 2:
                assert "+" in w, f"без ударения: {w!r} в {out!r}"


def test_uzhe_context():
    s = make()
    out = s.stress_sentence("Что уже хорошо.")
    assert "уж+е" in out  # «уже» = already, не «у́же»


def test_homograph_rules_fire():
    s = make()
    out = s.stress_sentence("Средневековый замок разрушен, а дверной замок заперт.")
    assert "з+амок" in out and "зам+ок" in out


def test_participle_and_homograph_stress():
    """Краткие причастия и контекстные омографы — по норме, не по нейросети."""
    st = make()
    out = st.stress_sentence("Задача не принята, но средства выделены и отчёт сдан.")
    assert "принят+а" in out
    assert "ср+едства" in out
    out2 = st.stress_sentence("Отчёт за четвёртый квартал сдан, жилой квартал застроен.")
    assert "кв+артал" in out2      # отчётный период
    assert "кварт+ал" in out2      # район застройки
    out3 = st.stress_sentence("Орган власти издал акт, музыкальный орган звучал.")
    assert "+Орган" in out3 and "орг+ан" in out3
