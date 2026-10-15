from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import MessageRole
from app.llm import LLMClient, Message
from app.modules.dialogs import prompts
from app.modules.dialogs.models import Dialog, DialogMessage
from app.modules.dialogs.scenarios import SCENARIOS
from app.modules.dialogs.schemas import (
    CorrectionRead,
    DialogFeedback,
    DialogMessageRead,
    DialogRead,
    DialogSummaryRead,
    ExchangeResult,
    SpeakerTurn,
)
from app.modules.learning import service as learning
from app.modules.learning.models import ErrorType, Mistake
from app.modules.learning.schemas import ErrorTypeRead
from app.modules.users.models import User

MAX_MESSAGES = 40  # ограничение длины диалога — защищает от лишних расходов на API
FALLBACK_ERROR_CODE = "vocabulary"  # если модель назвала тип ошибки, которого нет в БД


class ScenarioNotFoundError(Exception):
    pass


class DialogFinishedError(Exception):
    pass


class DialogTooLongError(Exception):
    pass


async def create_dialog(
    session: AsyncSession, llm: LLMClient, user: User, scenario_code: str
) -> DialogRead:
    scenario = SCENARIOS.get(scenario_code)
    if scenario is None:
        raise ScenarioNotFoundError
    error_types = await learning.list_error_types(session)
    system = prompts.speaker_system(scenario, user.cefr_level, _codes(error_types))

    # Сначала модель, потом запись: если ИИ недоступен, пустой диалог в БД не останется.
    opening = await llm.chat(system, [Message("user", prompts.OPENING_TRIGGER)])

    dialog = Dialog(user_id=user.id, scenario=scenario.code)
    session.add(dialog)
    await session.flush()
    session.add(
        DialogMessage(dialog_id=dialog.id, role=MessageRole.ASSISTANT, content=opening.strip())
    )
    await session.commit()
    return await get_dialog(session, user.id, dialog.id)


async def list_dialogs(session: AsyncSession, user_id: int) -> list[DialogSummaryRead]:
    rows = await session.execute(
        select(Dialog, func.count(DialogMessage.id))
        .outerjoin(DialogMessage, DialogMessage.dialog_id == Dialog.id)
        .where(Dialog.user_id == user_id)
        .group_by(Dialog.id)
        .order_by(Dialog.started_at.desc(), Dialog.id.desc())
    )
    return [
        DialogSummaryRead(
            id=d.id,
            scenario=d.scenario,
            title=_title(d.scenario),
            started_at=d.started_at,
            ended_at=d.ended_at,
            messages=n,
        )
        for d, n in rows
    ]


async def get_dialog(session: AsyncSession, user_id: int, dialog_id: int) -> DialogRead | None:
    dialog = await _owned(session, user_id, dialog_id)
    if dialog is None:
        return None
    messages = await _messages(session, dialog.id)
    corrections = await _corrections(session, [m.id for m in messages])
    return DialogRead(
        id=dialog.id,
        scenario=dialog.scenario,
        title=_title(dialog.scenario),
        started_at=dialog.started_at,
        ended_at=dialog.ended_at,
        summary=dialog.summary,
        messages=[_message_read(m, corrections.get(m.id, [])) for m in messages],
    )


async def send_message(
    session: AsyncSession, llm: LLMClient, user: User, dialog_id: int, content: str
) -> ExchangeResult | None:
    """Реплика ученика → ответ собеседника + найденные ошибки (записываются в mistakes)."""
    dialog = await _owned(session, user.id, dialog_id)
    if dialog is None:
        return None
    if dialog.ended_at is not None:
        raise DialogFinishedError
    history = await _messages(session, dialog.id)
    if len(history) + 2 > MAX_MESSAGES:
        raise DialogTooLongError

    error_types = await learning.list_error_types(session)
    system = prompts.speaker_system(
        SCENARIOS[dialog.scenario], user.cefr_level, _codes(error_types)
    )
    conversation = [Message("user", prompts.OPENING_TRIGGER)]
    conversation += [Message(m.role.value, m.content) for m in history]
    conversation.append(Message("user", content))

    turn = await llm.parse(system, conversation, SpeakerTurn)

    user_message = DialogMessage(dialog_id=dialog.id, role=MessageRole.USER, content=content)
    session.add(user_message)
    await session.flush()

    by_code = {et.code: et for et in error_types}
    saved: list[CorrectionRead] = []
    for c in turn.corrections:
        error_type = by_code.get(c.error_type) or by_code.get(FALLBACK_ERROR_CODE)
        if error_type is None or not c.fragment.strip() or c.fragment == c.correction:
            continue
        session.add(
            Mistake(
                dialog_message_id=user_message.id,
                error_type_id=error_type.id,
                fragment=c.fragment,
                correction=c.correction,
                explanation=c.explanation_ru,
            )
        )
        saved.append(
            CorrectionRead(
                fragment=c.fragment,
                correction=c.correction,
                explanation=c.explanation_ru,
                error_type=ErrorTypeRead(code=error_type.code, name=error_type.name),
            )
        )

    reply = DialogMessage(
        dialog_id=dialog.id, role=MessageRole.ASSISTANT, content=turn.reply.strip()
    )
    session.add(reply)
    await session.commit()
    return ExchangeResult(
        user_message=_message_read(user_message, saved), reply=_message_read(reply, [])
    )


async def finish_dialog(
    session: AsyncSession, llm: LLMClient, user: User, dialog_id: int
) -> DialogRead | None:
    """Завершает диалог и сохраняет отзыв наставника."""
    dialog = await _owned(session, user.id, dialog_id)
    if dialog is None:
        return None
    if dialog.ended_at is None:
        messages = await _messages(session, dialog.id)
        if any(m.role == MessageRole.USER for m in messages):
            corrections = await _corrections(session, [m.id for m in messages])
            feedback = await llm.parse(
                prompts.feedback_system(user.cefr_level),
                [Message("user", _transcript(messages, corrections))],
                DialogFeedback,
            )
            dialog.summary = _format_feedback(feedback)
        else:
            dialog.summary = "Разговор завершён без ваших реплик."
        dialog.ended_at = datetime.now(UTC)
        await session.commit()
    return await get_dialog(session, user.id, dialog.id)


def _title(code: str) -> str:
    scenario = SCENARIOS.get(code)
    return scenario.title if scenario else code


def _codes(error_types: list[ErrorType]) -> list[tuple[str, str]]:
    return [(et.code, et.name) for et in error_types]


async def _owned(session: AsyncSession, user_id: int, dialog_id: int) -> Dialog | None:
    return await session.scalar(
        select(Dialog).where(Dialog.id == dialog_id, Dialog.user_id == user_id)
    )


async def _messages(session: AsyncSession, dialog_id: int) -> list[DialogMessage]:
    return list(
        await session.scalars(
            select(DialogMessage)
            .where(DialogMessage.dialog_id == dialog_id)
            .order_by(DialogMessage.created_at, DialogMessage.id)
        )
    )


async def _corrections(
    session: AsyncSession, message_ids: list[int]
) -> dict[int, list[CorrectionRead]]:
    rows = await session.execute(
        select(Mistake, ErrorType)
        .join(ErrorType, ErrorType.id == Mistake.error_type_id)
        .where(Mistake.dialog_message_id.in_(message_ids))
        .order_by(Mistake.id)
    )
    result: dict[int, list[CorrectionRead]] = {}
    for mistake, error_type in rows:
        result.setdefault(mistake.dialog_message_id, []).append(
            CorrectionRead(
                fragment=mistake.fragment,
                correction=mistake.correction,
                explanation=mistake.explanation,
                error_type=ErrorTypeRead(code=error_type.code, name=error_type.name),
            )
        )
    return result


def _message_read(message: DialogMessage, corrections: list[CorrectionRead]) -> DialogMessageRead:
    return DialogMessageRead(
        id=message.id,
        role=message.role,
        content=message.content,
        created_at=message.created_at,
        corrections=corrections,
    )


def _transcript(messages: list[DialogMessage], corrections: dict[int, list[CorrectionRead]]) -> str:
    lines = []
    for m in messages:
        speaker = "Learner" if m.role == MessageRole.USER else "Emma"
        lines.append(f"{speaker}: {m.content}")
    found = [
        f"- {c.fragment} → {c.correction} ({c.error_type.name})"
        for m in messages
        for c in corrections.get(m.id, [])
    ]
    return (
        "Conversation:\n"
        + "\n".join(lines)
        + "\n\nMistakes found:\n"
        + ("\n".join(found) or "- none")
    )


def _format_feedback(feedback: DialogFeedback) -> str:
    parts = [feedback.summary_ru.strip()]
    if feedback.strengths_ru:
        parts.append("Получилось:\n" + "\n".join(f"• {s}" for s in feedback.strengths_ru))
    if feedback.to_improve_ru:
        parts.append("Над чем поработать:\n" + "\n".join(f"• {s}" for s in feedback.to_improve_ru))
    return "\n\n".join(parts)
