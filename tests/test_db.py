"""Tests for the data layer: users, patients and loans.

These cover the rules the UI relies on — that a file can only be out on one
loan at a time, that hospital numbers keep their leading zeros, and that the
repositories raise ``RecordsError`` subclasses the UI can show directly.
"""
from __future__ import annotations

import sqlite3
from datetime import date, timedelta

import pytest

from records_manager.db import (
    AlreadyBorrowedError,
    Database,
    DuplicateRecordError,
    HasLoanHistoryError,
    LastAdminError,
    LoanRepo,
    NotFoundError,
    Patient,
    PatientRepo,
    RecordsError,
    User,
    UserRepo,
    ValidationError,
    _raise_domain_error,
    hash_password,
    verify_password,
)

TODAY = date.today()
YESTERDAY = TODAY - timedelta(days=1)


def backdate(db: Database, loan_id: int, borrowed_on: date) -> None:
    """Move a loan's borrow date into the past.

    The repository always stamps ``date('now')``, so date-range tests need a
    way to spread loans across days.
    """
    with db.transaction() as conn:
        conn.execute("UPDATE loans SET borrowed_on = ? WHERE id = ?",
                     (borrowed_on.isoformat(), loan_id))


# --------------------------------------------------------------------------- #
# Password hashing
# --------------------------------------------------------------------------- #
class TestPasswordHashing:
    def test_hash_is_salted_and_verifies(self) -> None:
        first, second = hash_password("hunter2"), hash_password("hunter2")
        assert first != second, "each hash must use a fresh salt"
        assert verify_password("hunter2", first)
        assert verify_password("hunter2", second)

    def test_wrong_password_rejected(self) -> None:
        assert not verify_password("hunter3", hash_password("hunter2"))

    def test_plaintext_never_stored(self) -> None:
        assert "hunter2" not in hash_password("hunter2")

    def test_malformed_hash_is_rejected_not_raised(self) -> None:
        assert not verify_password("hunter2", "not-a-real-hash")


# --------------------------------------------------------------------------- #
# First run
# --------------------------------------------------------------------------- #
class TestFirstRun:
    def test_no_users_on_a_fresh_database(self, users: UserRepo) -> None:
        assert users.has_users() is False

    def test_has_users_once_the_admin_exists(self, users: UserRepo, admin: User) -> None:
        assert users.has_users() is True

    def test_schema_is_created_on_a_new_file(self, tmp_path) -> None:
        path = tmp_path / "nested" / "records.db"
        Database(path)
        assert path.exists(), "Database should create its parent directory and file"


# --------------------------------------------------------------------------- #
# Users
# --------------------------------------------------------------------------- #
class TestUsers:
    def test_create_returns_the_stored_user(self, users: UserRepo) -> None:
        user = users.create("Ada Admin", "ada", "pw", role="admin", email="ada@x.test")
        assert (user.name, user.username, user.role) == ("Ada Admin", "ada", "admin")
        assert user.email == "ada@x.test"
        assert user.is_admin is True

    def test_new_users_default_to_the_user_role(self, users: UserRepo) -> None:
        assert users.create("Bob", "bob", "pw").is_admin is False

    def test_authenticate_accepts_the_right_password(self, users: UserRepo, admin: User) -> None:
        assert users.authenticate("ada", "correct horse") == admin

    def test_authenticate_rejects_the_wrong_password(self, users: UserRepo, admin: User) -> None:
        assert users.authenticate("ada", "wrong horse") is None

    def test_authenticate_rejects_an_unknown_username(self, users: UserRepo, admin: User) -> None:
        assert users.authenticate("nobody", "correct horse") is None

    def test_duplicate_username_rejected(self, users: UserRepo, admin: User) -> None:
        with pytest.raises(DuplicateRecordError, match="ada"):
            users.create("Ada Impostor", "ada", "pw")

    def test_change_password_takes_effect(self, users: UserRepo, admin: User) -> None:
        users.change_password("ada", "new passphrase")
        assert users.authenticate("ada", "new passphrase") == admin
        assert users.authenticate("ada", "correct horse") is None

    def test_change_password_for_unknown_user(self, users: UserRepo) -> None:
        with pytest.raises(NotFoundError, match="nobody"):
            users.change_password("nobody", "pw")

    def test_list_all_is_ordered_by_name(self, users: UserRepo) -> None:
        users.create("Zoe", "zoe", "pw")
        users.create("Al", "al", "pw")
        assert [u.name for u in users.list_all()] == ["Al", "Zoe"]

    def test_delete_removes_the_account(self, users: UserRepo, admin: User) -> None:
        users.create("Bob", "bob", "pw")
        users.delete("bob")
        assert [u.username for u in users.list_all()] == ["ada"]
        assert users.authenticate("bob", "pw") is None

    def test_delete_unknown_user(self, users: UserRepo) -> None:
        with pytest.raises(NotFoundError, match="nobody"):
            users.delete("nobody")

    def test_last_admin_cannot_be_deleted(self, users: UserRepo, admin: User) -> None:
        users.create("Bob", "bob", "pw")  # a non-admin does not count
        with pytest.raises(LastAdminError):
            users.delete("ada")
        assert users.authenticate("ada", "correct horse") == admin

    def test_an_admin_can_be_deleted_when_another_remains(
        self, users: UserRepo, admin: User
    ) -> None:
        users.create("Bea Admin", "bea", "pw", role="admin")
        users.delete("ada")
        assert [u.username for u in users.list_all()] == ["bea"]


# --------------------------------------------------------------------------- #
# Patients
# --------------------------------------------------------------------------- #
class TestPatients:
    def test_add_then_get(self, patients: PatientRepo) -> None:
        patients.add(Patient("A1", "Doe", "Jane", "Box 1"))
        stored = patients.get("A1")
        assert (stored.surname, stored.first_names, stored.box_no) == ("Doe", "Jane", "Box 1")
        assert stored.scan_path is None

    def test_get_unknown_returns_none(self, patients: PatientRepo) -> None:
        assert patients.get("nope") is None

    def test_duplicate_hospital_number_rejected(self, patients: PatientRepo) -> None:
        patients.add(Patient("A1", "Doe", "Jane", "Box 1"))
        with pytest.raises(DuplicateRecordError, match="A1"):
            patients.add(Patient("A1", "Other", "Person", "Box 2"))

    def test_list_all_ordered_by_name(self, patients: PatientRepo) -> None:
        patients.add(Patient("1", "Young", "Ann", "B"))
        patients.add(Patient("2", "Adams", "Zoe", "B"))
        assert [p.surname for p in patients.list_all()] == ["Adams", "Young"]

    def test_delete_removes_a_patient_without_loans(self, patients: PatientRepo) -> None:
        patients.add(Patient("A1", "Doe", "Jane", "Box 1"))
        patients.delete("A1")
        assert patients.get("A1") is None

    def test_delete_unknown_patient(self, patients: PatientRepo) -> None:
        with pytest.raises(NotFoundError, match="nope"):
            patients.delete("nope")

    def test_update_unknown_patient(self, patients: PatientRepo) -> None:
        with pytest.raises(NotFoundError, match="nope"):
            patients.update("nope", Patient("nope", "Doe", "Jane", "Box 1"))

    def test_update_changes_fields(self, patients: PatientRepo) -> None:
        patients.add(Patient("A1", "Doe", "Jane", "Box 1"))
        patients.update("A1", Patient("A1", "Smith", "Jane", "Box 9", scan_path="/s.png"))
        stored = patients.get("A1")
        assert (stored.surname, stored.box_no, stored.scan_path) == ("Smith", "Box 9", "/s.png")

    def test_update_onto_an_existing_number_rejected(self, patients: PatientRepo) -> None:
        patients.add(Patient("A1", "Doe", "Jane", "Box 1"))
        patients.add(Patient("A2", "Roe", "John", "Box 2"))
        with pytest.raises(DuplicateRecordError, match="A1"):
            patients.update("A2", Patient("A1", "Roe", "John", "Box 2"))
        assert patients.get("A2") is not None, "the failed update must roll back"


class TestSearch:
    @pytest.fixture(autouse=True)
    def _seed(self, patients: PatientRepo) -> None:
        patients.add(Patient("00123", "Doe", "Jane", "Box 1"))
        patients.add(Patient("456", "Roe", "Richard", "Box 2"))

    def test_hospital_number_matches_exactly(self, patients: PatientRepo) -> None:
        assert [p.hospital_num for p in patients.search("00123")] == ["00123"]

    def test_hospital_number_is_not_a_partial_match(self, patients: PatientRepo) -> None:
        # Documented behaviour: the number matches exactly, so "123" must not
        # find "00123". Only names are matched partially.
        assert patients.search("123") == []

    def test_surname_matches_partially(self, patients: PatientRepo) -> None:
        assert [p.surname for p in patients.search("oe")] == ["Doe", "Roe"]

    def test_first_names_match_partially(self, patients: PatientRepo) -> None:
        assert [p.first_names for p in patients.search("Rich")] == ["Richard"]

    def test_search_is_case_insensitive(self, patients: PatientRepo) -> None:
        assert [p.surname for p in patients.search("doe")] == ["Doe"]

    def test_surrounding_whitespace_ignored(self, patients: PatientRepo) -> None:
        assert [p.hospital_num for p in patients.search("  00123  ")] == ["00123"]

    def test_no_match_returns_empty(self, patients: PatientRepo) -> None:
        assert patients.search("nobody") == []


class TestLeadingZeros:
    """Hospital numbers are TEXT: "00123" must never become 123."""

    def test_preserved_through_add_and_get(self, patients: PatientRepo) -> None:
        patients.add(Patient("00123", "Doe", "Jane", "Box 1"))
        assert patients.get("00123").hospital_num == "00123"

    def test_a_stripped_number_is_a_different_patient(self, patients: PatientRepo) -> None:
        patients.add(Patient("00123", "Doe", "Jane", "Box 1"))
        assert patients.get("123") is None
        patients.add(Patient("123", "Roe", "John", "Box 2"))  # must not collide
        assert patients.get("00123").surname == "Doe"
        assert patients.get("123").surname == "Roe"

    def test_preserved_through_the_edit_flow(self, patients: PatientRepo) -> None:
        patients.add(Patient("00123", "Doe", "Jane", "Box 1"))
        patients.update("00123", Patient("00456", "Doe", "Jane", "Box 1"))
        assert patients.get("00456").hospital_num == "00456"
        assert patients.get("00123") is None

    def test_preserved_on_a_loan(self, patients: PatientRepo, loans: LoanRepo) -> None:
        patients.add(Patient("00123", "Doe", "Jane", "Box 1"))
        loans.borrow("00123", "Zandi", "IT")
        assert loans.active()[0].hospital_num == "00123"


# --------------------------------------------------------------------------- #
# Loans
# --------------------------------------------------------------------------- #
@pytest.fixture
def patient(patients: PatientRepo) -> Patient:
    p = Patient("00123", "Doe", "Jane", "Box 1")
    patients.add(p)
    return p


class TestBorrowing:
    def test_borrow_creates_an_active_loan(
        self, loans: LoanRepo, patient: Patient, admin: User
    ) -> None:
        loans.borrow("00123", "Zandi", "IT", "audit", recorded_by=admin.id)
        [loan] = loans.active()
        assert (loan.borrower, loan.department, loan.reason) == ("Zandi", "IT", "audit")
        assert loan.patient_name == "Doe, Jane"
        assert loan.recorded_by == "Ada Admin"
        assert loan.borrowed_on == TODAY.isoformat()
        assert loan.returned_on is None
        assert loan.is_active is True

    def test_reason_and_recorder_are_optional(self, loans: LoanRepo, patient: Patient) -> None:
        loans.borrow("00123", "Zandi", "IT")
        [loan] = loans.active()
        assert loan.reason is None
        assert loan.recorded_by is None

    def test_double_borrow_blocked(self, loans: LoanRepo, patient: Patient) -> None:
        loans.borrow("00123", "Zandi", "IT")
        with pytest.raises(AlreadyBorrowedError, match="00123"):
            loans.borrow("00123", "Someone Else", "Records")
        assert len(loans.active()) == 1

    def test_borrow_for_an_unknown_patient(self, loans: LoanRepo) -> None:
        with pytest.raises(NotFoundError, match="nope"):
            loans.borrow("nope", "Zandi", "IT")

    def test_a_file_can_be_borrowed_again_after_return(
        self, loans: LoanRepo, patient: Patient
    ) -> None:
        loans.borrow("00123", "Zandi", "IT")
        loans.return_loan(loans.active()[0].id)
        loans.borrow("00123", "Someone Else", "Records")
        assert len(loans.active()) == 1
        assert len(loans.returned()) == 1

    def test_two_different_files_can_be_out_at_once(
        self, loans: LoanRepo, patients: PatientRepo, patient: Patient
    ) -> None:
        patients.add(Patient("00456", "Roe", "John", "Box 2"))
        loans.borrow("00123", "Zandi", "IT")
        loans.borrow("00456", "Zandi", "IT")
        assert len(loans.active()) == 2


class TestReturning:
    def test_return_marks_the_loan_returned(self, loans: LoanRepo, patient: Patient) -> None:
        loans.borrow("00123", "Zandi", "IT")
        loans.return_loan(loans.active()[0].id)
        assert loans.active() == []
        [loan] = loans.returned()
        assert loan.returned_on == TODAY.isoformat()
        assert loan.is_active is False

    def test_returning_twice_is_rejected(self, loans: LoanRepo, patient: Patient) -> None:
        loans.borrow("00123", "Zandi", "IT")
        loan_id = loans.active()[0].id
        loans.return_loan(loan_id)
        with pytest.raises(NotFoundError):
            loans.return_loan(loan_id)
        assert len(loans.returned()) == 1

    def test_returning_an_unknown_loan(self, loans: LoanRepo) -> None:
        with pytest.raises(NotFoundError):
            loans.return_loan(999)

    def test_the_borrower_survives_a_return_by_someone_else(
        self, users: UserRepo, patients: PatientRepo, loans: LoanRepo,
        patient: Patient, admin: User,
    ) -> None:
        """Anyone may return a file, and the loan keeps its own borrower.

        Whoever happens to be on the desk can take a file back, but the
        record of who had it must not follow the person handing it in.
        """
        clerk = users.create("Bea Clerk", "bea", "pw")
        loans.borrow("00123", "Zandi Moyo", "IT", "audit", recorded_by=admin.id)
        loan = loans.active()[0]

        # A different member of staff takes the file back in.
        assert clerk.id != admin.id
        loans.return_loan(loan.id)

        [returned] = loans.returned()
        assert returned.borrower == "Zandi Moyo", \
            "the borrower is who had the file, not who took it back"
        assert returned.recorded_by == "Ada Admin"
        assert returned.department == "IT"
        assert returned.reason == "audit"
        assert returned.borrowed_on == loan.borrowed_on

    def test_a_return_changes_nothing_but_the_return_date(
        self, loans: LoanRepo, patient: Patient, admin: User
    ) -> None:
        loans.borrow("00123", "Zandi Moyo", "IT", "audit", recorded_by=admin.id)
        before = loans.active()[0]
        loans.return_loan(before.id)
        after = loans.returned()[0]

        changed = {field for field in
                   ("id", "hospital_num", "patient_name", "borrower",
                    "department", "reason", "borrowed_on", "recorded_by")
                   if getattr(before, field) != getattr(after, field)}
        assert changed == set()
        assert after.returned_on is not None


class TestPatientDeletionWithLoans:
    def test_blocked_while_on_loan(
        self, patients: PatientRepo, loans: LoanRepo, patient: Patient
    ) -> None:
        loans.borrow("00123", "Zandi", "IT")
        with pytest.raises(HasLoanHistoryError):
            patients.delete("00123")
        assert patients.get("00123") is not None

    def test_blocked_by_returned_loan_history(
        self, patients: PatientRepo, loans: LoanRepo, patient: Patient
    ) -> None:
        loans.borrow("00123", "Zandi", "IT")
        loans.return_loan(loans.active()[0].id)
        with pytest.raises(HasLoanHistoryError):
            patients.delete("00123")
        assert patients.get("00123") is not None


class TestLoanHistory:
    """has_history() must agree with what delete() will allow."""

    def test_false_for_a_file_never_borrowed(self, loans: LoanRepo,
                                             patient: Patient) -> None:
        assert loans.has_history("00123") is False

    def test_true_while_the_file_is_out(self, loans: LoanRepo,
                                        patient: Patient) -> None:
        loans.borrow("00123", "Zandi", "IT")
        assert loans.has_history("00123") is True

    def test_true_after_the_file_comes_back(self, loans: LoanRepo,
                                            patient: Patient) -> None:
        loans.borrow("00123", "Zandi", "IT")
        loans.return_loan(loans.active()[0].id)
        assert loans.has_history("00123") is True

    def test_false_for_an_unknown_file(self, loans: LoanRepo) -> None:
        assert loans.has_history("nope") is False

    def test_is_specific_to_one_file(self, patients: PatientRepo,
                                     loans: LoanRepo, patient: Patient) -> None:
        patients.add(Patient("00456", "Roe", "John", "Box 2"))
        loans.borrow("00456", "Zandi", "IT")
        assert loans.has_history("00456") is True
        assert loans.has_history("00123") is False

    def test_leading_zeros_are_not_conflated(self, patients: PatientRepo,
                                             loans: LoanRepo,
                                             patient: Patient) -> None:
        patients.add(Patient("123", "Roe", "John", "Box 2"))
        loans.borrow("123", "Zandi", "IT")
        assert loans.has_history("123") is True
        assert loans.has_history("00123") is False

    @pytest.mark.parametrize("returned", [False, True])
    def test_agrees_with_delete_being_blocked(
        self, patients: PatientRepo, loans: LoanRepo, patient: Patient,
        returned: bool,
    ) -> None:
        loans.borrow("00123", "Zandi", "IT")
        if returned:
            loans.return_loan(loans.active()[0].id)
        assert loans.has_history("00123") is True
        with pytest.raises(HasLoanHistoryError):
            patients.delete("00123")

    def test_follows_a_renumbered_file(self, patients: PatientRepo,
                                       loans: LoanRepo, patient: Patient) -> None:
        loans.borrow("00123", "Zandi", "IT")
        patients.update("00123", Patient("00999", "Doe", "Jane", "Box 1"))
        assert loans.has_history("00999") is True
        assert loans.has_history("00123") is False


class TestHospitalNumberCascade:
    def test_renumbering_follows_the_loans(
        self, patients: PatientRepo, loans: LoanRepo, patient: Patient
    ) -> None:
        loans.borrow("00123", "Zandi", "IT")
        loans.return_loan(loans.active()[0].id)
        loans.borrow("00123", "Someone Else", "Records")

        patients.update("00123", Patient("00999", "Doe", "Jane", "Box 1"))

        assert loans.active()[0].hospital_num == "00999"
        assert loans.returned()[0].hospital_num == "00999"

    def test_the_active_loan_survives_renumbering(
        self, patients: PatientRepo, loans: LoanRepo, patient: Patient
    ) -> None:
        loans.borrow("00123", "Zandi", "IT")
        patients.update("00123", Patient("00999", "Doe", "Jane", "Box 1"))
        [loan] = loans.active()
        assert loan.borrower == "Zandi"
        assert loan.patient_name == "Doe, Jane"


class TestReports:
    @pytest.fixture
    def seeded(self, patients: PatientRepo, loans: LoanRepo, db: Database) -> LoanRepo:
        """Three loans spread over three days, two borrowers."""
        for num, surname in (("1", "One"), ("2", "Two"), ("3", "Three")):
            patients.add(Patient(num, surname, "Pat", "Box"))
        loans.borrow("1", "Zandi", "IT", "audit")
        loans.borrow("2", "Zandi", "IT", "audit")
        loans.borrow("3", "Other", "Records", "review")
        by_num = {loan.hospital_num: loan.id for loan in loans.active()}
        backdate(db, by_num["1"], TODAY - timedelta(days=5))
        backdate(db, by_num["2"], YESTERDAY)
        return loans

    def test_between_includes_both_endpoints(self, seeded: LoanRepo) -> None:
        found = seeded.between(TODAY - timedelta(days=5), TODAY)
        assert {loan.hospital_num for loan in found} == {"1", "2", "3"}

    def test_between_excludes_outside_the_range(self, seeded: LoanRepo) -> None:
        found = seeded.between(YESTERDAY, TODAY)
        assert {loan.hospital_num for loan in found} == {"2", "3"}

    def test_between_is_ordered_by_borrow_date(self, seeded: LoanRepo) -> None:
        found = seeded.between(TODAY - timedelta(days=10), TODAY)
        assert [loan.hospital_num for loan in found] == ["1", "2", "3"]

    def test_between_a_single_day(self, seeded: LoanRepo) -> None:
        assert [loan.hospital_num for loan in seeded.between(YESTERDAY, YESTERDAY)] == ["2"]

    def test_between_an_empty_range(self, seeded: LoanRepo) -> None:
        future = TODAY + timedelta(days=30)
        assert seeded.between(future, future + timedelta(days=1)) == []

    def test_between_covers_returned_loans_too(self, seeded: LoanRepo) -> None:
        seeded.return_loan(seeded.active()[0].id)
        found = seeded.between(TODAY - timedelta(days=10), TODAY)
        assert len(found) == 3, "a report by date must not drop returned loans"

    def test_by_borrower(self, seeded: LoanRepo) -> None:
        assert {loan.hospital_num for loan in seeded.by_borrower("Zandi")} == {"1", "2"}

    def test_by_borrower_ignores_surrounding_whitespace(self, seeded: LoanRepo) -> None:
        assert len(seeded.by_borrower("  Zandi  ")) == 2

    def test_by_borrower_unknown(self, seeded: LoanRepo) -> None:
        assert seeded.by_borrower("Nobody") == []

    def test_by_borrower_includes_returned_loans(self, seeded: LoanRepo) -> None:
        seeded.return_loan(seeded.by_borrower("Zandi")[0].id)
        assert len(seeded.by_borrower("Zandi")) == 2


# --------------------------------------------------------------------------- #
# Integrity error classification
# --------------------------------------------------------------------------- #
class TestMissingRequiredFields:
    """NOT NULL failures must read as validation errors, not as duplicates.

    Before this was fixed, every non-foreign-key IntegrityError in borrow()
    was reported as "already borrowed", telling the user to return a file
    that was never out.
    """

    def test_user_create_without_a_name(self, users: UserRepo) -> None:
        with pytest.raises(ValidationError, match="name is required"):
            users.create(None, "bob", "pw")

    def test_patient_add_without_a_surname(self, patients: PatientRepo) -> None:
        with pytest.raises(ValidationError, match="surname is required"):
            patients.add(Patient("A1", None, "Jane", "Box 1"))

    def test_patient_add_without_a_box_number(self, patients: PatientRepo) -> None:
        with pytest.raises(ValidationError, match="box_no is required"):
            patients.add(Patient("A1", "Doe", "Jane", None))

    def test_patient_update_without_a_surname(self, patients: PatientRepo) -> None:
        patients.add(Patient("A1", "Doe", "Jane", "Box 1"))
        with pytest.raises(ValidationError, match="surname is required"):
            patients.update("A1", Patient("A1", None, "Jane", "Box 1"))
        assert patients.get("A1").surname == "Doe", "the failed update must roll back"

    def test_borrow_without_a_borrower(self, loans: LoanRepo, patient: Patient) -> None:
        with pytest.raises(ValidationError, match="borrower is required"):
            loans.borrow("00123", None, "IT")
        assert loans.active() == []

    def test_borrow_without_a_department(self, loans: LoanRepo, patient: Patient) -> None:
        with pytest.raises(ValidationError, match="department is required"):
            loans.borrow("00123", "Zandi", None)

    def test_a_missing_field_is_not_reported_as_already_borrowed(
        self, loans: LoanRepo, patient: Patient
    ) -> None:
        with pytest.raises(ValidationError):
            loans.borrow("00123", None, "IT")

    def test_validation_errors_are_shown_to_the_user(self, loans: LoanRepo,
                                                     patient: Patient) -> None:
        # The UI catches RecordsError and shows str(err), so it must be one.
        with pytest.raises(RecordsError):
            loans.borrow("00123", None, "IT")


class TestCheckConstraints:
    def test_an_invalid_role_is_rejected(self, users: UserRepo) -> None:
        with pytest.raises(ValidationError, match="role is not an allowed value"):
            users.create("Bob", "bob", "pw", role="wizard")

    def test_the_message_does_not_quote_raw_sql(self, users: UserRepo) -> None:
        with pytest.raises(ValidationError) as caught:
            users.create("Bob", "bob", "pw", role="wizard")
        assert "IN (" not in str(caught.value)


class TestIntegrityErrorTranslation:
    """The helper must not dress up errors it does not recognise."""

    def test_unrecognised_integrity_error_passes_through(self) -> None:
        original = sqlite3.IntegrityError("something else entirely")
        with pytest.raises(sqlite3.IntegrityError, match="something else entirely"):
            _raise_domain_error(original, duplicate=DuplicateRecordError("dup"))

    def test_unique_without_a_duplicate_error_passes_through(self) -> None:
        original = sqlite3.IntegrityError("UNIQUE constraint failed: users.username")
        with pytest.raises(sqlite3.IntegrityError):
            _raise_domain_error(original)

    def test_foreign_key_without_a_missing_error_passes_through(self) -> None:
        original = sqlite3.IntegrityError("FOREIGN KEY constraint failed")
        with pytest.raises(sqlite3.IntegrityError):
            _raise_domain_error(original)

    def test_the_original_error_is_kept_as_the_cause(self, loans: LoanRepo,
                                                     patient: Patient) -> None:
        with pytest.raises(ValidationError) as caught:
            loans.borrow("00123", None, "IT")
        assert isinstance(caught.value.__cause__, sqlite3.IntegrityError)


# --------------------------------------------------------------------------- #
# Transactions
# --------------------------------------------------------------------------- #
class TestTransactions:
    def test_a_failed_transaction_rolls_back(self, db: Database, patients: PatientRepo) -> None:
        patients.add(Patient("A1", "Doe", "Jane", "Box 1"))
        with pytest.raises(RuntimeError):
            with db.transaction() as conn:
                conn.execute("DELETE FROM patients")
                raise RuntimeError("boom")
        assert patients.get("A1") is not None

    def test_foreign_keys_are_enforced(self, db: Database) -> None:
        with db.transaction() as conn:
            assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1

    def test_reopening_an_existing_database_keeps_data(
        self, tmp_path, patients: PatientRepo, db: Database
    ) -> None:
        patients.add(Patient("A1", "Doe", "Jane", "Box 1"))
        reopened = PatientRepo(Database(db.path))
        assert reopened.get("A1").surname == "Doe"
