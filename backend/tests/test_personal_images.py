import io

from PIL import Image

from app.modules.vocabulary.models import Word
from tests.test_telegram import bot_headers, connect, other_user, telegram_settings  # noqa: F401


def picture(color="red"):
    stream = io.BytesIO()
    Image.new("RGB", (30, 20), color).save(stream, format="PNG")
    return stream.getvalue()


async def own_word(client, headers):
    response = await client.post(
        "/vocabulary", headers=headers, json={"text": "bridge", "translation": "мост"}
    )
    assert response.status_code == 201
    return response.json()["word"]["id"]


async def test_image_uploaded_on_web_is_available_to_verified_bot_and_back(
    client,
    auth_headers,
):
    word_id = await own_word(client, auth_headers)
    await connect(client, auth_headers)
    path = f"/vocabulary/{word_id}/image"
    assert (await client.put(path, headers=auth_headers, content=picture())).status_code == 204
    web = await client.get(path, headers=auth_headers)
    bot = await client.get(path, headers=bot_headers())
    assert web.status_code == bot.status_code == 200
    assert web.content == bot.content
    assert web.headers["content-type"] == "image/jpeg"
    assert web.headers["cache-control"] == "private, no-store"
    Image.open(io.BytesIO(web.content)).verify()
    old_url = (await client.get("/vocabulary", headers=auth_headers)).json()[0]["word"]["image_url"]
    assert (
        await client.put(path, headers=bot_headers(), content=picture("blue"))
    ).status_code == 204
    new_url = (await client.get("/vocabulary", headers=auth_headers)).json()[0]["word"]["image_url"]
    assert old_url != new_url
    assert (await client.get(path, headers=auth_headers)).content != web.content
    page = (await client.get("/vocabulary/page", headers=bot_headers())).json()
    assert page["items"][0]["word"]["image_url"] == new_url
    cards = (await client.get("/vocabulary/review", headers=bot_headers())).json()
    assert cards[0]["word"]["image_url"] == new_url


async def test_image_is_private_even_when_two_users_share_same_word(client, auth_headers):
    word_id = await own_word(client, auth_headers)
    path = f"/vocabulary/{word_id}/image"
    await client.put(path, headers=auth_headers, content=picture())
    second = await other_user(client)
    assert (await client.get(path)).status_code == 401
    assert (await client.get(path, headers=second)).status_code == 404
    assert (await client.put(path, headers=second, content=picture())).status_code == 404
    await client.post("/vocabulary", headers=second, json={"word_id": word_id})
    assert (await client.get(path, headers=second)).status_code == 404
    assert (await client.put(path, headers=second, content=picture("blue"))).status_code == 204
    assert (await client.get(path, headers=second)).content != (
        await client.get(path, headers=auth_headers)
    ).content


async def test_bad_images_and_oversized_payload_do_not_replace_saved_picture(client, auth_headers):
    word_id = await own_word(client, auth_headers)
    path = f"/vocabulary/{word_id}/image"
    await client.put(path, headers=auth_headers, content=picture())
    before = (await client.get(path, headers=auth_headers)).content
    for data, status in [
        (b"not an image", 422),
        (b'<svg xmlns="http://www.w3.org/2000/svg"/>', 422),
        (b"x" * (5 * 1024 * 1024 + 1), 413),
    ]:
        assert (await client.put(path, headers=auth_headers, content=data)).status_code == status
        assert (await client.get(path, headers=auth_headers)).content == before


async def test_future_cards_can_be_repeated_without_changing_due_selection(client, auth_headers):
    word_id = await own_word(client, auth_headers)
    await client.post(
        f"/vocabulary/{word_id}/reviews",
        headers=auth_headers,
        json={"quality": 5, "source": "web"},
    )
    assert (await client.get("/vocabulary/review", headers=auth_headers)).json() == []
    response = await client.get(
        "/vocabulary/review", params={"include_future": True}, headers=auth_headers
    )
    assert response.status_code == 200
    assert response.json()[0]["word"]["id"] == word_id
    assert (await client.get("/vocabulary/review", headers=auth_headers)).json() == []


async def test_builtin_svg_is_rendered_as_png_for_telegram(client, auth_headers, db):
    word_id = await own_word(client, auth_headers)
    word = await db.get(Word, word_id)
    word.image_url = "/images/vocabulary/apple.svg"
    await db.commit()
    response = await client.get(f"/vocabulary/{word_id}/image", headers=auth_headers)
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.content.startswith(b"\x89PNG")
