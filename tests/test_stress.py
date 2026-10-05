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


def test_shared_accentor_model():
    """Модель ударений грузится один раз на все экземпляры."""
    from lektor.lingua.stress import StressAssigner
    from lektor.report import Report
    a1 = StressAssigner(Report())
    a2 = StressAssigner(Report())
    acc1 = a1._get_accentor()
    acc2 = a2._get_accentor()
    # либо обе None (нет модели), либо один и тот же объект
    assert acc1 is acc2
    assert StressAssigner._shared_acc_tried


def test_zamok_muka_homographs():
    """«замок на воротах» — замо́к; «феодальный замок» — за́мок;
    «пшеничная мука» — мукá; «муки ожидания» — му́ки."""
    from lektor.report import Report
    from lektor.lingua.stress import StressAssigner
    sa = StressAssigner(Report())
    out = sa.stress_sentence("Замок на воротах сорван.")
    assert "Зам+ок" in out
    out2 = sa.stress_sentence("Феодальный замок разрушен.")
    assert "з+амок" in out2
    out3 = sa.stress_sentence("Пшеничная мука изъята.")
    assert "мук+а" in out3
    out4 = sa.stress_sentence("Муки ожидания описаны.")
    assert "М+уки" in out4


def test_hyphen_words_get_stress():
    """Дефисные слова размечаются, а не уходят в модель «оголёнными»."""
    s = make()
    out = s.stress_sentence("Кто-то что-то знает по-прежнему.")
    low = out.lower()
    assert "кт+ото" in low and "чт+ото" in low
    assert "по-пр+ежнему" in low
    # двойных знаков и разрывов нет
    assert "++" not in out and "+-" not in out


def test_hyphen_clitics_unstressed():
    """Клитики «-нибудь», «-либо», «кое-» безударны."""
    s = make()
    out = s.stress_sentence("Как-нибудь кое-кто где-либо появится.")
    low = out.lower()
    assert "к+ак-нибудь" in low
    assert "кое-кт+о" in low
    assert "н+ибудь" not in low and "л+ибо" not in low and "к+ое-" not in low


def test_half_word_stress():
    """«пол-» формы: silero ошибается на «полгода/поллитра» — справочник точных ударений."""
    s = make()
    assert "полгод+а" in s.stress_sentence("полгода").lower()
    assert "пол-литр+а" in s.stress_sentence("пол-литра").lower()
    assert "полчас+а" in s.stress_sentence("полчаса").lower()
    assert "полутор+а" in s.stress_sentence("полутора").lower()
    # ошибочные первые-слоговые варианты исключены
    assert "п+олгода" not in s.stress_sentence("полгода").lower()


def test_ready_stress_not_duplicated():
    """«пол-» формы в предложении: по одному знаку на слово, без дублей."""
    s = make()
    out = s.stress_sentence("Прошло полчаса и пол-литра.")
    assert "полчас+а" in out.lower() and "пол-литр+а" in out.lower()
    assert out.count("+") == 3  # прошл+о, полчас+а, пол-литр+а (служебное «и» — без знака)
    assert "++" not in out


def test_service_hyphen_left_alone():
    """«из-за» целиком служебное — без знаков."""
    s = make()
    out = s.stress_sentence("Из-за дождя.")
    assert "из-за" in out.lower() and "+" not in out.lower().split("из-за")[0]


def test_to_izhest_unstressed():
    """«то есть» — связка «есть» безударна (и раздельно, и через дефис)."""
    s = make()
    out = s.stress_sentence("То есть, иными словами, это важно.")
    assert "то есть" in out.lower().replace("+", "") or "т+о есть" in out.lower()
    assert "+есть" not in out.lower()
    out2 = s.stress_sentence("то-есть")
    assert out2.lower() == "то-есть"
