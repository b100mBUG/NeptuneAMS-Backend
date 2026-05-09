from database.models import Class, Teacher
from schemas.classes import ClassResponse
from schemas.teachers import TeacherResponse


def class_to_response(c: Class) -> ClassResponse:
    return ClassResponse(
        id=c.id,
        school_id=c.school_id,
        name=c.name,
        date_added=c.date_added,
        assigned_teacher_ids=[t.id for t in (c.teachers or [])],
    )


def teacher_to_response(t: Teacher) -> TeacherResponse:
    return TeacherResponse.from_teacher(t)
