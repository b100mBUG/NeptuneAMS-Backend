from datetime import date, datetime

from pydantic import BaseModel, Field

from database.models import AttendanceStatus


class AttendanceCreate(BaseModel):
    std_id: str = Field(min_length=1, max_length=64)
    class_id: str = Field(min_length=1, description="Class context for authorization")
    status: AttendanceStatus = AttendanceStatus.present
    period: str = Field(default="morning", max_length=40)
    session_date: date | None = None
    note: str | None = Field(None, max_length=500)


class AttendanceResponse(BaseModel):
    id: str
    school_id: str
    std_id: str
    period: str
    session_date: date
    status: AttendanceStatus
    note: str | None
    marked_by_teacher_id: str | None
    created_at: datetime
    updated_at: datetime
    student_name: str | None = None

    model_config = {"from_attributes": True}


class AttendanceSummary(BaseModel):
    student_id: str
    student_name: str
    total: int
    present: int
    absent: int
    late: int
    excused: int
    rate: float
