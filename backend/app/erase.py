"""Erase one patient's data on request (O.Del_1): make erase PATIENT=<id> [CONFIRM=yes].

Run by data protection once they have verified the request; there is no endpoint for it.

Deleted: the patient, their diary entries and their shares. Kept: the access records of doctors'
reads, unlinked from the patient (patient_id set to NULL). They still say which doctor, when,
which days, whether notes were shown and under which consent wording, as clinical evidence and
for the ten-year retention (O.Log_3), without saying whose diary it was. See NOTES.md, "Erasure".
"""

import argparse
import logging
from dataclasses import dataclass

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import AccessLog, DiaryEntry, Patient, Share

logger = logging.getLogger("diary.erasure")


@dataclass(frozen=True)
class Erasure:
    entries: int
    shares: int
    access_records: int

    def __str__(self) -> str:
        return (
            f"{self.entries} diary entries and {self.shares} shares deleted, "
            f"{self.access_records} access records kept without the patient"
        )


def count(db: Session, patient_id: int) -> Erasure:
    def rows(model: type[DiaryEntry] | type[Share] | type[AccessLog]) -> int:
        query = select(func.count()).select_from(model).where(model.patient_id == patient_id)
        return db.scalar(query) or 0

    return Erasure(rows(DiaryEntry), rows(Share), rows(AccessLog))


def erase_patient(db: Session, patient_id: int) -> Erasure:
    """Erases in the caller's transaction; nothing changes unless the caller commits."""
    if db.get(Patient, patient_id, with_for_update=True) is None:
        raise LookupError("No such patient")
    erased = count(db, patient_id)
    # The only change the access log's trigger allows.
    db.execute(update(AccessLog).where(AccessLog.patient_id == patient_id).values(patient_id=None))
    db.execute(delete(DiaryEntry).where(DiaryEntry.patient_id == patient_id))
    db.execute(delete(Share).where(Share.patient_id == patient_id))
    db.execute(delete(Patient).where(Patient.id == patient_id))
    return erased


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("patient_id", type=int)
    parser.add_argument("--confirm", action="store_true", help="erase; without it, a dry run")
    args = parser.parse_args(argv)

    # Prints and logs counts only, never names or health data (O.Log_4).
    with SessionLocal() as db:
        if db.get(Patient, args.patient_id) is None:
            print("No such patient. Nothing erased.")
            return 1
        if not args.confirm:
            print(f"Dry run, nothing changed. Erasing would mean: {count(db, args.patient_id)}.")
            print("Run again with CONFIRM=yes to erase.")
            return 0
        erased = erase_patient(db, args.patient_id)
        db.commit()
    logger.info("Patient erased: %s", erased)
    print(f"Erased: {erased}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
