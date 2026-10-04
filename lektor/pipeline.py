# -*- coding: utf-8 -*-
"""Конвейер «Лектора» (требование 27):

  загрузка и предобработка -> синтаксический анализ -> просодическая разметка
  -> синтез речи -> постобработка аудио.

Все модули заменяемые; конвейер управляет этапами, прогрессом, отменой
и собирает отчёт (тр. 30).
"""
from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, List, Optional

from .config import (Settings, OUTPUT_DIR, ENGINE_CHATTERBOX, ENGINE_SAPI,
                     ENGINE_SILERO, SAMPLE_RATE, CACHE_DIR)
from .lingua.focus import FocusFinder
from .lingua.intonation import IntonationPlanner
from .lingua.normalizer import TextNormalizer
from .lingua.segmentation import Segmenter, Boundary
from .lingua.stress import StressAssigner
from .lingua.syntax import SyntaxAnalyzer, W
from .lingua.tokenizer import split_sentences
from .report import Report
from .synthesis.backends import Backend, Segment, Utterance
from .textproc import ssml as ssml_mod
from .textproc.cleaner import Cleaner


class Stage(str, Enum):
    CLEAN = "Подготовка текста"
    ANALYZE = "Анализ текста"
    SYNTH = "Синтез речи"
    FINAL = "Завершение"


@dataclass
class JobResult:
    audio_path: str = ""
    duration_sec: float = 0.0
    report: Optional[Report] = None
    markup: str = ""
    engine: str = ""
    voice: str = ""


def build_backend(settings: Settings, log=print) -> Optional[Backend]:
    """Создаёт движок по настройкам с цепочкой запасных вариантов."""
    from .synthesis.silero_backend import SileroBackend
    from .synthesis.chatterbox_backend import ChatterboxBackend
    from .synthesis.sapi_backend import SapiBackend

    order = [settings.engine]
    for e in (ENGINE_SILERO, ENGINE_CHATTERBOX, ENGINE_SAPI):
        if e not in order:
            order.append(e)

    for engine in order:
        try:
            if engine == ENGINE_CHATTERBOX and ChatterboxBackend.is_available():
                return ChatterboxBackend(
                    sample_path=settings.chatterbox_sample,
                    exaggeration=settings.chatterbox_exaggeration,
                    cfg_weight=settings.chatterbox_cfg_weight, log=log)
            if engine == ENGINE_SILERO:
                return SileroBackend(log=log)
            if engine == ENGINE_SAPI and SapiBackend.is_available():
                return SapiBackend(log=log)
        except Exception as e:
            log(f"Движок {engine} недоступен: {e}")
    return None


class Pipeline:
    def __init__(self, settings: Settings,
                 progress: Callable[[str, float, str], None] = None,
                 cancel_event=None, log=None, cache: bool = True):
        self.settings = settings
        self.progress = progress or (lambda *a, **k: None)
        self.cache = cache
        self.cancel_event = cancel_event
        self.log = log or (lambda *a, **k: None)
        self.report: Optional[Report] = None
        self._syntax = SyntaxAnalyzer()

    # ------------------------------------------------------------------
    def _stage(self, stage: Stage, frac: float, msg: str = "") -> None:
        self.progress(stage.value, max(0.0, min(1.0, frac)), msg)

    def _cancelled(self) -> bool:
        return self.cancel_event is not None and self.cancel_event.is_set()

    # ==================================================================
    # Полный прогон: текст -> аудиофайл
    # ==================================================================
    def run(self, text: str, title: str, out_dir: str = None,
            out_path: str = None) -> JobResult:
        t0 = time.time()
        self.report = Report(title)
        result = JobResult(report=self.report)

        # 1) подготовка
        self._stage(Stage.CLEAN, 0.0, "очистка текста от служебного шума")
        clean = Cleaner(self.report, self.settings.footnotes).clean(text)
        ssml_res = ssml_mod.extract_ssml(clean, self.report)
        doc_text = ssml_res.text
        if not doc_text.strip():
            self.report.note("Текст пуст после очистки.")
            result.markup = ""
            return result

        # 2) анализ
        self._stage(Stage.ANALYZE, 0.0, "разбор предложений")
        utterances, markup = self._analyze(doc_text, ssml_res, collect_markup=True)
        if self._cancelled():
            return result
        if not utterances:
            self.report.note("Не нашлось ни одного предложения для озвучки.")
            return result

        # 3) синтез
        backend = build_backend(self.settings, self.log)
        if backend is None:
            raise RuntimeError(
                "Ни один движок синтеза недоступен. Запустите install.bat "
                "(скачает модели Silero) и повторите.")
        result.engine = backend.label
        voice = self._resolve_voice(backend)
        result.voice = voice

        from datetime import datetime
        if out_path:
            # точный путь вывода (CLI -o файл.mp3): папку создаём,
            # имя и расширение — как указал пользователь
            out_dir = os.path.dirname(os.path.abspath(out_path))
            os.makedirs(out_dir, exist_ok=True)
            base = os.path.splitext(out_path)[0]
        else:
            out_dir = out_dir or OUTPUT_DIR
            os.makedirs(out_dir, exist_ok=True)
            safe_title = re.sub(r'[\\/:*?"<>|]+', "_", title)[:60] or "лекция"
            stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
            base = os.path.join(out_dir, f"{safe_title} [{stamp}]")

        self._stage(Stage.SYNTH, 0.0, f"голос: {voice}")

        def synth_progress(done: int, total: int, msg: str) -> None:
            self._stage(Stage.SYNTH, done / max(1, total),
                        f"{done} из {total} реплик. {msg}")

        from .synthesis.renderer import Renderer
        from datetime import datetime as _dt
        renderer = Renderer(backend, voice,
                            speed=self.settings.speed,
                            inter_pause_scale=1.0,
                            progress=synth_progress,
                            cancel_event=self.cancel_event,
                            cache_dir=CACHE_DIR if self.cache else None,
                            meta={"title": title, "artist": "Лектор",
                                  "album": "Аудиолекции",
                                  "genre": "Аудиокнига",
                                  "year": str(_dt.now().year)})
        # при MP3 пишем потоково сразу в итоговый файл (без гигабайтного
        # промежуточного WAV); если lameenc недоступен, рендер сам
        # переключится на WAV и здесь сконвертирует
        out_file = base + (".mp3" if self.settings.fmt == "mp3" else ".wav")
        duration = renderer.render(utterances, out_file)
        if self._cancelled():
            for junk in (out_file, os.path.splitext(out_file)[0] + ".wav"):
                try:
                    os.unlink(junk)
                except Exception:
                    pass
            return result

        # 4) финализация
        self._stage(Stage.FINAL, 0.9, "сохранение и отчёт")
        if out_file.lower().endswith(".wav"):
            out_path = Renderer.export(
                out_file, self.settings.fmt,
                meta={"title": title, "artist": "Лектор",
                      "album": "Аудиолекции", "genre": "Аудиокнига",
                      "year": str(_dt.now().year)} if self.settings.fmt == "mp3" else None)
        else:
            out_path = out_file
        result.audio_path = out_path
        result.duration_sec = duration
        result.markup = markup

        if getattr(renderer, "failed", 0):
            self.report.note(
                f"Не синтезировано реплик: {renderer.failed} "
                "(пропущены в аудио; см. предупреждения выше)")
        if renderer.cache_hits or renderer.cache_misses:
            self.report.stats["кэш синтеза"] = (
                f"{renderer.cache_hits} реплик из кэша, "
                f"{renderer.cache_misses} синтезировано")
        self.report.stats["длительность_аудио_сек"] = round(duration, 1)
        self.report.stats["время_сборки_сек"] = round(time.time() - t0, 1)
        self.report.finish(duration, time.time() - t0)
        self.report.save(out_path)
        self._stage(Stage.FINAL, 1.0, "готово")
        return result

    # ==================================================================
    # Разметка без синтеза (проверка текста, тесты, --markup)
    # ==================================================================
    def _analyze_wrap(self, text: str):
        """Обёртка для тестов и предпросмотра: текст -> реплики + разметка."""
        from .textproc.cleaner import Cleaner
        from .textproc import ssml as ssml_mod
        self.report = getattr(self, "report", None) or Report("предпросмотр")
        clean = Cleaner(self.report, self.settings.footnotes).clean(text)
        ssml_res = ssml_mod.extract_ssml(clean, self.report)
        return self._analyze(ssml_res.text, ssml_res, collect_markup=True)

    def dry_run(self, text: str, title: str = "Проверка") -> JobResult:
        self.report = Report(title)
        clean = Cleaner(self.report, self.settings.footnotes).clean(text)
        ssml_res = ssml_mod.extract_ssml(clean, self.report)
        utterances, markup = self._analyze(ssml_res.text, ssml_res, collect_markup=True)
        return JobResult(report=self.report, markup=markup)

    # ==================================================================
    # Анализ: предложения -> реплики с просодией
    # ==================================================================
    def _analyze(self, doc_text: str, ssml_res, collect_markup: bool = False):
        s = self.settings
        mode = s.mode_params()
        normalizer = TextNormalizer(self.report, expand_abbrevs=s.expand_abbrevs)
        stress = StressAssigner(self.report)
        segmenter = Segmenter(self.report, fix_commas=s.fix_commas)
        focus_finder = FocusFinder(set(stress.legal_lemma.keys()))
        inton = IntonationPlanner()

        sentences = split_sentences(doc_text)
        total = max(1, len(sentences))
        utterances: List[Utterance] = []
        markup_lines: List[str] = []
        in_footnotes = False
        words_total = 0
        syntagm_total = 0

        prev_end = None
        for idx, sent in enumerate(sentences):
            if self._cancelled():
                break
            self._stage(Stage.ANALYZE, idx / total,
                        f"предложение {idx + 1} из {total}")
            if sent.text.strip().lower().startswith("сноски"):
                in_footnotes = True
            # граница абзаца: между предложениями есть перевод строки —
            # после него пауза заметно длиннее (тр. 11, «как человек»)
            new_paragraph = (prev_end is not None
                             and "\n" in doc_text[prev_end:sent.start])
            prev_end = sent.end

            # -- нормализация (числа, даты, аббревиатуры; тр. 23-25)
            norm = normalizer.normalize_sentence(sent.text)
            if not norm or not norm.strip():
                continue

            # -- ударения (тр. 1-7): пары (токен, форма для синтеза)
            pairs = stress.stress_tokens(norm)
            spoken = {i: p[1] for i, p in enumerate(pairs)}

            # -- синтаксическое дерево (тр. 9)
            words = self._syntax.analyze_sentence(norm)
            words_total += sum(1 for w in words if w.is_word)
            if not any(w.is_word for w in words):
                continue

            # -- SSML-директивы пользователя внутри этого предложения
            forced = {}
            for b in ssml_res.breaks:
                if sent.start <= b.pos < sent.end:
                    local = b.pos - sent.start
                    w_id = None
                    for w in words:
                        if w.start < local:
                            w_id = w.id
                        else:
                            break
                    if w_id is not None:
                        forced[w_id + 1] = b.time_ms

            emph_words = set()
            for e in ssml_res.emphases:
                if sent.start <= e.pos < sent.end:
                    emph_words.add(e.word.lower().strip("+"))

            # -- синтагмы и паузы (тр. 8, 10-14)
            syntagms = segmenter.segment(
                words,
                pause_intra_ms=int(mode["pause_intra_ms"] * s.pause_scale),
                pause_inter_ms=int(mode["pause_inter_ms"] * s.inter_pause_scale),
                pause_enum_ms=int(mode["pause_enum_ms"] * s.pause_scale),
                forced_breaks=forced)
            syntagm_total += len(syntagms)

            # -- логическое ударение (тр. 15-17)
            for syn in syntagms:
                f = focus_finder.find(syn.words)
                for w in syn.words:
                    if w.is_word and w.text.lower().strip("+") in emph_words:
                        f.word_id = w.id
                        f.reason = "SSML <emphasis> пользователя"
                syn.focus_id = f.word_id

            # -- тип предложения и интонационные контуры (тр. 18-21)
            final_punct = sent.text.rstrip()[-1:] if sent.text.rstrip() else "."
            if final_punct not in ".!?…":
                final_punct = ""
            heading = (final_punct == "" and len(words) <= 10)
            stype = "IK1_heading" if heading else inton.classify_sentence(words, final_punct or ".")
            plans = inton.assign(syntagms, stype)

            # -- реплика
            utterances.extend(self._to_utterances(
                syntagms, plans, spoken, mode, len(norm), in_footnotes, ssml_res,
                sent, markup_lines if collect_markup else None, new_paragraph))

        self.report.stats["слов"] = words_total
        self.report.stats["предложений"] = total
        self.report.stats["синтагм"] = syntagm_total
        if getattr(stress, "heuristic_count", 0):
            self.report.stats["ударений предположительно"] = stress.heuristic_count
        return utterances, "\n".join(markup_lines)

    # ------------------------------------------------------------------
    def _to_utterances(self, syntagms, plans, spoken, mode, sent_len: int,
                       is_footnote: bool, ssml_res, sent, markup_lines=None,
                       new_paragraph: bool = False) -> List[Utterance]:
        """Синтагмы -> реплики для движка (сегменты, паузы, ударения, темп)."""
        emphasis_mode = mode.get("emphasis", "subtle")
        complex_slow = sent_len > mode.get("complex_threshold", 170)

        # тексты синтагм
        texts = [syn.text(spoken) for syn in syntagms]

        segments: List[Segment] = []
        for i, (syn, plan) in enumerate(zip(syntagms, plans)):
            txt = texts[i].strip()
            if not txt:
                continue
            is_final = i == len(syntagms) - 1
            seg = Segment(
                text=txt,
                pause_after_ms=syn.pause_ms,
                rate=plan.rate,
                pitch=plan.pitch,
                final=is_final,
                # вопрос без вопросительного слова (ИК-3): подъём тона
                # на последнем слове — без него звучит утверждением
                question_rise=(is_final and plan.contour == "IK3_polar_question"),
            )
            # сложные фрагменты читаются медленнее (тр. 21)
            if complex_slow and plan.rate is None:
                seg.rate = "slow"
            # SSML <prosody> поверх сегмента
            for p in ssml_res.prosody:
                a0, a1 = sent.start, sent.start + sent_len
                if a0 <= p.start <= a1 or a0 <= p.end <= a1:
                    if p.rate:
                        seg.rate = p.rate
                    if p.pitch:
                        seg.pitch = p.pitch
            segments.append(seg)

            # страховка: сверхдлинный сегмент (текст без запятых/точек)
            # режем по словам — у движков есть предел длины запроса
            if len(txt) > 400:
                chunks, cur = [], ""
                for w in txt.split(" "):
                    if cur and len(cur) + len(w) + 1 > 350:
                        chunks.append(cur)
                        cur = w
                    else:
                        cur = (cur + " " + w).strip()
                if cur:
                    chunks.append(cur)
                rest = chunks[1:]
                seg.text = chunks[0]
                mid_pause = int(mode["pause_intra_ms"]
                                * self.settings.pause_scale)
                for j, chunk in enumerate(rest):
                    last = j == len(rest) - 1
                    segments.append(Segment(
                        text=chunk,
                        pause_after_ms=seg.pause_after_ms if last else mid_pause,
                        rate=seg.rate, pitch=seg.pitch, final=seg.final,
                        question_rise=(seg.question_rise if last else False)))

            # КАПС-слово из судебного акта («суд УКАЗАЛ…») —
            # говоримое усиление: голосом выделяем, как в документе
            if seg.emphasize_word is None:
                for tok in txt.split():
                    core = tok.strip(".,!?;:…«»()[]\"'—")
                    letters = core.replace("+", "")
                    if (len(letters) >= 4 and letters.isupper()
                            and any(v in letters for v in "АЕЁИОУЫЭЮЯ")):
                        # аббревиатуры без гласных (СССР, РФ) не трогаем
                        seg.emphasize_word = core
                        break

            # логическое ударение (тр. 15-17)
            if emphasis_mode != "off" and syn.focus_id >= 0:
                focus_word = next((w for w in syn.words if w.id == syn.focus_id), None)
                if focus_word is not None:
                    word_spoken = spoken.get(focus_word.id, focus_word.text)
                    if emphasis_mode == "strong":
                        seg.emphasize_word = word_spoken
                    elif segments and len(segments) >= 1:
                        # тонкий режим: небольшая пауза перед смысловым словом
                        prev = segments[-1] if segments[-1] is not seg else (segments[-2] if len(segments) > 1 else None)
                        if prev is not None and prev is not seg:
                            prev.pause_after_ms = max(prev.pause_after_ms, prev.pause_after_ms + 70)

        if not segments:
            return []
        # завершающая пауза между предложениями; после абзаца — длиннее
        base_pause = syntagms[-1].pause_ms or int(mode["pause_inter_ms"])
        if new_paragraph:
            base_pause = max(base_pause, int(mode["pause_inter_ms"] * 1.6))
        segments[-1].pause_after_ms = base_pause

        # маркировка для предпросмотра
        if markup_lines is not None:
            parts = []
            for seg in segments:
                parts.append(seg.text)
                if seg.pause_after_ms:
                    parts.append(f"⟦{seg.pause_after_ms} мс⟧")
            markup_lines.append((" ".join(parts)))

        # длинное предложение делим на несколько реплик: у Silero качество
        # и стабильность интонации заметно выше на коротких фрагментах
        out: List[Utterance] = []
        if sum(len(sg.text) for sg in segments) <= 320:
            out.append(Utterance(segments=segments, gain_db=-4.0 if is_footnote else 0.0))
        else:
            current: List[Segment] = []
            cur_len = 0
            for seg in segments:
                current.append(seg)
                cur_len += len(seg.text)
                if cur_len > 200 and seg.pause_after_ms >= 120:
                    out.append(Utterance(segments=current,
                                         gain_db=-4.0 if is_footnote else 0.0))
                    current, cur_len = [], 0
            if current:
                out.append(Utterance(segments=current,
                                     gain_db=-4.0 if is_footnote else 0.0))
        return out

    # ------------------------------------------------------------------
    def _resolve_voice(self, backend: Backend) -> str:
        voices = {v.id: v for v in backend.voices()}
        want = self.settings.voice
        if want in voices:
            return want
        if backend.id == ENGINE_CHATTERBOX:
            return "hd_default"
        vs = list(voices)
        return vs[0] if vs else "xenia"
