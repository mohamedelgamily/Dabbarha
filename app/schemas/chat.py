from pydantic import BaseModel, ConfigDict, Field, field_validator


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    conversation_id: int | None = None

    @field_validator("message")
    @classmethod
    def message_must_not_be_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("message must not be empty or whitespace")
        return v

    model_config = ConfigDict(extra="forbid")


class ChatResponse(BaseModel):
    response: str
    metadata: dict[str, str] | None = None
    conversation_id: int
