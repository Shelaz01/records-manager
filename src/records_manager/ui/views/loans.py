"""The loans view: files currently out, files already returned."""
from __future__ import annotations

import tkinter as tk
from typing import TYPE_CHECKING
from tkinter import ttk

from ...db import Loan, RecordsError
from .. import style
from ..widgets import (DataTable, PlaceholderEntry, _centre_on_parent,
                       confirm, show_error)

if TYPE_CHECKING:
    from ...app import App

ACTIVE_COLUMNS = ("Hospital No", "Patient", "Borrower", "Department", "Reason",
                  "Borrowed On", "Days Out", "Recorded By")
#: Sized to fit the content area without a horizontal scrollbar at the
#: default window width.
ACTIVE_WIDTHS = (95, 145, 135, 110, 135, 100, 75, 115)

RETURNED_COLUMNS = ("Hospital No", "Patient", "Borrower", "Department",
                    "Borrowed On", "Returned On", "Recorded By")
RETURNED_WIDTHS = (95, 155, 145, 120, 105, 105, 125)

#: Index of the Days Out column, which the active tab opens sorted on.
DAYS_OUT_COLUMN = 6

DEPARTMENTS = ("Outpatients", "Theatre", "Maternity", "Radiology",
               "Paediatrics", "Records", "Audit", "Pharmacy")


class BorrowDialog(tk.Toplevel):
    """Book a file out by its number, resolving it as the number is typed.

    This view lists loans rather than files, so there is no row to select:
    the number is typed. Typing it blind is how a file gets booked out
    against the wrong record, so the register is consulted as you go and
    Borrow stays shut until the number names a file that is actually in.

    Read :attr:`result` afterwards: the entered values, or None if cancelled.
    """

    def __init__(self, master: tk.Misc, app: App) -> None:
        super().__init__(master)
        self.app = app
        self.result: dict[str, str] | None = None
        self._available = False

        self.title("Borrow a file")
        self.transient(master.winfo_toplevel())
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", self._cancel)

        body = ttk.Frame(self, padding=style.PAD_LARGE)
        body.pack(fill="both", expand=True)
        body.columnconfigure(1, weight=1, minsize=260)

        ttk.Label(body, text="Borrow a file", style="Heading.TLabel").grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, style.PAD))

        self._values = {name: tk.StringVar() for name in
                        ("hospital_num", "borrower", "department", "reason")}

        ttk.Label(body, text="Hospital number *",
                  style="FieldLabel.TLabel").grid(row=1, column=0, sticky="w",
                                                  padx=(0, style.PAD))
        number = ttk.Entry(body, textvariable=self._values["hospital_num"])
        number.grid(row=1, column=1, sticky="ew")

        #: What the register says about the number typed so far.
        self._lookup = ttk.Label(body, text="", style="Muted.TLabel",
                                 wraplength=300, justify="left")
        self._lookup.grid(row=2, column=1, sticky="w",
                          pady=(style.PAD_TINY, style.PAD_SMALL))

        rows = (("borrower", "Borrower", True),
                ("department", "Department", True),
                ("reason", "Reason", False))
        for index, (key, label, required) in enumerate(rows, start=3):
            ttk.Label(body, text=f"{label}{' *' if required else ''}",
                      style="FieldLabel.TLabel").grid(
                row=index, column=0, sticky="w", padx=(0, style.PAD),
                pady=style.PAD_SMALL)
            if key == "department":
                widget = ttk.Combobox(body, textvariable=self._values[key],
                                      values=list(DEPARTMENTS))
            else:
                widget = ttk.Entry(body, textvariable=self._values[key])
            widget.grid(row=index, column=1, sticky="ew", pady=style.PAD_SMALL)

        self._error = ttk.Label(body, text="", style="Danger.TLabel")
        self._error.grid(row=6, column=0, columnspan=2, sticky="w",
                         pady=(style.PAD_SMALL, 0))

        buttons = ttk.Frame(body)
        buttons.grid(row=7, column=0, columnspan=2, sticky="e",
                     pady=(style.PAD, 0))
        ttk.Button(buttons, text="Cancel", command=self._cancel).pack(
            side="left", padx=(0, style.PAD_SMALL))
        self._submit_button = ttk.Button(buttons, text="Borrow",
                                         style="Accent.TButton",
                                         command=self._submit)
        self._submit_button.pack(side="left")

        self._values["hospital_num"].trace_add("write",
                                               lambda *_: self._resolve())
        self._resolve()

        self.bind("<Return>", lambda _event: self._submit())
        self.bind("<Escape>", lambda _event: self._cancel())
        number.focus_set()
        _centre_on_parent(self, master)
        self.grab_set()
        self.wait_window(self)

    # -- lookup ------------------------------------------------------------- #
    def _resolve(self) -> None:
        """Say what the typed number refers to, and whether it can go out."""
        number = self._values["hospital_num"].get().strip()
        self._available = False

        if not number:
            self._lookup.configure(text="", style="Muted.TLabel")
            self._update_button()
            return

        try:
            patient = self.app.patients.get(number)
            loan = self._active_loan(number) if patient is not None else None
        except RecordsError as error:
            self._lookup.configure(text=str(error), style="Danger.TLabel")
            self._update_button()
            return

        if patient is None:
            self._lookup.configure(text="No file with that number",
                                   style="Muted.TLabel")
        elif loan is not None:
            self._lookup.configure(
                text=f"{patient.surname}, {patient.first_names} — "
                     f"{patient.box_no}, out with {loan.borrower} since "
                     f"{loan.borrowed_on}",
                style="Warning.TLabel")
        else:
            self._available = True
            self._lookup.configure(
                text=f"{patient.surname}, {patient.first_names} — "
                     f"{patient.box_no}, available",
                style="TLabel")
        self._update_button()

    def _active_loan(self, number: str) -> Loan | None:
        return next((loan for loan in self.app.loans.active()
                     if loan.hospital_num == number), None)

    def _update_button(self) -> None:
        self._submit_button.state(["!disabled"] if self._available
                                  else ["disabled"])

    # -- result -------------------------------------------------------------- #
    def _submit(self) -> None:
        if not self._available:
            return
        values = {key: variable.get().strip()
                  for key, variable in self._values.items()}
        missing = [label for key, label in (("borrower", "Borrower"),
                                            ("department", "Department"))
                   if not values[key]]
        if missing:
            self._error.configure(text=f"Please fill in: {', '.join(missing)}.")
            return
        self.result = values
        self.destroy()

    def _cancel(self) -> None:
        self.result = None
        self.destroy()


class LoansView(ttk.Frame):
    """Active and returned loans, with borrowing and returning."""

    def __init__(self, master: tk.Misc, app: App) -> None:
        super().__init__(master)
        self.app = app

        self.rowconfigure(2, weight=1)
        self.columnconfigure(0, weight=1)

        self._build_header()
        self._build_tabs()
        self._build_buttons()

        self.refresh()

    # -- layout ------------------------------------------------------------- #
    def _build_header(self) -> None:
        header = ttk.Frame(self)
        header.grid(row=0, column=0, sticky="ew", pady=(0, style.PAD))
        header.columnconfigure(1, weight=1)

        ttk.Label(header, text="Loans", style="Heading.TLabel").grid(
            row=0, column=0, sticky="w")

        search = ttk.Frame(header)
        search.grid(row=0, column=1, sticky="e")
        self._search = PlaceholderEntry(
            search, "Search by borrower, patient or hospital number", width=42,
            on_change=lambda _text: self.refresh())
        self._search.pack(side="left")
        ttk.Button(search, text="Clear", command=self._clear_search).pack(
            side="left", padx=(style.PAD_SMALL, 0))

        self._count = ttk.Label(self, text="", style="Muted.TLabel")
        self._count.grid(row=1, column=0, sticky="w", pady=(0, style.PAD_SMALL))

    def _build_tabs(self) -> None:
        self._tabs = ttk.Notebook(self)
        self._tabs.grid(row=2, column=0, sticky="nsew")

        active_page = ttk.Frame(self._tabs, padding=style.PAD_SMALL)
        returned_page = ttk.Frame(self._tabs, padding=style.PAD_SMALL)
        for page in (active_page, returned_page):
            page.rowconfigure(0, weight=1)
            page.columnconfigure(0, weight=1)

        self._tabs.add(active_page, text="Active")
        self._tabs.add(returned_page, text="Returned")
        self._tabs.bind("<<NotebookTabChanged>>",
                        lambda _event: self._update_buttons())

        self._active: DataTable[Loan] = DataTable(
            active_page, ACTIVE_COLUMNS, widths=ACTIVE_WIDTHS,
            on_activate=lambda _loan: self._return_loan(),
            on_select=lambda _loan: self._update_buttons())
        self._active.grid(row=0, column=0, sticky="nsew")
        # Longest out first: the files most worth chasing are at the top.
        self._active.sort_by(DAYS_OUT_COLUMN, reverse=True)

        self._returned: DataTable[Loan] = DataTable(
            returned_page, RETURNED_COLUMNS, widths=RETURNED_WIDTHS,
            on_select=lambda _loan: self._update_buttons())
        self._returned.grid(row=0, column=0, sticky="nsew")

    def _build_buttons(self) -> None:
        bar = ttk.Frame(self)
        bar.grid(row=3, column=0, sticky="ew", pady=(style.PAD, 0))

        self._borrow_button = ttk.Button(bar, text="Borrow a file",
                                         style="Accent.TButton",
                                         command=self._borrow)
        self._borrow_button.pack(side="left")

        self._return_button = ttk.Button(bar, text="Return selected",
                                         command=self._return_loan)
        self._return_button.pack(side="left", padx=(style.PAD_SMALL, 0))


    # -- data --------------------------------------------------------------- #
    @property
    def _showing_active(self) -> bool:
        return self._tabs.index(self._tabs.select()) == 0

    @property
    def _table(self) -> DataTable[Loan]:
        return self._active if self._showing_active else self._returned

    def refresh(self) -> None:
        """Reload both tabs, applying the current search term."""
        try:
            active = self._filter(self.app.loans.active())
            returned = self._filter(self.app.loans.returned())
        except RecordsError as error:
            show_error(self, "Could not load loans", str(error))
            return

        today = _today()
        self._active.set_rows(
            active,
            key=lambda loan: str(loan.id),
            values=lambda loan: (
                loan.hospital_num, loan.patient_name, loan.borrower,
                loan.department, loan.reason or "", loan.borrowed_on,
                _days_out(loan, today), loan.recorded_by or ""),
        )
        self._returned.set_rows(
            returned,
            key=lambda loan: str(loan.id),
            values=lambda loan: (
                loan.hospital_num, loan.patient_name, loan.borrower,
                loan.department, loan.borrowed_on, loan.returned_on or "",
                loan.recorded_by or ""),
        )

        self._tabs.tab(0, text=f"Active ({len(active)})")
        self._tabs.tab(1, text=f"Returned ({len(returned)})")
        self._describe(active, returned)
        self._update_buttons()

    def _filter(self, loans: list[Loan]) -> list[Loan]:
        """Narrow a list to the search term, matching the columns on show."""
        term = self._search.value.strip().casefold()
        if not term:
            return loans
        return [loan for loan in loans
                if term in " ".join((loan.hospital_num, loan.patient_name,
                                     loan.borrower, loan.department,
                                     loan.reason or "")).casefold()]

    def _describe(self, active: list[Loan], returned: list[Loan]) -> None:
        term = self._search.value.strip()
        if term:
            self._count.configure(
                text=f"{len(active)} active and {len(returned)} returned "
                     f"loans match “{term}”")
        else:
            files = "file is" if len(active) == 1 else "files are"
            self._count.configure(text=f"{len(active)} {files} currently out")

    def _clear_search(self) -> None:
        self._search.clear()
        self._search.focus_set()

    def _update_buttons(self) -> None:
        """Returning applies to an active loan only."""
        can_return = self._showing_active and self._active.selected() is not None
        self._return_button.state(["!disabled"] if can_return else ["disabled"])

    # -- actions ------------------------------------------------------------ #
    def _borrow(self) -> None:
        dialog = BorrowDialog(self, self.app)
        if dialog.result is None:
            return

        recorded_by = self.app.user.id if self.app.user is not None else None
        number = dialog.result["hospital_num"]
        try:
            self.app.loans.borrow(number, dialog.result["borrower"],
                                  dialog.result["department"],
                                  dialog.result["reason"] or None, recorded_by)
        except RecordsError as error:
            show_error(self, "Could not borrow file", str(error))
            return

        self.app.set_status(f"{number} booked out to {dialog.result['borrower']}")
        self.refresh()

    def _return_loan(self) -> None:
        loan = self._active.selected()
        if loan is None or not self._showing_active:
            return

        # The borrower is named because the loan keeps them: whoever is
        # signed in can return a file, and it stays on their record.
        if not confirm(
            self, "Return file",
            f"Return {loan.hospital_num} ({loan.patient_name}), borrowed by "
            f"{loan.borrower} on {loan.borrowed_on}?",
            confirm_text="Mark returned", kind="info",
        ):
            return

        try:
            self.app.loans.return_loan(loan.id)
        except RecordsError as error:
            # Someone else may have returned it since this table was drawn.
            show_error(self, "Could not return file", str(error))
            self.refresh()
            return

        self.app.set_status(f"{loan.hospital_num} returned by {loan.borrower}")
        self.refresh()


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _today() -> str:
    from datetime import date
    return date.today().isoformat()


def _days_out(loan: Loan, today: str) -> int:
    """How long a file has been out, in whole days."""
    from datetime import date
    try:
        borrowed = date.fromisoformat(loan.borrowed_on)
    except ValueError:
        return 0
    return max((date.fromisoformat(today) - borrowed).days, 0)


