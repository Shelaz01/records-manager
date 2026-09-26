"""CSV export for loan reports.

Pure data work: no Tkinter here, so the UI can build a preview table from
the same rows it exports and the export itself stays testable.
"""
from __future__ import annotations

import csv
from pathlib import Path

from .db import Loan

#: Column headings, in order. The UI's preview table uses these too, so the
#: report on screen and the exported file can never drift apart.
COLUMNS: tuple[str, ...] = (
    "Hospital No",
    "Patient",
    "Borrower",
    "Department",
    "Reason",
    "Borrowed On",
    "Returned On",
    "Recorded By",
)


def loan_to_row(loan: Loan) -> tuple[str, ...]:
    """Render one loan as a row of strings, aligned with :data:`COLUMNS`.

    Optional fields become an empty cell rather than the string "None", so a
    loan that is still out shows a blank Returned On.
    """
    return (
        loan.hospital_num,
        loan.patient_name,
        loan.borrower,
        loan.department,
        loan.reason or "",
        loan.borrowed_on,
        loan.returned_on or "",
        loan.recorded_by or "",
    )


def export_loans_csv(loans: list[Loan], path: Path) -> None:
    """Write ``loans`` to ``path`` as CSV, replacing any existing file.

    An empty list still writes the header row, so the file says "no loans in
    this range" rather than being mistaken for a failed export.

    Written as UTF-8 with a BOM: these reports get opened in Excel, which
    otherwise misreads non-ASCII names. ``newline=""`` is what the csv module
    requires to avoid a blank line between rows on Windows.
    """
    with Path(path).open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(COLUMNS)
        writer.writerows(loan_to_row(loan) for loan in loans)
