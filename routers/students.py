from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from actions.bulk_students import (
    bulk_create_students,
    parse_student_rows_csv,
    parse_student_rows_json,
    parse_student_rows_xlsx,
)
from actions.students import (
    create_student,
    delete_student,
    edit_student,
    fetch_students_page,
    search_students_page,
    undo_delete_student,
)
from auth import get_current_admin, get_current_user
from subscription_guard import SubscriptionGuard
from config_db import get_db
from database.models import Admin, Teacher
from pagination import Page, PageDep
from schemas.students import BulkStudentJsonBody, StudentCreate, StudentResponse, StudentUpdate
from rate_limit import BULK_IMPORT_LIMIT, limiter
from tenancy import require_class_in_school, school_id_from_user

router = APIRouter(prefix="/classes/{class_id}/students", tags=["Students"], dependencies=[Depends(SubscriptionGuard)])

DB = Annotated[AsyncSession, Depends(get_db)]
AdminAuth = Annotated[Admin, Depends(get_current_admin)]
AnyAuth = Annotated[Admin | Teacher, Depends(get_current_user)]


@router.post("/", response_model=StudentResponse, status_code=status.HTTP_201_CREATED)
async def add_student(class_id: str, body: StudentCreate, db: DB, admin: AdminAuth):
    await require_class_in_school(db, admin.school_id, class_id)
    try:
        return await create_student(
            db,
            school_id=admin.school_id,
            admission_id=body.id,
            name=body.name,
            class_id=class_id,
        )
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Student id already exists in this school")


@router.post("/import", status_code=status.HTTP_201_CREATED)
@limiter.limit(BULK_IMPORT_LIMIT)
async def import_students_json(request: Request, class_id: str, body: BulkStudentJsonBody, db: DB, admin: AdminAuth):
    await require_class_in_school(db, admin.school_id, class_id)
    rows = parse_student_rows_json(body.students)
    if not rows:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No valid student rows parsed")
    try:
        n = await bulk_create_students(db, school_id=admin.school_id, class_id=class_id, rows=rows)
    except IntegrityError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Bulk insert failed (duplicate id or constraint). No rows committed.",
        )
    return {"inserted": n}


@router.post("/import-file", status_code=status.HTTP_201_CREATED)
@limiter.limit(BULK_IMPORT_LIMIT)
async def import_students_file(
    request: Request,
    class_id: str,
    db: DB,
    admin: AdminAuth,
    file: UploadFile = File(...),
):
    await require_class_in_school(db, admin.school_id, class_id)
    name = (file.filename or "").lower()
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty file")
    if name.endswith(".csv"):
        rows = parse_student_rows_csv(raw)
    elif name.endswith(".xlsx"):
        rows = parse_student_rows_xlsx(raw)
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported file type — use .csv or .xlsx",
        )
    if not rows:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No valid student rows parsed")
    try:
        n = await bulk_create_students(db, school_id=admin.school_id, class_id=class_id, rows=rows)
    except IntegrityError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Bulk insert failed (duplicate id or constraint). No rows committed.",
        )
    return {"inserted": n}


@router.get("/", response_model=Page[StudentResponse])
async def list_students(class_id: str, db: DB, user: AnyAuth, page: PageDep):
    sid = school_id_from_user(user)
    await require_class_in_school(db, sid, class_id)
    items, total = await fetch_students_page(db, sid, class_id, page)
    return Page(
        items=[StudentResponse.model_validate(s) for s in items],
        total=total,
        page=page.page,
        page_size=page.page_size,
    )


@router.get("/search", response_model=Page[StudentResponse])
async def search(class_id: str, q: str, db: DB, user: AnyAuth, page: PageDep):
    sid = school_id_from_user(user)
    await require_class_in_school(db, sid, class_id)
    items, total = await search_students_page(db, sid, class_id, q, page)
    return Page(
        items=[StudentResponse.model_validate(s) for s in items],
        total=total,
        page=page.page,
        page_size=page.page_size,
    )


@router.patch("/{student_id}", response_model=StudentResponse)
async def update_student(class_id: str, student_id: str, body: StudentUpdate, db: DB, admin: AdminAuth):
    student = await edit_student(db, admin.school_id, class_id, student_id, body.name)
    if not student:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found")
    return student


@router.delete("/{student_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_student(class_id: str, student_id: str, db: DB, admin: AdminAuth):
    result = await delete_student(db, admin.school_id, class_id, student_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found")


@router.patch("/{student_id}/restore", response_model=StudentResponse)
async def restore_student(class_id: str, student_id: str, db: DB, admin: AdminAuth):
    student = await undo_delete_student(db, admin.school_id, class_id, student_id)
    if not student:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found or not deleted")
    return student
