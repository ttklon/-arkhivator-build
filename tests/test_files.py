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


def test_broken_docx_human_message(tmp_path):
    """Повреждённый .docx — понятное сообщение вместо техжаргона."""
    import pytest
    from lektor.textproc.files import read_file
    bad = tmp_path / "битый.docx"
    bad.write_text("это не docx", encoding="utf-8")
    with pytest.raises(RuntimeError) as e:
        read_file(str(bad))
    assert "повреждён" in str(e.value) or "docx" in str(e.value)


def test_pdf_scan_no_text_layer(tmp_path):
    """PDF без текстового слоя — подсказка про скан/OCR."""
    import pytest
    from lektor.textproc.files import read_file
    try:
        import fitz  # noqa
    except ImportError:
        pytest.skip("PyMuPDF не установлен")
    doc = fitz.Document()
    doc.new_page()
    scan = tmp_path / "скан.pdf"
    doc.save(str(scan))
    with pytest.raises(RuntimeError) as e:
        read_file(str(scan))
    assert "текстового слоя" in str(e.value) or "скан" in str(e.value)
