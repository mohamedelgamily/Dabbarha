from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class AccountDeletionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    password: str = Field(min_length=1)
    confirm_permanent_deletion: Literal[True]
