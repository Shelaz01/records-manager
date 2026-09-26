"""Tests for the demo data seeder.

Pure data work, so none of this needs a display or a Tk root.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from records_manager.db import Database, LoanRepo, PatientRepo, UserRepo
from records_manager.demo import DAYS_OF_HISTORY, PATIENT_COUNT, seed_demo


@pytest.fixture
def seeded(db: Database) -> Database:
    seed_demo(db)
    return db


class TestSeeding:
    def test_creates_the_expected_number_of_patients(self, seeded: Database) -> None:
        assert len(PatientRepo(seeded).list_all()) == PATIENT_COUNT

    def test_creates_both_active_and_returned_loans(self, seeded: Database) -> None:
        loans = LoanRepo(seeded)
        assert loans.active(), "demo data needs files currently out"
        assert loans.returned(), "demo data needs returned loans for the history"

    def test_creates_no_accounts(self, seeded: Database) -> None:
        # Inventing an admin would skip the first-run setup screen and leave
        # a known password in the database.
        assert UserRepo(seeded).has_users() is False

    def test_returns_a_summary(self, db: Database) -> None:
        assert "patients" in seed_demo(db)

    def test_is_safe_to_run_twice(self, db: Database) -> None:
        seed_demo(db)
        seed_demo(db)
        assert len(PatientRepo(db).list_all()) == PATIENT_COUNT

    def test_is_deterministic(self, tmp_path) -> None:
        first, second = Database(tmp_path / "a.db"), Database(tmp_path / "b.db")
        seed_demo(first)
        seed_demo(second)
        names = lambda db: [(p.hospital_num, p.surname, p.first_names)
                            for p in PatientRepo(db).list_all()]
        assert names(first) == names(second)


class TestSeededData:
    def test_hospital_numbers_keep_leading_zeros(self, seeded: Database) -> None:
        numbers = [p.hospital_num for p in PatientRepo(seeded).list_all()]
        assert any(n.startswith("0") for n in numbers)
        assert "00001" in numbers

    def test_loans_span_the_history_window(self, seeded: Database) -> None:
        loans = LoanRepo(seeded)
        dates = [date.fromisoformat(loan.borrowed_on)
                 for loan in loans.active() + loans.returned()]
        assert max(dates) - min(dates) > timedelta(days=30), \
            "loans should be spread out, not all on one day"

    def test_no_loan_predates_the_history_window(self, seeded: Database) -> None:
        loans = LoanRepo(seeded)
        earliest = min(date.fromisoformat(loan.borrowed_on)
                       for loan in loans.active() + loans.returned())
        assert earliest >= date.today() - timedelta(days=DAYS_OF_HISTORY)

    def test_returned_loans_are_returned_after_they_were_borrowed(
        self, seeded: Database
    ) -> None:
        for loan in LoanRepo(seeded).returned():
            assert loan.returned_on >= loan.borrowed_on

    def test_no_file_is_out_twice(self, seeded: Database) -> None:
        active = [loan.hospital_num for loan in LoanRepo(seeded).active()]
        assert len(active) == len(set(active))

    def test_some_loans_have_no_reason(self, seeded: Database) -> None:
        # Exercises the blank-cell path in the CSV export.
        loans = LoanRepo(seeded)
        assert any(loan.reason is None for loan in loans.active() + loans.returned())

    def test_every_loan_points_at_a_real_patient(self, seeded: Database) -> None:
        patients = {p.hospital_num for p in PatientRepo(seeded).list_all()}
        loans = LoanRepo(seeded)
        for loan in loans.active() + loans.returned():
            assert loan.hospital_num in patients
