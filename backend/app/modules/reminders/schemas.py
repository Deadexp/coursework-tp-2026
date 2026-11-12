from datetime import date, datetime
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator

TIME_PATTERN = r"^(?:[01][0-9]|2[0-3]):[0-5][0-9]$"


class SettingsRead(BaseModel):
    enabled: bool
    time: str
    timezone: str


class SettingsPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool | None = Field(default=None, strict=True)
    time: str | None = Field(default=None, pattern=TIME_PATTERN)
    timezone: str | None = Field(default=None, min_length=1, max_length=100)

    @field_validator("enabled", "time", "timezone", mode="before")
    @classmethod
    def reject_null(cls, value):
        if value is None:
            raise ValueError("Поле не может быть null")
        return value

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("Укажите часовой пояс IANA, например Europe/Moscow") from None
        return value


class ClaimRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    limit: int = Field(default=1, ge=1, le=20, strict=True)


class ClaimRead(BaseModel):
    delivery_id: int
    claim_token: UUID
    telegram_id: int
    local_date: date
    scheduled_at: datetime


class Acknowledge(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_token: UUID
    outcome: Literal["sent", "retry", "forbidden", "failed"]
    retry_after_seconds: int = Field(default=0, ge=0, le=3600, strict=True)
    telegram_message_id: int | None = Field(default=None, gt=0, strict=True)


class DeliveryRead(BaseModel):
    status: Literal["pending", "claimed", "sent", "failed", "cancelled"]
