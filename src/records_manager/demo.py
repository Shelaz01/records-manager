"""Fill a database with fictional data, for screenshots and trying the app.

Every name, hospital number and phone number here is invented. Nothing in
this module comes from a real patient record.

Run it with ``python -m records_manager --seed-demo``.
"""
from __future__ import annotations

import random
from datetime import date, timedelta

from .db import Database, LoanRepo, Patient, PatientRepo, RecordsError, UserRepo

#: Fixed so repeated runs and screenshots line up.
SEED = 20240521

SURNAMES = (
    "Banda", "Chirwa", "Dube", "Gumbo", "Hove", "Jeke", "Kamba", "Madziva",
    "Mhango", "Moyo", "Ncube", "Ndlovu", "Nyathi", "Phiri", "Sibanda",
    "Tapera", "Zimuto", "Chigumba", "Mutasa", "Rusike",
)
FIRST_NAMES = (
    "Anesu", "Blessing", "Chipo", "Dumisani", "Emmanuel", "Farai", "Gamuchirai",
    "Hazvinei", "Itai", "Kudakwashe", "Lorraine", "Munashe", "Nyasha",
    "Panashe", "Rufaro", "Simbarashe", "Tadiwa", "Tinashe", "Vimbai", "Yeukai",
)
DEPARTMENTS = ("Outpatients", "Theatre", "Maternity", "Radiology",
               "Paediatrics", "Records", "Audit", "Pharmacy")
REASONS = ("Follow-up appointment", "Internal audit", "Clinical review",
           "Insurance query", "Theatre list", "Transfer of care", None)

PATIENT_COUNT = 30
DAYS_OF_HISTORY = 90


def _backdate(db: Database, loan_id: int, borrowed_on: date,
              returned_on: date | None) -> None:
    """Move a loan into the past.

    ``LoanRepo.borrow`` always stamps today, which would leave every demo
    loan on the same date and make the reports view look broken. This is the
    one place demo data needs SQL; the UI still never does.
    """
    with db.transaction() as conn:
        conn.execute(
            "UPDATE loans SET borrowed_on = ?, returned_on = ? WHERE id = ?",
            (borrowed_on.isoformat(),
             returned_on.isoformat() if returned_on else None,
             loan_id),
        )


def seed_demo(db: Database) -> str:
    """Add fictional patients and loans. Returns a one-line summary.

    Existing records are left alone, so this is safe to re-run; patients
    whose hospital numbers are already present are skipped.

    No accounts are created. The first run of the app asks for an
    administrator, and inventing one here would both skip that screen and
    leave a known password in the database. Where accounts already exist,
    loans are attributed to them so the Recorded By column is filled in.
    """
    rng = random.Random(SEED)
    patients = PatientRepo(db)
    loans = LoanRepo(db)

    staff = [user.id for user in UserRepo(db).list_all()] or [None]
    today = date.today()

    added = 0
    numbers: list[str] = []
    for index in range(PATIENT_COUNT):
        # Leading zeros on purpose: they are a real hazard in this system.
        hospital_num = f"{index + 1:05d}"
        numbers.append(hospital_num)
        patient = Patient(
            hospital_num=hospital_num,
            surname=rng.choice(SURNAMES),
            first_names=rng.choice(FIRST_NAMES),
            box_no=f"Box {rng.randint(1, 12)}",
        )
        try:
            patients.add(patient)
            added += 1
        except RecordsError:
            pass  # already seeded

    active = returned = 0
    # Returned loans first, so a file can be borrowed again afterwards
    # without tripping the one-active-loan rule.
    for hospital_num in rng.sample(numbers, 18):
        borrowed = today - timedelta(days=rng.randint(21, DAYS_OF_HISTORY))
        given_back = borrowed + timedelta(days=rng.randint(1, 14))
        if _borrow(loans, hospital_num, rng, staff):
            _backdate(db, _latest_active(loans, hospital_num), borrowed, given_back)
            returned += 1

    for hospital_num in rng.sample(numbers, 9):
        borrowed = today - timedelta(days=rng.randint(0, 20))
        if _borrow(loans, hospital_num, rng, staff):
            _backdate(db, _latest_active(loans, hospital_num), borrowed, None)
            active += 1

    return (f"Seeded {added} patients, {active} active loans and "
            f"{returned} returned loans into {db.path}.")


def _borrow(loans: LoanRepo, hospital_num: str, rng: random.Random,
            staff: list[int | None]) -> bool:
    """Book one file out, reporting whether it worked."""
    try:
        loans.borrow(
            hospital_num,
            borrower=f"{rng.choice(FIRST_NAMES)} {rng.choice(SURNAMES)}",
            department=rng.choice(DEPARTMENTS),
            reason=rng.choice(REASONS),
            recorded_by=rng.choice(staff),
        )
    except RecordsError:
        return False
    return True


def _latest_active(loans: LoanRepo, hospital_num: str) -> int:
    """The id of the open loan just created for this file."""
    return next(loan.id for loan in loans.active()
                if loan.hospital_num == hospital_num)
