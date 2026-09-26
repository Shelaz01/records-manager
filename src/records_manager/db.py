"""Data layer for Records Manager.

All database access goes through the repository classes here. The UI never
opens connections or writes SQL itself; it calls these methods and catches
the domain errors defined below.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterator, NoReturn

SCHEMA_PATH = Path(__file__).with_name("schema.sql")
DEFAULT_DB_PATH = Path.home() / ".records_manager" / "records.db"


# --------------------------------------------------------------------------- #
# Errors
# --------------------------------------------------------------------------- #
class RecordsError(Exception):
    """Base class for all data-layer errors the UI should show to the user."""


class DuplicateRecordError(RecordsError):
    """A record with this key already exists."""


class NotFoundError(RecordsError):
    """The referenced record does not exist."""


class AlreadyBorrowedError(RecordsError):
    """The file is already out on an active loan."""


class HasLoanHistoryError(RecordsError):
    """The patient cannot be deleted because loans reference them."""


class LastAdminError(RecordsError):
    """The operation would leave the system with no admin account."""


class ValidationError(RecordsError):
    """A value was missing or out of range (a NOT NULL or CHECK failure)."""


# --------------------------------------------------------------------------- #
# Integrity error translation
# --------------------------------------------------------------------------- #
def _field_name(message: str) -> str:
    """Pull the offending column out of a SQLite constraint message.

    SQLite reports these as 'NOT NULL constraint failed: loans.borrower', and
    a CHECK as its expression, e.g. "CHECK constraint failed: role IN
    ('admin', 'user')". Taking the first word and dropping the table prefix
    gives the column in both cases, so the message stays readable in a
    messagebox instead of quoting raw SQL back at the user.
    """
    _, _, detail = message.partition(":")
    first_word = detail.strip().split(" ")[0]
    return first_word.rsplit(".", 1)[-1] if first_word else "A required field"


def _raise_domain_error(
    error: sqlite3.IntegrityError,
    *,
    duplicate: RecordsError | None = None,
    missing: RecordsError | None = None,
) -> NoReturn:
    """Translate a SQLite IntegrityError into a domain error and raise it.

    `duplicate` is raised for UNIQUE/PRIMARY KEY violations and `missing` for
    FOREIGN KEY violations, so each caller supplies wording that fits its own
    table. NOT NULL and CHECK failures become a ValidationError naming the
    column. Anything unrecognised is re-raised unchanged rather than being
    reported as a problem it isn't.
    """
    message = str(error)
    if duplicate is not None and ("UNIQUE constraint failed" in message
                                  or "PRIMARY KEY constraint failed" in message):
        raise duplicate from error
    if missing is not None and "FOREIGN KEY constraint failed" in message:
        raise missing from error
    if "NOT NULL constraint failed" in message:
        raise ValidationError(f"{_field_name(message)} is required.") from error
    if "CHECK constraint failed" in message:
        raise ValidationError(
            f"{_field_name(message)} is not an allowed value.") from error
    raise error


# --------------------------------------------------------------------------- #
# Models
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class User:
    id: int
    name: str
    email: str | None
    username: str
    role: str

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


@dataclass(frozen=True)
class Patient:
    hospital_num: str
    surname: str
    first_names: str
    box_no: str
    scan_path: str | None = None


@dataclass(frozen=True)
class Loan:
    id: int
    hospital_num: str
    patient_name: str
    borrower: str
    department: str
    reason: str | None
    borrowed_on: str
    returned_on: str | None
    recorded_by: str | None

    @property
    def is_active(self) -> bool:
        return self.returned_on is None


# --------------------------------------------------------------------------- #
# Password hashing (stdlib scrypt, no extra dependency)
# --------------------------------------------------------------------------- #
_SCRYPT_N, _SCRYPT_R, _SCRYPT_P = 2**14, 8, 1


def hash_password(password: str) -> str:
    """Return a salted scrypt hash in the form 'scrypt$n$r$p$salt$hash'."""
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt,
                            n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P)
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Check a password against a stored hash in constant time."""
    try:
        _, n, r, p, salt_hex, digest_hex = stored.split("$")
    except ValueError:
        return False
    digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt_hex),
                            n=int(n), r=int(r), p=int(p))
    return hmac.compare_digest(digest.hex(), digest_hex)


# Used so failed logins for unknown usernames take as long as wrong passwords.
_DUMMY_HASH = hash_password(secrets.token_hex(8))


# --------------------------------------------------------------------------- #
# Connection management
# --------------------------------------------------------------------------- #
class Database:
    """Owns the database file and hands out short-lived transactions."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path or os.environ.get("RECORDS_DB", DEFAULT_DB_PATH))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.init_schema()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Open a connection, commit on success, roll back on error, always close."""
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def init_schema(self) -> None:
        """Create tables and indexes if they don't exist yet."""
        with self.transaction() as conn:
            conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- #
# Repositories
# --------------------------------------------------------------------------- #
class UserRepo:
    def __init__(self, db: Database) -> None:
        self._db = db

    @staticmethod
    def _to_user(row: sqlite3.Row) -> User:
        return User(row["id"], row["name"], row["email"], row["username"], row["role"])

    def has_users(self) -> bool:
        """False on first run, when the admin account still needs creating."""
        with self._db.transaction() as conn:
            return conn.execute("SELECT 1 FROM users LIMIT 1").fetchone() is not None

    def create(self, name: str, username: str, password: str,
               role: str = "user", email: str | None = None) -> User:
        try:
            with self._db.transaction() as conn:
                cur = conn.execute(
                    "INSERT INTO users (name, email, username, password_hash, role) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (name, email, username, hash_password(password), role),
                )
                row = conn.execute("SELECT * FROM users WHERE id = ?",
                                   (cur.lastrowid,)).fetchone()
        except sqlite3.IntegrityError as e:
            _raise_domain_error(
                e, duplicate=DuplicateRecordError(f"Username '{username}' is already taken."))
        return self._to_user(row)

    def authenticate(self, username: str, password: str) -> User | None:
        """Return the user if the credentials are valid, otherwise None."""
        with self._db.transaction() as conn:
            row = conn.execute("SELECT * FROM users WHERE username = ?",
                               (username,)).fetchone()
        if row is None:
            verify_password(password, _DUMMY_HASH)
            return None
        return self._to_user(row) if verify_password(password, row["password_hash"]) else None

    def change_password(self, username: str, new_password: str) -> None:
        with self._db.transaction() as conn:
            cur = conn.execute("UPDATE users SET password_hash = ? WHERE username = ?",
                               (hash_password(new_password), username))
        if cur.rowcount == 0:
            raise NotFoundError(f"No user named '{username}'.")

    def list_all(self) -> list[User]:
        with self._db.transaction() as conn:
            rows = conn.execute("SELECT * FROM users ORDER BY name").fetchall()
        return [self._to_user(r) for r in rows]

    def delete(self, username: str) -> None:
        with self._db.transaction() as conn:
            row = conn.execute("SELECT role FROM users WHERE username = ?",
                               (username,)).fetchone()
            if row is None:
                raise NotFoundError(f"No user named '{username}'.")
            if row["role"] == "admin":
                admins = conn.execute(
                    "SELECT COUNT(*) FROM users WHERE role = 'admin'").fetchone()[0]
                if admins <= 1:
                    raise LastAdminError("Can't delete the only admin account.")
            conn.execute("DELETE FROM users WHERE username = ?", (username,))


class PatientRepo:
    def __init__(self, db: Database) -> None:
        self._db = db

    @staticmethod
    def _to_patient(row: sqlite3.Row) -> Patient:
        return Patient(row["hospital_num"], row["surname"], row["first_names"],
                       row["box_no"], row["scan_path"])

    def add(self, patient: Patient) -> None:
        try:
            with self._db.transaction() as conn:
                conn.execute(
                    "INSERT INTO patients (hospital_num, surname, first_names, box_no, scan_path) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (patient.hospital_num, patient.surname, patient.first_names,
                     patient.box_no, patient.scan_path),
                )
        except sqlite3.IntegrityError as e:
            _raise_domain_error(e, duplicate=DuplicateRecordError(
                f"Hospital number {patient.hospital_num} already exists."))

    def get(self, hospital_num: str) -> Patient | None:
        with self._db.transaction() as conn:
            row = conn.execute("SELECT * FROM patients WHERE hospital_num = ?",
                               (hospital_num,)).fetchone()
        return self._to_patient(row) if row else None

    def list_all(self) -> list[Patient]:
        with self._db.transaction() as conn:
            rows = conn.execute("SELECT * FROM patients ORDER BY surname, first_names").fetchall()
        return [self._to_patient(r) for r in rows]

    def search(self, term: str) -> list[Patient]:
        """Match hospital number exactly, or surname/first names partially."""
        term = term.strip()
        like = f"%{term}%"
        with self._db.transaction() as conn:
            rows = conn.execute(
                "SELECT * FROM patients "
                "WHERE hospital_num = ? OR surname LIKE ? OR first_names LIKE ? "
                "ORDER BY surname, first_names",
                (term, like, like),
            ).fetchall()
        return [self._to_patient(r) for r in rows]

    def update(self, original_num: str, patient: Patient) -> None:
        """Update a patient; changing the hospital number cascades to their loans."""
        try:
            with self._db.transaction() as conn:
                cur = conn.execute(
                    "UPDATE patients SET hospital_num = ?, surname = ?, first_names = ?, "
                    "box_no = ?, scan_path = ? WHERE hospital_num = ?",
                    (patient.hospital_num, patient.surname, patient.first_names,
                     patient.box_no, patient.scan_path, original_num),
                )
        except sqlite3.IntegrityError as e:
            _raise_domain_error(e, duplicate=DuplicateRecordError(
                f"Hospital number {patient.hospital_num} already exists."))
        if cur.rowcount == 0:
            raise NotFoundError(f"No patient with hospital number {original_num}.")

    def delete(self, hospital_num: str) -> None:
        try:
            with self._db.transaction() as conn:
                cur = conn.execute("DELETE FROM patients WHERE hospital_num = ?",
                                   (hospital_num,))
        except sqlite3.IntegrityError as e:
            raise HasLoanHistoryError(
                "This file has borrowing history and can't be deleted.") from e
        if cur.rowcount == 0:
            raise NotFoundError(f"No patient with hospital number {hospital_num}.")


class LoanRepo:
    _SELECT = """
        SELECT l.id, l.hospital_num,
               p.surname || ', ' || p.first_names AS patient_name,
               l.borrower, l.department, l.reason,
               l.borrowed_on, l.returned_on,
               u.name AS recorded_by
        FROM loans l
        JOIN patients p ON p.hospital_num = l.hospital_num
        LEFT JOIN users u ON u.id = l.recorded_by
    """

    def __init__(self, db: Database) -> None:
        self._db = db

    def _query(self, where: str = "", params: tuple = ()) -> list[Loan]:
        with self._db.transaction() as conn:
            rows = conn.execute(f"{self._SELECT} {where}", params).fetchall()
        return [Loan(**dict(r)) for r in rows]

    def borrow(self, hospital_num: str, borrower: str, department: str,
               reason: str | None = None, recorded_by: int | None = None) -> None:
        try:
            with self._db.transaction() as conn:
                conn.execute(
                    "INSERT INTO loans (hospital_num, borrower, department, reason, recorded_by) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (hospital_num, borrower, department, reason, recorded_by),
                )
        except sqlite3.IntegrityError as e:
            _raise_domain_error(
                e,
                duplicate=AlreadyBorrowedError(
                    f"File {hospital_num} is already borrowed. "
                    "It must be returned first."),
                missing=NotFoundError(f"No patient with hospital number {hospital_num}."),
            )

    def return_loan(self, loan_id: int) -> None:
        with self._db.transaction() as conn:
            cur = conn.execute(
                "UPDATE loans SET returned_on = date('now') "
                "WHERE id = ? AND returned_on IS NULL",
                (loan_id,),
            )
        if cur.rowcount == 0:
            raise NotFoundError("That loan doesn't exist or was already returned.")

    def has_history(self, hospital_num: str) -> bool:
        """True if any loan references this file, whether or not it came back.

        Lets the UI explain up front that a file cannot be deleted, instead
        of asking the user to confirm and only then refusing.
        """
        with self._db.transaction() as conn:
            row = conn.execute(
                "SELECT 1 FROM loans WHERE hospital_num = ? LIMIT 1",
                (hospital_num,),
            ).fetchone()
        return row is not None

    def active(self) -> list[Loan]:
        return self._query("WHERE l.returned_on IS NULL ORDER BY l.borrowed_on")

    def returned(self) -> list[Loan]:
        return self._query("WHERE l.returned_on IS NOT NULL ORDER BY l.returned_on DESC")

    def between(self, start: date, end: date) -> list[Loan]:
        """Loans borrowed within [start, end], for the date-range report."""
        return self._query("WHERE l.borrowed_on BETWEEN ? AND ? ORDER BY l.borrowed_on",
                           (start.isoformat(), end.isoformat()))

    def by_borrower(self, borrower: str) -> list[Loan]:
        """All loans for one borrower, for the single-borrower report."""
        return self._query("WHERE l.borrower = ? ORDER BY l.borrowed_on",
                           (borrower.strip(),))
