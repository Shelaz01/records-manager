"""The one place the application's look is defined.

Fonts, spacing and the accent colour live here and nowhere else: no widget
sets its own font or padding inline. Everything is ``ttk``; ``sv_ttk``
supplies the base light theme and this module layers the named styles the
views use on top of it.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

import sv_ttk

# --------------------------------------------------------------------------- #
# Palette
# --------------------------------------------------------------------------- #
#: Accent, matching sv-ttk's light theme so built-in Accent widgets agree.
ACCENT = "#005fb8"
ACCENT_TEXT = "#ffffff"

#: Sidebar and status bar sit slightly back from the content area.
SURFACE = "#f3f3f3"
#: Sidebar item under the pointer, and the current one.
SURFACE_HOVER = "#e9e9e9"
SURFACE_ACTIVE = "#e4eefb"
BORDER = "#e5e5e5"
MUTED = "#5d5d5d"
DANGER = "#c42b1c"
#: Barely-there red wash, for a destructive button under the pointer.
DANGER_TINT = "#fdf3f2"
WARNING = "#9d5d00"
SUCCESS = "#0f7b0f"

#: The white of an entry box, which destructive buttons sit on so they read
#: as an outline rather than as a filled, grey control.
FIELD = "#ffffff"

#: Width of the accent bar marking the current sidebar item.
NAV_BAR_WIDTH = 3

# --------------------------------------------------------------------------- #
# Spacing
# --------------------------------------------------------------------------- #
PAD_TINY = 2
PAD_SMALL = 6
PAD = 12
PAD_LARGE = 20

# --------------------------------------------------------------------------- #
# Fonts
# --------------------------------------------------------------------------- #
#: Preferred faces in order; the first one installed wins, so the app looks
#: right on Windows without breaking elsewhere.
_FAMILIES = ("Segoe UI", "Inter", "Helvetica Neue", "DejaVu Sans", "TkDefaultFont")

FONT: tuple[str, int] = ("TkDefaultFont", 10)
FONT_BOLD: tuple[str, int, str] = ("TkDefaultFont", 10, "bold")
FONT_SMALL: tuple[str, int] = ("TkDefaultFont", 9)
FONT_TINY: tuple[str, int] = ("TkDefaultFont", 8)
FONT_HEADING: tuple[str, int, str] = ("TkDefaultFont", 14, "bold")
FONT_TITLE: tuple[str, int, str] = ("TkDefaultFont", 20, "bold")

#: Row height has to clear the font, or Treeview clips descenders.
ROW_HEIGHT = 30


def _pick_family(root: tk.Misc) -> str:
    """Return the first preferred font family actually installed."""
    available = set(tkfont.families(root))
    for family in _FAMILIES:
        if family in available:
            return family
    return "TkDefaultFont"


def _set_fonts(root: tk.Misc) -> None:
    """Resolve the font constants against the chosen family."""
    global FONT, FONT_BOLD, FONT_SMALL, FONT_TINY, FONT_HEADING, FONT_TITLE

    family = _pick_family(root)
    FONT = (family, 10)
    FONT_BOLD = (family, 10, "bold")
    FONT_SMALL = (family, 9)
    FONT_TINY = (family, 8)
    FONT_HEADING = (family, 14, "bold")
    FONT_TITLE = (family, 20, "bold")

    # Named fonts so stock widgets (menus, entries) follow along.
    for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont"):
        tkfont.nametofont(name).configure(family=family, size=10)
    tkfont.nametofont("TkHeadingFont").configure(family=family, size=10, weight="bold")


def apply(root: tk.Misc) -> None:
    """Apply the theme and register the named styles the views use.

    Call once, on the root window, before building any widgets.
    """
    sv_ttk.set_theme("light")
    _set_fonts(root)

    style = ttk.Style(root)

    # Text -------------------------------------------------------------- #
    style.configure("TLabel", font=FONT)
    style.configure("Title.TLabel", font=FONT_TITLE)
    style.configure("Heading.TLabel", font=FONT_HEADING)
    style.configure("Muted.TLabel", font=FONT_SMALL, foreground=MUTED)
    #: Field hints, a size below the muted description text.
    style.configure("Hint.TLabel", font=FONT_TINY, foreground=MUTED)
    style.configure("Danger.TLabel", font=FONT_SMALL, foreground=DANGER)
    style.configure("Warning.TLabel", font=FONT_SMALL, foreground=WARNING)
    style.configure("Success.TLabel", font=FONT_SMALL, foreground=SUCCESS)
    style.configure("FieldLabel.TLabel", font=FONT_BOLD)
    #: A form value shown as context rather than offered for editing.
    style.configure("FieldValue.TLabel", font=FONT)
    #: Greyed prompt text inside an empty search box.
    style.configure("Placeholder.TEntry", foreground=MUTED)

    # Modal dialogs: a glyph beside the message, sized to sit level with it.
    style.configure("DialogTitle.TLabel", font=FONT_BOLD)
    style.configure("DialogIconDanger.TLabel", font=(FONT[0], 26),
                    foreground=DANGER)
    style.configure("DialogIconWarning.TLabel", font=(FONT[0], 26),
                    foreground=WARNING)
    style.configure("DialogIconInfo.TLabel", font=(FONT[0], 26),
                    foreground=ACCENT)

    # Surfaces ----------------------------------------------------------- #
    style.configure("Sidebar.TFrame", background=SURFACE)
    style.configure("Status.TFrame", background=SURFACE)
    style.configure("Sidebar.TLabel", background=SURFACE, font=FONT_SMALL,
                    foreground=MUTED)
    style.configure("Status.TLabel", background=SURFACE, font=FONT_SMALL,
                    foreground=MUTED)

    # Sidebar navigation -------------------------------------------------- #
    # Built from frames and labels rather than ttk.Button: sv-ttk draws
    # buttons from images, so a flat item and an accent bar cannot be had by
    # configuring a button style.
    style.configure("Nav.TFrame", background=SURFACE)
    style.configure("NavHover.TFrame", background=SURFACE_HOVER)
    style.configure("NavActive.TFrame", background=SURFACE_ACTIVE)

    # The left accent bar: invisible until the item is the current one.
    style.configure("NavBar.TFrame", background=SURFACE)
    style.configure("NavBarHover.TFrame", background=SURFACE_HOVER)
    style.configure("NavBarActive.TFrame", background=ACCENT)

    style.configure("Nav.TLabel", background=SURFACE, font=FONT)
    style.configure("NavHover.TLabel", background=SURFACE_HOVER, font=FONT)
    style.configure("NavActive.TLabel", background=SURFACE_ACTIVE,
                    font=FONT_BOLD, foreground=ACCENT)

    # The keyboard shortcut shown at the right of each sidebar item.
    style.configure("NavHint.TLabel", background=SURFACE, font=FONT_TINY,
                    foreground=MUTED)
    style.configure("NavHintHover.TLabel", background=SURFACE_HOVER,
                    font=FONT_TINY, foreground=MUTED)
    style.configure("NavHintActive.TLabel", background=SURFACE_ACTIVE,
                    font=FONT_TINY, foreground=ACCENT)

    style.configure("Brand.TLabel", background=SURFACE, font=FONT_BOLD)

    # Buttons -------------------------------------------------------------- #
    # Destructive actions are never the accent button: the accent reads as
    # "this is what you came here to do", which is wrong for deleting a file.
    # sv-ttk draws buttons from images, so a red outline on white cannot be
    # had by configuring a button style -- DangerButton builds one from
    # frames instead, and these are its parts.
    style.configure("DangerBorder.TFrame", background=DANGER)
    style.configure("DangerFill.TFrame", background=FIELD)
    style.configure("DangerFillHover.TFrame", background=DANGER_TINT)
    style.configure("DangerText.TLabel", background=FIELD, foreground=DANGER,
                    font=FONT)
    style.configure("DangerTextHover.TLabel", background=DANGER_TINT,
                    foreground=DANGER, font=FONT)

    # Tables -------------------------------------------------------------- #
    style.configure("Treeview", font=FONT, rowheight=ROW_HEIGHT)
    style.configure("Treeview.Heading", font=FONT_BOLD)

    _set_tooltip_defaults(root)


def _set_tooltip_defaults(root: tk.Misc) -> None:
    """Match plain tk widgets (menus, messageboxes) to the ttk theme."""
    root.option_add("*Menu.font", FONT)
    root.option_add("*Dialog.msg.font", FONT)


def heading(master: tk.Misc, text: str) -> ttk.Label:
    """A view's title label, spaced consistently across every screen."""
    return ttk.Label(master, text=text, style="Heading.TLabel")
