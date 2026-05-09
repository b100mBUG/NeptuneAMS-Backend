from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from actions.teachers import (
    delete_teacher,
    edit_teacher,
    fetch_teacher_by_id,
    search_teachers_page,
    set_teacher_classes,
    undo_delete_teacher,
)
from auth import get_current_admin, get_current_teacher
from subscription_guard import SubscriptionGuard
from config_db import get_db
from database.models import Admin, Teacher
from pagination import Page, PageDep
from schemas.teachers import TeacherClassesUpdate, TeacherResponse, TeacherUpdate
from serializers import teacher_to_response

router = APIRouter(prefix="/teachers", tags=["Teachers"], dependencies=[Depends(SubscriptionGuard)])

DB = Annotated[AsyncSession, Depends(get_db)]
AdminAuth = Annotated[Admin, Depends(get_current_admin)]
TeachAuth = Annotated[Teacher, Depends(get_current_teacher)]


@router.get("/me", response_model=TeacherResponse)
async def get_me(teacher: TeachAuth, db: DB):
    t = await fetch_teacher_by_id(db, teacher.school_id, teacher.id)
    if not t:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Teacher not found")
    return teacher_to_response(t)


@router.patch("/me", response_model=TeacherResponse)
async def update_me(body: TeacherUpdate, db: DB, teacher: TeachAuth):
    t = await edit_teacher(db, teacher.school_id, teacher.id, body.name)
    if not t:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Teacher not found")
    return teacher_to_response(t)


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
async def delete_me(db: DB, teacher: TeachAuth):
    await delete_teacher(db, teacher.school_id, teacher.id)


@router.get("/", response_model=Page[TeacherResponse])
async def list_teachers(db: DB, admin: AdminAuth, page: PageDep):
    items, total = await search_teachers_page(db, admin.school_id, "", page)
    return Page(
        items=[teacher_to_response(t) for t in items],
        total=total,
        page=page.page,
        page_size=page.page_size,
    )


@router.get("/search", response_model=Page[TeacherResponse])
async def search(q: str, db: DB, admin: AdminAuth, page: PageDep):
    items, total = await search_teachers_page(db, admin.school_id, q, page)
    return Page(
        items=[teacher_to_response(t) for t in items],
        total=total,
        page=page.page,
        page_size=page.page_size,
    )


@router.patch("/{teacher_id}/classes", response_model=TeacherResponse)
async def update_teacher_classes(teacher_id: str, body: TeacherClassesUpdate, db: DB, admin: AdminAuth):
    try:
        t = await set_teacher_classes(db, admin.school_id, teacher_id, body.class_ids)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    if not t:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Teacher not found")
    return teacher_to_response(t)


@router.delete("/{teacher_id}/admin", status_code=status.HTTP_204_NO_CONTENT)
async def admin_delete_teacher(teacher_id: str, db: DB, admin: AdminAuth):
    result = await delete_teacher(db, admin.school_id, teacher_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Teacher not found")


@router.patch("/{teacher_id}/restore", response_model=TeacherResponse)
async def restore_teacher(teacher_id: str, db: DB, admin: AdminAuth):
    teacher = await undo_delete_teacher(db, admin.school_id, teacher_id)
    if not teacher:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Teacher not found or not deleted")
    t = await fetch_teacher_by_id(db, admin.school_id, teacher_id)
    return teacher_to_response(t)
