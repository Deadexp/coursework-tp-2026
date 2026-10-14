"""Проверка ответов на упражнения. Чистые функции без БД — легко тестировать."""

import random
import re

_APOSTROPHES = str.maketrans({"’": "'", "‘": "'", "`": "'"})


def normalize(text: str) -> str:
    """Регистр, лишние пробелы, «умные» апострофы и точка в конце не влияют на проверку."""
    text = text.translate(_APOSTROPHES).lower()
    text = re.sub(r"\s+", " ", text).strip()
    return text.rstrip(".!?").rstrip()


def is_correct(answer: str, correct_answers: list[str]) -> bool:
    given = normalize(answer)
    return any(given == normalize(c) for c in correct_answers)


def shuffled_words(sentence: str, seed: int) -> list[str]:
    """Слова для упражнения «собери предложение»: перемешаны, но одинаково при каждом запросе."""
    words = sentence.split()
    shuffled = words[:]
    random.Random(seed).shuffle(shuffled)
    if shuffled == words and len(words) > 1:
        shuffled = shuffled[1:] + shuffled[:1]
    return shuffled
