from fastapi import APIRouter, HTTPException, status

from app.core.db import SessionDep
from app.modules.learning import service
from app.modules.learning.schemas import AttemptCreate, AttemptResult, TopicDetail, TopicSummary
from app.modules.users.deps import CurrentUser

router = APIRouter(tags=["learning"])


@router.get("/topics")
async def list_topics(user: CurrentUser, session: SessionDep) -> list[TopicSummary]:
    return await service.list_topics(session, user.id)


@router.get("/topics/{topic_id}")
async def get_topic(topic_id: int, _: CurrentUser, session: SessionDep) -> TopicDetail:
    topic = await service.get_topic(session, topic_id)
    if topic is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Topic not found")
    return topic


@router.post("/exercises/{exercise_id}/attempts", status_code=status.HTTP_201_CREATED)
async def submit_attempt(
    exercise_id: int, data: AttemptCreate, user: CurrentUser, session: SessionDep
) -> AttemptResult:
    result = await service.submit_attempt(session, user.id, exercise_id, data)
    if result is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Exercise not found")
    return result
