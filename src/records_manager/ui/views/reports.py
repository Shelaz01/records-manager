"""The reports view: pick a date range or a borrower, preview, export."""
from __future__ import annotations

import tkinter as tk
from datetime import date, timedelta
from pathlib import Path
from typing import TYPE_CHECKING
from tkinter import filedialog, ttk

from tkcalendar import DateEntry

from ...db import Loan, RecordsError
from ...reports import COLUMNS, export_loans_csv, loan_to_row
from .. import style
from ..widgets import DataTable, PlaceholderEntry, show_error, show_info

if TYPE_CHECKING:
    from ...app import App

#: Sized so the eight export columns fit without a horizontal scrollbar.
WIDTHS = (88, 140, 128, 104, 122, 98, 98, 108)

#: How far back the date range reaches when the view opens.
DEFAULT_DAYS = 30


class ReportsView(ttk.Frame):
    """Build a loan report, look at it, then write it out as CSV."""

    def __init__(self, master: tk.Misc, app: App) -> None:
        super().__init__(master)
        self.app = app
        self._loans: list[Loan] = []

        self.rowconfigure(3, weight=1)
        self.columnconfigure(0, weight=1)

        ttk.Label(self, text="Reports", style="Heading.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, style.PAD))

        self._build_controls()
        self._count = ttk.Label(self, text="", style="Muted.TLabel")
        self._count.grid(row=2, column=0, sticky="w", pady=(0, style.PAD_SMALL))

        self._table: DataTable[Loan] = DataTable(self, COLUMNS, widths=WIDTHS)
        self._table.grid(row=3, column=0, sticky="nsew")

        self._build_buttons()
        self.run_report()

    # -- layout ------------------------------------------------------------- #
    def _build_controls(self) -> None:
        box = ttk.LabelFrame(self, text="Report", padding=style.PAD)
        box.grid(row=1, column=0, sticky="ew", pady=(0, style.PAD))

        self._mode = tk.StringVar(value="range")
        ttk.Radiobutton(box, text="By date borrowed", value="range",
                        variable=self._mode, command=self._mode_changed).grid(
            row=0, column=0, sticky="w", padx=(0, style.PAD))

        today = date.today()
        self._from = DateEntry(box, date_pattern="yyyy-mm-dd", width=12,
                               maxdate=today)
        self._from.set_date(today - timedelta(days=DEFAULT_DAYS))
        self._from.grid(row=0, column=1, padx=(0, style.PAD_SMALL))

        ttk.Label(box, text="to").grid(row=0, column=2, padx=(0, style.PAD_SMALL))

        self._to = DateEntry(box, date_pattern="yyyy-mm-dd", width=12,
                             maxdate=today)
        self._to.set_date(today)
        self._to.grid(row=0, column=3, padx=(0, style.PAD))

        ttk.Radiobutton(box, text="By borrower", value="borrower",
                        variable=self._mode, command=self._mode_changed).grid(
            row=1, column=0, sticky="w", pady=(style.PAD_SMALL, 0))

        self._borrower = PlaceholderEntry(box, "Borrower's name", width=28)
        self._borrower.grid(row=1, column=1, columnspan=3, sticky="w",
                            pady=(style.PAD_SMALL, 0))

        ttk.Button(box, text="Run report", style="Accent.TButton",
                   command=self.run_report).grid(
            row=0, column=4, rowspan=2, padx=(style.PAD, 0))

        self._mode_changed()

    def _build_buttons(self) -> None:
        bar = ttk.Frame(self)
        bar.grid(row=4, column=0, sticky="ew", pady=(style.PAD, 0))

        self._export = ttk.Button(bar, text="Export CSV…", command=self._export_csv)
        self._export.pack(side="left")

        self._summary = ttk.Label(bar, text="", style="Muted.TLabel")
        self._summary.pack(side="right")

    def _mode_changed(self) -> None:
        """Grey out the inputs that do not belong to the chosen report."""
        by_range = self._mode.get() == "range"
        for widget in (self._from, self._to):
            widget.configure(state="normal" if by_range else "disabled")
        self._borrower.state(["disabled"] if by_range else ["!disabled"])

    # -- running ------------------------------------------------------------ #
    def run_report(self) -> None:
        """Fetch the rows for the chosen report and show them."""
        try:
            if self._mode.get() == "range":
                start, end = self._from.get_date(), self._to.get_date()
                if start > end:
                    show_error(self, "Check the dates",
                               "The start date is after the end date.")
                    return
                self._loans = self.app.loans.between(start, end)
                described = f"borrowed between {start} and {end}"
            else:
                name = self._borrower.value.strip()
                if not name:
                    show_error(self, "Name needed",
                               "Enter the borrower's name to run this report.")
                    return
                self._loans = self.app.loans.by_borrower(name)
                described = f"borrowed by {name}"
        except RecordsError as error:
            show_error(self, "Could not run the report", str(error))
            return

        self._table.set_rows(self._loans, key=lambda loan: str(loan.id),
                             values=loan_to_row)
        count = len(self._loans)
        loans = "loan" if count == 1 else "loans"
        self._count.configure(text=f"{count} {loans} {described}")

        returned = sum(1 for loan in self._loans if not loan.is_active)
        self._summary.configure(
            text=f"{count - returned} still out, {returned} returned"
            if count else "")
        self._export.state(["!disabled"] if count else ["disabled"])

    # -- exporting ----------------------------------------------------------- #
    def _export_csv(self) -> None:
        if not self._loans:
            return

        chosen = filedialog.asksaveasfilename(
            parent=self, title="Export report", defaultextension=".csv",
            initialfile=self._suggested_name(),
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")])
        if not chosen:
            return

        try:
            export_loans_csv(self._loans, Path(chosen))
        except OSError as error:
            show_error(self, "Could not export the report", str(error))
            return

        count = len(self._loans)
        self.app.set_status(f"Exported {count} loans to {Path(chosen).name}")
        show_info(self, "Report exported",
                  f"{count} loans written to {Path(chosen).name}.")

    def _suggested_name(self) -> str:
        """A file name that says what the report is, without being asked."""
        if self._mode.get() == "range":
            return f"loans-{self._from.get_date()}-to-{self._to.get_date()}.csv"
        safe = "-".join(self._borrower.value.split()).lower() or "borrower"
        return f"loans-{safe}.csv"
