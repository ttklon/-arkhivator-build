# -*- coding: utf-8 -*-
"""Настройки приложения «Лектор»: пути, движки, режимы озвучки, пользовательские параметры."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, asdict, field
from typing import Optional

APP_NAME = "Лектор"

# Корень приложения — папка, в которой лежит пакет lektor
APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Служебные папки (создаются автоматически)
DATA_DIR = os.path.join(APP_DIR, "данные")            # настройки и отчёты
USER_DICT_DIR = os.path.join(APP_DIR, "словари")      # пользовательские словари
OUTPUT_DIR = os.path.join(APP_DIR, "Аудиолекции")     # готовые аудиофайлы
MODELS_DIR = os.path.join(APP_DIR, "модели")          # скачанные модели
CACHE_DIR = os.path.join(DATA_DIR, "кэш")             # кэш синтеза реплик
SETTINGS_PATH = os.path.join(DATA_DIR, "настройки.json")

SAMPLE_RATE = 48000  # Гц, итоговая частота всех движков

# ---------------------------------------------------------------------------
# Движки синтеза
# ---------------------------------------------------------------------------
ENGINE_SILERO = "silero"          # быстрый, работает везде, точные ударения через «+»
ENGINE_CHATTERBOX = "chatterbox"  # HD: самый живой голос, нужна NVIDIA (6+ ГБ)
ENGINE_SAPI = "sapi"              # запасной: встроенные голоса Windows

SILERO_VOICES = [
    ("xenia", "Ксения (v4) — женский, спокойный"),
    ("baya", "Бая (v4) — женский, мягкий"),
    ("aidar", "Айдар (v4) — мужской, ровный"),
    ("eugene", "Евгений (v4) — мужской, низкий"),
    ("kseniya", "Ксения (v3) — женский, классический"),
]

# ---------------------------------------------------------------------------
# Режимы озвучки (требования 20, 21, 29)
# ---------------------------------------------------------------------------
MODES = {
    # «Лекция» — умеренный темп, паузы для осмысления, логические ударения.
    "lecture": dict(
        label="Лекция",
        speed=0.95,            # множитель темпа речи
        pause_intra_ms=240,    # пауза между синтагмами (норма 150–300 мс)
        pause_inter_ms=520,    # пауза между предложениями (норма 400–600 мс)
        pause_enum_ms=260,     # пауза между пунктами перечисления
        emphasis="subtle",     # логическое ударение: subtle | strong | off
        complex_tempo=0.90,    # замедление сложных фрагментов на ~10 %
        complex_threshold=170, # при длине синтагмы/предложения свыше N символов
    ),
    # «Чтение документа» — быстрее, минимум пауз, только структурные остановки.
    "document": dict(
        label="Чтение документа",
        speed=1.06,
        pause_intra_ms=160,
        pause_inter_ms=420,
        pause_enum_ms=200,
        emphasis="off",
        complex_tempo=0.97,
        complex_threshold=230,
    ),
}


def ensure_dirs() -> None:
    """Создаёт служебные папки и шаблоны пользовательских словарей."""
    for d in (DATA_DIR, USER_DICT_DIR, OUTPUT_DIR, MODELS_DIR, CACHE_DIR):
        os.makedirs(d, exist_ok=True)
    stress_dict = os.path.join(USER_DICT_DIR, "ударения.txt")
    if not os.path.exists(stress_dict):
        with open(stress_dict, "w", encoding="utf-8") as f:
            f.write(
                "# Пользовательский словарь ударений.\n"
                "# По одному слову в строке: знак «+» ставится ПЕРЕД ударной гласной.\n"
                "# Примеры:\n"
                "# остр+ота\n"
                "# м+ука\n"
                "# догов+оры\n"
                "# Пустые строки и строки, начинающиеся с #, игнорируются.\n"
            )
    replaces = os.path.join(USER_DICT_DIR, "замены.txt")
    if not os.path.exists(replaces):
        with open(replaces, "w", encoding="utf-8") as f:
            f.write(
                "# Словарь замен: как читать слово или аббревиатуру.\n"
                "# Формат: как написано в тексте = как читать вслух (по одному в строке).\n"
                "# Примеры:\n"
                "# ФЗО = эф зэ о\n"
                "# эстоппель = эстопп+эль\n"
            )


# ---------------------------------------------------------------------------
# Настройки пользователя (сохраняются между сессиями — требование 28)
# ---------------------------------------------------------------------------
@dataclass
class Settings:
    # Движок и голос
    engine: str = ENGINE_SILERO
    voice: str = "xenia"                    # голос Silero
    chatterbox_sample: str = ""             # путь к образцу голоса для клонирования (HD)
    chatterbox_exaggeration: float = 0.4    # 0..1.5 — «эмоциональность» HD-голоса
    chatterbox_cfg_weight: float = 0.3      # 0..1 — стабильность HD-голоса
    # Режим и темп
    mode: str = "lecture"
    speed: float = 1.0                      # общий множитель скорости (0.7..1.3)
    # Паузы (масштабируются от режима)
    pause_scale: float = 1.0                # множитель пауз внутри предложения
    inter_pause_scale: float = 1.0          # множитель пауз между предложениями
    # Логика текста
    fix_commas: bool = True                 # исправлять запятые по синтаксису (тр. 8–10)
    expand_abbrevs: bool = True             # расшифровка аббревиатур при первом упоминании (тр. 23)
    footnotes: str = "skip"                 # skip | end — что делать со сносками (тр. 26)
    read_numbers: bool = True               # нормализация чисел, дат, статей (тр. 24–25)
    # Выдача
    fmt: str = "mp3"                        # mp3 | wav
    open_folder: bool = True                # открывать папку с результатом
    window: str = ""                        # размер и положение окна (WxH+X+Y)
    recent: list = field(default_factory=list)  # недавние файлы (пути)
    appearance: str = "dark"                # dark | light — тема интерфейса

    def mode_params(self) -> dict:
        return dict(MODES.get(self.mode, MODES["lecture"]))


def load_settings() -> Settings:
    ensure_dirs()
    s = Settings()
    try:
        if os.path.exists(SETTINGS_PATH):
            with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            for k, v in data.items():
                if hasattr(s, k):
                    setattr(s, k, v)
    except Exception:
        pass  # повреждённые настройки не должны ломать запуск
    return s


def save_settings(s: Settings) -> None:
    ensure_dirs()
    try:
        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(asdict(s), f, ensure_ascii=False, indent=2)
    except Exception:
        pass
