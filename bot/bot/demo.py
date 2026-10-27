"""Isolated sample-data adapter. No site, database, or LLM connections.

Production clients must use the backend API. This adapter deliberately keeps
everything in memory and uses illustrative intervals, not the backend's SM-2.
"""

import random
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta


@dataclass(frozen=True)
class Word:
    id: int
    text: str
    translation: str


WORDS = (
    Word(1, "apple", "яблоко"),
    Word(2, "journey", "путешествие"),
    Word(3, "improve", "улучшать"),
    Word(4, "enough", "достаточно"),
    Word(5, "habit", "привычка"),
    Word(6, "careful", "осторожный"),
    Word(7, "mistake", "ошибка"),
    Word(8, "remember", "помнить"),
)
LEVELS = ("A1", "A2", "B1", "B2", "C1", "C2")


def normalize_answer(text: str) -> str:
    """Accept case, surrounding whitespace and an optional final full stop."""
    return text.strip().casefold().removesuffix(".").rstrip()


@dataclass(frozen=True)
class GapExercise:
    sentence: str
    answers: tuple[str, ...]
    explanation: str

    def accepts(self, text: str) -> bool:
        return normalize_answer(text) in self.answers

    @property
    def completed_sentence(self) -> str:
        return self.sentence.replace("___", self.answers[0])


# One fixed exercise per demo word; the Russian hint is the word's translation.
GAP_EXERCISES = {
    1: GapExercise(
        "I eat an ___ every morning.", ("apple",),
        "Apple — яблоко. Перед apple здесь стоит артикль an.",
    ),
    2: GapExercise(
        "The long train ___ took six hours.", ("journey",),
        "Journey — путешествие или поездка. Здесь речь о поездке на поезде.",
    ),
    3: GapExercise(
        "I practise English to ___ my pronunciation.", ("improve",),
        "Improve — улучшать. После to здесь нужна начальная форма глагола.",
    ),
    4: GapExercise(
        "We have ___ chairs for everyone.", ("enough",),
        "Enough — достаточно. Enough chairs означает «достаточно стульев».",
    ),
    5: GapExercise(
        "Reading before bed is a good ___.", ("habit",),
        "Habit — привычка. Чтение перед сном здесь названо хорошей привычкой.",
    ),
    6: GapExercise(
        "Be ___ when you cross the road.", ("careful",),
        "Careful — осторожный. Be careful означает «будь осторожен».",
    ),
    7: GapExercise(
        "I made a spelling ___ in this word.", ("mistake",),
        "Mistake — ошибка. A spelling mistake — ошибка в написании слова.",
    ),
    8: GapExercise(
        "Please ___ to close the door.", ("remember",),
        "Remember — помнить. Remember to close означает «не забудь закрыть».",
    ),
}


@dataclass
class Record:
    mistakes: int = 0
    next_due: datetime | None = None


@dataclass
class Learner:
    level: str = "A1"
    words: dict[int, Record] = field(default_factory=dict)
    reviewed: int = 0
    attempted: int = 0
    correct: int = 0
    daily_date: str | None = None


class DemoClient:
    """Temporary stand-in for the future HTTP learning client, per user."""

    def __init__(self) -> None:
        self.learners: dict[int, Learner] = {}

    def learner(self, user_id: int) -> Learner:
        return self.learners.setdefault(user_id, Learner())

    def review_words(self, user_id: int, *, difficult: bool = False) -> list[Word]:
        learner = self.learner(user_id)
        if difficult:
            return sorted(
                [w for w in WORDS if learner.words.get(w.id, Record()).mistakes > 0],
                key=lambda w: learner.words[w.id].mistakes,
                reverse=True,
            )
        now = datetime.now(UTC)
        return [
            w
            for w in WORDS
            if (due := learner.words.get(w.id, Record()).next_due) is None or due <= now
        ]

    def rate(self, user_id: int, word: Word, quality: int) -> datetime:
        intervals = {
            1: timedelta(minutes=10),
            3: timedelta(days=1),
            4: timedelta(days=3),
            5: timedelta(days=7),
        }
        if quality not in intervals:
            raise ValueError("Invalid review rating")
        learner = self.learner(user_id)
        record = learner.words.setdefault(word.id, Record())
        record.mistakes += quality == 1
        record.next_due = datetime.now(UTC) + intervals[quality]
        learner.reviewed += 1
        return record.next_due

    def quiz_words(self, user_id: int) -> list[Word]:
        # Include problem words first; fill the rest from a shuffled sample.
        difficult = self.review_words(user_id, difficult=True)
        rest = [w for w in WORDS if w not in difficult]
        random.shuffle(rest)
        return (difficult + rest)[:5]

    def record_answer(self, user_id: int, word: Word, correct: bool) -> None:
        learner = self.learner(user_id)
        learner.attempted += 1
        learner.correct += correct
        self.rate(user_id, word, 4 if correct else 1)

    def choices(self, word: Word) -> list[str]:
        options = random.sample([w.translation for w in WORDS if w.id != word.id], 3)
        options.append(word.translation)
        random.shuffle(options)
        return options

    def daily_words(self, user_id: int) -> list[Word]:
        due = self.review_words(user_id)
        difficult = self.review_words(user_id, difficult=True)
        candidates = list(dict.fromkeys(difficult + due + list(WORDS)))
        return candidates[:5]


@dataclass
class Flow:
    mode: str
    words: list[Word]
    position: int = 0
    correct: int = 0
    cards_reviewed: int = 0
    ticket: str = ""
    stage: str = ""
    options: list[str] = field(default_factory=list)

    @property
    def word(self) -> Word:
        return self.words[self.position]

    @property
    def is_card(self) -> bool:
        return self.mode in ("review", "difficult") or (
            self.mode == "daily" and self.position < 3
        )
