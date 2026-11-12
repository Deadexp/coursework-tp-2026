from pydantic import BaseModel, Field

from app.core.enums import CefrLevel
from app.modules.vocabulary.schemas import LOCAL_IMAGE_PATTERN, WordSearchResult


class VocabularyModuleRead(BaseModel):
    id: int
    slug: str
    title: str
    description: str
    cefr_level: CefrLevel
    position: int
    word_count: int
    in_vocabulary_count: int
    cover_image_url: str | None = Field(default=None, pattern=LOCAL_IMAGE_PATTERN)


class VocabularyModuleDetail(VocabularyModuleRead):
    words: list[WordSearchResult]
