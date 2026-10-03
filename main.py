# -*- coding: utf-8 -*-
"""Точка входа «Лектора»: pythonw main.py (окно приложения)."""
import sys


def run() -> int:
    try:
        from lektor.ui.gui import main
        return main()
    except Exception as e:
        # показать ошибку даже без консоли
        try:
            import tkinter as tk
            from tkinter import messagebox
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror("Лектор — ошибка запуска", str(e))
        except Exception:
            print(f"Ошибка запуска: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(run())
