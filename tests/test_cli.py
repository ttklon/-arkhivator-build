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
