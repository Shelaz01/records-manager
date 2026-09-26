"""Read an admission form: open or scan it, review what was read, then save.

Nothing reaches the database until the user has seen the values and agreed
to them. A hospital number that already exists never has its name or box
overwritten -- only the scan is attached.
"""
from __future__ import annotations

import shutil
import tkinter as tk
from pathlib import Path
from typing import TYPE_CHECKING
from tkinter import filedialog, ttk

from PIL import Image, ImageTk

from ...db import Patient, RecordsError
from ...scanning import ocr, scanner
from ...scanning.filing import (DEFAULT_EXTENSION, describe_episode,
                                 names_match, scan_filename, scans_dir)
from .. import style
from ..widgets import _centre_on_parent, show_error

if TYPE_CHECKING:
    from ...app import App

PREVIEW_SIZE = (240, 320)

OPEN_TYPES = [
    ("Images", "*.png *.jpg *.jpeg *.tif *.tiff *.bmp"),
    ("All files", "*.*"),
]


class ScanDialog(tk.Toplevel):
    """Open or scan a form, review the fields read off it, then save."""

    def __init__(self, master: tk.Misc, app: App) -> None:
        super().__init__(master)
        self.app = app
        self.saved = False

        self._image: Image.Image | None = None
        self._source: Path | None = None
        self._preview: ImageTk.PhotoImage | None = None
        self._episode_suffix: str | None = None
        self._existing: Patient | None = None

        self.title("Scan admission form")
        self.transient(master.winfo_toplevel())
        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.resizable(False, False)

        body = ttk.Frame(self, padding=style.PAD)
        body.pack(fill="both", expand=True)

        self._build_source(body)
        self._build_preview(body)
        self._build_form(body)
        self._build_actions(body)

        self._update_state()
        self.bind("<Escape>", lambda _event: self._cancel())

        # Loading a form adds a preview and may add the already-registered
        # panel, so the dialog grows after it is first placed. Re-clamp on a
        # size change, or a tall dialog ends up hanging off the window.
        self._last_size: tuple[int, int] | None = None
        self.bind("<Configure>", self._resized)
        _centre_on_parent(self, master)
        self.grab_set()
        self.wait_window(self)

    # -- layout ------------------------------------------------------------- #
    def _build_source(self, parent: ttk.Frame) -> None:
        header = ttk.Frame(parent)
        header.grid(row=0, column=0, columnspan=2, sticky="ew",
                    pady=(0, style.PAD))

        ttk.Label(header, text="Scan admission form",
                  style="Heading.TLabel").pack(anchor="w")

        buttons = ttk.Frame(header)
        buttons.pack(anchor="w", pady=(style.PAD_SMALL, 0))

        ttk.Button(buttons, text="Open image…", command=self._open_image).pack(
            side="left")
        self._scan_button = ttk.Button(buttons, text="Scan page",
                                       command=self._scan_page)
        self._scan_button.pack(side="left", padx=(style.PAD_SMALL, 0))

        # Availability is reported up front, not discovered by clicking.
        self._availability = ttk.Label(header, text="", style="Muted.TLabel",
                                       wraplength=520, justify="left")
        self._availability.pack(anchor="w", pady=(style.PAD_SMALL, 0))
        self._report_availability()

    def _report_availability(self) -> None:
        notes = []
        if not scanner.is_available():
            self._scan_button.state(["disabled"])
            notes.append(
                "No scanner: WIA scanning needs Windows and the scan extra. "
                "Open an image file instead.")
        if not ocr.is_available():
            notes.append(
                "No text recognition: install Tesseract to have the fields "
                "read automatically. You can still type them in.")
        self._availability.configure(text="\n".join(notes))
        if not notes:
            self._availability.pack_forget()

    def _build_preview(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="Preview", padding=style.PAD_SMALL)
        frame.grid(row=1, column=0, sticky="n", padx=(0, style.PAD))

        self._preview_label = ttk.Label(
            frame, text="No form loaded.\n\nOpen an image or scan a page.",
            style="Muted.TLabel", anchor="center", justify="center",
            width=34)
        self._preview_label.pack(fill="both", expand=True)
        frame.configure(width=PREVIEW_SIZE[0], height=PREVIEW_SIZE[1])
        frame.pack_propagate(False)

    def _build_form(self, parent: ttk.Frame) -> None:
        form = ttk.Frame(parent)
        form.grid(row=1, column=1, sticky="nsew")
        form.columnconfigure(1, weight=1, minsize=220)

        self._values = {name: tk.StringVar() for name in
                        ("hospital_num", "surname", "first_names", "box_no")}
        self._episode = tk.StringVar()

        ttk.Label(form, text="Read from the form", style="FieldLabel.TLabel").grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, style.PAD_SMALL))

        self._entries: dict[str, ttk.Entry] = {}
        rows = (("hospital_num", "Hospital number"), ("surname", "Surname"),
                ("first_names", "First names"), ("box_no", "Box number"))

        row = 1
        for key, label in rows:
            ttk.Label(form, text=f"{label} *", style="FieldLabel.TLabel").grid(
                row=row, column=0, sticky="w", padx=(0, style.PAD),
                pady=style.PAD_TINY)
            entry = ttk.Entry(form, textvariable=self._values[key])
            entry.grid(row=row, column=1, sticky="ew", pady=style.PAD_TINY)
            self._entries[key] = entry
            row += 1

            if key == "hospital_num":
                # Shown under the number so the reviewer can check it against
                # the paper, including the admission suffix that is
                # deliberately not part of the file number.
                ttk.Label(form, text="Episode number on form",
                          style="Hint.TLabel").grid(row=row, column=0,
                                                    sticky="w")
                ttk.Label(form, textvariable=self._episode,
                          style="FieldValue.TLabel").grid(
                    row=row, column=1, sticky="w", pady=(0, style.PAD_SMALL))
                row += 1

            if key == "box_no":
                # The box is assigned by the records office, so it is never
                # printed on the admission form and OCR can never supply it.
                ttk.Label(form, text="not on the form, enter manually",
                          style="Hint.TLabel").grid(
                    row=row, column=1, sticky="w", pady=(0, style.PAD_SMALL))
                row += 1

        # Every field gates Save, so every field re-checks it.
        for variable in self._values.values():
            variable.trace_add("write", lambda *_: self._revalidate())

        self._notice = ttk.Label(form, text="", style="Muted.TLabel",
                                 wraplength=320, justify="left")
        self._notice.grid(row=row, column=0, columnspan=2, sticky="w",
                          pady=(style.PAD_SMALL, 0))
        #: Where the already-registered panel goes, below everything else.
        self._existing_row = row + 1

        self._existing_box = ttk.LabelFrame(form, text="Already registered",
                                            padding=style.PAD_SMALL)
        self._existing_label = ttk.Label(self._existing_box, text="",
                                         wraplength=380, justify="left")
        self._existing_label.pack(anchor="w")
        self._mismatch = ttk.Label(self._existing_box, text="",
                                   style="Danger.TLabel", wraplength=380,
                                   justify="left")

    def _build_actions(self, parent: ttk.Frame) -> None:
        bar = ttk.Frame(parent)
        bar.grid(row=2, column=0, columnspan=2, sticky="e",
                 pady=(style.PAD, 0))

        ttk.Button(bar, text="Cancel", command=self._cancel).pack(
            side="left", padx=(0, style.PAD_SMALL))
        self._attach_button = ttk.Button(
            bar, text="Attach scan to existing record",
            command=self._attach_to_existing)
        self._save_button = ttk.Button(bar, text="Save new patient",
                                       style="Accent.TButton", command=self._save)
        self._save_button.pack(side="left")

    # -- loading ------------------------------------------------------------ #
    def _open_image(self) -> None:
        chosen = filedialog.askopenfilename(
            parent=self, title="Open admission form", filetypes=OPEN_TYPES)
        if not chosen:
            return
        try:
            image = Image.open(chosen)
            image.load()
        except (OSError, ValueError) as error:
            show_error(self, "Could not open image",
                       f"{Path(chosen).name} could not be read.\n\n{error}")
            return
        self._load(image, Path(chosen))

    def _scan_page(self) -> None:
        try:
            image = scanner.scan_page()
        except scanner.ScannerUnavailableError as error:
            show_error(self, "Cannot scan", str(error))
            return
        if image is None:
            show_error(self, "No scanner found",
                       "No scanner is connected. Open an image file instead.")
            return
        self._load(image, None)

    def _load(self, image: Image.Image, source: Path | None) -> None:
        """Show a form and fill the fields in from it."""
        self._image = image
        self._source = source
        self._show_preview(image)

        fields = self._read(image)
        self._apply(fields)

    def _read(self, image: Image.Image) -> dict[str, str | None]:
        """Run OCR, or return empty fields when it is unavailable."""
        if not ocr.is_available():
            return {}
        try:
            text = ocr.extract_text(ocr.preprocess(image))
        except ocr.OCRUnavailableError as error:
            show_error(self, "Could not read the form", str(error))
            return {}
        return ocr.parse_fields(text)

    def _apply(self, fields: dict[str, str | None]) -> None:
        """Pre-fill the form, presenting names the way a person writes them."""
        self._episode_suffix = fields.get("episode_suffix")
        self._episode.set(describe_episode(fields.get("episode"),
                                           fields.get("hospital_num"),
                                           self._episode_suffix))
        self._values["hospital_num"].set(fields.get("hospital_num") or "")
        self._values["surname"].set(ocr.title_case(fields.get("surname")) or "")
        self._values["first_names"].set(
            ocr.title_case(fields.get("first_names")) or "")
        self._revalidate()

    def _show_preview(self, image: Image.Image) -> None:
        thumbnail = image.copy()
        thumbnail.thumbnail(PREVIEW_SIZE)
        self._preview = ImageTk.PhotoImage(thumbnail, master=self)
        self._preview_label.configure(image=self._preview, text="")

    # -- existing patients --------------------------------------------------- #
    def _revalidate(self) -> None:
        """Look the number up, and re-check whether saving is possible yet."""
        number = self._values["hospital_num"].get().strip()
        self._existing = None
        if number:
            try:
                self._existing = self.app.patients.get(number)
            except RecordsError:
                self._existing = None
        self._update_state()

    def _can_save(self) -> bool:
        """A new patient needs every field, including the box OCR cannot read."""
        return self._image is not None and all(
            self._values[key].get().strip()
            for key in ("hospital_num", "surname", "first_names", "box_no"))

    def _update_state(self) -> None:
        has_image = self._image is not None
        for entry in self._entries.values():
            entry.state(["!disabled"] if has_image else ["disabled"])

        if self._existing is not None:
            self._show_existing(self._existing)
        else:
            self._existing_box.grid_forget()
            self._notice.configure(
                text="Check the details against the form before saving."
                if has_image else "")
            self._attach_button.pack_forget()
            self._save_button.pack(side="left")

        # Attaching needs only a form and a match; saving a new patient
        # needs every field filled in.
        self._save_button.state(["!disabled"] if self._can_save()
                                else ["disabled"])
        self._attach_button.state(["!disabled"] if has_image else ["disabled"])

    def _show_existing(self, patient: Patient) -> None:
        """Offer to attach the scan rather than to create a second record."""
        self._existing_box.grid(row=self._existing_row, column=0, columnspan=2,
                                sticky="ew", pady=(style.PAD_SMALL, 0))
        self._existing_label.configure(
            text=f"Registered to {patient.surname}, {patient.first_names} "
                 f"({patient.box_no}). Attaching updates the scan only — "
                 f"the name and box number are left as they are.")

        if names_match(patient.surname, patient.first_names,
                              self._values["surname"].get(),
                              self._values["first_names"].get()):
            self._mismatch.pack_forget()
        else:
            self._mismatch.configure(
                text=f"The form reads {self._values['surname'].get()}, "
                     f"{self._values['first_names'].get()}. Check the hospital "
                     f"number — a misread digit is likelier than a "
                     f"changed name.")
            self._mismatch.pack(anchor="w", pady=(style.PAD_SMALL, 0))

        self._notice.configure(text="")
        self._save_button.pack_forget()
        self._attach_button.pack(side="left")

    # -- saving -------------------------------------------------------------- #
    def _file_scan(self, hospital_num: str) -> str | None:
        """Copy the form into the scans folder. Returns the stored path."""
        if self._image is None:
            return None

        extension = (self._source.suffix if self._source
                     else DEFAULT_EXTENSION)
        target_dir = scans_dir(self.app.db.path)
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / scan_filename(
            hospital_num, self._episode_suffix, extension)

        if self._source is not None:
            shutil.copyfile(self._source, target)
        else:
            self._image.save(target)
        return str(target)

    def _save(self) -> None:
        values = {key: variable.get().strip()
                  for key, variable in self._values.items()}
        missing = [label for key, label in
                   (("hospital_num", "Hospital number"), ("surname", "Surname"),
                    ("first_names", "First names"), ("box_no", "Box number"))
                   if not values[key]]
        if missing:
            self._notice.configure(text=f"Please fill in: {', '.join(missing)}.")
            return

        try:
            scan_path = self._file_scan(values["hospital_num"])
            self.app.patients.add(Patient(
                hospital_num=values["hospital_num"],
                surname=values["surname"],
                first_names=values["first_names"],
                box_no=values["box_no"],
                scan_path=scan_path,
            ))
        except RecordsError as error:
            show_error(self, "Could not save patient", str(error))
            return
        except OSError as error:
            show_error(self, "Could not file the scan", str(error))
            return

        self.saved = True
        self.app.set_status(f"Added {values['hospital_num']} from a scanned form")
        self.destroy()

    def _attach_to_existing(self) -> None:
        """Update the scan only, never the name or the box number."""
        patient = self._existing
        if patient is None:
            return

        try:
            scan_path = self._file_scan(patient.hospital_num)
            self.app.patients.update(patient.hospital_num, Patient(
                hospital_num=patient.hospital_num,
                surname=patient.surname,
                first_names=patient.first_names,
                box_no=patient.box_no,
                scan_path=scan_path,
            ))
        except RecordsError as error:
            show_error(self, "Could not attach the scan", str(error))
            return
        except OSError as error:
            show_error(self, "Could not file the scan", str(error))
            return

        self.saved = True
        self.app.set_status(f"Attached a scan to {patient.hospital_num}")
        self.destroy()

    def _resized(self, event: tk.Event) -> None:
        """Keep the dialog inside its parent as its contents change size."""
        if event.widget is not self:
            return
        size = (event.width, event.height)
        if size == self._last_size:
            return
        self._last_size = size
        _centre_on_parent(self, self.master)

    def _cancel(self) -> None:
        self.saved = False
        self.destroy()
