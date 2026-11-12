from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, status

from app.core.db import SessionDep
from app.modules.users.telegram_auth import VocabularyUser
from app.modules.vocabulary import modules_service
from app.modules.vocabulary.modules_schemas import VocabularyModuleDetail, VocabularyModuleRead
from app.modules.vocabulary.schemas import AddedCount

router = APIRouter(prefix="/vocabulary/modules", tags=["vocabulary modules"])
ModuleId = Annotated[int, Path(gt=0)]


@router.get("")
async def list_modules(user: VocabularyUser, session: SessionDep) -> list[VocabularyModuleRead]:
    return await modules_service.list_modules(session, user.id)


@router.get("/{module_id}")
async def module_detail(
    module_id: ModuleId, user: VocabularyUser, session: SessionDep
) -> VocabularyModuleDetail:
    module = await modules_service.module_detail(session, user.id, module_id)
    if module is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Vocabulary module not found")
    return module


@router.post("/{module_id}/add")
async def add_module_words(
    module_id: ModuleId, user: VocabularyUser, session: SessionDep
) -> AddedCount:
    added = await modules_service.add_module_words(session, user.id, module_id)
    if added is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Vocabulary module not found")
    return AddedCount(added=added)
