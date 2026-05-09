from datetime import datetime, timedelta, timezone
from typing import Annotated, Literal

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
import bcrypt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config_db import get_db
from database.models import Teacher, Admin
from settings import get_settings

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

Role = Literal["teacher", "admin", "platform"]


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def create_access_token(subject_id: str, role: Role, school_id: str = "") -> str:
    settings = get_settings()
    payload = {
        "sub": subject_id,
        "role": role,
        "sch": school_id or None,
        "exp": datetime.now(timezone.utc) + timedelta(hours=12),
    }
    return jwt.encode(payload, settings.secret_key, algorithm="HS256")


async def get_current_platform(
    token: Annotated[str, Depends(oauth2_scheme)],
) -> dict:
    payload = _decode_token(token)
    if payload.get("role") != "platform":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Platform access required")
    return payload


def _decode_token(token: str) -> dict:
    settings = get_settings()
    try:
        return jwt.decode(token, settings.secret_key, algorithms=["HS256"])
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_teacher(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Teacher:
    payload = _decode_token(token)
    if payload.get("role") != "teacher":
        raise HTTPException(status_code=403, detail="Teacher access required")
    school_id = payload.get("sch")
    sub = payload.get("sub")
    if not school_id or not sub:
        raise HTTPException(status_code=401, detail="Invalid token payload")
    teacher = (
        await db.execute(
            select(Teacher).where(
                Teacher.id == sub,
                Teacher.school_id == school_id,
                Teacher.is_deleted.is_(False),
            )
        )
    ).scalars().first()
    if not teacher:
        raise HTTPException(status_code=401, detail="Teacher account not found")
    return teacher


async def get_current_admin(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Admin:
    payload = _decode_token(token)
    if payload.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    school_id = payload.get("sch")
    sub = payload.get("sub")
    if not school_id or not sub:
        raise HTTPException(status_code=401, detail="Invalid token payload")
    admin = (
        await db.execute(
            select(Admin).where(
                Admin.id == sub,
                Admin.school_id == school_id,
                Admin.is_deleted.is_(False),
            )
        )
    ).scalars().first()
    if not admin:
        raise HTTPException(status_code=401, detail="Admin account not found")
    return admin


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Teacher | Admin:
    payload = _decode_token(token)
    role = payload.get("role")
    school_id = payload.get("sch")
    sub = payload.get("sub")
    if not school_id or not sub:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    if role == "admin":
        user = (
            await db.execute(
                select(Admin).where(
                    Admin.id == sub,
                    Admin.school_id == school_id,
                    Admin.is_deleted.is_(False),
                )
            )
        ).scalars().first()
    elif role == "teacher":
        user = (
            await db.execute(
                select(Teacher).where(
                    Teacher.id == sub,
                    Teacher.school_id == school_id,
                    Teacher.is_deleted.is_(False),
                )
            )
        ).scalars().first()
    else:
        user = None

    if not user:
        raise HTTPException(status_code=401, detail="Account not found")
    return user
