"""Reusable widgets: a sortable table and a modal form dialog."""
from __future__ import annotations

import re
import tkinter as tk
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Generic, TypeVar
from tkinter import ttk

from . import style

T = TypeVar("T")


class DataTable(ttk.Frame, Generic[T]):
    """A Treeview with scrollbars and click-to-sort headings.

    The model objects are kept in a dict keyed by row id, and selections are
    read back from that dict. Nothing reads values out of the Treeview: it
    stores everything as display strings and would hand back ``123`` for a
    hospital number of ``"00123"``.
    """

    def __init__(
        self,
        master: tk.Misc,
        columns: Sequence[str],
        *,
        widths: Sequence[int] | None = None,
        anchors: Sequence[str] | None = None,
        on_activate: Callable[[T], None] | None = None,
        on_select: Callable[[T | None], None] | None = None,
        on_delete: Callable[[T], None] | None = None,
    ) -> None:
        super().__init__(master)
        self._columns = tuple(columns)
        self._items: dict[str, T] = {}
        self._rows: list[tuple[str, tuple[str, ...], tuple[str, ...]]] = []
        self._sort_column: int | None = None
        self._sort_reverse = False
        self._on_activate = on_activate
        self._on_select = on_select
        self._on_delete = on_delete

        self.tree = ttk.Treeview(self, columns=self._columns, show="headings",
                                 selectmode="browse")
        self._vertical = ttk.Scrollbar(self, orient="vertical",
                                       command=self.tree.yview)
        self._horizontal = ttk.Scrollbar(self, orient="horizontal",
                                         command=self.tree.xview)
        # Routed through _scrolled so the bars can hide when nothing overflows.
        self.tree.configure(yscrollcommand=self._scrolled_vertical,
                            xscrollcommand=self._scrolled_horizontal)
        vertical, horizontal = self._vertical, self._horizontal

        for index, name in enumerate(self._columns):
            width = widths[index] if widths else 140
            anchor = anchors[index] if anchors else "w"
            self.tree.heading(name, text=name,
                              command=lambda i=index: self.sort_by(i))
            self.tree.column(name, width=width, anchor=anchor, stretch=True)

        self.tree.grid(row=0, column=0, sticky="nsew")
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal.grid(row=1, column=0, sticky="ew")
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

        self.tree.bind("<<TreeviewSelect>>", self._selection_changed)
        self.tree.bind("<Double-1>", self._activated)
        self.tree.bind("<Return>", self._activated)
        self.tree.bind("<Delete>", self._deleted)

    # -- scrollbars --------------------------------------------------------- #
    def _scrolled_vertical(self, first: str, last: str) -> None:
        self._vertical.set(first, last)
        self._toggle(self._vertical, first, last, row=0, column=1, sticky="ns")

    def _scrolled_horizontal(self, first: str, last: str) -> None:
        self._horizontal.set(first, last)
        self._toggle(self._horizontal, first, last, row=1, column=0, sticky="ew")

    @staticmethod
    def _toggle(bar: ttk.Scrollbar, first: str, last: str, **grid) -> None:
        """Show a scrollbar only when the content actually overflows."""
        covers_everything = float(first) <= 0.0 and float(last) >= 1.0
        if covers_everything:
            bar.grid_remove()
        elif not bar.winfo_ismapped():
            bar.grid(**grid)

    # -- row styling -------------------------------------------------------- #
    def tag_configure(self, name: str, **options) -> None:
        """Register a row tag, e.g. a colour for files that are out on loan."""
        self.tree.tag_configure(name, **options)

    # -- populating -------------------------------------------------------- #
    def set_rows(
        self,
        items: Sequence[T],
        *,
        key: Callable[[T], str],
        values: Callable[[T], Sequence[Any]],
        tags: Callable[[T], Sequence[str]] | None = None,
    ) -> None:
        """Replace the contents. ``key`` gives each row's id, ``values`` its cells."""
        self._items = {key(item): item for item in items}
        self._rows = [
            (key(item),
             tuple(str(value) for value in values(item)),
             tuple(tags(item)) if tags is not None else ())
            for item in items
        ]
        self._render()

    def clear(self) -> None:
        self._items.clear()
        self._rows.clear()
        self._render()

    def _render(self) -> None:
        selected = self.selected_key()
        self.tree.delete(*self.tree.get_children())
        for iid, row, tags in self._sorted_rows():
            self.tree.insert("", "end", iid=iid, values=row, tags=tags)
        if selected is not None and self.tree.exists(selected):
            self.tree.selection_set(selected)

    def _sorted_rows(self) -> list[tuple[str, tuple[str, ...], tuple[str, ...]]]:
        if self._sort_column is None:
            return self._rows
        index = self._sort_column
        return sorted(self._rows, key=lambda row: _sort_key(row[1][index]),
                      reverse=self._sort_reverse)

    # -- sorting ----------------------------------------------------------- #
    def sort_by(self, index: int, *, reverse: bool | None = None) -> None:
        """Sort by a column, reversing when it is already the sort column.

        Pass ``reverse`` to set a direction outright, which is how a view
        establishes the order it wants to open on.
        """
        if reverse is not None:
            self._sort_column, self._sort_reverse = index, reverse
        elif self._sort_column == index:
            self._sort_reverse = not self._sort_reverse
        else:
            self._sort_column, self._sort_reverse = index, False
        self._update_headings()
        self._render()

    def _update_headings(self) -> None:
        for index, name in enumerate(self._columns):
            marker = ""
            if index == self._sort_column:
                marker = "  ▼" if self._sort_reverse else "  ▲"
            self.tree.heading(name, text=f"{name}{marker}")

    # -- selection --------------------------------------------------------- #
    def selected_key(self) -> str | None:
        selection = self.tree.selection()
        return selection[0] if selection else None

    def selected(self) -> T | None:
        """The selected model object, or None. Never reads Treeview values."""
        key = self.selected_key()
        return self._items.get(key) if key is not None else None

    def select_first(self) -> None:
        children = self.tree.get_children()
        if children:
            self.tree.selection_set(children[0])

    @property
    def row_count(self) -> int:
        return len(self._rows)

    def _selection_changed(self, _event: tk.Event) -> None:
        if self._on_select is not None:
            self._on_select(self.selected())

    def _activated(self, _event: tk.Event) -> str | None:
        item = self.selected()
        if item is not None and self._on_activate is not None:
            self._on_activate(item)
        return "break"

    def _deleted(self, _event: tk.Event) -> str | None:
        item = self.selected()
        if item is not None and self._on_delete is not None:
            self._on_delete(item)
        return "break"


def _sort_key(value: str) -> tuple[int, float | str]:
    """Sort numerically when a column holds numbers, alphabetically otherwise.

    Blanks sort last either way, so active loans with no return date do not
    float to the top of a sorted report.
    """
    if not value:
        return (2, "")
    try:
        return (0, float(value))
    except ValueError:
        return (1, value.casefold())


# --------------------------------------------------------------------------- #
# Modal form
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Field:
    """One row of a :class:`FormDialog`."""

    key: str
    label: str
    required: bool = True
    #: Preset value, used when editing an existing record.
    initial: str = ""
    #: Suggestions; renders a combobox instead of a plain entry.
    choices: tuple[str, ...] | None = None
    #: With choices, whether the list is exhaustive. False lets the user
    #: type a value that is not offered, for things like a department name
    #: the list has not caught up with.
    strict: bool = True
    #: Blanked out and shown as dots.
    secret: bool = False
    #: Shown but not editable, e.g. a hospital number read off a scan.
    readonly: bool = False
    #: Context rather than input: rendered as plain text, not a box the user
    #: might try to type in. Its initial value is still returned.
    display: bool = False


class FormDialog(tk.Toplevel):
    """A modal dialog that collects a set of fields.

    Read :attr:`result` after it closes: a dict of the entered values, or
    None if the user cancelled. Closing the dialog closes only the dialog —
    never the window underneath it.
    """

    def __init__(self, master: tk.Misc, title: str, fields: Sequence[Field],
                 *, submit_text: str = "Save") -> None:
        super().__init__(master)
        self.result: dict[str, str] | None = None
        self._fields = tuple(fields)
        self._variables: dict[str, tk.StringVar] = {}

        self.title(title)
        self.transient(master.winfo_toplevel())
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", self._cancel)

        body = ttk.Frame(self, padding=style.PAD_LARGE)
        body.pack(fill="both", expand=True)

        ttk.Label(body, text=title, style="Heading.TLabel").grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, style.PAD))

        first: tk.Widget | None = None
        for row, field in enumerate(self._fields, start=1):
            # Only real inputs are marked required: a value shown as context
            # is not something the user can fill in.
            needs_marker = field.required and not (field.display or field.readonly)
            label = field.label + (" *" if needs_marker else "")
            ttk.Label(body, text=label, style="FieldLabel.TLabel").grid(
                row=row, column=0, sticky="w", padx=(0, style.PAD),
                pady=style.PAD_SMALL)

            variable = tk.StringVar(value=field.initial)
            self._variables[field.key] = variable
            widget = self._build_input(body, field, variable)
            widget.grid(row=row, column=1, sticky="ew", pady=style.PAD_SMALL)
            if first is None and not (field.readonly or field.display):
                first = widget

        body.columnconfigure(1, weight=1, minsize=240)

        self._error = ttk.Label(body, text="", style="Danger.TLabel")
        self._error.grid(row=len(self._fields) + 1, column=0, columnspan=2,
                         sticky="w", pady=(style.PAD_SMALL, 0))

        buttons = ttk.Frame(body)
        buttons.grid(row=len(self._fields) + 2, column=0, columnspan=2,
                     sticky="e", pady=(style.PAD, 0))
        ttk.Button(buttons, text="Cancel", command=self._cancel).pack(
            side="left", padx=(0, style.PAD_SMALL))
        ttk.Button(buttons, text=submit_text, style="Accent.TButton",
                   command=self._submit).pack(side="left")

        self.bind("<Return>", lambda _event: self._submit())
        self.bind("<Escape>", lambda _event: self._cancel())

        if first is not None:
            first.focus_set()
        _centre_on_parent(self, master)

        self.grab_set()
        self.wait_window(self)

    def _build_input(self, parent: tk.Misc, field: Field,
                     variable: tk.StringVar) -> tk.Widget:
        if field.display:
            return ttk.Label(parent, textvariable=variable, style="FieldValue.TLabel")
        if field.choices is not None:
            return ttk.Combobox(parent, textvariable=variable,
                                values=list(field.choices),
                                state="readonly" if field.strict else "normal")
        entry = ttk.Entry(parent, textvariable=variable,
                          show="•" if field.secret else "")
        if field.readonly:
            entry.state(["readonly"])
        return entry

    def _submit(self) -> None:
        values = {key: variable.get().strip()
                  for key, variable in self._variables.items()}
        missing = [field.label for field in self._fields
                   if field.required and not values[field.key]]
        if missing:
            self._error.configure(
                text=f"Please fill in: {', '.join(missing)}.")
            return
        self.result = values
        self.destroy()

    def _cancel(self) -> None:
        self.result = None
        self.destroy()


class PlaceholderEntry(ttk.Entry):
    """An entry that shows greyed prompt text while it is empty.

    The prompt is never part of the value: read :attr:`value`, which returns
    an empty string while the placeholder is showing, so a search cannot
    accidentally run against the prompt itself.
    """

    def __init__(self, master: tk.Misc, placeholder: str, *,
                 on_change: Callable[[str], None] | None = None,
                 **kwargs) -> None:
        self._variable = tk.StringVar()
        super().__init__(master, textvariable=self._variable, **kwargs)
        self._placeholder = placeholder
        self._showing = False
        self._on_change = on_change
        #: Counts writes this widget makes itself, which must not be
        #: reported as something the user typed.
        self._suppress = 0

        self._variable.trace_add("write", self._changed)
        self.bind("<FocusIn>", self._focus_in)
        self.bind("<FocusOut>", self._focus_out)
        # Typing clears the prompt before the character lands, so the two
        # can never end up concatenated.
        self.bind("<Key>", self._key_pressed)
        self._show_placeholder()

    def insert(self, index, string: str) -> None:
        """Insert text, dropping the prompt first."""
        self._hide_placeholder()
        super().insert(index, string)

    @property
    def value(self) -> str:
        """What the user actually typed."""
        return "" if self._showing else self._variable.get()

    def clear(self) -> None:
        self._set_quietly("")
        self._showing = False
        self.configure(foreground="")
        if self._on_change is not None:
            self._on_change("")
        if self.focus_get() is not self:
            self._show_placeholder()

    def _set_quietly(self, text: str) -> None:
        """Change the text without reporting it as something the user typed."""
        self._suppress += 1
        try:
            self._variable.set(text)
        finally:
            self._suppress -= 1

    def _show_placeholder(self) -> None:
        if self._variable.get():
            return
        self._showing = True
        self._set_quietly(self._placeholder)
        self.configure(foreground=style.MUTED)

    def _hide_placeholder(self) -> None:
        if not self._showing:
            return
        self._showing = False
        self._set_quietly("")
        self.configure(foreground="")

    def _focus_in(self, _event: tk.Event) -> None:
        self._hide_placeholder()

    def _focus_out(self, _event: tk.Event) -> None:
        self._show_placeholder()

    def _key_pressed(self, event: tk.Event) -> None:
        # Ignore pure modifiers and navigation, which should not clear it.
        if event.char:
            self._hide_placeholder()

    def _changed(self, *_args) -> None:
        if self._suppress:
            return
        # A write we did not make is the user typing, so the prompt is over.
        if self._showing:
            self._showing = False
            self.configure(foreground="")
        if self._on_change is not None:
            self._on_change(self._variable.get())


class NavButton(ttk.Frame):
    """A sidebar destination: flat until it is the current one.

    The current item gets an accent bar down its left edge and a tinted
    background; the rest are flat against the sidebar.
    """

    def __init__(self, master: tk.Misc, text: str, command: Callable[[], None],
                 *, image: tk.PhotoImage | None = None,
                 accelerator: str | None = None) -> None:
        super().__init__(master, style="Nav.TFrame", takefocus=True)
        self._command = command
        self._active = False
        self._focused = False

        self._bar = ttk.Frame(self, style="NavBar.TFrame",
                              width=style.NAV_BAR_WIDTH)
        self._bar.pack(side="left", fill="y")
        self._bar.pack_propagate(False)

        self._label = ttk.Label(self, text=text, image=image, style="Nav.TLabel",
                                compound="left" if image else "none",
                                padding=(style.PAD, style.PAD_SMALL))
        self._label.pack(side="left", fill="both", expand=True)

        #: Shows the keyboard shortcut, so it is discoverable without docs.
        self._hint: ttk.Label | None = None
        if accelerator:
            self._hint = ttk.Label(self, text=accelerator, style="NavHint.TLabel",
                                   padding=(0, 0, style.PAD, 0))
            self._hint.pack(side="right")

        for widget in self._parts:
            widget.bind("<Button-1>", self._activated)
            widget.bind("<Enter>", self._entered)
            widget.bind("<Leave>", self._left)
            widget.configure(cursor="hand2")

        # Keyboard: Tab reaches the item, Enter or Space activates it.
        self.bind("<Return>", self._activated)
        self.bind("<KP_Enter>", self._activated)
        self.bind("<space>", self._activated)
        self.bind("<FocusIn>", self._focus_in)
        self.bind("<FocusOut>", self._focus_out)

    @property
    def _parts(self) -> tuple[tk.Widget, ...]:
        widgets: tuple[tk.Widget, ...] = (self, self._label, self._bar)
        return widgets + ((self._hint,) if self._hint is not None else ())

    def set_active(self, active: bool) -> None:
        self._active = active
        self._refresh()

    def _refresh(self) -> None:
        if self._active:
            variant = "Active"
        elif self._focused:
            variant = "Hover"
        else:
            variant = ""
        self.configure(style=f"Nav{variant}.TFrame")
        self._bar.configure(style=f"NavBar{variant}.TFrame")
        self._label.configure(style=f"Nav{variant}.TLabel")
        if self._hint is not None:
            self._hint.configure(style=f"NavHint{variant}.TLabel")

    def _activated(self, _event: tk.Event) -> str:
        self.focus_set()
        self._command()
        return "break"

    def _entered(self, _event: tk.Event) -> None:
        if not self._active:
            self.configure(style="NavHover.TFrame")
            self._bar.configure(style="NavBarHover.TFrame")
            self._label.configure(style="NavHover.TLabel")
            if self._hint is not None:
                self._hint.configure(style="NavHintHover.TLabel")

    def _left(self, _event: tk.Event) -> None:
        self._refresh()

    def _focus_in(self, _event: tk.Event) -> None:
        self._focused = True
        self._refresh()

    def _focus_out(self, _event: tk.Event) -> None:
        self._focused = False
        self._refresh()


def bind_wraplength(label: ttk.Label, container: tk.Misc, *,
                    padding: int = 0) -> None:
    """Keep ``label``'s text wrapping to the width of ``container``.

    Fixed wrap widths leave text breaking mid-sentence in a wide window and
    overflowing a narrow one, so the width is recomputed on every resize.
    """

    def resize(event: tk.Event) -> None:
        width = max(event.width - padding, 120)
        if label.winfo_exists():
            label.configure(wraplength=width)

    container.bind("<Configure>", resize, add="+")


class DangerButton(ttk.Frame):
    """A destructive action: red text inside a red outline, on white.

    Built from frames because sv-ttk renders buttons from images, so a
    ttk.Button cannot be given a white face and a red border by configuring
    its style. Behaves as a button otherwise: focusable, and activated by
    Return or Space as well as by clicking.
    """

    def __init__(self, master: tk.Misc, text: str,
                 command: Callable[[], None]) -> None:
        super().__init__(master, style="DangerBorder.TFrame", takefocus=True)
        self._command = command

        self._fill = ttk.Frame(self, style="DangerFill.TFrame")
        self._fill.pack(fill="both", expand=True, padx=1, pady=1)

        self._label = ttk.Label(self._fill, text=text, style="DangerText.TLabel",
                                anchor="center",
                                padding=(style.PAD, style.PAD_SMALL))
        self._label.pack(fill="both", expand=True)

        for widget in (self, self._fill, self._label):
            widget.bind("<Button-1>", self._activated)
            widget.bind("<Enter>", lambda _event: self._hover(True))
            widget.bind("<Leave>", lambda _event: self._hover(False))
            widget.configure(cursor="hand2")

        self.bind("<Return>", self._activated)
        self.bind("<KP_Enter>", self._activated)
        self.bind("<space>", self._activated)
        self.bind("<FocusIn>", lambda _event: self._hover(True))
        self.bind("<FocusOut>", lambda _event: self._hover(False))

    def _hover(self, on: bool) -> None:
        self._fill.configure(style=f"DangerFill{'Hover' if on else ''}.TFrame")
        self._label.configure(style=f"DangerText{'Hover' if on else ''}.TLabel")

    def _activated(self, _event: tk.Event) -> str:
        self._command()
        return "break"

    def invoke(self) -> None:
        """Match ttk.Button, so callers can trigger it the same way."""
        self._command()


class MessageDialog(tk.Toplevel):
    """A themed replacement for ``tkinter.messagebox``.

    The stock message boxes are native Windows dialogs: they ignore the
    application's theme and fonts, so they look foreign next to everything
    else. This one is built from the same ttk styles as the rest of the UI.

    Read :attr:`result` afterwards: True if the confirming button was used.
    """

    #: Glyph and style per kind of message.
    _ICONS = {
        "error": ("✕", "DialogIconDanger.TLabel"),
        "warning": ("⚠", "DialogIconWarning.TLabel"),
        "info": ("ℹ", "DialogIconInfo.TLabel"),
    }

    def __init__(self, master: tk.Misc, title: str, message: str, *,
                 kind: str = "info", confirm_text: str | None = None,
                 dismiss_text: str = "OK",
                 confirm_style: str = "TButton") -> None:
        super().__init__(master)
        self.result = False

        self.title(title)
        self.transient(master.winfo_toplevel())
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", self._dismiss)

        body = ttk.Frame(self, padding=style.PAD_LARGE)
        body.pack(fill="both", expand=True)

        glyph, icon_style = self._ICONS.get(kind, self._ICONS["info"])
        ttk.Label(body, text=glyph, style=icon_style).grid(
            row=0, column=0, sticky="n", padx=(0, style.PAD))

        ttk.Label(body, text=title, style="DialogTitle.TLabel").grid(
            row=0, column=1, sticky="w")
        ttk.Label(body, text=message, wraplength=360, justify="left").grid(
            row=1, column=1, sticky="w", pady=(style.PAD_SMALL, 0))

        buttons = ttk.Frame(body)
        buttons.grid(row=2, column=0, columnspan=2, sticky="e",
                     pady=(style.PAD_LARGE, 0))

        if confirm_text is None:
            # A statement, not a question: one button, and it is the default.
            default = ttk.Button(buttons, text=dismiss_text,
                                 style="Accent.TButton", command=self._dismiss)
            default.pack(side="left")
        else:
            cancel = ttk.Button(buttons, text=dismiss_text,
                                command=self._dismiss)
            cancel.pack(side="left", padx=(0, style.PAD_SMALL))
            if confirm_style == "danger":
                DangerButton(buttons, confirm_text, self._confirm).pack(
                    side="left")
            else:
                ttk.Button(buttons, text=confirm_text, style=confirm_style,
                           command=self._confirm).pack(side="left")
            # The safe button takes the focus and Return, so leaning on the
            # keyboard cannot delete a record.
            default = cancel

        self.bind("<Escape>", lambda _event: self._dismiss())
        self.bind("<Return>", lambda _event: default.invoke())
        default.focus_set()

        _centre_on_parent(self, master)
        self.grab_set()
        self.wait_window(self)

    def _confirm(self) -> None:
        self.result = True
        self.destroy()

    def _dismiss(self) -> None:
        self.result = False
        self.destroy()


def show_error(parent: tk.Misc, title: str, message: str) -> None:
    """Report a failure the user needs to read."""
    MessageDialog(parent, title, message, kind="error")


def show_info(parent: tk.Misc, title: str, message: str) -> None:
    MessageDialog(parent, title, message, kind="info")


def confirm(parent: tk.Misc, title: str, message: str, *,
            confirm_text: str = "OK", kind: str = "warning",
            destructive: bool = False) -> bool:
    """Ask a yes/no question. Returns True only if the user agreed.

    Cancel keeps the focus and the Return key, so leaning on the keyboard
    cannot destroy anything. A destructive action is styled as a warning
    rather than as the accent button.
    """
    dialog = MessageDialog(
        parent, title, message, kind=kind, confirm_text=confirm_text,
        dismiss_text="Cancel",
        confirm_style="danger" if destructive else "Accent.TButton",
    )
    return dialog.result


def _centre_on_parent(window: tk.Toplevel, parent: tk.Misc) -> None:
    """Place a dialog over the window that opened it, and keep it inside.

    A tall dialog centred by thirds hangs off the bottom, so the position is
    clamped to the parent's edges whenever the dialog is small enough to fit.
    """
    window.update_idletasks()
    root = parent.winfo_toplevel()
    width, height = window.winfo_width(), window.winfo_height()

    # geometry() positions the window frame, while winfo_rootx/y report the
    # client area inside it. The difference is the title bar, which has to
    # be counted or the dialog is placed a title bar too high.
    offset_x, offset_y = _decoration(window)
    frame_width, frame_height = width + offset_x * 2, height + offset_y

    left, top = root.winfo_rootx(), root.winfo_rooty()
    x = left + (root.winfo_width() - frame_width) // 2
    y = top + (root.winfo_height() - frame_height) // 3

    if frame_height <= root.winfo_height():
        y = min(max(y, top), top + root.winfo_height() - frame_height)
    if frame_width <= root.winfo_width():
        x = min(max(x, left), left + root.winfo_width() - frame_width)

    window.geometry(f"+{max(x, 0)}+{max(y, 0)}")


def _decoration(window: tk.Toplevel) -> tuple[int, int]:
    """How far the client area sits inside the window frame."""
    match = re.search(r"\+(-?\d+)\+(-?\d+)$", window.geometry())
    if match is None:  # pragma: no cover - geometry always carries a position
        return (0, 0)
    frame_x, frame_y = int(match.group(1)), int(match.group(2))
    return (max(window.winfo_rootx() - frame_x, 0),
            max(window.winfo_rooty() - frame_y, 0))
