"""Authentication stub; real authentication is out of scope.

The bearer token is "<role>-<id>", e.g. "patient-1" or "clinician-2".
"""

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Clinician, Patient

ACCOUNTS: dict[str, type[Patient] | type[Clinician]] = {"patient": Patient, "clinician": Clinician}


@dataclass(frozen=True)
class User:
    role: str
    id: int
    name: str


def current_user(
    db: Annotated[Session, Depends(get_db)],
    authorization: Annotated[str | None, Header()] = None,
) -> User:
    role, _, raw_id = (authorization or "").removeprefix("Bearer ").partition("-")
    model = ACCOUNTS.get(role)
    account = db.get(model, int(raw_id)) if model and raw_id.isdigit() else None
    if account is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token")
    return User(role=role, id=account.id, name=account.name)


def current_patient(user: Annotated[User, Depends(current_user)]) -> User:
    if user.role != "patient":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Patients only")
    return user


def current_clinician(user: Annotated[User, Depends(current_user)]) -> User:
    if user.role != "clinician":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Clinicians only")
    return user
