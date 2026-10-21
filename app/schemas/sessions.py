"""New opt-in contracts; legacy login's Token response stays unchanged."""
import base64
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator
from app.schemas.auth import UserLogin
from app.schemas.validation import TrimmedText


def canonical_random(value: str) -> str:
    try:
        raw = base64.b64decode(value + "=", altchars=b"-_", validate=True)
        if len(raw) != 32 or base64.urlsafe_b64encode(raw).decode().rstrip("=") != value:
            raise ValueError()
    except (ValueError, UnicodeError):
        raise ValueError("Use a canonical 32-byte base64url credential.") from None
    return value


RandomCredential = Annotated[str, Field(min_length=43, max_length=43), AfterValidator(canonical_random)]


class SessionLogin(UserLogin):
    model_config = ConfigDict(extra="forbid")
    device_label: TrimmedText | None = Field(default=None, min_length=1, max_length=80)


class RefreshRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    refresh_token: RandomCredential
    retry_key: RandomCredential


class LogoutRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    refresh_token: RandomCredential


class RevokeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # Legacy passwords can be shorter/longer than new registration limits.
    password: str = Field(min_length=1)

    @field_validator("password")
    @classmethod
    def valid_unicode(cls, value):
        if any(0xD800 <= ord(char) <= 0xDFFF for char in value):
            raise ValueError("Password must contain valid Unicode.")
        return value


class SessionToken(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    refresh_token: str
    refresh_expires_at: int
    session_id: str
    session_expires_at: int


class SessionSummary(BaseModel):
    id: str
    device_label: str | None
    created_at: int
    last_refreshed_at: int
    idle_expires_at: int
    absolute_expires_at: int
    revoked_at: int | None
    current: bool
