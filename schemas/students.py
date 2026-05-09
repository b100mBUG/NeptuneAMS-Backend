from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


class StudentCreate(BaseModel):
    id: str = Field(min_length=1, max_length=64, description="Admission / student number")
    name: str = Field(min_length=1, max_length=120)

    @field_validator("id", "name")
    @classmethod
    def strip_(cls, v: str) -> str:
        return v.strip()


class StudentUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=120)

    @field_validator("name")
    @classmethod
    def strip_(cls, v: str) -> str:
        return v.strip()


class StudentResponse(BaseModel):
    school_id: str
    id: str
    name: str
    c_id: str
    date_added: datetime

    model_config = {"from_attributes": True}


class BulkStudentJsonBody(BaseModel):
    students: list[dict[str, Any]]

    @field_validator("students")
    @classmethod
    def non_empty(cls, v: list) -> list:
        if not v:
            raise ValueError("students must not be empty")
        return v
