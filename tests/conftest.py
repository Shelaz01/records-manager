"""Shared fixtures for the data-layer tests.

Every test gets its own SQLite file under pytest's ``tmp_path``, so tests
are independent and never touch the real database in ``~/.records_manager``.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from records_manager.db import Database, LoanRepo, PatientRepo, User, UserRepo


@pytest.fixture
def db(tmp_path: Path) -> Database:
    """A freshly created, empty database for a single test."""
    return Database(tmp_path / "records.db")


@pytest.fixture
def users(db: Database) -> UserRepo:
    return UserRepo(db)


@pytest.fixture
def patients(db: Database) -> PatientRepo:
    return PatientRepo(db)


@pytest.fixture
def loans(db: Database) -> LoanRepo:
    return LoanRepo(db)


@pytest.fixture
def admin(users: UserRepo) -> User:
    """A single admin account, as the first-run setup screen would create."""
    return users.create("Ada Admin", "ada", "correct horse", role="admin")
