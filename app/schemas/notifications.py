from datetime import date, datetime
from decimal import Decimal
import re
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


NotificationCategory = Literal["upcoming", "due_today", "overdue", "payment_completed"]


class NotificationPreferencesUpdate(BaseModel):
    reminders_enabled: bool = False
    reminder_offsets: list[Literal[7, 3, 1, 0]] = Field(default_factory=lambda: [7, 3, 1, 0], min_length=1, max_length=4)
    reminder_time: str = "09:00"
    timezone: str = "Africa/Cairo"
    quiet_start: str | None = "22:00"
    quiet_end: str | None = "07:00"
    language: Literal["en", "ar"] = "en"
    privacy_mode: Literal["detailed", "private"] = "private"
    overdue_enabled: bool = False
    categories: list[NotificationCategory] = Field(default_factory=lambda: ["upcoming", "due_today"], max_length=4)

    model_config = ConfigDict(extra="forbid")

    @field_validator("reminder_time", "quiet_start", "quiet_end")
    @classmethod
    def valid_time(cls, value):
        if value is not None and not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value):
            raise ValueError("Use a 24-hour time in HH:MM format.")
        return value

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value):
        if len(value) > 64:
            raise ValueError("Choose a supported time zone.")
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("Choose a valid IANA time zone, such as Africa/Cairo.") from None
        return value

    @model_validator(mode="after")
    def coherent_preferences(self):
        if len(set(self.reminder_offsets)) != len(self.reminder_offsets):
            raise ValueError("Reminder offsets cannot be repeated.")
        if len(set(self.categories)) != len(self.categories):
            raise ValueError("Notification categories cannot be repeated.")
        if (self.quiet_start is None) != (self.quiet_end is None):
            raise ValueError("Set both quiet-hour times or leave both empty.")
        return self


class NotificationPreferencesResponse(NotificationPreferencesUpdate):
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True, extra="forbid")


class PushDeviceCreate(BaseModel):
    token: str = Field(min_length=20, max_length=300)
    platform: Literal["ios", "android"]

    model_config = ConfigDict(extra="forbid")

    @field_validator("token")
    @classmethod
    def valid_expo_token(cls, value):
        if not re.fullmatch(r"(?:Expo|Exponent)PushToken\[[A-Za-z0-9_+=/-]{1,256}\]", value):
            raise ValueError("Enter a valid Expo push token from this app installation.")
        return value


class PushDeviceResponse(BaseModel):
    id: int
    platform: Literal["ios", "android"]
    active: bool
    last_registered_at: datetime
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PaymentOccurrenceResponse(BaseModel):
    id: int
    obligation_id: int
    installment_id: int | None
    occurrence_key: str
    payment_kind: Literal["regular", "down_payment"]
    due_date: date
    scheduled_amount: Decimal
    schedule_version: int
    state: Literal["unpaid", "paid", "superseded"]
    paid_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class PaymentOccurrenceList(BaseModel):
    rows: list[PaymentOccurrenceResponse]


class NotificationResponse(BaseModel):
    id: int
    obligation_id: int | None
    notification_type: Literal["upcoming", "due_today", "overdue", "payment_completed"]
    title: str
    body: str
    route: str | None
    scheduled_at: datetime
    delivery_state: Literal["queued", "sending", "accepted", "platform_accepted", "failed", "cancelled"]
    read_at: datetime | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class NotificationPage(BaseModel):
    items: list[NotificationResponse]
    next_before_id: int | None
    unread_count: int
