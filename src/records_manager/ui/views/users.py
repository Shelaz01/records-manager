"""The users view: staff accounts. Administrators only."""
from __future__ import annotations

import tkinter as tk
from typing import TYPE_CHECKING
from tkinter import ttk

from ...db import RecordsError, User
from .. import style
from ..widgets import DataTable, Field, FormDialog, confirm, show_error

if TYPE_CHECKING:
    from ...app import App

COLUMNS = ("Name", "Username", "Role", "Email")
WIDTHS = (220, 170, 120, 260)

ROLES = ("user", "admin")

MIN_PASSWORD_LENGTH = 8


class UsersView(ttk.Frame):
    """Lists staff accounts, and adds, edits or removes them."""

    def __init__(self, master: tk.Misc, app: App) -> None:
        super().__init__(master)
        self.app = app

        self.rowconfigure(2, weight=1)
        self.columnconfigure(0, weight=1)

        ttk.Label(self, text="Users", style="Heading.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, style.PAD_SMALL))
        self._count = ttk.Label(self, text="", style="Muted.TLabel")
        self._count.grid(row=1, column=0, sticky="w", pady=(0, style.PAD_SMALL))

        self._table: DataTable[User] = DataTable(
            self, COLUMNS, widths=WIDTHS,
            on_select=lambda _user: self._update_buttons())
        self._table.tag_configure("admin", foreground=style.ACCENT)
        self._table.grid(row=2, column=0, sticky="nsew")

        self._build_buttons()
        self.refresh()

    def _build_buttons(self) -> None:
        bar = ttk.Frame(self)
        bar.grid(row=3, column=0, sticky="ew", pady=(style.PAD, 0))

        ttk.Button(bar, text="Add user", style="Accent.TButton",
                   command=self._add).pack(side="left")

        self._buttons: dict[str, ttk.Button] = {}
        for label, command in (("Change password", self._change_password),
                               ("Delete", self._delete)):
            button = ttk.Button(bar, text=label, command=command)
            button.pack(side="left", padx=(style.PAD_SMALL, 0))
            self._buttons[label] = button

        self._update_buttons()

    # -- data --------------------------------------------------------------- #
    def refresh(self) -> None:
        """Reload the account list."""
        try:
            users = self.app.users.list_all()
        except RecordsError as error:
            show_error(self, "Could not load users", str(error))
            return

        self._table.set_rows(
            users,
            key=lambda user: user.username,
            values=lambda user: (user.name, user.username,
                                 "Administrator" if user.is_admin else "User",
                                 user.email or ""),
            tags=lambda user: (("admin",) if user.is_admin else ()),
        )
        admins = sum(1 for user in users if user.is_admin)
        accounts = "account" if len(users) == 1 else "accounts"
        self._count.configure(
            text=f"{len(users)} {accounts}, {admins} with administrator access")
        self._update_buttons()

    def _update_buttons(self) -> None:
        selected = self._table.selected() is not None
        for button in self._buttons.values():
            button.state(["!disabled"] if selected else ["disabled"])

    # -- actions ------------------------------------------------------------ #
    def _add(self) -> None:
        dialog = FormDialog(self, "Add user", (
            Field("name", "Full name"),
            Field("username", "Username"),
            Field("password", "Password", secret=True),
            Field("role", "Role", choices=ROLES, initial="user"),
            Field("email", "Email", required=False),
        ), submit_text="Add")
        if dialog.result is None:
            return

        password = dialog.result["password"]
        if len(password) < MIN_PASSWORD_LENGTH:
            show_error(self, "Password too short",
                       f"Use a password of at least {MIN_PASSWORD_LENGTH} "
                       "characters.")
            return

        try:
            self.app.users.create(dialog.result["name"],
                                  dialog.result["username"], password,
                                  role=dialog.result["role"],
                                  email=dialog.result["email"] or None)
        except RecordsError as error:
            show_error(self, "Could not add user", str(error))
            return

        self.app.set_status(f"Added user {dialog.result['username']}")
        self.refresh()

    def _change_password(self) -> None:
        user = self._table.selected()
        if user is None:
            return

        dialog = FormDialog(self, f"Change password for {user.username}", (
            Field("user", "Account", initial=f"{user.name} ({user.username})",
                  display=True),
            Field("password", "New password", secret=True),
            Field("confirm", "Confirm password", secret=True),
        ), submit_text="Change password")
        if dialog.result is None:
            return

        password = dialog.result["password"]
        if password != dialog.result["confirm"]:
            show_error(self, "Passwords do not match",
                       "The two passwords are different. Try again.")
            return
        if len(password) < MIN_PASSWORD_LENGTH:
            show_error(self, "Password too short",
                       f"Use a password of at least {MIN_PASSWORD_LENGTH} "
                       "characters.")
            return

        try:
            self.app.users.change_password(user.username, password)
        except RecordsError as error:
            show_error(self, "Could not change the password", str(error))
            return

        self.app.set_status(f"Changed the password for {user.username}")

    def _delete(self) -> None:
        user = self._table.selected()
        if user is None:
            return

        signed_in = self.app.user is not None and user.id == self.app.user.id
        warning = (" You are signed in as this account and will be signed out."
                   if signed_in else "")
        if not confirm(
            self, "Delete user",
            f"Delete the account for {user.name} ({user.username})?{warning}",
            confirm_text="Delete", destructive=True,
        ):
            return

        try:
            self.app.users.delete(user.username)
        except RecordsError as error:
            # The last administrator cannot be removed.
            show_error(self, "Could not delete user", str(error))
            return

        self.app.set_status(f"Deleted user {user.username}")
        if signed_in:
            self.app.sign_out()
            return
        # Refresh after the sign-out check: this view is gone in that case.
        self.refresh()
