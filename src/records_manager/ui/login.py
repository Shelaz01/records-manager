"""Login screen."""
from __future__ import annotations

import tkinter as tk
from typing import TYPE_CHECKING
from tkinter import ttk

from ..db import RecordsError
from . import assets, style

if TYPE_CHECKING:
    from ..app import App


class LoginScreen(ttk.Frame):
    """Asks for a username and password and hands the user to the main window."""

    def __init__(self, app: App) -> None:
        super().__init__(app, padding=style.PAD_LARGE)
        self.app = app

        card = ttk.Frame(self, padding=style.PAD_LARGE)
        card.place(relx=0.5, rely=0.5, anchor="center")

        self._icon = assets.load_icon(self, 64)
        if self._icon is not None:
            ttk.Label(card, image=self._icon).grid(
                row=0, column=0, columnspan=2, pady=(0, style.PAD))

        ttk.Label(card, text="Records Manager", style="Title.TLabel").grid(
            row=1, column=0, columnspan=2)
        ttk.Label(card, text="Sign in to continue", style="Muted.TLabel").grid(
            row=2, column=0, columnspan=2, pady=(style.PAD_TINY, style.PAD_LARGE))

        ttk.Label(card, text="Username", style="FieldLabel.TLabel").grid(
            row=3, column=0, sticky="w", padx=(0, style.PAD), pady=style.PAD_SMALL)
        self._username = ttk.Entry(card)
        self._username.grid(row=3, column=1, sticky="ew", pady=style.PAD_SMALL)

        ttk.Label(card, text="Password", style="FieldLabel.TLabel").grid(
            row=4, column=0, sticky="w", padx=(0, style.PAD), pady=style.PAD_SMALL)
        self._password = ttk.Entry(card, show="•")
        self._password.grid(row=4, column=1, sticky="ew", pady=style.PAD_SMALL)

        self._error = ttk.Label(card, text="", style="Danger.TLabel",
                                wraplength=300)
        self._error.grid(row=5, column=0, columnspan=2, sticky="w",
                         pady=(style.PAD_SMALL, 0))

        ttk.Button(card, text="Sign in", style="Accent.TButton",
                   command=self._sign_in).grid(
            row=6, column=0, columnspan=2, sticky="ew", pady=(style.PAD, 0))

        card.columnconfigure(1, weight=1, minsize=220)
        self.bind_all("<Return>", self._on_return)
        self.after(50, self._username.focus_set)

    def _on_return(self, _event: tk.Event) -> None:
        self._sign_in()

    def _sign_in(self) -> None:
        username = self._username.get().strip()
        password = self._password.get()
        if not (username and password):
            self._error.configure(text="Enter your username and password.")
            return

        try:
            user = self.app.users.authenticate(username, password)
        except RecordsError as error:
            self._error.configure(text=str(error))
            return

        if user is None:
            # Deliberately not saying which of the two was wrong.
            self._error.configure(text="Incorrect username or password.")
            self._password.delete(0, "end")
            self._password.focus_set()
            return

        self.unbind_all("<Return>")
        self.app.show_main(user)


