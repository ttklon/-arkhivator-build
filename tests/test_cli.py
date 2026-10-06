# -*- coding: utf-8 -*-
"""Интерфейс командной строки."""
import pytest

from lektor import __version__


def test_version_flag(capsys):
    """--version печатает версию и завершается с кодом 0."""
    from lektor.cli import main
    with pytest.raises(SystemExit) as e:
        main(["--version"])
    assert e.value.code == 0
    out = capsys.readouterr().out
    assert __version__ in out


def test_doctor_prints_version(capsys):
    """Самодиагностика показывает версию программы."""
    from lektor.cli import doctor
    doctor()
    out = capsys.readouterr().out
    assert __version__ in out


def test_load_settings_type_validation(tmp_path, monkeypatch):
    """Битые настройки (неверные типы, выход за диапазон) не роняют GUI."""
    import json
    import os
    from lektor import config

    monkeypatch.setattr(config, "SETTINGS_PATH",
                        str(tmp_path / "настройки.json"))
    p = str(tmp_path / "настройки.json")
    json.dump({"speed": "быстро", "mode": 123, "chapters": "да",
               "pause_scale": 99, "voice": ["xenia"], "footnotes": "end"},
              open(p, "w", encoding="utf-8"), ensure_ascii=False)
    s = config.load_settings()
    assert s.speed == 1.0 and s.mode == "lecture"
    assert s.chapters is False and s.pause_scale == 2.0
    assert s.voice == "xenia" and s.footnotes == "end"
    # полностью битый файл — молчаливые дефолты
    open(p, "w", encoding="utf-8").write("{битый")
    s2 = config.load_settings()
    assert s2.speed == 1.0


def test_batch_folder_output_and_rc(tmp_path, monkeypatch):
    """Пакетный режим: -o задаёт папку вывода; rc=1 при частичном успехе."""
    import os
    from lektor import config
    from lektor.cli import main
    src = tmp_path / "тексты"
    src.mkdir()
    (src / "первый.txt").write_text(
        "Первый файл пакетного теста. Два предложения.", encoding="utf-8")
    (src / "пустой.txt").write_text("   \n\n", encoding="utf-8")
    out = tmp_path / "выход"
    # изолируем пользовательские папки программы
    monkeypatch.setattr(config, "OUTPUT_DIR", str(out))
    rc = main([str(src), "-o", str(out)])
    assert rc == 1                      # один из двух — частичный успех
    mps = [f for f in os.listdir(str(out)) if f.endswith(".mp3")]
    assert len(mps) == 1                # -o реально использован как папка
