# -*- coding: utf-8 -*-
"""Чтение файлов любых распространённых форматов: txt, docx, pdf, fb2, epub, md.

Возвращает обычный текст; нумерация страниц, колонтитулы и прочий «шум»
убирает модуль cleaner (тр. 26).
"""
from __future__ import annotations

import os
import re
import zipfile
from typing import Tuple

SUPPORTED = (".txt", ".md", ".docx", ".pdf", ".fb2", ".epub", ".rtf",
              ".html", ".htm")


def read_file(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    if ext in (".txt", ".md"):
        return _read_txt(path)
    if ext == ".docx":
        return _read_docx(path)
    if ext == ".pdf":
        return _read_pdf(path)
    if ext in (".fb2", ".epub"):
        return _read_book(path)
    if ext in (".html", ".htm"):
        return _read_html(path)
    if ext == ".rtf":
        return _read_txt(path)  # простая попытка; rtf встречается редко
    # неизвестный формат — пробуем как текст
    return _read_txt(path)


def _read_txt(path: str) -> str:
    raw = open(path, "rb").read()
    if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
        return raw.decode("utf-16", errors="ignore")
    try:
        import charset_normalizer
        guess = charset_normalizer.from_bytes(raw).best()
        if guess:
            return str(guess)
    except Exception:
        pass
    for enc in ("utf-8", "cp1251", "utf-16", "latin-1"):
        try:
            return raw.decode(enc)
        except Exception:
            continue
    return raw.decode("utf-8", errors="replace")


def _read_html(path: str) -> str:
    """HTML-страница: убираем разметку, блочные элементы — с новой строки."""
    html = _read_txt(path)
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        for t in soup(["script", "style", "head", "nav", "footer"]):
            t.decompose()
        # блочные элементы заканчиваем переводом строки, инлайн-теги
        # (жирный, ссылка) НЕ должны рвать предложение на «абзацы»
        for el in soup.find_all(["p", "div", "li", "h1", "h2", "h3", "h4",
                                 "h5", "h6", "br", "tr", "section", "article"]):
            el.append("\n")
        text = soup.get_text(" ")
    except ImportError:
        # без BeautifulSoup — грубая очистка
        text = re.sub(r"(?is)<(script|style).*?</\1>", " ", html)
        text = re.sub(r"<br\s*/?>", "\n", text)
        text = re.sub(r"</(p|div|li|h[1-6])>", "\n", text)
        text = re.sub(r"<[^>]+>", " ", text)
        import html as _h
        text = _h.unescape(text)
    return re.sub(r"\n{3,}", "\n\n", text)


def _read_docx(path: str) -> str:
    import docx  # python-docx
    d = docx.Document(path)
    parts = [p.text for p in d.paragraphs if p.text and p.text.strip()]
    # таблицы тоже содержат важный текст
    for table in d.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells if c.text.strip()]
            if cells:
                parts.append(" — ".join(cells))
    return "\n\n".join(parts)


def _read_pdf(path: str) -> str:
    import fitz  # PyMuPDF
    doc = fitz.open(path)
    pages = []
    for page in doc:
        pages.append(page.get_text("text"))
    return "\n\n".join(pages)


def _read_book(path: str) -> str:
    """fb2 и epub — это zip/xml, достаём текст."""
    texts = []
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        if path.lower().endswith(".fb2"):
            targets = [n for n in names if n.endswith(".fb2") or n.endswith(".xml")]
            targets = targets or [names[0]]
        else:  # epub: html-главы
            targets = [n for n in names if n.endswith((".html", ".xhtml", ".htm"))]
            targets.sort()
        for name in targets:
            data = z.read(name)
            try:
                html = data.decode("utf-8", errors="replace")
            except Exception:
                continue
            try:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(html, "html.parser")
                for bad in soup(["script", "style", "head"]):
                    bad.decompose()
                txt = soup.get_text("\n")
            except Exception:
                txt = re.sub(r"<[^>]+>", " ", html)
            txt = re.sub(r"\n{3,}", "\n\n", txt).strip()
            if txt:
                texts.append(txt)
    return "\n\n".join(texts)


def detect_title(path: str, text: str) -> str:
    """Имя для аудиофайла: из названия файла или первой строки."""
    base = os.path.splitext(os.path.basename(path))[0] if path else ""
    if base:
        return re.sub(r'[\\/:*?"<>|]+', "_", base)[:80]
    first = text.strip().splitlines()[0] if text.strip() else "текст"
    return first[:80].strip()
