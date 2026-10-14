from datetime import UTC, datetime

import pytest

from app.modules.vocabulary.sm2 import MIN_EASE, Sm2State, next_review_at, review


def test_perfect_answers_grow_intervals_1_6_16() -> None:
    state = Sm2State()
    intervals = []
    for _ in range(3):
        state = review(state, 5)
        intervals.append(state.interval_days)

    # 1 день → 6 дней → round(6 × 2.7) = 16 дней; EF растёт на 0.1 за каждый ответ «легко»
    assert intervals == [1, 6, 16]
    assert state.ease_factor == pytest.approx(2.8)
    assert state.repetitions == 3


def test_quality_4_keeps_ease_and_3_lowers_it() -> None:
    assert review(Sm2State(), 4).ease_factor == pytest.approx(2.5)
    assert review(Sm2State(), 3).ease_factor == pytest.approx(2.36)


def test_forgotten_word_restarts_cycle() -> None:
    learned = Sm2State(ease_factor=2.5, interval_days=16, repetitions=3)

    state = review(learned, 1)

    assert (state.interval_days, state.repetitions) == (1, 0)
    assert state.ease_factor == pytest.approx(1.96)


def test_ease_never_drops_below_minimum() -> None:
    state = Sm2State()
    for _ in range(10):
        state = review(state, 0)
    assert state.ease_factor == MIN_EASE


def test_quality_out_of_range_is_rejected() -> None:
    with pytest.raises(ValueError):
        review(Sm2State(), 6)


def test_next_review_at_adds_interval() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    assert next_review_at(Sm2State(interval_days=6), now) == datetime(2026, 1, 7, tzinfo=UTC)
