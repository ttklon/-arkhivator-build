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
        return _read_rtf(path)
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


_RTF_SKIP_GROUPS = {"fonttbl", "colortbl", "stylesheet", "info", "pict",
                    "object", "generator", "themedata", "listtable",
                    "listoverridetable", "rsidtbl", "latentstyles",
                    "datastore", "xmlnstbl", "filetbl", "colorschememapping"}


def _read_rtf(path: str) -> str:
    """RTF (Word-эпоха, в юрархивах встречается): мини-парсер без зависимостей.

    Старое поведение — «читать как текст» — озвучивало команды
    («\\rtf1\\ansi\\fs24…»); теперь: \'XX (cp1251) и \\uNNNN — в буквы,
    \\par — абзац, таблицы шрифтов/цветов/метаданные — вырезаются.
    """
    raw = _read_txt(path)
    if not raw.lstrip().startswith("{"):
        return raw                      # не RTF — читаем как есть
    out = []
    i, n = 0, len(raw)
    while i < n:
        ch = raw[i]
        if ch == "{":
            m = re.match(r"\{\\(?:\*\\)?([a-z]+)", raw[i:i + 40])
            if m and m.group(1).lower() in _RTF_SKIP_GROUPS:
                depth, j = 1, i + 1
                while j < n and depth:
                    if raw[j] == "{":
                        depth += 1
                    elif raw[j] == "}":
                        depth -= 1
                    j += 1
                i = j
                continue
            i += 1
        elif ch == "}":
            i += 1
        elif ch == "\\":
            if raw[i:i + 2] == "\\'":
                try:
                    out.append(bytes([int(raw[i + 2:i + 4], 16)]).decode("cp1251"))
                except Exception:
                    pass
                i += 4
            elif raw[i:i + 2] == "\\u":
                m = re.match(r"\\u(-?\d+)", raw[i:])
                if m:
                    out.append(chr(int(m.group(1)) & 0xFFFF))
                    i += m.end()
                    # за \uNNNN может следовать ?-заменитель и/или \'XX-фолбэк
                    if i < n and raw[i] == "?":
                        i += 1
                    if raw[i:i + 2] == "\\'":
                        i += 4
                else:
                    i += 2
            else:
                m = re.match(r"\\([a-z]+)(-?\d+)? ?", raw[i:], re.IGNORECASE)
                if m:
                    word = m.group(1).lower()
                    if word in ("par", "line", "page", "sect", "pard"):
                        out.append("\n")
                    elif word == "tab":
                        out.append(" ")
                    elif word == "emdash":
                        out.append("—")
                    elif word == "endash":
                        out.append("–")
                    elif word == "lquote":
                        out.append("«")
                    elif word == "rquote":
                        out.append("»")
                    elif word == "ldblquote":
                        out.append("«")
                    elif word == "rdblquote":
                        out.append("»")
                    elif word == "_":
                        out.append("-")
                    i += m.end()
                else:
                    i += 1              # \\{\} — экранированные символы
        else:
            out.append(ch)
            i += 1
    text = "".join(out)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" ?\n ?", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


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
    try:
        import docx  # python-docx
        d = docx.Document(path)
    except ImportError:
        raise RuntimeError("не установлен python-docx: запустите install.bat "
                           "или «pip install python-docx»")
    except Exception:
        raise RuntimeError("файл повреждён или не является документом Word (.docx); "
                           "для старого формата .doc пересохраните как .docx или .txt")
    parts = []

    def add_table(table):
        # ячейки строки — через тире, строки — абзацами
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells if c.text.strip()]
            if cells:
                parts.append(" — ".join(cells))

    # абзацы и таблицы в ИСХОДНОМ порядке (w:p и w:tbl чередуются в теле
    # документа); раньше таблицы выпадали в конец текста
    try:
        from docx.oxml.ns import qn
        from docx.table import Table as _Table
        from docx.text.paragraph import Paragraph as _Par
        for child in d.element.body.iterchildren():
            if child.tag == qn("w:p"):
                t = _Par(child, d).text
                if t and t.strip():
                    parts.append(t)
            elif child.tag == qn("w:tbl"):
                add_table(_Table(child, d))
    except Exception:
        # запасной путь для экзотических структур — как раньше
        parts = [p.text for p in d.paragraphs if p.text and p.text.strip()]
        for table in d.tables:
            add_table(table)
    return "\n\n".join(parts)


def _read_pdf(path: str) -> str:
    try:
        import pymupdf as fitz  # PyMuPDF: import fitz удалён в новых версиях
        doc = fitz.open(path)
    except ImportError:
        raise RuntimeError("не установлен PyMuPDF: запустите install.bat "
                           "или «pip install PyMuPDF»")
    except Exception:
        raise RuntimeError("файл повреждён или не является документом PDF")
    pages = []
    for page in doc:
        pages.append(page.get_text("text"))
    text = "\n\n".join(pages)
    if not text.strip():
        raise RuntimeError("в PDF нет текстового слоя — похоже на скан; "
                           "распознайте текст (OCR) и сохраните как .txt/.docx")
    return text


def _read_book(path: str) -> str:
    """fb2 и epub — это zip/xml, достаём текст.

    fb2 часто лежит незазипованным (просто XML) — читаем и так, и так.
    """
    texts = []
    try:
        z = zipfile.ZipFile(path)
    except zipfile.BadZipFile:
        if path.lower().endswith(".fb2"):
            # незазипованный fb2 — обычный XML-файл
            try:
                html = open(path, "rb").read().decode("utf-8", errors="replace")
            except Exception as e:
                raise RuntimeError(f"fb2 не читается: {e}")
            txt = _soup_text(html)
            if txt:
                return txt
            raise RuntimeError("В fb2 не нашлось текста — файл пуст или повреждён.")
        raise RuntimeError(
            "Файл повреждён или не является действительным epub "
            "(внутри нет zip-контейнера).")
    with z:
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
            txt = _soup_text(html)
            if txt:
                texts.append(txt)
    return "\n\n".join(texts)


def _soup_text(html: str) -> str:
    """Текст из html/xml: убрать скрипты/стили, вытащить содержимое."""
    try:
        from bs4 import BeautifulSoup
        try:
            # fb2 — это XML: bs4 печатает предупреждение, гасим его
            from bs4 import XMLParsedAsHTMLWarning
            import warnings
            warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)
        except Exception:
            pass
        soup = BeautifulSoup(html, "html.parser")
        for bad in soup(["script", "style", "head"]):
            bad.decompose()
        txt = soup.get_text("\n")
    except Exception:
        txt = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\n{3,}", "\n\n", txt).strip()


def detect_title(path: str, text: str) -> str:
    """Имя для аудиофайла: из названия файла или первой строки."""
    base = os.path.splitext(os.path.basename(path))[0] if path else ""
    if base:
        return re.sub(r'[\\/:*?"<>|]+', "_", base)[:80]
    first = text.strip().splitlines()[0] if text.strip() else "текст"
    return first[:80].strip()
