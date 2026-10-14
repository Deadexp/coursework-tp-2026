from httpx import AsyncClient

USER = {"email": "Anna@Example.com", "password": "secret-pass", "display_name": "Anna"}


async def register(client: AsyncClient, **overrides: str):
    return await client.post("/auth/register", json={**USER, **overrides})


async def login(client: AsyncClient, email: str, password: str):
    return await client.post("/auth/login", data={"username": email, "password": password})


async def test_register_returns_user_without_password(client: AsyncClient) -> None:
    response = await register(client)

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "anna@example.com"
    assert body["display_name"] == "Anna"
    assert body["cefr_level"] == "A1"
    assert "password" not in body and "password_hash" not in body


async def test_register_duplicate_email_is_case_insensitive(client: AsyncClient) -> None:
    await register(client)
    response = await register(client, email="ANNA@example.com")

    assert response.status_code == 409


async def test_register_rejects_short_password_and_bad_email(client: AsyncClient) -> None:
    assert (await register(client, password="short")).status_code == 422
    assert (await register(client, email="not-an-email")).status_code == 422


async def test_login_and_get_me(client: AsyncClient) -> None:
    await register(client)

    response = await login(client, "anna@example.com", "secret-pass")
    assert response.status_code == 200
    token = response.json()["access_token"]

    me = await client.get("/users/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email"] == "anna@example.com"


async def test_login_wrong_password_or_unknown_email(client: AsyncClient) -> None:
    await register(client)

    assert (await login(client, "anna@example.com", "wrong-pass")).status_code == 401
    assert (await login(client, "nobody@example.com", "secret-pass")).status_code == 401


async def test_me_requires_valid_token(client: AsyncClient) -> None:
    assert (await client.get("/users/me")).status_code == 401
    bad = await client.get("/users/me", headers={"Authorization": "Bearer garbage"})
    assert bad.status_code == 401
