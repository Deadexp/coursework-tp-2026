"""Алгоритм интервального повторения SM-2 (SuperMemo 2).

Оценка ответа quality — от 0 до 5:
    5 — вспомнил сразу, 4 — вспомнил с небольшой заминкой, 3 — вспомнил с трудом,
    0–2 — не вспомнил (слово начинает цикл заново).

Чем легче слово даётся (ease_factor), тем быстрее растут интервалы: 1 день → 6 дней →
6 × EF → … Трудные слова повторяются чаще — это и есть «повторение проблемных слов».
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

MIN_EASE = 1.3


@dataclass(frozen=True)
class Sm2State:
    ease_factor: float = 2.5
    interval_days: int = 0
    repetitions: int = 0


def review(state: Sm2State, quality: int) -> Sm2State:
    if not 0 <= quality <= 5:
        raise ValueError("quality must be between 0 and 5")

    if quality >= 3:
        if state.repetitions == 0:
            interval = 1
        elif state.repetitions == 1:
            interval = 6
        else:
            interval = round(state.interval_days * state.ease_factor)
        repetitions = state.repetitions + 1
    else:
        interval = 1
        repetitions = 0

    penalty = 5 - quality
    ease = state.ease_factor + 0.1 - penalty * (0.08 + penalty * 0.02)
    return Sm2State(
        ease_factor=round(max(MIN_EASE, ease), 4),
        interval_days=interval,
        repetitions=repetitions,
    )


def next_review_at(state: Sm2State, now: datetime) -> datetime:
    return now + timedelta(days=state.interval_days)
