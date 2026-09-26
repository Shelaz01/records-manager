"""Drive the application and capture a screenshot of each screen.

Writes into ``docs/screenshots/``. Windows only: it reads the window's real
on-screen rectangle through the Desktop Window Manager.

    python tools/screenshots.py

This is a development tool, not part of the application. It reaches into
screen internals to fill in fields and switch views, which is why it lives
here rather than in the package.
"""
from __future__ import annotations

import ctypes
import shutil
import sys
import tempfile
import time
import tkinter as tk
from ctypes import wintypes
from pathlib import Path

from PIL import ImageGrab

from forms import render_form
from records_manager.app import App
from records_manager.db import Database
from records_manager.demo import seed_demo

OUT = Path(__file__).resolve().parents[1] / "docs" / "screenshots"

#: GetWindowRect includes an invisible resize border, so a grab made from it
#: picks up whatever sits behind the window. The DWM reports what is actually
#: drawn. https://learn.microsoft.com/windows/win32/api/dwmapi
DWMWA_EXTENDED_FRAME_BOUNDS = 9

#: The DWM rectangle still overshoots the drawn pixels by one on each side,
#: which lets a row of whatever is behind the window into the capture.
#: Measured, not guessed: without it the outermost row and column are the
#: desktop rather than the window.
EDGE_INSET = 1

DEMO_USER = ("Shelton Lino", "shelton", "demo-password")
GEOMETRY = "1180x720+120+80"
SETTLE = 0.6


def window_rect(window) -> tuple[int, int, int, int]:
    """The window's visible rectangle, excluding the invisible resize border."""
    hwnd = ctypes.windll.user32.GetParent(window.winfo_id()) or window.winfo_id()
    rect = wintypes.RECT()
    result = ctypes.windll.dwmapi.DwmGetWindowAttribute(
        wintypes.HWND(hwnd),
        ctypes.c_uint(DWMWA_EXTENDED_FRAME_BOUNDS),
        ctypes.byref(rect),
        ctypes.sizeof(rect),
    )
    if result != 0:  # S_OK
        ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))
    return (rect.left + EDGE_INSET, rect.top + EDGE_INSET,
            rect.right - EDGE_INSET, rect.bottom - EDGE_INSET)


def grab(app: App, name: str) -> None:
    """Bring the window forward, let it settle, and capture exactly it."""
    app.update_idletasks()
    app.update()
    app.lift()
    app.attributes("-topmost", True)
    app.update()
    time.sleep(SETTLE)
    app.update()

    ImageGrab.grab(window_rect(app), all_screens=True).save(OUT / f"{name}.png")
    print(f"  {name}.png")
    app.attributes("-topmost", False)


def grab_region(app: App, extra, name: str, *, dialog_only: bool = False) -> None:
    """Capture a dialog, with the main window behind it where that fits.

    The union of the two rectangles is only clean while the dialog sits
    inside the main window. A taller dialog would drag desktop into the
    corners, so those are captured on their own.
    """
    app.update_idletasks()
    app.update()
    time.sleep(SETTLE)
    app.update()

    main, over = window_rect(app), window_rect(extra)
    overflows = over[1] < main[1] or over[3] > main[3]
    if dialog_only or overflows:
        bbox = over
    else:
        bbox = (min(main[0], over[0]), min(main[1], over[1]),
                max(main[2], over[2]), max(main[3], over[3]))
    ImageGrab.grab(bbox, all_screens=True).save(OUT / f"{name}.png")
    print(f"  {name}.png")


def _is_dialog(window) -> bool:
    """One of the application's own modals.

    Not every Toplevel is a dialog: tkcalendar's date picker puts a tooltip
    and a calendar popup in the tree, and neither should be photographed or
    closed as though it were one.
    """
    return hasattr(window, "_cancel") or hasattr(window, "_dismiss")


def find_dialog(widget) -> tk.Toplevel | None:
    """The topmost open modal, wherever it sits in the widget tree.

    A dialog's master is the view that opened it, not the root, so this
    walks the whole tree. Widgets can be destroyed while the walk is under
    way, so every step is guarded.
    """
    try:
        children = widget.winfo_children()
    except tk.TclError:
        return None

    for child in children:
        try:
            if not child.winfo_exists():
                continue
        except tk.TclError:
            continue
        if isinstance(child, tk.Toplevel) and _is_dialog(child):
            # A dialog opened from a dialog sits deeper: prefer that one.
            return find_dialog(child) or child
        found = find_dialog(child)
        if found is not None:
            return found
    return None


def close_dialog(dialog) -> None:
    """Dismiss a modal of either kind, if it is still open."""
    try:
        if not dialog.winfo_exists():
            return
    except tk.TclError:
        return
    closer = getattr(dialog, "_cancel", None) or getattr(dialog, "_dismiss", None)
    if closer is not None:
        closer()


def close_all(app: App) -> None:
    for _ in range(4):
        dialog = find_dialog(app)
        if dialog is None:
            return
        close_dialog(dialog)
        app.update()


def capture_dialog(app: App, open_dialog, name: str, *, fill=None,
                   then=None) -> None:
    """Open a modal, screenshot it over the main window, then close it.

    Both dialog kinds block in ``wait_window``, so the shot is taken from an
    ``after`` callback that runs inside that nested event loop.

    ``then`` is an action performed on the dialog instead of photographing
    it -- submitting the form, or agreeing to a confirmation. Whatever modal
    is on screen once that settles is the one captured, which is how the
    repository errors get photographed: they only appear after the first
    dialog has closed.
    """

    def shoot() -> None:
        dialog = find_dialog(app)
        if dialog is None:
            print(f"  !! no dialog for {name}")
            return
        if fill is not None:
            fill(dialog)
            dialog.update()
        if then is not None:
            app.after(250, shoot_result)
            then(dialog)
            return
        grab_region(app, dialog, name)
        close_dialog(dialog)

    def shoot_result() -> None:
        """Whatever is on screen after the action: an error, or the form."""
        dialog = find_dialog(app)
        if dialog is None:
            print(f"  !! nothing on screen for {name}")
            return
        grab_region(app, dialog, name)
        close_all(app)

    app.after(150, shoot)
    open_dialog()
    close_all(app)
    app.update()


def select_row(app: App, key: str) -> None:
    """Select a table row by its id, as clicking it would."""
    table = app._screen._view._table
    table.tree.selection_set(key)
    table.tree.see(key)
    app.update()


def launch(db_path: Path) -> App:
    app = App(db_path)
    app.geometry(GEOMETRY)
    return app


def create_admin(app: App) -> None:
    """Fill in and submit the first-run setup screen, as a user would."""
    name, username, password = DEMO_USER
    screen = app._screen
    screen._name.insert(0, name)
    screen._username.insert(0, username)
    screen._password.insert(0, password)
    screen._confirm.insert(0, password)
    app.update()


def sign_in(app: App) -> None:
    _, username, password = DEMO_USER
    screen = app._screen
    screen._username.insert(0, username)
    screen._password.insert(0, password)
    app.update()
    screen._sign_in()
    app.update()


def set_entry(dialog, key: str, value: str) -> None:
    dialog._variables[key].set(value)


def load_form(dialog, image_path: Path, fixture: str) -> None:
    """Put a form into the scan dialog with its fields already read.

    Tesseract is not installed here, so the image-to-text step is the one
    thing substituted: the fields come from running the real parse_fields
    over the same fixture the image was drawn from. Everything downstream --
    title casing, the existing-patient lookup, the mismatch check -- is the
    application's own code.
    """
    from PIL import Image

    from records_manager.scanning import ocr

    fixture_text = (Path("tests/fixtures") / f"{fixture}.txt").read_text(
        encoding="utf-8")
    dialog._image = Image.open(image_path)
    dialog._source = image_path
    dialog._show_preview(dialog._image)
    dialog._apply(ocr.parse_fields(fixture_text))


def capture_scan(app: App, workspace: Path) -> None:
    """The scan flow: unavailable, reviewed, and an already-registered file.

    Each shot renders the fixture its fields are filled from, so the preview
    and the form agree. A screenshot whose preview contradicts its fields
    teaches the reader to distrust both.
    """
    from records_manager.db import Patient, RecordsError

    view = app._screen._view
    fixtures = Path("tests/fixtures")
    typical = render_form((fixtures / "typical_form.txt").read_text("utf-8"),
                          workspace / "typical.png")
    hyphenated = render_form(
        (fixtures / "hyphenated_surname.txt").read_text("utf-8"),
        workspace / "hyphenated.png")

    def register(patient: Patient) -> None:
        try:
            app.patients.add(patient)
        except RecordsError:
            pass

    # 1. Opened with no scanner and no Tesseract: both explained, not hidden.
    capture_dialog(app, view._scan, "30-scan-unavailable")

    # 2. A form loaded and read, ready for review. 20481 is not registered,
    #    so this is a new patient.
    capture_dialog(app, view._scan, "31-scan-review",
                   fill=lambda d: load_form(d, typical, "typical_form"))

    # 3. The same form, now that 20481 belongs to the patient named on it:
    #    a returning patient, so attach rather than create a second record.
    register(Patient("20481", "Ncube", "Thandiwe", "Box 6"))
    capture_dialog(app, view._scan, "32-scan-existing",
                   fill=lambda d: load_form(d, typical, "typical_form"))

    # 4. A form whose number lands on somebody else's file. The name on the
    #    paper disagrees with the record, which is what a misread digit
    #    looks like.
    register(Patient("50287", "Gumbo", "Tendai John", "Box 2"))
    capture_dialog(app, view._scan, "33-scan-name-mismatch",
                   fill=lambda d: load_form(d, hyphenated, "hyphenated_surname"))


def capture_patients(app: App) -> None:
    """The patients view and each of its dialogs and failure cases."""
    view = app._screen._view

    grab(app, "10-patients")

    view._search_entry.focus_set()
    view._search_entry.insert(0, "Nc")
    app.update()
    grab(app, "11-patients-search")
    view._clear_search()
    app.update()

    # Add, submitted with required fields left blank.
    capture_dialog(app, view._add, "12-add-validation",
                   fill=lambda d: (set_entry(d, "hospital_num", "00042"),
                                   set_entry(d, "surname", "Chikowore")),
                   then=lambda d: d._submit())

    # Edit, pre-filled from a record whose number has leading zeros.
    select_row(app, "00007")
    capture_dialog(app, view._edit, "13-edit-leading-zeros")

    # Delete confirmation, on a file that has never been borrowed.
    on_loan = sorted(loan.hospital_num for loan in app.loans.active())
    history = {loan.hospital_num for loan in
               app.loans.active() + app.loans.returned()}
    clean = next(p.hospital_num for p in app.patients.list_all()
                 if p.hospital_num not in history)
    select_row(app, clean)
    capture_dialog(app, view._delete, "14-delete-confirm")

    # A file with borrowing history is refused before being asked about.
    select_row(app, on_loan[0])
    capture_dialog(app, view._delete, "15-delete-blocked")

    # Borrow an available file.
    available = next(p.hospital_num for p in app.patients.list_all()
                     if p.hospital_num not in set(on_loan))
    select_row(app, available)
    capture_dialog(app, view._borrow, "16-borrow",
                   fill=lambda d: (set_entry(d, "borrower", "Tendai Moyo"),
                                   set_entry(d, "department", "Radiology"),
                                   set_entry(d, "reason", "Clinical review")))

    # Borrowing a file that is already out is refused. The UI disables
    # Borrow for a file it knows is out, so the way to reach this error
    # honestly is a stale view: someone else books the file out while this
    # table is on screen. Borrow it behind the view's back, without
    # refreshing, and the guard is legitimately out of date.
    spare = next(p.hospital_num for p in app.patients.list_all()
                 if p.hospital_num not in set(on_loan) and p.hospital_num != available)
    select_row(app, spare)
    app.loans.borrow(spare, "Someone Else", "Records")
    capture_dialog(app, view._borrow, "17-borrow-already-out",
                   fill=lambda d: (set_entry(d, "borrower", "Tendai Moyo"),
                                   set_entry(d, "department", "Radiology")),
                   then=lambda d: d._submit())

    app._screen.show("patients")
    app.update()


def capture_loans(app: App) -> None:
    """The loans view: both tabs, the borrow dialog and a return."""
    app._screen.show("loans")
    app.update()
    view = app._screen._view

    grab(app, "20-loans-active")

    view._tabs.select(1)
    app.update()
    grab(app, "21-loans-returned")
    view._tabs.select(0)
    app.update()

    # Borrowing here takes a typed number, resolved against the register as
    # it is typed. Both outcomes are worth showing.
    out = {loan.hospital_num for loan in app.loans.active()}
    available = next(p.hospital_num for p in app.patients.list_all()
                     if p.hospital_num not in out)

    def borrow_values(dialog, number, **rest):
        dialog._values["hospital_num"].set(number)
        for key, value in rest.items():
            dialog._values[key].set(value)

    capture_dialog(app, view._borrow, "22-loans-borrow",
                   fill=lambda d: borrow_values(d, available,
                                                borrower="Tendai Moyo",
                                                department="Theatre",
                                                reason="Theatre list"))

    # A file already out: the lookup says who has it, and Borrow is shut.
    capture_dialog(app, view._borrow, "24-loans-borrow-unavailable",
                   fill=lambda d: borrow_values(d, sorted(out)[0],
                                                borrower="Tendai Moyo",
                                                department="Theatre"))

    # Returning asks first, and names the file and the borrower.
    first = view._active.tree.get_children()[0]
    view._active.tree.selection_set(first)
    app.update()
    capture_dialog(app, view._return_loan, "23-loans-return-confirm")

    app._screen.set_status("Ready")
    app.update()


def capture_reports(app: App) -> None:
    """The reports view: a date range, and the same report by borrower."""
    app._screen.show("reports")
    app.update()
    view = app._screen._view

    grab(app, "40-reports-range")

    busiest = max((loan.borrower for loan in app.loans.returned()),
                  key=lambda name: sum(1 for loan in app.loans.returned()
                                       if loan.borrower == name))
    view._mode.set("borrower")
    view._mode_changed()
    view._borrower.insert(0, busiest)
    view.run_report()
    app.update()
    grab(app, "41-reports-by-borrower")


def capture_users(app: App) -> None:
    """The users view: the list, adding one, and changing a password."""
    app._screen.show("users")
    app.update()
    view = app._screen._view

    # The Add dialog, filled in. Submitting would close it, leaving nothing
    # to photograph, so the account itself is created straight afterwards.
    capture_dialog(app, view._add, "42-users-add",
                   fill=lambda d: (set_entry(d, "name", "Bea Chirwa"),
                                   set_entry(d, "username", "bea"),
                                   set_entry(d, "password", "demo-password"),
                                   set_entry(d, "role", "user"),
                                   set_entry(d, "email", "bea@example.test")))
    app.users.create("Bea Chirwa", "bea", "demo-password", role="user",
                     email="bea@example.test")
    view.refresh()
    app.update()
    grab(app, "43-users")

    view._table.tree.selection_set("bea")
    app.update()
    capture_dialog(app, view._change_password, "44-users-password",
                   fill=lambda d: (set_entry(d, "password", "new-password"),
                                   set_entry(d, "confirm", "new-password")))

    # The only administrator cannot be removed.
    view._table.tree.selection_set("shelton")
    app.update()
    capture_dialog(app, view._delete, "45-users-last-admin",
                   then=lambda d: d._confirm())

    app._screen.set_status("Ready")
    app.update()


def main() -> int:
    if sys.platform != "win32":
        print("This tool needs Windows to read the window bounds.")
        return 1

    OUT.mkdir(parents=True, exist_ok=True)
    workspace = Path(tempfile.mkdtemp(prefix="records-shots-"))
    fresh, seeded = workspace / "fresh.db", workspace / "seeded.db"

    try:
        print("first run")
        app = launch(fresh)
        grab(app, "01-setup")
        create_admin(app)
        grab(app, "02-setup-filled")
        app._screen._create()
        app.update()
        app.destroy()

        shutil.copy(fresh, seeded)
        print(seed_demo(Database(seeded)))

        print("signed in")
        app = launch(seeded)
        grab(app, "03-login")
        sign_in(app)
        grab(app, "04-patients")

        capture_patients(app)
        capture_scan(app, workspace)

        capture_loans(app)

        capture_reports(app)
        capture_users(app)

        app._screen.show("patients")
        app._screen.set_status("Exported 27 loans to loans.csv")
        app.update()
        grab(app, "50-status")
        app.destroy()
    finally:
        shutil.rmtree(workspace, ignore_errors=True)

    print(f"done -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
