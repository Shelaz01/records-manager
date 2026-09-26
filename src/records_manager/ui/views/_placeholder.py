"""Stand-in for a view that a later sub-step fills in."""
from __future__ import annotations

from typing import TYPE_CHECKING
from tkinter import ttk

from .. import style
from ..widgets import bind_wraplength

if TYPE_CHECKING:
    import tkinter as tk

    from ...app import App


class PlaceholderView(ttk.Frame):
    """Shows the view's title and what it will do once built."""

    title = "View"
    summary = ""

    def __init__(self, master: tk.Misc, app: App) -> None:
        super().__init__(master)
        self.app = app

        ttk.Label(self, text=self.title, style="Heading.TLabel").pack(
            anchor="w", pady=(0, style.PAD_SMALL))
        summary = ttk.Label(self, text=self.summary, style="Muted.TLabel",
                            justify="left")
        summary.pack(anchor="w", fill="x")
        bind_wraplength(summary, self)
