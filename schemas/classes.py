from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class ClassCreate(BaseModel):
    name: str = Field(min_length=1, max_length=32)

    @field_validator("name")
    @classmethod
    def strip_(cls, v: str) -> str:
        return v.strip()


class ClassUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=32)

    @field_validator("name")
    @classmethod
    def strip_(cls, v: str) -> str:
        return v.strip()


class ClassResponse(BaseModel):
    id: str
    school_id: str
    name: str
    date_added: datetime
    assigned_teacher_ids: list[str] = Field(default_factory=list)

    model_config = {"from_attributes": True}
