from collections import defaultdict
from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import CefrLevel
from app.modules.placement.content import load_content
from app.modules.placement.models import (
    PlacementAnswer,
    PlacementAttempt,
    PlacementOption,
    PlacementQuestion,
)
from app.modules.placement.schemas import (
    AnswerFeedback,
    AttemptRead,
    LevelScore,
    PlacementLevel,
    PlacementResult,
    QuestionRead,
    SubmitInput,
)
from app.modules.users import service as users

LEVELS: tuple[PlacementLevel, ...] = ("A1", "A2", "B1")
LIMITATIONS = (
    "Это авторский учебный тест для выбора стартовых материалов A1–B1, "
    "а не сертификация CEFR. Он проверяет отдельные навыки грамматики, лексики "
    "и чтения; говорение, аудирование и развёрнутое письмо не оцениваются. "
    "Результат приблизительный: пороги не проходили независимую валидацию, "
    "а повторение знакомых вопросов может повысить балл. Уровни выше B1 не проверяются."
)


async def _owned_attempt(
    session: AsyncSession, user_id: int, attempt_id: int, *, lock: bool = False
) -> PlacementAttempt:
    stmt = select(PlacementAttempt).where(
        PlacementAttempt.id == attempt_id, PlacementAttempt.user_id == user_id
    )
    if lock:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    attempt = await session.scalar(stmt)
    if attempt is None:
        raise HTTPException(404, "Диагностический тест не найден.")
    return attempt


def _result(
    attempt: PlacementAttempt,
    questions: list[PlacementQuestion],
    options: dict[int, list[PlacementOption]],
    answers: dict[int, int],
) -> PlacementResult:
    feedback = []
    counts = dict.fromkeys(LEVELS, 0)
    totals = dict.fromkeys(LEVELS, 0)
    for question in questions:
        right = next(option.position for option in options[question.id] if option.is_correct)
        chosen = answers[question.id]
        ok = chosen == right
        counts[question.level] += int(ok)
        totals[question.level] += 1
        feedback.append(
            AnswerFeedback(
                question_id=str(question.id),
                option_index=chosen,
                correct_option_index=right,
                is_correct=ok,
                explanation=question.explanation,
            )
        )

    recommended: PlacementLevel = "A1"
    for level in LEVELS:
        if counts[level] < attempt.pass_mark:
            break
        recommended = level
    threshold = f"{attempt.pass_mark} из 8"
    if counts["A1"] < attempt.pass_mark:
        summary = (
            "Начните с базовых материалов A1: в первом блоке пока не достигнут "
            f"порог {threshold}. Это не подтверждение владения уровнем A1."
        )
    elif recommended == "B1":
        summary = (
            f"Можно начать с материалов B1: во всех трёх блоках набрано не менее {threshold}. "
            "B1 — верхняя граница этого теста."
        )
    else:
        summary = (
            f"Рекомендуем начать с материалов {recommended}. Порог {threshold} достигнут "
            "в соответствующем и всех предыдущих блоках. Повторите ошибки перед переходом дальше."
        )
    return PlacementResult(
        recommended_level=recommended,
        correct=sum(counts.values()),
        total=len(questions),
        scores=[
            LevelScore(level=level, correct=counts[level], total=totals[level]) for level in LEVELS
        ],
        summary=summary,
        limitations=LIMITATIONS,
        answers=feedback,
    )


async def _read_many(
    session: AsyncSession,
    attempts: list[PlacementAttempt],
    *,
    include_questions: bool = True,
) -> list[AttemptRead]:
    if not attempts:
        return []
    ids = [attempt.id for attempt in attempts]
    questions = list(
        await session.scalars(
            select(PlacementQuestion)
            .where(PlacementQuestion.attempt_id.in_(ids))
            .order_by(PlacementQuestion.position)
        )
    )
    by_attempt: dict[int, list[PlacementQuestion]] = defaultdict(list)
    for question in questions:
        by_attempt[question.attempt_id].append(question)
    options: dict[int, list[PlacementOption]] = defaultdict(list)
    for option in await session.scalars(
        select(PlacementOption)
        .join(PlacementQuestion, PlacementQuestion.id == PlacementOption.question_id)
        .where(PlacementQuestion.attempt_id.in_(ids))
        .order_by(PlacementOption.position)
    ):
        options[option.question_id].append(option)
    answers = {
        answer.question_id: answer.option_index
        for answer in await session.scalars(
            select(PlacementAnswer)
            .join(PlacementQuestion, PlacementQuestion.id == PlacementAnswer.question_id)
            .where(PlacementQuestion.attempt_id.in_(ids))
        )
    }
    reads = []
    for attempt in attempts:
        assigned = by_attempt[attempt.id]
        reads.append(
            AttemptRead(
                id=attempt.id,
                version=attempt.version,
                status="completed" if attempt.submitted_at else "in_progress",
                started_at=attempt.started_at,
                submitted_at=attempt.submitted_at,
                applied_at=attempt.applied_at,
                total=len(assigned),
                questions=[
                    QuestionRead(
                        id=str(q.id),
                        position=q.position,
                        level=q.level,
                        skill=q.skill,
                        prompt=q.prompt,
                        passage=q.passage,
                        options=[o.text for o in options[q.id]],
                    )
                    for q in assigned
                ]
                if include_questions
                else [],
                result=_result(attempt, assigned, options, answers)
                if attempt.submitted_at
                else None,
            )
        )
    return reads


async def start(session: AsyncSession, user_id: int) -> AttemptRead:
    content = load_content()
    attempt = PlacementAttempt(
        user_id=user_id, version=content.version, pass_mark=content.pass_mark
    )
    session.add(attempt)
    await session.flush()
    questions = [
        PlacementQuestion(
            attempt_id=attempt.id,
            code=item.id,
            position=item.position,
            level=item.level,
            skill=item.skill,
            prompt=item.prompt,
            passage=item.passage,
            explanation=item.explanation,
        )
        for item in content.questions
    ]
    session.add_all(questions)
    await session.flush()
    session.add_all(
        PlacementOption(
            question_id=question.id,
            position=index,
            text=option,
            is_correct=index == item.correct_option_index,
        )
        for question, item in zip(questions, content.questions, strict=True)
        for index, option in enumerate(item.options)
    )
    await session.commit()
    return (await _read_many(session, [attempt]))[0]


async def read(session: AsyncSession, user_id: int, attempt_id: int) -> AttemptRead:
    attempt = await _owned_attempt(session, user_id, attempt_id)
    return (await _read_many(session, [attempt]))[0]


async def history(session: AsyncSession, user_id: int, limit: int) -> list[AttemptRead]:
    attempts = list(
        await session.scalars(
            select(PlacementAttempt)
            .where(PlacementAttempt.user_id == user_id)
            .order_by(PlacementAttempt.started_at.desc(), PlacementAttempt.id.desc())
            .limit(limit)
        )
    )
    return await _read_many(session, attempts, include_questions=False)


async def submit(
    session: AsyncSession, user_id: int, attempt_id: int, data: SubmitInput
) -> AttemptRead:
    attempt = await _owned_attempt(session, user_id, attempt_id, lock=True)
    questions = list(
        await session.scalars(
            select(PlacementQuestion).where(PlacementQuestion.attempt_id == attempt.id)
        )
    )
    given = {answer.question_id: answer.option_index for answer in data.answers}
    if set(given) != {str(question.id) for question in questions}:
        raise HTTPException(422, "Нужен один ответ на каждый вопрос именно этого теста.")
    if attempt.submitted_at is not None:
        stored = {
            str(question_id): index
            for question_id, index in await session.execute(
                select(PlacementQuestion.id, PlacementAnswer.option_index)
                .join(PlacementAnswer, PlacementAnswer.question_id == PlacementQuestion.id)
                .where(PlacementQuestion.attempt_id == attempt.id)
            )
        }
        if stored != given:
            raise HTTPException(409, "Тест уже сдан. Для других ответов начните новый тест.")
    else:
        session.add_all(
            PlacementAnswer(question_id=question.id, option_index=given[str(question.id)])
            for question in questions
        )
        attempt.submitted_at = datetime.now(UTC)
        await session.commit()
    return (await _read_many(session, [attempt]))[0]


async def apply(session: AsyncSession, user_id: int, attempt_id: int) -> AttemptRead:
    attempt = await _owned_attempt(session, user_id, attempt_id, lock=True)
    if attempt.submitted_at is None:
        raise HTTPException(409, "Сначала завершите диагностический тест.")
    state = (await _read_many(session, [attempt]))[0]
    if attempt.applied_at is None:
        await users.set_level(
            session, user_id, CefrLevel(state.result.recommended_level), commit=False
        )
        attempt.applied_at = datetime.now(UTC)
        await session.commit()
        state.applied_at = attempt.applied_at
    return state
