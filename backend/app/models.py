from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    false,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Patient(Base):
    __tablename__ = "patients"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(320), unique=True)
    timezone: Mapped[str] = mapped_column(String(64))  # IANA name, e.g. "Europe/Berlin"
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Clinician(Base):
    __tablename__ = "clinicians"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    practice: Mapped[str] = mapped_column(String(200))


class DiaryEntry(Base):
    __tablename__ = "diary_entries"
    __table_args__ = (CheckConstraint("mood BETWEEN 1 AND 5", name="mood_range"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), index=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    mood: Mapped[int]
    symptoms: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    note: Mapped[str | None] = mapped_column(Text)
    # "app-v1" entries were sent without a time zone and stored as if they were UTC.
    source: Mapped[str] = mapped_column(String(16), server_default="app-v2")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Share(Base):
    """A patient's consent for one clinician to read their diary for a period of days."""

    __tablename__ = "shares"
    __table_args__ = (
        CheckConstraint("from_date <= to_date", name="share_period"),
        Index("ix_shares_clinician_id_patient_id", "clinician_id", "patient_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), index=True)
    clinician_id: Mapped[int] = mapped_column(ForeignKey("clinicians.id"))
    # Inclusive calendar days, read in `timezone`: the patient's time zone when they consented,
    # so a later change to their profile can't change what this share covers.
    from_date: Mapped[date]
    to_date: Mapped[date]
    timezone: Mapped[str] = mapped_column(String(64))
    include_notes: Mapped[bool] = mapped_column(default=False, server_default=false())
    # Which consent wording the patient agreed to (O.Cons_3).
    consent_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # Shares are never deleted: a revoked share is the record of what was consented to.
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AccessLog(Base):
    """One clinician read of a patient's diary (O.Log_1). Append-only: a database trigger
    rejects UPDATE and DELETE (O.Log_3)."""

    __tablename__ = "access_log"
    __table_args__ = (Index("ix_access_log_patient_id_accessed_at", "patient_id", "accessed_at"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    # No foreign keys to patients or entries: the record must outlive their erasure (O.Del_1).
    patient_id: Mapped[int]
    clinician_id: Mapped[int] = mapped_column(ForeignKey("clinicians.id"))
    accessed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    entry_ids: Mapped[list[int]] = mapped_column(ARRAY(Integer))
    notes_shown: Mapped[bool]
