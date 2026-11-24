"""Private word illustrations shared by the website and verified Telegram account."""

import io
import os
import re
import warnings
from pathlib import Path

from fastapi import HTTPException, Request
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.modules.vocabulary.models import UserWord, Word

MAX_UPLOAD = 5 * 1024 * 1024
MAX_PIXELS = 16_000_000


def normalize(data: bytes) -> bytes:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as source:
                if source.format not in ("JPEG", "PNG", "WEBP"):
                    raise ValueError("Unsupported image")
                if source.width * source.height > MAX_PIXELS:
                    raise ValueError("Image dimensions too large")
                source.load()
                image = ImageOps.exif_transpose(source).convert("RGBA")
                image.thumbnail((768, 768))
                background = Image.new("RGB", image.size, "white")
                background.paste(image, mask=image.getchannel("A"))
                output = io.BytesIO()
                background.save(output, format="JPEG", quality=85)
                return output.getvalue()
    except (
        UnidentifiedImageError,
        OSError,
        ValueError,
        Image.DecompressionBombWarning,
        Image.DecompressionBombError,
    ):
        raise HTTPException(422, "Нужна корректная картинка JPEG, PNG или WebP до 16 Мп.") from None


async def upload(session: AsyncSession, user_id: int, word_id: int, request: Request) -> None:
    row = await session.get(UserWord, (user_id, word_id))
    if row is None:
        raise HTTPException(404, "Слова нет в личном словаре.")
    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data) > MAX_UPLOAD:
            raise HTTPException(413, "Картинка должна быть не больше 5 МБ.")
    row.image_data = await run_in_threadpool(normalize, bytes(data))
    await session.commit()


async def read(session: AsyncSession, user_id: int, word_id: int) -> tuple[bytes, str]:
    row = (
        await session.execute(
            select(UserWord, Word)
            .join(Word, Word.id == UserWord.word_id)
            .where(UserWord.user_id == user_id, UserWord.word_id == word_id)
        )
    ).first()
    if row is None:
        raise HTTPException(404, "Слова нет в личном словаре.")
    user_word, word = row
    if user_word.image_data:
        return user_word.image_data, "image/jpeg"
    if not word.image_url or not re.fullmatch(
        r"/images/vocabulary/[a-z0-9][a-z0-9-]*\.svg", word.image_url
    ):
        raise HTTPException(404, "У слова нет картинки.")
    directory = Path(
        os.getenv(
            "WORD_IMAGES_DIR",
            str(Path(__file__).resolve().parents[4] / "frontend/public/images/vocabulary"),
        )
    )
    path = directory / word.image_url.rsplit("/", 1)[-1]
    if not path.is_file():
        raise HTTPException(404, "Картинка не найдена.")
    # Only repository-owned SVGs are rendered; uploaded SVG/XML is never accepted.
    import cairosvg

    rendered = await run_in_threadpool(
        cairosvg.svg2png, url=str(path), output_width=384, output_height=384
    )
    return rendered, "image/png"
