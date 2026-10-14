from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, CreatedAt, IntPK
from app.core.enums import PlanItemType, pg_enum


class LessonPlan(Base):
    __tablename__ = "lesson_plans"

    id: Mapped[IntPK]
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    rationale: Mapped[str]
    created_at: Mapped[CreatedAt]


class LessonPlanItem(Base):
    __tablename__ = "lesson_plan_items"
    __table_args__ = (
        UniqueConstraint("plan_id", "position"),
        # Ссылка заполнена ровно тогда, когда её требует тип пункта.
        CheckConstraint(
            "(type = 'topic' AND topic_id IS NOT NULL AND exercise_id IS NULL)"
            " OR (type = 'exercise' AND exercise_id IS NOT NULL AND topic_id IS NULL)"
            " OR (type IN ('word_review', 'dialog') AND topic_id IS NULL AND exercise_id IS NULL)",
            name="target_matches_type",
        ),
    )

    id: Mapped[IntPK]
    plan_id: Mapped[int] = mapped_column(ForeignKey("lesson_plans.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(Integer)
    type: Mapped[PlanItemType] = mapped_column(pg_enum(PlanItemType, "plan_item_type"))
    topic_id: Mapped[int | None] = mapped_column(ForeignKey("topics.id"))
    exercise_id: Mapped[int | None] = mapped_column(ForeignKey("exercises.id"))
    done_at: Mapped[datetime | None]
