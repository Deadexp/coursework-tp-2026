"""Загрузка учебного контента из content/course.json в БД.

Запуск: docker compose run --rm api python -m app.seed

Повторный запуск безопасен: записи находятся по естественным ключам (название темы,
код ошибки, слово+часть речи+перевод, тема+текст задания) и обновляются, а не дублируются.
Упражнения, удалённые из файла, в БД остаются — на них могут ссылаться ответы пользователей.
"""

import asyncio
import json
from pathlib import Path

from pydantic import BaseModel, Field, model_validator
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import SessionLocal
from app.core.enums import CefrLevel, ExerciseType
from app.modules.learning.models import ErrorType, Exercise, ExerciseAnswer, Topic
from app.modules.vocabulary.models import TopicWord, Word
from app.modules.vocabulary.modules_models import ModuleWord, VocabularyModule
from app.modules.vocabulary.schemas import LOCAL_IMAGE_PATTERN

CONTENT_FILE = Path(__file__).resolve().parents[1] / "content" / "course.json"
MODULES_FILE = CONTENT_FILE.with_name("vocabulary_modules.json")


class ErrorTypeIn(BaseModel):
    code: str
    name: str
    topic: str | None


class WordIn(BaseModel):
    text: str
    part_of_speech: str
    translation: str
    transcription: str | None = None
    example: str | None = None
    image_url: str | None = Field(default=None, pattern=LOCAL_IMAGE_PATTERN)


class ExerciseIn(BaseModel):
    type: ExerciseType
    prompt: str
    correct: list[str]
    options: list[str] | None = None
    explanation: str | None = None
    error_type: str | None = None  # по умолчанию — тип ошибки, привязанный к теме

    @model_validator(mode="after")
    def check_answers(self) -> "ExerciseIn":
        if not self.correct:
            raise ValueError(f"{self.prompt!r}: нужен хотя бы один правильный ответ")
        if self.type == ExerciseType.MULTIPLE_CHOICE:
            if not self.options or not set(self.correct) <= set(self.options):
                raise ValueError(f"{self.prompt!r}: правильный ответ должен быть среди options")
        elif self.options:
            raise ValueError(f"{self.prompt!r}: options бывают только у multiple_choice")
        return self


class TopicIn(BaseModel):
    title: str
    cefr_level: CefrLevel
    position: int
    theory: str
    words: list[WordIn] = []
    exercises: list[ExerciseIn] = []


class Course(BaseModel):
    error_types: list[ErrorTypeIn]
    topics: list[TopicIn]

    @model_validator(mode="after")
    def check_references(self) -> "Course":
        titles = {t.title for t in self.topics}
        codes = {e.code for e in self.error_types}
        if len(titles) != len(self.topics) or len(codes) != len(self.error_types):
            raise ValueError("Названия тем и коды ошибок должны быть уникальными")
        if len({t.position for t in self.topics}) != len(self.topics):
            raise ValueError("Позиции тем должны быть уникальными")
        for et in self.error_types:
            if et.topic is not None and et.topic not in titles:
                raise ValueError(f"Тип ошибки {et.code!r} ссылается на несуществующую тему")
        for topic in self.topics:
            if len({ex.prompt for ex in topic.exercises}) != len(topic.exercises):
                raise ValueError(f"{topic.title!r}: задания должны иметь разные формулировки")
            for ex in topic.exercises:
                if ex.error_type is not None and ex.error_type not in codes:
                    raise ValueError(f"{ex.prompt!r}: неизвестный тип ошибки {ex.error_type!r}")
        return self


class VocabularyModuleIn(BaseModel):
    slug: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    cefr_level: CefrLevel
    position: int = Field(gt=0)
    words: list[WordIn] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_words(self) -> "VocabularyModuleIn":
        keys = {(w.text, w.part_of_speech, w.translation) for w in self.words}
        if len(keys) != len(self.words):
            raise ValueError(f"{self.slug!r}: слово повторяется внутри модуля")
        return self


class VocabularyModules(BaseModel):
    modules: list[VocabularyModuleIn]

    @model_validator(mode="after")
    def unique_modules(self) -> "VocabularyModules":
        if len({m.slug for m in self.modules}) != len(self.modules):
            raise ValueError("Slug модуля должен быть уникальным")
        if len({m.position for m in self.modules}) != len(self.modules):
            raise ValueError("Позиция модуля должна быть уникальной")
        return self


def load_course(path: Path = CONTENT_FILE) -> Course:
    return Course.model_validate(json.loads(path.read_text(encoding="utf-8")))


def load_vocabulary_modules(path: Path = MODULES_FILE) -> VocabularyModules:
    return VocabularyModules.model_validate(json.loads(path.read_text(encoding="utf-8")))


async def seed(
    session: AsyncSession, course: Course, modules: VocabularyModules | None = None
) -> None:
    topics = {t.title: await _upsert_topic(session, t) for t in course.topics}
    await session.flush()

    error_types: dict[str, ErrorType] = {}
    for et in course.error_types:
        error_types[et.code] = await _upsert_error_type(
            session, et, topics[et.topic].id if et.topic else None
        )
    await session.flush()
    topic_error_type = {
        et.topic: error_types[et.code] for et in course.error_types if et.topic is not None
    }

    for topic_in in course.topics:
        topic = topics[topic_in.title]
        for word_in in topic_in.words:
            word = await _upsert_word(session, word_in)
            await session.flush()
            await session.merge(TopicWord(topic_id=topic.id, word_id=word.id))
        for ex_in in topic_in.exercises:
            error_type = (
                error_types[ex_in.error_type]
                if ex_in.error_type
                else topic_error_type.get(topic_in.title)
            )
            await _upsert_exercise(session, topic.id, ex_in, error_type)

    if modules is not None:
        await _seed_modules(session, modules)
    await session.commit()


async def _upsert_topic(session: AsyncSession, data: TopicIn) -> Topic:
    topic = await session.scalar(select(Topic).where(Topic.title == data.title))
    if topic is None:
        topic = Topic(title=data.title)
        session.add(topic)
    topic.cefr_level = data.cefr_level
    topic.position = data.position
    topic.theory = data.theory
    return topic


async def _upsert_error_type(
    session: AsyncSession, data: ErrorTypeIn, topic_id: int | None
) -> ErrorType:
    error_type = await session.scalar(select(ErrorType).where(ErrorType.code == data.code))
    if error_type is None:
        error_type = ErrorType(code=data.code)
        session.add(error_type)
    error_type.name = data.name
    error_type.topic_id = topic_id
    return error_type


async def _upsert_word(session: AsyncSession, data: WordIn) -> Word:
    word = await session.scalar(
        select(Word).where(
            Word.text == data.text,
            Word.part_of_speech == data.part_of_speech,
            Word.translation == data.translation,
        )
    )
    if word is None:
        word = Word(
            text=data.text, part_of_speech=data.part_of_speech, translation=data.translation
        )
        session.add(word)
    word.transcription = data.transcription
    word.example = data.example
    # A course-only refresh must not erase an illustration supplied by a module.
    if "image_url" in data.model_fields_set:
        word.image_url = data.image_url
    return word


async def _seed_modules(session: AsyncSession, data: VocabularyModules) -> None:
    for module_in in data.modules:
        module = await session.scalar(
            select(VocabularyModule).where(VocabularyModule.slug == module_in.slug)
        )
        if module is None:
            module = VocabularyModule(slug=module_in.slug)
            session.add(module)
        module.title = module_in.title
        module.description = module_in.description
        module.cefr_level = module_in.cefr_level
        module.position = module_in.position
        await session.flush()

        # These are catalog memberships, not study history. Replacing them allows
        # card reordering while preserving Word IDs, UserWords and WordReviews.
        await session.execute(delete(ModuleWord).where(ModuleWord.module_id == module.id))
        for position, word_in in enumerate(module_in.words, start=1):
            word = await _upsert_word(session, word_in)
            await session.flush()
            session.add(ModuleWord(module_id=module.id, word_id=word.id, position=position))


async def _upsert_exercise(
    session: AsyncSession, topic_id: int, data: ExerciseIn, error_type: ErrorType | None
) -> None:
    exercise = await session.scalar(
        select(Exercise).where(Exercise.topic_id == topic_id, Exercise.prompt == data.prompt)
    )
    if exercise is None:
        exercise = Exercise(topic_id=topic_id, prompt=data.prompt)
        session.add(exercise)
    exercise.type = data.type
    exercise.explanation = data.explanation
    exercise.error_type_id = error_type.id if error_type else None
    await session.flush()

    # Варианты ответа пересоздаём целиком: на них никто не ссылается.
    await session.execute(delete(ExerciseAnswer).where(ExerciseAnswer.exercise_id == exercise.id))
    if data.type == ExerciseType.MULTIPLE_CHOICE:
        answers = [(text, text in data.correct) for text in data.options or []]
    else:
        answers = [(text, True) for text in data.correct]
    session.add_all(
        ExerciseAnswer(exercise_id=exercise.id, text=text, is_correct=ok) for text, ok in answers
    )


async def main() -> None:
    course = load_course()
    modules = load_vocabulary_modules()
    async with SessionLocal() as session:
        await seed(session, course, modules)
    exercises = sum(len(t.exercises) for t in course.topics)
    words = sum(len(t.words) for t in course.topics)
    cards = sum(len(m.words) for m in modules.modules)
    print(
        f"Загружено: тем {len(course.topics)}, упражнений {exercises}, слов курса {words}; "
        f"словарных модулей {len(modules.modules)}, карточек {cards}"
    )


if __name__ == "__main__":
    asyncio.run(main())
