"""Сценарии разговора с виртуальным носителем языка."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Scenario:
    code: str
    title: str
    description: str  # для ученика, по-русски
    prompt: str  # для модели, по-английски


SCENARIOS = {
    s.code: s
    for s in [
        Scenario(
            "intro",
            "Знакомство",
            "Расскажите о себе: откуда вы, чем занимаетесь, что любите.",
            "You meet the learner at an English-speaking club. Get to know each other: "
            "where they are from, what they do, their hobbies.",
        ),
        Scenario(
            "cafe",
            "В кафе",
            "Закажите напиток и что-нибудь поесть в кафе в Лондоне.",
            "You are a barista in a small café in London. The learner is a customer ordering "
            "drinks and food; ask about sizes, milk, eating in or taking away, payment.",
        ),
        Scenario(
            "airport",
            "В аэропорту",
            "Пройдите регистрацию на рейс: багаж, место, посадка.",
            "You are a check-in agent at Heathrow airport. Check the learner in for a flight: "
            "passport, luggage, seat preference, boarding time and gate.",
        ),
        Scenario(
            "interview",
            "Собеседование",
            "Пройдите короткое собеседование на стажировку.",
            "You interview the learner for a junior internship at an IT company. Ask about "
            "their studies, skills, a project they are proud of, and why they want the job.",
        ),
        Scenario(
            "free",
            "Свободная тема",
            "Поговорите о чём угодно — фильмах, учёбе, планах на выходные.",
            "Have a friendly casual chat about anything the learner wants: films, studies, "
            "weekend plans, travel.",
        ),
    ]
}
