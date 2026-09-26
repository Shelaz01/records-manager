"""The signed-in window: menubar, sidebar, content area and status bar."""
from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING
from tkinter import ttk

from .. import __version__
from . import assets, style
from .views import loans, patients, reports, users
from .widgets import NavButton, show_info

if TYPE_CHECKING:
    from ..app import App


@dataclass(frozen=True)
class NavItem:
    """One sidebar destination."""

    key: str
    label: str
    factory: Callable[..., ttk.Frame]
    admin_only: bool = False


NAV_ITEMS: tuple[NavItem, ...] = (
    NavItem("patients", "Patients", patients.PatientsView),
    NavItem("loans", "Loans", loans.LoansView),
    NavItem("reports", "Reports", reports.ReportsView),
    NavItem("users", "Users", users.UsersView, admin_only=True),
)


class MainWindow(ttk.Frame):
    """Hosts one view at a time; switching destroys the previous one."""

    def __init__(self, app: App) -> None:
        super().__init__(app)
        self.app = app
        self._view: ttk.Frame | None = None
        self._current: str | None = None
        self._buttons: dict[str, NavButton] = {}
        self._hotkeys: list[str] = []

        self._build_menubar()

        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)
        self._build_sidebar()
        self._build_content()
        self._build_status_bar()

        self.show("patients")

    # -- chrome ------------------------------------------------------------ #
    def _build_menubar(self) -> None:
        menubar = tk.Menu(self.app)

        file_menu = tk.Menu(menubar, tearoff=False)
        file_menu.add_command(label="Export report…",
                              command=lambda: self.show("reports"))
        file_menu.add_separator()
        file_menu.add_command(label="Sign out", command=self.app.sign_out)
        file_menu.add_command(label="Exit", command=self.app.destroy)
        menubar.add_cascade(label="File", menu=file_menu)

        if self.app.user is not None and self.app.user.is_admin:
            admin_menu = tk.Menu(menubar, tearoff=False)
            admin_menu.add_command(label="Manage users",
                                   command=lambda: self.show("users"))
            menubar.add_cascade(label="Admin", menu=admin_menu)

        help_menu = tk.Menu(menubar, tearoff=False)
        help_menu.add_command(label="About", command=self._about)
        menubar.add_cascade(label="Help", menu=help_menu)

        self.app.configure(menu=menubar)

    def _build_sidebar(self) -> None:
        sidebar = ttk.Frame(self, style="Sidebar.TFrame",
                            padding=(0, style.PAD_SMALL))
        sidebar.grid(row=0, column=0, sticky="nsw")

        brand = ttk.Frame(sidebar, style="Sidebar.TFrame")
        brand.pack(fill="x", padx=style.PAD, pady=(style.PAD_SMALL, style.PAD))
        self._brand_icon = assets.load_icon(self, 32)
        ttk.Label(brand, text="Records Manager", image=self._brand_icon,
                  compound="left" if self._brand_icon else "none",
                  style="Brand.TLabel").pack(anchor="w")

        for index, item in enumerate(self._visible_items, start=1):
            button = NavButton(sidebar, item.label,
                               lambda key=item.key: self.show(key),
                               accelerator=f"Ctrl+{index}")
            button.pack(fill="x")
            self._buttons[item.key] = button
            self._bind_hotkey(index, item.key)

        ttk.Frame(sidebar, style="Sidebar.TFrame").pack(fill="both", expand=True)

    def _build_content(self) -> None:
        self._content = ttk.Frame(self, padding=style.PAD)
        self._content.grid(row=0, column=1, sticky="nsew")
        self._content.rowconfigure(0, weight=1)
        self._content.columnconfigure(0, weight=1)

    def _build_status_bar(self) -> None:
        ttk.Separator(self, orient="horizontal").grid(
            row=1, column=0, columnspan=2, sticky="ew")

        bar = ttk.Frame(self, style="Status.TFrame", padding=(style.PAD,
                                                              style.PAD_SMALL))
        bar.grid(row=2, column=0, columnspan=2, sticky="ew")

        who = "not signed in"
        if self.app.user is not None:
            role = "administrator" if self.app.user.is_admin else "user"
            who = f"{self.app.user.name} ({role})"
        ttk.Label(bar, text=f"Signed in as {who}", style="Status.TLabel").pack(
            side="left")

        self._status = ttk.Label(bar, text="Ready", style="Status.TLabel")
        self._status.pack(side="right")

    # -- keyboard ----------------------------------------------------------- #
    def _bind_hotkey(self, index: int, key: str) -> None:
        """Bind Ctrl+<index> to a view, wherever the focus happens to be."""
        sequence = f"<Control-Key-{index}>"
        self.bind_all(sequence, lambda _event, view=key: self._hotkey(view))
        self._hotkeys.append(sequence)

    def _hotkey(self, key: str) -> str:
        self.show(key)
        return "break"

    def destroy(self) -> None:
        """Drop the global shortcuts before going away.

        bind_all reaches the whole application, so a signed-out window would
        otherwise keep switching views behind the login screen.
        """
        for sequence in self._hotkeys:
            try:
                self.unbind_all(sequence)
            except tk.TclError:  # pragma: no cover - window already gone
                pass
        self._hotkeys.clear()
        super().destroy()

    # -- view switching ----------------------------------------------------- #
    @property
    def _is_admin(self) -> bool:
        return self.app.user is not None and self.app.user.is_admin

    @property
    def _visible_items(self) -> list[NavItem]:
        """Sidebar entries this user may see, in order."""
        return [item for item in NAV_ITEMS
                if not item.admin_only or self._is_admin]

    def show(self, key: str) -> None:
        """Replace the content area with the named view."""
        item = next((entry for entry in NAV_ITEMS if entry.key == key), None)
        if item is None or (item.admin_only and not self._is_admin):
            return

        if self._view is not None:
            self._view.destroy()
            self._view = None

        self._view = item.factory(self._content, self.app)
        self._view.grid(row=0, column=0, sticky="nsew")

        self._current = key
        for nav_key, button in self._buttons.items():
            button.set_active(nav_key == key)

    def set_status(self, message: str) -> None:
        """Report the last action in the status bar."""
        self._status.configure(text=message)

    def _about(self) -> None:
        show_info(
            self, "About Records Manager",
            f"Version {__version__}\n\n"
            "Patient file tracking: records, borrowing and returns, "
            "search and CSV reports.",
        )
