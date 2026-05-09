from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from slug_utils import normalize_slug


class ProvisionSchoolRequest(BaseModel):
    school_name: str = Field(min_length=1, max_length=120)
    school_slug: str = Field(min_length=2, max_length=80)
    admin_name: str = Field(min_length=1, max_length=120)
    admin_email: str
    admin_password: str = Field(min_length=8, max_length=128)

    @field_validator("school_slug")
    @classmethod
    def slug_ok(cls, v: str) -> str:
        return normalize_slug(v)

    @field_validator("admin_email")
    @classmethod
    def email_norm(cls, v: str) -> str:
        return v.strip().lower()


class ProvisionSchoolResponse(BaseModel):
    school_id: str
    slug: str
    admin_id: str


class PlatformAuthRequest(BaseModel):
    platform_secret: str = Field(min_length=1)


class SchoolOverviewResponse(BaseModel):
    id: str
    name: str
    slug: str
    is_active: bool
    created_at: datetime
    admin_count: int
    teacher_count: int
    class_count: int
    student_count: int


class SchoolActivePatch(BaseModel):
    is_active: bool
