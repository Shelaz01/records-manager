"""Locating and loading the image files the interface uses.

Paths are resolved relative to this module, never absolutely, and every
loader returns None rather than raising: a missing or unreadable image
must never stop the application starting.
"""
from __future__ import annotations

import tkinter as tk
from pathlib import Path

#: Assets live inside the package so they ship in a wheel: an installed
#: application that cannot find its own icon is a broken one.
_ROOTS = (Path(__file__).resolve().parents[1] / "assets",)

#: Icon sizes Tk is given for the title bar and taskbar, largest first.
WINDOW_ICON_SIZES = (256, 48, 32, 16)


def asset_path(name: str) -> Path | None:
    """The first existing file called ``name``, or None if there is none."""
    for root in _ROOTS:
        candidate = root / name
        if candidate.exists():
            return candidate
    return None


def load_image(widget: tk.Misc, name: str) -> tk.PhotoImage | None:
    """Load an image by file name, or None when it is missing or unreadable."""
    path = asset_path(name)
    if path is None:
        return None
    try:
        return tk.PhotoImage(master=widget, file=str(path))
    except tk.TclError:
        return None


def load_icon(widget: tk.Misc, size: int) -> tk.PhotoImage | None:
    """Load the application icon at a given pixel size."""
    return load_image(widget, f"icon-{size}.png")


def window_icons(widget: tk.Misc) -> list[tk.PhotoImage]:
    """Every icon size available, for ``iconphoto``.

    Tk picks the closest match per use, so handing it several sizes gives a
    sharp title bar and a sharp taskbar button from the one call.
    """
    icons = (load_icon(widget, size) for size in WINDOW_ICON_SIZES)
    return [icon for icon in icons if icon is not None]
