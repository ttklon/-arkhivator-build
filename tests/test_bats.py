# -*- coding: utf-8 -*-
"""Bat-файлы: кодировка CP866, CRLF, ключевые команды."""
import os

BATS = ("install.bat", "ЛЕКТОР.bat", "Озвучить файл.bat", "ДИАГНОСТИКА.bat")


def test_bats_cp866_crlf():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for name in BATS:
        path = os.path.join(root, name)
        assert os.path.exists(path), name
        data = open(path, "rb").read()
        data.decode("cp866")          # не битая кодировка консоли
        assert b"\r\n" in data        # переводы строк Windows
        assert b"<<<" not in data     # без артефактов конфликтов
        assert b"@echo off" in data


def test_diagnostics_bat_runs_doctor():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    data = open(os.path.join(root, "ДИАГНОСТИКА.bat"), "rb").read()
    data.decode("cp866")
    assert b"--doctor" in data
