# -*- coding: utf-8 -*-
"""Чтение файлов разных форматов."""
import os

from lektor.textproc.files import read_file, SUPPORTED


def test_html_stripped(tmp_path):
    p = tmp_path / "страница.html"
    p.write_text(
        "<html><head><style>.x{}</style><script>var a=1;</script></head>"
        "<body><h1>Заголовок</h1><p>Первый <b>абзац</b> текста.</p>"
        "<ul><li>пункт раз</li><li>пункт два</li></ul></body></html>",
        encoding="utf-8")
    t = read_file(str(p))
    flat = " ".join(t.split())
    assert "var a" not in t and ".x" not in t
    assert "Заголовок" in flat
    assert "Первый абзац текста." in flat   # инлайн-теги не рвут фразу
    assert ".html" in SUPPORTED


def test_txt_encodings(tmp_path):
    p = tmp_path / "cp1251.txt"
    p.write_bytes("Проверка кодировки.".encode("cp1251"))
    assert "Проверка" in read_file(str(p))
    p2 = tmp_path / "utf16.txt"
    p2.write_bytes("Другая кодировка.".encode("utf-16"))
    assert "Другая" in read_file(str(p2))
