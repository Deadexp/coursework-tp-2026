from sqlalchemy import and_, func, literal, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.vocabulary.models import UserWord, Word
from app.modules.vocabulary.modules_models import ModuleWord, VocabularyModule
from app.modules.vocabulary.modules_schemas import VocabularyModuleDetail, VocabularyModuleRead
from app.modules.vocabulary.schemas import WordRead, WordSearchResult


async def list_modules(session: AsyncSession, user_id: int) -> list[VocabularyModuleRead]:
    cover = (
        select(Word.image_url)
        .join(ModuleWord, ModuleWord.word_id == Word.id)
        .where(ModuleWord.module_id == VocabularyModule.id, Word.image_url.is_not(None))
        .order_by(ModuleWord.position)
        .limit(1)
        .correlate(VocabularyModule)
        .scalar_subquery()
    )
    rows = await session.execute(
        select(
            VocabularyModule,
            func.count(ModuleWord.word_id),
            func.count(UserWord.word_id),
            cover,
        )
        .outerjoin(ModuleWord, ModuleWord.module_id == VocabularyModule.id)
        .outerjoin(
            UserWord,
            and_(UserWord.word_id == ModuleWord.word_id, UserWord.user_id == user_id),
        )
        .group_by(VocabularyModule.id)
        .order_by(VocabularyModule.position, VocabularyModule.id)
    )
    return [_module_read(module, total, added, image) for module, total, added, image in rows]


async def module_detail(
    session: AsyncSession, user_id: int, module_id: int
) -> VocabularyModuleDetail | None:
    module = await session.get(VocabularyModule, module_id)
    if module is None:
        return None
    rows = await session.execute(
        select(Word, UserWord.word_id.is_not(None))
        .join(ModuleWord, ModuleWord.word_id == Word.id)
        .outerjoin(UserWord, and_(UserWord.word_id == Word.id, UserWord.user_id == user_id))
        .where(ModuleWord.module_id == module_id)
        .order_by(ModuleWord.position, Word.id)
    )
    words = [
        WordSearchResult(**WordRead.model_validate(word).model_dump(), in_vocabulary=added)
        for word, added in rows
    ]
    summary = _module_read(
        module,
        len(words),
        sum(word.in_vocabulary for word in words),
        next((word.image_url for word in words if word.image_url), None),
    )
    return VocabularyModuleDetail(**summary.model_dump(), words=words)


async def add_module_words(session: AsyncSession, user_id: int, module_id: int) -> int | None:
    if await session.get(VocabularyModule, module_id) is None:
        return None
    # Defaults on UserWord start the existing SM-2 cycle. Already learned words
    # are never updated: their dates, intervals and reviews remain intact.
    result = await session.execute(
        insert(UserWord)
        .from_select(
            ["user_id", "word_id"],
            select(literal(user_id), ModuleWord.word_id).where(ModuleWord.module_id == module_id),
        )
        .on_conflict_do_nothing(index_elements=["user_id", "word_id"])
    )
    await session.commit()
    return result.rowcount


def _module_read(
    module: VocabularyModule, total: int, added: int, image_url: str | None
) -> VocabularyModuleRead:
    return VocabularyModuleRead(
        id=module.id,
        slug=module.slug,
        title=module.title,
        description=module.description,
        cefr_level=module.cefr_level,
        position=module.position,
        word_count=total,
        in_vocabulary_count=added,
        cover_image_url=image_url,
    )
