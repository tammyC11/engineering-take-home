from datetime import date, datetime
from typing import Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


class EntryIn(BaseModel):
    recorded_at: AwareDatetime
    mood: int = Field(ge=1, le=5)
    symptoms: list[str] = Field(default_factory=list, max_length=20)
    note: str | None = Field(default=None, max_length=2000)


class EntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    recorded_at: datetime
    mood: int
    symptoms: list[str]
    note: str | None


class ClinicianOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    practice: str


class ShareIn(BaseModel):
    clinician_id: int
    from_date: date
    to_date: date
    include_notes: bool = False

    @model_validator(mode="after")
    def period_is_ordered(self) -> Self:
        if self.from_date > self.to_date:
            raise ValueError("from_date must not be after to_date")
        return self


class ShareOut(BaseModel):
    """Exactly the fields in API.md; the share's time zone and consent version stay internal."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    clinician_id: int
    from_date: date
    to_date: date
    include_notes: bool
    created_at: datetime
    revoked_at: datetime | None


class ClinicianEntryOut(BaseModel):
    """A diary entry as a doctor sees it; separate from EntryOut so /entries never changes."""

    id: int
    recorded_at: datetime
    mood: int
    symptoms: list[str]
    note: str | None


class AccessRecordOut(BaseModel):
    clinician_id: int
    clinician_name: str
    accessed_at: datetime
    entry_ids: list[int]


class TelemetryEvent(BaseModel):
    event: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")


class Me(BaseModel):
    role: str
    id: int
    name: str
