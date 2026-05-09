from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from actions.classes import (
    create_class,
    delete_class,
    fetch_classes_page,
    list_teachers_for_class,
    search_classes_page,
    undo_delete_class,
    edit_class,
)
from auth import get_current_admin, get_current_user
from subscription_guard import SubscriptionGuard
from config_db import get_db
from database.models import Admin, Teacher
from pagination import Page, PageDep
from schemas.classes import ClassCreate, ClassUpdate, ClassResponse
from schemas.teachers import TeacherResponse
from serializers import class_to_response, teacher_to_response
from tenancy import school_id_from_user

router = APIRouter(prefix="/classes", tags=["Classes"], dependencies=[Depends(SubscriptionGuard)])

DB = Annotated[AsyncSession, Depends(get_db)]
AdminAuth = Annotated[Admin, Depends(get_current_admin)]
AnyAuth = Annotated[Admin | Teacher, Depends(get_current_user)]


@router.post("/", response_model=ClassResponse, status_code=status.HTTP_201_CREATED)
async def add_class(body: ClassCreate, db: DB, admin: AdminAuth):
    cls = await create_class(db, admin.school_id, body.name)
    await db.refresh(cls, attribute_names=["teachers"])
    return class_to_response(cls)


@router.get("/", response_model=Page[ClassResponse])
async def list_classes(db: DB, user: AnyAuth, page: PageDep):
    sid = school_id_from_user(user)
    items, total = await fetch_classes_page(db, sid, page)
    out = [class_to_response(c) for c in items]
    return Page(items=out, total=total, page=page.page, page_size=page.page_size)


@router.get("/search", response_model=Page[ClassResponse])
async def search(q: str, db: DB, user: AnyAuth, page: PageDep):
    sid = school_id_from_user(user)
    items, total = await search_classes_page(db, sid, q, page)
    return Page(
        items=[class_to_response(c) for c in items],
        total=total,
        page=page.page,
        page_size=page.page_size,
    )


@router.get("/{class_id}/teachers", response_model=list[TeacherResponse])
async def class_teachers(class_id: str, db: DB, admin: AdminAuth):
    sid = admin.school_id
    rows = await list_teachers_for_class(db, sid, class_id)
    return [teacher_to_response(t) for t in rows]


@router.patch("/{class_id}", response_model=ClassResponse)
async def update_class(class_id: str, body: ClassUpdate, db: DB, admin: AdminAuth):
    cls = await edit_class(db, admin.school_id, class_id, body.name)
    if not cls:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Class not found")
    await db.refresh(cls, attribute_names=["teachers"])
    return class_to_response(cls)


@router.delete("/{class_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_class(class_id: str, db: DB, admin: AdminAuth):
    result = await delete_class(db, admin.school_id, class_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Class not found")


@router.patch("/{class_id}/restore", response_model=ClassResponse)
async def restore_class(class_id: str, db: DB, admin: AdminAuth):
    cls = await undo_delete_class(db, admin.school_id, class_id)
    if not cls:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Class not found or not deleted")
    await db.refresh(cls, attribute_names=["teachers"])
    return class_to_response(cls)
