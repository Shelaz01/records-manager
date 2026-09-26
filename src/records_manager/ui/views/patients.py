"""The patients view: search the file register, edit records, book files out."""
from __future__ import annotations

import tkinter as tk
from typing import TYPE_CHECKING
from tkinter import ttk

from ...db import Patient, RecordsError
from .. import style
from ..widgets import (DataTable, Field, FormDialog, PlaceholderEntry, confirm,
                       show_error)
from .scan import ScanDialog

if TYPE_CHECKING:
    from ...app import App

COLUMNS = ("Hospital No", "Surname", "First Names", "Box", "Status")
WIDTHS = (130, 200, 240, 110, 130)

#: Departments offered in the borrow dialog. Free text is still allowed.
DEPARTMENTS = ("Outpatients", "Theatre", "Maternity", "Radiology",
               "Paediatrics", "Records", "Audit", "Pharmacy")


class PatientsView(ttk.Frame):
    """Lists patients, with the actions that operate on the selected one."""

    def __init__(self, master: tk.Misc, app: App) -> None:
        super().__init__(master)
        self.app = app
        self._on_loan: set[str] = set()

        self.rowconfigure(2, weight=1)
        self.columnconfigure(0, weight=1)

        self._build_header()
        self._build_table()
        self._build_buttons()

        self.refresh()

    # -- layout ------------------------------------------------------------- #
    def _build_header(self) -> None:
        header = ttk.Frame(self)
        header.grid(row=0, column=0, sticky="ew", pady=(0, style.PAD))
        header.columnconfigure(1, weight=1)

        ttk.Label(header, text="Patients", style="Heading.TLabel").grid(
            row=0, column=0, sticky="w")

        search = ttk.Frame(header)
        search.grid(row=0, column=1, sticky="e")

        self._search_entry = PlaceholderEntry(
            search, "Search by name or hospital number", width=36,
            on_change=lambda _text: self.refresh())
        self._search_entry.pack(side="left")

        ttk.Button(search, text="Clear", command=self._clear_search).pack(
            side="left", padx=(style.PAD_SMALL, 0))

        self._count = ttk.Label(self, text="", style="Muted.TLabel")
        self._count.grid(row=1, column=0, sticky="w", pady=(0, style.PAD_SMALL))

    def _build_table(self) -> None:
        self._table: DataTable[Patient] = DataTable(
            self, COLUMNS, widths=WIDTHS,
            on_activate=lambda _patient: self._edit(),
            on_select=lambda _patient: self._update_buttons(),
            on_delete=lambda _patient: self._delete(),
        )
        self._table.tag_configure("on_loan", foreground=style.WARNING)
        self._table.grid(row=2, column=0, sticky="nsew")

    def _build_buttons(self) -> None:
        bar = ttk.Frame(self)
        bar.grid(row=3, column=0, sticky="ew", pady=(style.PAD, 0))

        self._add_button = ttk.Button(bar, text="Add", style="Accent.TButton",
                                      command=self._add)
        self._add_button.pack(side="left")

        # Always available: a form can be attached and typed up even where
        # there is no scanner and no text recognition.
        ttk.Button(bar, text="Scan form", command=self._scan).pack(
            side="left", padx=(style.PAD_SMALL, 0))

        self._buttons: dict[str, ttk.Button] = {}
        for label, command in (("Edit", self._edit), ("Delete", self._delete),
                               ("Borrow", self._borrow)):
            button = ttk.Button(bar, text=label, command=command)
            button.pack(side="left", padx=(style.PAD_SMALL, 0))
            self._buttons[label] = button

        self._update_buttons()

    # -- data --------------------------------------------------------------- #
    def refresh(self) -> None:
        """Reload the table, applying the current search term."""
        term = self._search_entry.value.strip()
        try:
            patients = (self.app.patients.search(term) if term
                        else self.app.patients.list_all())
            self._on_loan = {loan.hospital_num for loan in self.app.loans.active()}
        except RecordsError as error:
            self._show_error("Could not load patients", error)
            return

        self._table.set_rows(
            patients,
            key=lambda patient: patient.hospital_num,
            values=lambda patient: (
                patient.hospital_num,
                patient.surname,
                patient.first_names,
                patient.box_no,
                "On loan" if patient.hospital_num in self._on_loan else "Available",
            ),
            tags=lambda patient: (
                ("on_loan",) if patient.hospital_num in self._on_loan else ()),
        )
        self._count.configure(text=self._describe_count(len(patients), term))
        self._update_buttons()

    @staticmethod
    def _describe_count(count: int, term: str) -> str:
        if term:
            match = "file matches" if count == 1 else "files match"
            return f"{count} {match} “{term}”"
        return f"{count} file" + ("" if count == 1 else "s") + " in the register"

    def _clear_search(self) -> None:
        self._search_entry.clear()
        self._search_entry.focus_set()

    def _update_buttons(self) -> None:
        """Enable the per-record actions only when a row is selected."""
        patient = self._table.selected()
        state = ["!disabled"] if patient is not None else ["disabled"]
        for button in self._buttons.values():
            button.state(state)
        if patient is not None and patient.hospital_num in self._on_loan:
            self._buttons["Borrow"].state(["disabled"])

    # -- actions ------------------------------------------------------------ #
    def _add(self) -> None:
        dialog = FormDialog(self, "Add patient", (
            Field("hospital_num", "Hospital number"),
            Field("surname", "Surname"),
            Field("first_names", "First names"),
            Field("box_no", "Box number"),
        ), submit_text="Add")
        if dialog.result is None:
            return

        patient = Patient(
            hospital_num=dialog.result["hospital_num"],
            surname=dialog.result["surname"],
            first_names=dialog.result["first_names"],
            box_no=dialog.result["box_no"],
        )
        if self._attempt("Could not add patient", self.app.patients.add, patient):
            self._announce(f"Added {patient.hospital_num}")
            self.refresh()

    def _scan(self) -> None:
        dialog = ScanDialog(self, self.app)
        if dialog.saved:
            self.refresh()

    def _edit(self) -> None:
        patient = self._table.selected()
        if patient is None:
            return

        dialog = FormDialog(self, f"Edit {patient.hospital_num}", (
            Field("hospital_num", "Hospital number", initial=patient.hospital_num),
            Field("surname", "Surname", initial=patient.surname),
            Field("first_names", "First names", initial=patient.first_names),
            Field("box_no", "Box number", initial=patient.box_no),
        ))
        if dialog.result is None:
            return

        updated = Patient(
            hospital_num=dialog.result["hospital_num"],
            surname=dialog.result["surname"],
            first_names=dialog.result["first_names"],
            box_no=dialog.result["box_no"],
            scan_path=patient.scan_path,
        )
        # The original number is what identifies the row: reading it back from
        # the table would lose a leading zero.
        if self._attempt("Could not save changes", self.app.patients.update,
                         patient.hospital_num, updated):
            self._announce(f"Saved {updated.hospital_num}")
            self.refresh()

    def _delete(self) -> None:
        patient = self._table.selected()
        if patient is None:
            return

        # Say why it cannot be deleted before asking the user to confirm
        # something that was never going to happen.
        try:
            if self.app.loans.has_history(patient.hospital_num):
                show_error(
                    self, "Cannot delete this file",
                    f"File {patient.hospital_num} has borrowing history, so "
                    "its record has to be kept. Files can only be deleted if "
                    "they have never been borrowed.")
                return
        except RecordsError as error:
            self._show_error("Could not check borrowing history", error)
            return

        confirmed = confirm(
            self, "Delete file",
            f"Delete the record for {patient.surname}, {patient.first_names} "
            f"({patient.hospital_num})? This cannot be undone.",
            confirm_text="Delete", destructive=True,
        )
        if not confirmed:
            return

        if self._attempt("Could not delete file", self.app.patients.delete,
                         patient.hospital_num):
            self._announce(f"Deleted {patient.hospital_num}")
            self.refresh()

    def _borrow(self) -> None:
        patient = self._table.selected()
        if patient is None:
            return

        dialog = FormDialog(self, f"Borrow {patient.hospital_num}", (
            Field("hospital_num", "Hospital number",
                  initial=patient.hospital_num, display=True),
            Field("patient", "Patient",
                  initial=f"{patient.surname}, {patient.first_names}",
                  display=True),
            Field("borrower", "Borrower"),
            Field("department", "Department", choices=DEPARTMENTS, strict=False),
            Field("reason", "Reason", required=False),
        ), submit_text="Borrow")
        if dialog.result is None:
            return

        recorded_by = self.app.user.id if self.app.user is not None else None
        if self._attempt(
            "Could not borrow file",
            self.app.loans.borrow,
            patient.hospital_num,
            dialog.result["borrower"],
            dialog.result["department"],
            dialog.result["reason"] or None,
            recorded_by,
        ):
            self._announce(f"{patient.hospital_num} booked out to "
                           f"{dialog.result['borrower']}")
            self.refresh()

    # -- plumbing ----------------------------------------------------------- #
    def _attempt(self, title: str, action, *args) -> bool:
        """Run a repository call, reporting any domain error to the user."""
        try:
            action(*args)
        except RecordsError as error:
            self._show_error(title, error)
            return False
        return True

    def _show_error(self, title: str, error: RecordsError) -> None:
        show_error(self, title, str(error))

    def _announce(self, message: str) -> None:
        self.app.set_status(message)
