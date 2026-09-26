"""Where a scanned admission form is filed, and under what name.

Pure functions, kept out of the UI so the naming rules can be tested
without a display or a scanner.
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher
from pathlib import Path

#: Anything outside this set is replaced, so a hospital number read off a
#: form can never escape the scans directory or upset the filesystem.
_UNSAFE = re.compile(r"[^A-Za-z0-9_-]")

#: Extension used when the source file has none we recognise.
DEFAULT_EXTENSION = ".png"

KNOWN_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"})

#: Below this, two names are treated as different people rather than as one
#: name misread. Tuned to accept OCR noise ("NCUBE" vs "NCU8E") but reject a
#: different surname, which points at a misread hospital number.
NAME_MATCH_THRESHOLD = 0.8


def scan_filename(hospital_num: str, suffix: str | None = None,
                  extension: str = DEFAULT_EXTENSION) -> str:
    """Name for a scan: the file number, plus the admission it came from.

    Without the suffix a patient's second admission would overwrite the
    first, losing the earlier form.
    """
    stem = f"{hospital_num}_{suffix}" if suffix else hospital_num
    extension = extension.lower()
    if not extension.startswith("."):
        extension = f".{extension}"
    if extension not in KNOWN_EXTENSIONS:
        extension = DEFAULT_EXTENSION
    return f"{_UNSAFE.sub('-', stem)}{extension}"


def scans_dir(database_path: Path) -> Path:
    """The scans folder that belongs with a database file."""
    return Path(database_path).parent / "scans"


def describe_episode(raw: str | None, base: str | None,
                     suffix: str | None) -> str:
    """Explain the episode number as read, and what was taken from it.

    Dropping the admission suffix is deliberate but silent, so the reviewer
    is shown the working: "A10619:2 (admission 2 -> file 10619)".
    """
    if not raw:
        return "not found"
    if suffix and base:
        return f"{raw} (admission {suffix} → file {base})"
    return raw


def names_match(stored_surname: str, stored_first_names: str,
                read_surname: str | None, read_first_names: str | None) -> bool:
    """Whether an OCR'd name plausibly belongs to the stored record.

    Used to spot a misread hospital number: if the number matches a patient
    but the name does not, the number is far more likely to be wrong than
    the patient to have changed their name.

    Each field is judged on its own, and only where OCR read something. A
    field it could not read is no evidence either way, so a form whose first
    names came out blank does not get reported as the wrong patient.
    """
    pairs = [(stored, read) for stored, read in
             ((stored_surname, read_surname),
              (stored_first_names, read_first_names))
             if read and read.strip()]
    return all(_similar(stored, read) for stored, read in pairs)


def _similar(stored: str, read: str) -> bool:
    """Whether one name is plausibly the other, misread."""
    stored, read = _normalise(stored), _normalise(read)
    if not read:
        return True
    # "Tendai" against a stored "Tendai John": OCR caught part of the name,
    # which is not a different person.
    if stored.startswith(read) or read.startswith(stored):
        return True
    return SequenceMatcher(None, stored, read).ratio() >= NAME_MATCH_THRESHOLD


def _normalise(name: str) -> str:
    return " ".join(name.split()).casefold()
