import asyncio
from datetime import UTC, date, datetime, time, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.modules.reminders import service
from app.modules.reminders.models import ReminderDelivery
from tests.test_telegram import TEST_SERVICE, bot_headers, connect, other_user

SERVICE_HEADERS = {"X-Service-Token": TEST_SERVICE}


@pytest.fixture(autouse=True)
def reminder_clock(monkeypatch):
    clock = [datetime(2030, 1, 2, 16, 0, tzinfo=UTC)]  # 19:00 Europe/Moscow
    monkeypatch.setattr(settings, "bot_service_token", TEST_SERVICE)
    monkeypatch.setattr(settings, "bot_username", "course_test_bot")
    monkeypatch.setattr(service, "utcnow", lambda: clock[0])
    return clock


async def enable(client, headers, **changes):
    await connect(client, headers)
    response = await client.patch(
        "/reminders/settings", headers=headers, json={"enabled": True, **changes}
    )
    assert response.status_code == 200
    return response.json()


async def claim(client, headers=SERVICE_HEADERS):
    return await client.post("/reminders/claims", headers=headers, json={"limit": 1})


async def acknowledge(client, delivery, outcome="sent", **extra):
    return await client.post(
        f"/reminders/deliveries/{delivery['delivery_id']}/ack",
        headers=SERVICE_HEADERS,
        json={"claim_token": delivery["claim_token"], "outcome": outcome, **extra},
    )


async def test_opt_in_defaults_link_requirement_and_user_isolation(client, auth_headers):
    assert (await client.get("/reminders/settings")).status_code == 401
    assert (await client.patch("/reminders/settings", json={"enabled": True})).status_code == 401
    default = {"enabled": False, "time": "19:00", "timezone": "Europe/Moscow"}
    assert (await client.get("/reminders/settings", headers=auth_headers)).json() == default
    assert (
        await client.patch("/reminders/settings", headers=auth_headers, json={"enabled": True})
    ).status_code == 409
    assert (await claim(client)).json() == []
    saved = await enable(client, auth_headers, time="08:30", timezone="Asia/Tokyo")
    assert saved == {"enabled": True, "time": "08:30", "timezone": "Asia/Tokyo"}
    assert (await client.get("/reminders/settings", headers=bot_headers())).json() == saved
    second = await other_user(client)
    assert (await client.get("/reminders/settings", headers=second)).json() == default
    assert (
        await client.get("/reminders/settings", headers=bot_headers(9000000002))
    ).status_code == 403


@pytest.mark.parametrize(
    "invalid",
    [
        {"time": "24:00"},
        {"time": "9:00"},
        {"time": "09:60"},
        {"time": None},
        {"enabled": "true"},
        {"timezone": "Mars/Olympus"},
        {"timezone": "../etc/passwd"},
        {"timezone": None},
        {"telegram_id": 123},
    ],
)
async def test_settings_validation(client, auth_headers, invalid):
    assert (
        await client.patch("/reminders/settings", headers=auth_headers, json=invalid)
    ).status_code == 422


async def test_worker_endpoints_require_service_auth(client, auth_headers):
    for headers in ({}, auth_headers, {"X-Telegram-ID": "9000000001"}):
        assert (await claim(client, headers)).status_code == 401
        assert (
            await client.post(
                "/reminders/deliveries/1/ack",
                headers=headers,
                json={"claim_token": str(uuid4()), "outcome": "sent"},
            )
        ).status_code == 401
    # A worker never accepts a caller-supplied recipient.
    assert (
        await client.post(
            "/reminders/claims", headers=SERVICE_HEADERS, json={"limit": 1, "telegram_id": 1}
        )
    ).status_code == 422


async def test_concurrent_claims_and_one_delivery_per_local_day(
    client, auth_headers, reminder_clock
):
    await enable(client, auth_headers)
    results = await asyncio.gather(claim(client), claim(client), claim(client))
    deliveries = [row for result in results for row in result.json()]
    assert len(deliveries) == 1
    delivery = deliveries[0]
    assert delivery["telegram_id"] == 9000000001
    assert (await claim(client)).json() == []
    assert (await acknowledge(client, delivery, telegram_message_id=123)).json() == {
        "status": "sent"
    }
    assert (await acknowledge(client, delivery, telegram_message_id=123)).status_code == 200
    assert (await claim(client)).json() == []
    reminder_clock[0] += timedelta(days=1)
    tomorrow = (await claim(client)).json()
    assert len(tomorrow) == 1 and tomorrow[0]["delivery_id"] != delivery["delivery_id"]


async def test_disabled_settings_revoke_queued_delivery(client, auth_headers, reminder_clock):
    await enable(client, auth_headers)
    delivery = (await claim(client)).json()[0]
    changed = await client.patch(
        "/reminders/settings", headers=bot_headers(), json={"enabled": False}
    )
    assert changed.json()["enabled"] is False
    assert (await acknowledge(client, delivery, "retry")).json() == {"status": "cancelled"}
    reminder_clock[0] += timedelta(days=1)
    assert (await claim(client)).json() == []


async def test_leases_retry_backoff_stale_tokens_and_attempt_limit(
    client, auth_headers, reminder_clock, db
):
    await enable(client, auth_headers)
    first = (await claim(client)).json()[0]
    assert (await acknowledge(client, first, "retry")).json() == {"status": "pending"}
    # Retried acknowledgement must not postpone the same attempt twice.
    assert (await acknowledge(client, first, "retry")).json() == {"status": "pending"}
    reminder_clock[0] += timedelta(seconds=59)
    assert (await claim(client)).json() == []
    reminder_clock[0] += timedelta(seconds=1)
    second = (await claim(client)).json()[0]
    assert second["claim_token"] != first["claim_token"]
    assert (await acknowledge(client, first)).status_code == 409
    # Simulate a worker crash with a lease, but no acknowledgement.
    reminder_clock[0] += service.LEASE + timedelta(seconds=1)
    third = (await claim(client)).json()[0]
    assert third["claim_token"] != second["claim_token"]
    assert (await acknowledge(client, second)).status_code == 409
    assert (await acknowledge(client, third, "retry")).json() == {"status": "failed"}
    reminder_clock[0] += timedelta(minutes=10)
    assert (await claim(client)).json() == []
    stored = await db.scalar(select(ReminderDelivery))
    assert stored.attempts == 3


async def test_forbidden_disables_reminders_and_is_idempotent(client, auth_headers, reminder_clock):
    await enable(client, auth_headers)
    delivery = (await claim(client)).json()[0]
    for _ in range(2):
        assert (await acknowledge(client, delivery, "forbidden")).json() == {"status": "failed"}
    assert (await client.get("/reminders/settings", headers=auth_headers)).json()[
        "enabled"
    ] is False
    reminder_clock[0] += timedelta(days=1)
    assert (await claim(client)).json() == []


async def test_inflight_forbidden_still_opts_out_after_schedule_change(client, auth_headers):
    await enable(client, auth_headers)
    delivery = (await claim(client)).json()[0]
    assert (
        await client.patch("/reminders/settings", headers=auth_headers, json={"time": "20:00"})
    ).status_code == 200
    assert (await acknowledge(client, delivery, "forbidden")).json() == {"status": "failed"}
    response = await client.get("/reminders/settings", headers=auth_headers)
    assert response.json()["enabled"] is False


async def test_successful_inflight_send_is_recorded_after_opt_out(client, auth_headers):
    await enable(client, auth_headers)
    delivery = (await claim(client)).json()[0]
    await client.patch("/reminders/settings", headers=auth_headers, json={"enabled": False})
    assert (await acknowledge(client, delivery, telegram_message_id=456)).json() == {
        "status": "sent"
    }
    response = await client.get("/reminders/settings", headers=auth_headers)
    assert response.json()["enabled"] is False


async def test_catch_up_window_timezone_and_no_old_backlog(client, auth_headers, reminder_clock):
    await enable(client, auth_headers, time="17:00", timezone="Europe/Berlin")
    reminder_clock[0] -= timedelta(seconds=1)
    assert (await claim(client)).json() == []
    reminder_clock[0] += timedelta(minutes=30)
    delivery = (await claim(client)).json()[0]
    assert delivery["scheduled_at"].startswith("2030-01-02T16:00:00")
    await acknowledge(client, delivery)
    reminder_clock[0] = datetime(2030, 1, 6, 17, 1, tzinfo=UTC)
    assert (await claim(client)).json() == []


async def test_catch_up_crosses_midnight_without_replaying_older_days(
    client, auth_headers, reminder_clock
):
    await enable(client, auth_headers, time="23:45", timezone="UTC")
    reminder_clock[0] = datetime(2030, 1, 3, 0, 10, tzinfo=UTC)
    delivery = (await claim(client)).json()[0]
    assert delivery["local_date"] == "2030-01-02"
    assert (await claim(client)).json() == []


def test_dst_missing_time_is_skipped_and_repeated_time_uses_first_occurrence():
    assert service.scheduled_at(date(2030, 3, 31), time(2, 30), "Europe/Berlin") is None
    assert service.scheduled_at(date(2030, 10, 27), time(2, 30), "Europe/Berlin") == datetime(
        2030, 10, 27, 0, 30, tzinfo=UTC
    )
