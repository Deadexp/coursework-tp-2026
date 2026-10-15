import json
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import PlanItemType
from app.llm import LLMClient, LLMError, Message
from app.modules.learning import service as learning
from app.modules.learning.models import Topic
from app.modules.recommendations.models import LessonPlan, LessonPlanItem
from app.modules.recommendations.prompts import MENTOR_SYSTEM
from app.modules.recommendations.schemas import MentorPlan, PlanItemRead, PlanRead
from app.modules.users.models import User
from app.modules.vocabulary import service as vocabulary

MAX_STEPS = 6
STEP_TITLES = {
    PlanItemType.WORD_REVIEW: "Повторить слова",
    PlanItemType.DIALOG: "Поговорить с собеседником",
}


async def learner_context(session: AsyncSession, user: User) -> dict:
    """Всё, что наставник знает об ученике: уровень, прогресс, ошибки, словарь."""
    topics = await learning.list_topics(session, user.id)
    weak = await learning.weak_spots(session, user.id)
    problems = await vocabulary.problem_words(session, user.id, days=30, limit=5)
    return {
        "level": user.cefr_level,
        "topics": [
            {
                "id": t.id,
                "title": t.title,
                "level": t.cefr_level,
                "solved": f"{t.exercises_solved}/{t.exercises_total}",
            }
            for t in topics
        ],
        "weak_spots_last_14_days": [
            {
                "skill": w.name,
                "mistakes": w.mistakes,
                "topic_id": w.topic_id,
                "examples": w.examples,
            }
            for w in weak
        ],
        "words_due_today": await vocabulary.count_due(session, user.id),
        "hard_words": [p.word.text for p in problems],
    }


async def create_plan(session: AsyncSession, llm: LLMClient, user: User) -> PlanRead:
    context = await learner_context(session, user)
    plan = await llm.parse(
        MENTOR_SYSTEM,
        [Message("user", "Learner data:\n" + json.dumps(context, ensure_ascii=False, indent=2))],
        MentorPlan,
    )

    # Модели доверяем выбор, но не ссылки: несуществующие темы и повторы отбрасываем.
    topic_ids = {t["id"] for t in context["topics"]}
    steps, seen = [], set()
    for step in plan.steps:
        key = (step.type, step.topic_id if step.type == "topic" else None)
        if key in seen or (step.type == "topic" and step.topic_id not in topic_ids):
            continue
        seen.add(key)
        steps.append(step)
    if not steps:
        raise LLMError("Наставник не смог составить план, попробуйте ещё раз")

    lesson_plan = LessonPlan(user_id=user.id, rationale=plan.summary_ru.strip())
    session.add(lesson_plan)
    await session.flush()
    for position, step in enumerate(steps[:MAX_STEPS], start=1):
        session.add(
            LessonPlanItem(
                plan_id=lesson_plan.id,
                position=position,
                type=PlanItemType(step.type),
                topic_id=step.topic_id if step.type == "topic" else None,
                reason=step.reason_ru,
            )
        )
    await session.commit()
    return await latest_plan(session, user.id)


async def latest_plan(session: AsyncSession, user_id: int) -> PlanRead | None:
    plan = await session.scalar(
        select(LessonPlan)
        .where(LessonPlan.user_id == user_id)
        .order_by(LessonPlan.created_at.desc(), LessonPlan.id.desc())
        .limit(1)
    )
    if plan is None:
        return None
    rows = await session.execute(
        select(LessonPlanItem, Topic.title)
        .outerjoin(Topic, Topic.id == LessonPlanItem.topic_id)
        .where(LessonPlanItem.plan_id == plan.id)
        .order_by(LessonPlanItem.position)
    )
    return PlanRead(
        id=plan.id,
        summary=plan.rationale,
        created_at=plan.created_at,
        items=[_item_read(item, title) for item, title in rows],
    )


async def mark_done(session: AsyncSession, user_id: int, item_id: int) -> PlanItemRead | None:
    row = (
        await session.execute(
            select(LessonPlanItem, Topic.title)
            .join(LessonPlan, LessonPlan.id == LessonPlanItem.plan_id)
            .outerjoin(Topic, Topic.id == LessonPlanItem.topic_id)
            .where(LessonPlanItem.id == item_id, LessonPlan.user_id == user_id)
        )
    ).first()
    if row is None:
        return None
    item, title = row
    if item.done_at is None:
        item.done_at = datetime.now(UTC)
        await session.commit()
    return _item_read(item, title)


def _item_read(item: LessonPlanItem, topic_title: str | None) -> PlanItemRead:
    return PlanItemRead(
        id=item.id,
        position=item.position,
        type=item.type,
        topic_id=item.topic_id,
        title=topic_title or STEP_TITLES.get(item.type, item.type.value),
        reason=item.reason,
        done=item.done_at is not None,
    )
