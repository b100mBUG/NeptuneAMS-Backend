from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class ClassBrief(BaseModel):
    id: str
    name: str


class TeacherCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: str
    password: str = Field(min_length=8, max_length=128)
    class_ids: list[str] = Field(min_length=1)

    @field_validator("email")
    @classmethod
    def email_norm(cls, v: str) -> str:
        return v.strip().lower()

    @field_validator("name")
    @classmethod
    def name_strip(cls, v: str) -> str:
        return v.strip()


class TeacherClassesUpdate(BaseModel):
    class_ids: list[str] = Field(min_length=1)


class TeacherUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=120)

    @field_validator("name")
    @classmethod
    def name_strip(cls, v: str) -> str:
        return v.strip()


class TeacherResponse(BaseModel):
    id: str
    school_id: str
    name: str
    email: str
    date_added: datetime
    classes: list[ClassBrief]

    @classmethod
    def from_teacher(cls, t):
        return cls(
            id=t.id,
            school_id=t.school_id,
            name=t.name,
            email=t.email,
            date_added=t.date_added,
            classes=[ClassBrief(id=c.id, name=c.name) for c in (t.classes or [])],
        )


class AdminTeacherResponse(BaseModel):
    """Teacher row for admin lists — same as TeacherResponse."""

    id: str
    school_id: str
    name: str
    email: str
    date_added: datetime
    classes: list[ClassBrief]
