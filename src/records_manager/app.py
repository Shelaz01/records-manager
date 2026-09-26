"""Application entry point: owns the single Tk root and switches screens.

There is exactly one ``tk.Tk()`` for the whole program. Screens are frames
swapped inside it; anything that needs its own window is a ``Toplevel``.
"""
from __future__ import annotations

import argparse
import ctypes
import sys
import tkinter as tk
from pathlib import Path
from typing import Sequence

from .db import Database, LoanRepo, PatientRepo, User, UserRepo
from .ui import assets, style
from .ui.login import LoginScreen
from .ui.main_window import MainWindow
from .ui.setup import SetupScreen

WINDOW_TITLE = "Records Manager"
MIN_SIZE = (960, 600)
START_SIZE = (1180, 720)


def _enable_dpi_awareness() -> None:
    """Render at the display's real resolution on Windows.

    Without this, Windows bitmap-stretches the window on a scaled display
    (125% is the common default) and every label and table row comes out
    blurry. Must run before the first window exists. A no-op elsewhere, and
    harmless if the host has already set an awareness level.
    """
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)  # system DPI aware
    except (AttributeError, OSError):
        try:
            ctypes.windll.user32.SetProcessDPIAware()  # pre-8.1 fallback
        except (AttributeError, OSError):
            pass


class App(tk.Tk):
    """The root window, holding the repositories and the signed-in user."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        _enable_dpi_awareness()
        super().__init__()
        self.db = Database(db_path)
        self.users = UserRepo(self.db)
        self.patients = PatientRepo(self.db)
        self.loans = LoanRepo(self.db)
        self.user: User | None = None

        self.title(WINDOW_TITLE)
        self.minsize(*MIN_SIZE)
        self.geometry("{}x{}".format(*START_SIZE))
        style.apply(self)

        # Held on the instance: Tk drops images that are not referenced.
        self._icons = assets.window_icons(self)
        if self._icons:
            self.iconphoto(True, *self._icons)

        self._screen: tk.Widget | None = None
        self.show_start()

    # -- screen switching --------------------------------------------------- #
    def _swap(self, screen: tk.Widget) -> None:
        """Replace the current screen, destroying the old one."""
        if self._screen is not None:
            self._screen.destroy()
        self._screen = screen
        screen.pack(fill="both", expand=True)

    def show_start(self) -> None:
        """Show setup on a fresh database, otherwise the login screen."""
        if self.users.has_users():
            self.show_login()
        else:
            self.show_setup()

    def show_setup(self) -> None:
        self._clear_menu()
        self._swap(SetupScreen(self))

    def show_login(self) -> None:
        self._clear_menu()
        self._swap(LoginScreen(self))

    def show_main(self, user: User) -> None:
        """Sign ``user`` in and show the main window."""
        self.user = user
        self._swap(MainWindow(self))

    def sign_out(self) -> None:
        self.user = None
        self.show_login()

    def _clear_menu(self) -> None:
        """Drop the menubar, which belongs to the signed-in window only."""
        self.configure(menu=tk.Menu(self))

    # -- status ------------------------------------------------------------- #
    def set_status(self, message: str) -> None:
        """Pass a message to the status bar, when a main window is showing."""
        if isinstance(self._screen, MainWindow):
            self._screen.set_status(message)


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="records-manager",
        description="Hospital patient file records manager.",
    )
    parser.add_argument(
        "--seed-demo", action="store_true",
        help="fill the database with fictional demo data, then exit",
    )
    parser.add_argument(
        "--db", metavar="PATH", default=None,
        help="use this database file instead of ~/.records_manager/records.db",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> None:
    """Start the application, or seed demo data and exit."""
    args = _parse_args(argv)

    if args.seed_demo:
        from .demo import seed_demo

        summary = seed_demo(Database(args.db))
        print(summary)
        return

    App(args.db).mainloop()
