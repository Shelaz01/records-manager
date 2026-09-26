"""First-run screen: create the administrator account.

Shown only while ``UserRepo.has_users()`` is false. There is no default or
hardcoded account, so this is how the very first user gets in.
"""
from __future__ import annotations

import tkinter as tk
from typing import TYPE_CHECKING
from tkinter import ttk

from ..db import RecordsError
from . import assets, style

if TYPE_CHECKING:
    from ..app import App

#: Matches the check in :meth:`SetupScreen._create`.
MIN_PASSWORD_LENGTH = 8


class SetupScreen(ttk.Frame):
    """Collects the details of the first administrator."""

    def __init__(self, app: App) -> None:
        super().__init__(app, padding=style.PAD_LARGE)
        self.app = app

        card = ttk.Frame(self, padding=style.PAD_LARGE)
        card.place(relx=0.5, rely=0.5, anchor="center")

        # Icon and headings are centred over the field grid, matching login.
        self._icon = assets.load_icon(self, 64)
        if self._icon is not None:
            ttk.Label(card, image=self._icon).grid(
                row=0, column=0, columnspan=2, pady=(0, style.PAD))

        ttk.Label(card, text="Welcome", style="Title.TLabel").grid(
            row=1, column=0, columnspan=2)
        ttk.Label(
            card,
            text="No accounts exist yet. Create the administrator account\n"
                 "to finish setting up Records Manager.",
            style="Muted.TLabel", justify="center",
        ).grid(row=2, column=0, columnspan=2, pady=(style.PAD_SMALL,
                                                    style.PAD_LARGE))

        self._name = self._row(card, 3, "Full name")
        self._username = self._row(card, 4, "Username")
        self._password = self._row(card, 5, "Password", secret=True)

        ttk.Label(card, text=f"At least {MIN_PASSWORD_LENGTH} characters.",
                  style="Hint.TLabel").grid(row=6, column=1, sticky="w",
                                            pady=(0, style.PAD_SMALL))

        self._confirm = self._row(card, 7, "Confirm password", secret=True)

        self._error = ttk.Label(card, text="", style="Danger.TLabel",
                                wraplength=320)
        self._error.grid(row=8, column=0, columnspan=2, sticky="w",
                         pady=(style.PAD_SMALL, 0))

        create = ttk.Button(card, text="Create account", style="Accent.TButton",
                            command=self._create)
        create.grid(row=9, column=0, columnspan=2, sticky="ew",
                    pady=(style.PAD, 0))

        card.columnconfigure(1, weight=1, minsize=240)
        self.bind_all("<Return>", self._on_return)
        self.after(50, self._name.focus_set)

    def _row(self, parent: tk.Misc, row: int, label: str, *,
             secret: bool = False) -> ttk.Entry:
        ttk.Label(parent, text=label, style="FieldLabel.TLabel").grid(
            row=row, column=0, sticky="w", padx=(0, style.PAD),
            pady=style.PAD_SMALL)
        entry = ttk.Entry(parent, show="•" if secret else "")
        entry.grid(row=row, column=1, sticky="ew", pady=style.PAD_SMALL)
        return entry

    def _on_return(self, _event: tk.Event) -> None:
        self._create()

    def _create(self) -> None:
        name = self._name.get().strip()
        username = self._username.get().strip()
        password = self._password.get()
        confirm = self._confirm.get()

        if not (name and username and password):
            self._fail("Please fill in every field.")
            return
        if password != confirm:
            self._fail("The passwords do not match.")
            return
        if len(password) < MIN_PASSWORD_LENGTH:
            self._fail(f"Use a password of at least {MIN_PASSWORD_LENGTH} "
                       "characters.")
            return

        try:
            user = self.app.users.create(name, username, password, role="admin")
        except RecordsError as error:
            self._fail(str(error))
            return

        self.unbind_all("<Return>")
        self.app.show_main(user)

    def _fail(self, message: str) -> None:
        self._error.configure(text=message)
