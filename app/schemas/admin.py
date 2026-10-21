from pydantic import BaseModel, ConfigDict, Field


class AdminStepUpRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(pattern=r"^[0-9]{6}$", min_length=6, max_length=6)


class AdminStepUpResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    admin_role: str
