from app.modules.learning.checking import is_correct, normalize, shuffled_words


def test_normalize_ignores_case_spaces_apostrophes_and_final_punctuation() -> None:
    assert normalize("  He  DOESN’T like  coffee. ") == "he doesn't like coffee"


def test_is_correct_accepts_any_listed_variant() -> None:
    assert is_correct("does not like", ["doesn't like", "does not like"])
    assert is_correct("The", ["the"])
    assert not is_correct("a", ["an"])
    assert not is_correct("doesn't likes", ["doesn't like"])


def test_shuffled_words_are_stable_and_actually_shuffled() -> None:
    sentence = "I usually get up at seven"
    first = shuffled_words(sentence, seed=42)

    assert first == shuffled_words(sentence, seed=42)
    assert sorted(first) == sorted(sentence.split())
    assert first != sentence.split()
