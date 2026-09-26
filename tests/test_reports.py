"""Tests for CSV export of loan reports."""
from __future__ import annotations

import csv
from pathlib import Path

import pytest

from records_manager.db import Loan, LoanRepo, Patient, PatientRepo, User
from records_manager.reports import COLUMNS, export_loans_csv, loan_to_row

ENCODING = "utf-8-sig"


def make_loan(**overrides) -> Loan:
    """A loan with sensible defaults, so each test states only what it cares about."""
    fields = {
        "id": 1,
        "hospital_num": "00123",
        "patient_name": "Doe, Jane",
        "borrower": "Zandi",
        "department": "IT",
        "reason": "audit",
        "borrowed_on": "2024-05-08",
        "returned_on": None,
        "recorded_by": "Ada Admin",
    }
    fields.update(overrides)
    return Loan(**fields)


def read_rows(path: Path) -> list[list[str]]:
    with path.open(newline="", encoding=ENCODING) as handle:
        return list(csv.reader(handle))


# --------------------------------------------------------------------------- #
# Row rendering
# --------------------------------------------------------------------------- #
class TestLoanToRow:
    def test_columns_are_in_order(self) -> None:
        assert loan_to_row(make_loan()) == (
            "00123", "Doe, Jane", "Zandi", "IT", "audit",
            "2024-05-08", "", "Ada Admin",
        )

    def test_a_row_has_one_cell_per_column(self) -> None:
        assert len(loan_to_row(make_loan())) == len(COLUMNS)

    @pytest.mark.parametrize("field", ["reason", "returned_on", "recorded_by"])
    def test_optional_fields_become_empty_cells(self, field: str) -> None:
        row = loan_to_row(make_loan(**{field: None}))
        assert "None" not in row
        assert "" in row


# --------------------------------------------------------------------------- #
# File output
# --------------------------------------------------------------------------- #
class TestExport:
    def test_header_row(self, tmp_path: Path) -> None:
        path = tmp_path / "loans.csv"
        export_loans_csv([], path)
        assert read_rows(path)[0] == list(COLUMNS)

    def test_an_empty_report_still_writes_the_header(self, tmp_path: Path) -> None:
        path = tmp_path / "loans.csv"
        export_loans_csv([], path)
        assert len(read_rows(path)) == 1

    def test_one_loan_writes_one_data_row(self, tmp_path: Path) -> None:
        path = tmp_path / "loans.csv"
        export_loans_csv([make_loan()], path)
        rows = read_rows(path)
        assert len(rows) == 2
        assert rows[1] == ["00123", "Doe, Jane", "Zandi", "IT", "audit",
                           "2024-05-08", "", "Ada Admin"]

    def test_order_is_preserved(self, tmp_path: Path) -> None:
        path = tmp_path / "loans.csv"
        loans = [make_loan(id=n, hospital_num=f"A{n}") for n in (1, 2, 3)]
        export_loans_csv(loans, path)
        assert [row[0] for row in read_rows(path)[1:]] == ["A1", "A2", "A3"]

    def test_a_returned_loan_shows_its_return_date(self, tmp_path: Path) -> None:
        path = tmp_path / "loans.csv"
        export_loans_csv([make_loan(returned_on="2024-05-20")], path)
        assert read_rows(path)[1][6] == "2024-05-20"

    def test_an_active_loan_leaves_returned_on_blank(self, tmp_path: Path) -> None:
        path = tmp_path / "loans.csv"
        export_loans_csv([make_loan(returned_on=None)], path)
        assert read_rows(path)[1][6] == ""

    def test_export_replaces_an_existing_file(self, tmp_path: Path) -> None:
        path = tmp_path / "loans.csv"
        export_loans_csv([make_loan(), make_loan(id=2)], path)
        export_loans_csv([make_loan()], path)
        assert len(read_rows(path)) == 2, "the old rows must not be left behind"

    def test_accepts_a_string_path(self, tmp_path: Path) -> None:
        path = tmp_path / "loans.csv"
        export_loans_csv([make_loan()], str(path))
        assert path.exists()


# --------------------------------------------------------------------------- #
# Data that breaks naive CSV writing
# --------------------------------------------------------------------------- #
class TestAwkwardValues:
    def test_leading_zeros_are_written_intact(self, tmp_path: Path) -> None:
        path = tmp_path / "loans.csv"
        export_loans_csv([make_loan(hospital_num="00123")], path)
        assert read_rows(path)[1][0] == "00123"
        assert "00123" in path.read_text(encoding=ENCODING)

    def test_a_comma_in_a_value_is_quoted(self, tmp_path: Path) -> None:
        path = tmp_path / "loans.csv"
        export_loans_csv([make_loan(reason="audit, urgent")], path)
        assert read_rows(path)[1][4] == "audit, urgent"

    def test_a_quote_in_a_value_survives(self, tmp_path: Path) -> None:
        path = tmp_path / "loans.csv"
        export_loans_csv([make_loan(borrower='O"Brien')], path)
        assert read_rows(path)[1][2] == 'O"Brien'

    def test_a_newline_in_a_value_stays_in_one_field(self, tmp_path: Path) -> None:
        path = tmp_path / "loans.csv"
        export_loans_csv([make_loan(reason="audit\nurgent")], path)
        rows = read_rows(path)
        assert len(rows) == 2, "an embedded newline must not split the row"
        assert rows[1][4] == "audit\nurgent"

    def test_non_ascii_names_round_trip(self, tmp_path: Path) -> None:
        path = tmp_path / "loans.csv"
        export_loans_csv([make_loan(patient_name="Ncubé, Thandiwé")], path)
        assert read_rows(path)[1][1] == "Ncubé, Thandiwé"

    def test_no_blank_line_between_rows(self, tmp_path: Path) -> None:
        # Opening without newline="" produces \r\r\n on Windows, which shows
        # up as an empty row in Excel.
        path = tmp_path / "loans.csv"
        export_loans_csv([make_loan()], path)
        assert b"\r\r\n" not in path.read_bytes()

    def test_written_with_a_bom_for_excel(self, tmp_path: Path) -> None:
        path = tmp_path / "loans.csv"
        export_loans_csv([], path)
        assert path.read_bytes().startswith(b"\xef\xbb\xbf")


# --------------------------------------------------------------------------- #
# Against real repository output
# --------------------------------------------------------------------------- #
class TestWithRealLoans:
    @pytest.fixture
    def seeded(self, patients: PatientRepo, loans: LoanRepo, admin: User) -> LoanRepo:
        patients.add(Patient("00123", "Doe", "Jane", "Box 1"))
        patients.add(Patient("00456", "Roe", "John", "Box 2"))
        loans.borrow("00123", "Zandi", "IT", "audit", recorded_by=admin.id)
        loans.borrow("00456", "Other", "Records", recorded_by=admin.id)
        return loans

    def test_exports_loans_straight_from_the_repository(
        self, seeded: LoanRepo, tmp_path: Path
    ) -> None:
        path = tmp_path / "loans.csv"
        export_loans_csv(seeded.active(), path)
        rows = read_rows(path)
        assert len(rows) == 3
        assert {row[0] for row in rows[1:]} == {"00123", "00456"}

    def test_the_recorder_is_named_not_numbered(
        self, seeded: LoanRepo, tmp_path: Path
    ) -> None:
        path = tmp_path / "loans.csv"
        export_loans_csv(seeded.active(), path)
        assert read_rows(path)[1][7] == "Ada Admin"

    def test_a_loan_with_no_reason_exports_blank(
        self, seeded: LoanRepo, tmp_path: Path
    ) -> None:
        path = tmp_path / "loans.csv"
        export_loans_csv(seeded.by_borrower("Other"), path)
        assert read_rows(path)[1][4] == ""

    def test_a_date_range_report_exports(
        self, seeded: LoanRepo, tmp_path: Path
    ) -> None:
        from datetime import date
        path = tmp_path / "loans.csv"
        export_loans_csv(seeded.between(date.today(), date.today()), path)
        assert len(read_rows(path)) == 3
