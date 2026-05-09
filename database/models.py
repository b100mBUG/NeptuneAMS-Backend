import enum
from datetime import datetime, timezone, date
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    String,
    Table,
    Column,
    UniqueConstraint,
    Index,
    Integer,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class AttendanceStatus(str, enum.Enum):
    present = "present"
    absent  = "absent"
    late    = "late"
    excused = "excused"


teacher_classes = Table(
    "teacher_classes",
    Base.metadata,
    Column("teacher_id", String(36), ForeignKey("teachers.id", ondelete="CASCADE"), primary_key=True),
    Column("class_id",   String(36), ForeignKey("classes.id",  ondelete="CASCADE"), primary_key=True),
)


class School(Base):
    __tablename__ = "schools"

    id:         Mapped[str]      = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name:       Mapped[str]      = mapped_column(String(120))
    slug:       Mapped[str]      = mapped_column(String(80), unique=True, index=True)
    is_active:  Mapped[bool]     = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    admins:   Mapped[list["Admin"]]   = relationship(back_populates="school")
    teachers: Mapped[list["Teacher"]] = relationship(back_populates="school")
    classes:  Mapped[list["Class"]]   = relationship(back_populates="school")


class Admin(Base):
    __tablename__ = "admins"

    id:         Mapped[str]      = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    school_id:  Mapped[str]      = mapped_column(ForeignKey("schools.id", ondelete="CASCADE"), index=True)
    name:       Mapped[str]      = mapped_column(String(120))
    email:      Mapped[str]      = mapped_column(String(255))
    pwd_hash:   Mapped[str]      = mapped_column(String(255))
    is_deleted: Mapped[bool]     = mapped_column(Boolean, default=False)
    date_added: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    school: Mapped["School"] = relationship(back_populates="admins")

    __table_args__ = (
        UniqueConstraint("school_id", "email", name="uq_admin_school_email"),
        # Fast lookup for login + is_deleted filter
        Index("ix_admins_school_email_active", "school_id", "email", "is_deleted"),
    )


class Class(Base):
    __tablename__ = "classes"

    id:         Mapped[str]      = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    school_id:  Mapped[str]      = mapped_column(ForeignKey("schools.id", ondelete="CASCADE"), index=True)
    name:       Mapped[str]      = mapped_column(String(32))
    is_deleted: Mapped[bool]     = mapped_column(Boolean, default=False)
    date_added: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    school:   Mapped["School"]    = relationship(back_populates="classes")
    students: Mapped[list["Student"]] = relationship(
        back_populates="class_", cascade="all, delete-orphan",
    )
    teachers: Mapped[list["Teacher"]] = relationship(
        secondary=teacher_classes, back_populates="classes",
    )

    __table_args__ = (
        UniqueConstraint("school_id", "name", name="uq_class_school_name"),
        # Used in listing active classes per school
        Index("ix_classes_school_active", "school_id", "is_deleted"),
    )


class Teacher(Base):
    __tablename__ = "teachers"

    id:         Mapped[str]      = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    school_id:  Mapped[str]      = mapped_column(ForeignKey("schools.id", ondelete="CASCADE"), index=True)
    name:       Mapped[str]      = mapped_column(String(120))
    email:      Mapped[str]      = mapped_column(String(255))
    pwd_hash:   Mapped[str]      = mapped_column(String(255))
    is_deleted: Mapped[bool]     = mapped_column(Boolean, default=False)
    date_added: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    school:  Mapped["School"]   = relationship(back_populates="teachers")
    classes: Mapped[list["Class"]] = relationship(
        secondary=teacher_classes, back_populates="teachers",
    )

    __table_args__ = (
        UniqueConstraint("school_id", "email", name="uq_teacher_school_email"),
        # Login + active filter
        Index("ix_teachers_school_email_active", "school_id", "email", "is_deleted"),
    )


class Student(Base):
    """Admission number is `id`, scoped by `school_id` (composite PK)."""

    __tablename__ = "students"

    school_id:  Mapped[str]      = mapped_column(ForeignKey("schools.id", ondelete="CASCADE"), primary_key=True)
    id:         Mapped[str]      = mapped_column(String(64), primary_key=True)
    name:       Mapped[str]      = mapped_column(String(120))
    c_id:       Mapped[str]      = mapped_column(ForeignKey("classes.id", ondelete="CASCADE"), index=True)
    is_deleted: Mapped[bool]     = mapped_column(Boolean, default=False)
    date_added: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    class_:     Mapped["Class"]       = relationship(back_populates="students")
    attendance: Mapped[list["Attendance"]] = relationship(
        back_populates="student", cascade="all, delete-orphan",
    )

    __table_args__ = (
        # Core lookup: all active students in a class
        Index("ix_students_class_active", "c_id", "is_deleted"),
        # Name search per school
        Index("ix_students_school_name", "school_id", "name"),
    )


class Attendance(Base):
    __tablename__ = "attendance"

    id:                   Mapped[str]        = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    school_id:            Mapped[str]        = mapped_column(ForeignKey("schools.id", ondelete="CASCADE"))
    std_id:               Mapped[str]        = mapped_column(String(64))
    period:               Mapped[str]        = mapped_column(String(40), default="morning")
    session_date:         Mapped[date]       = mapped_column(Date)
    status:               Mapped[str]        = mapped_column(String(16), default=AttendanceStatus.present.value)
    note:                 Mapped[str | None] = mapped_column(String(500), nullable=True)
    marked_by_teacher_id: Mapped[str | None] = mapped_column(
        ForeignKey("teachers.id", ondelete="SET NULL"), nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow,
    )

    student: Mapped["Student"] = relationship(back_populates="attendance")

    __table_args__ = (
        ForeignKeyConstraint(
            ["school_id", "std_id"],
            ["students.school_id", "students.id"],
            ondelete="CASCADE",
        ),
        # Uniqueness: one record per student per period per day
        UniqueConstraint(
            "school_id", "std_id", "period", "session_date",
            name="uq_attendance_student_period_day",
        ),
        # ── Query indexes ──────────────────────────────────────────────────────
        # Most-used: fetch a class's attendance for a day
        Index("ix_att_school_date",        "school_id", "session_date"),
        # Teacher activity queries (marked_by + date range)
        Index("ix_att_teacher_date",       "marked_by_teacher_id", "session_date"),
        # Per-student history
        Index("ix_att_student_date",       "school_id", "std_id", "session_date"),
        # Analysis: school + date range + status (aggregation queries)
        Index("ix_att_school_date_status", "school_id", "session_date", "status"),
    )


class SubscriptionTier(str, enum.Enum):
    tier_500  = "tier_500"
    tier_1000 = "tier_1000"
    tier_1500 = "tier_1500"
    tier_2000 = "tier_2000"
    tier_2500 = "tier_2500"


class PaymentStatus(str, enum.Enum):
    pending = "pending"
    success = "success"
    failed  = "failed"


class SchoolSubscription(Base):
    """Tracks the active subscription / expiry for a school."""
    __tablename__ = "school_subscriptions"

    id:                       Mapped[str]        = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    school_id:                Mapped[str]        = mapped_column(ForeignKey("schools.id", ondelete="CASCADE"), unique=True, index=True)
    subscription_start:       Mapped[date | None] = mapped_column(Date, nullable=True)
    subscription_end:         Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    student_count_at_payment: Mapped[int]         = mapped_column(Integer, default=0)
    amount_paid:              Mapped[int]         = mapped_column(Integer, default=0)
    updated_at:               Mapped[datetime]    = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    school: Mapped["School"] = relationship()


class PaymentLog(Base):
    """Every Paystack transaction attempt, success or failure."""
    __tablename__ = "payment_logs"

    id:                   Mapped[str]        = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    school_id:            Mapped[str]        = mapped_column(ForeignKey("schools.id", ondelete="CASCADE"), index=True)
    paystack_reference:   Mapped[str]        = mapped_column(String(120), unique=True, index=True)
    paystack_access_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    amount:               Mapped[int]        = mapped_column(Integer)
    student_count:        Mapped[int]        = mapped_column(Integer)
    status:               Mapped[str]        = mapped_column(String(16), default=PaymentStatus.pending.value, index=True)
    gateway_response:     Mapped[str | None] = mapped_column(String(255), nullable=True)
    paid_at:              Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at:           Mapped[datetime]   = mapped_column(DateTime(timezone=True), default=utcnow)

    school: Mapped["School"] = relationship()
