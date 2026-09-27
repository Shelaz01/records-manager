"""Read patient details off a scanned admission form.

The pipeline is: ``preprocess`` cleans the image up, ``extract_text`` runs
Tesseract over it, and ``parse_fields`` pulls the three fields the patient
form needs out of that text.

Tesseract and OpenCV are optional. Nothing here imports them at module
level, so the application always starts; call :func:`is_available` before
offering the scan features and disable them when it returns False.
"""
from __future__ import annotations

import os
import re

from PIL import Image

#: Tesseract options: one uniform block of text, default LSTM engine.
TESSERACT_CONFIG = "--psm 6 --oem 3"

#: Override the Tesseract binary location without touching the code.
TESSERACT_CMD_ENV = "TESSERACT_CMD"

#: Set to any non-empty value to make the application behave as though
#: Tesseract were not installed. Useful for checking that the degraded path
#: still works on a machine that does have it, and for documenting that
#: path, but it is also a way to turn OCR off on a machine where it is
#: installed but unwanted.
DISABLE_ENV = "RECORDS_DISABLE_OCR"


def _disabled() -> bool:
    return bool(os.environ.get(DISABLE_ENV))


class OCRUnavailableError(RuntimeError):
    """Tesseract or OpenCV is not installed, or Tesseract will not run."""


_DISABLED_MESSAGE = (
    "Text recognition is switched off: unset RECORDS_DISABLE_OCR to use it.")


# --------------------------------------------------------------------------- #
# Availability
# --------------------------------------------------------------------------- #
def _configure_tesseract(pytesseract) -> None:
    """Point pytesseract at the binary named by ``TESSERACT_CMD``, if set."""
    command = os.environ.get(TESSERACT_CMD_ENV)
    if command:
        pytesseract.pytesseract.tesseract_cmd = command


def is_available() -> bool:
    """True when preprocessing and OCR can actually run.

    Checks that both libraries import *and* that the Tesseract binary
    responds, since pytesseract installs fine without Tesseract itself.
    """
    if _disabled():
        return False
    try:
        import cv2  # noqa: F401
        import pytesseract
    except ImportError:
        return False

    _configure_tesseract(pytesseract)
    try:
        pytesseract.get_tesseract_version()
    except Exception:
        return False
    return True


# --------------------------------------------------------------------------- #
# Image pipeline
# --------------------------------------------------------------------------- #
def preprocess(image: Image.Image) -> Image.Image:
    """Return a black-and-white copy of ``image`` that OCRs more reliably.

    Converts to greyscale and applies Otsu thresholding, which picks the
    cut-off per image and so copes with the uneven lighting typical of a
    photographed or flatbed-scanned form.
    """
    if _disabled():
        raise OCRUnavailableError(_DISABLED_MESSAGE)
    try:
        import cv2
        import numpy as np
    except ImportError as error:  # pragma: no cover - needs [scan] absent
        raise OCRUnavailableError(
            "Image preprocessing needs OpenCV. Install the scan extra: "
            'pip install "records-manager[scan]"'
        ) from error

    greyscale = np.array(image.convert("L"))
    _, thresholded = cv2.threshold(
        greyscale, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return Image.fromarray(thresholded)


def extract_text(image: Image.Image) -> str:
    """Run Tesseract over ``image`` and return the raw recognised text."""
    if _disabled():
        raise OCRUnavailableError(_DISABLED_MESSAGE)
    try:
        import pytesseract
    except ImportError as error:  # pragma: no cover - needs [scan] absent
        raise OCRUnavailableError(
            "Text extraction needs Tesseract. Install the scan extra: "
            'pip install "records-manager[scan]"'
        ) from error

    _configure_tesseract(pytesseract)
    try:
        return pytesseract.image_to_string(image, config=TESSERACT_CONFIG)
    except pytesseract.TesseractNotFoundError as error:
        raise OCRUnavailableError(
            "Tesseract is not installed or not on PATH. Install it, or set "
            f"{TESSERACT_CMD_ENV} to the full path of the executable."
        ) from error


# --------------------------------------------------------------------------- #
# Field parsing
# --------------------------------------------------------------------------- #
# Values sit to the right of their label on the same line, and the next
# column's label ends the value. Captures never cross a line break: on these
# forms the following line is the next field, so running on would swallow it.
_STOP_WORDS = ("Title", "Episode", "Gender", "Race", "Date", "Relationship",
               "Nationality", "ID No")

# "Episode Number" sits mid-line, after the first names, so it is not anchored.
# Only [ \t] separates the parts, never \s, so a blank field cannot reach past
# the end of the line and capture the next one. The lookahead stops the label
# itself being read as the value when the field is empty.
_EPISODE_RE = re.compile(
    r"Episode(?:[ \t]+(?:Numbers?|No\.?))?[ \t]*[:\-]?[ \t]*"
    r"(?!Numbers?\b)(?!No\b)([A-Za-z0-9:/\-]+)",
    re.IGNORECASE,
)


def _label_re(label: str) -> re.Pattern[str]:
    """Match ``label`` at the start of a line and capture the rest of it.

    Anchoring matters: the form repeats these labels further down for the
    next of kin and the medical aid member, prefixed ("Member's Surname"),
    and those must not be mistaken for the patient's own details.
    """
    return re.compile(rf"^[ \t]*{label}[ \t]*[:\-]?[ \t]*(.*)$",
                      re.IGNORECASE | re.MULTILINE)


_FIRST_NAMES_RE = _label_re(r"First\s+Names")
_SURNAME_RE = _label_re(r"Surname")


#: Stray marks OCR leaves at the edge of a value, e.g. a ruled line read as
#: a dash or the tail of a box border. Only trimmed from the ends.
_EDGE_NOISE = " .,:;|_-*"


def _clean(value: str | None) -> str | None:
    """Collapse whitespace and trim edge noise, returning None if nothing is left."""
    if value is None:
        return None
    collapsed = " ".join(value.split()).strip(_EDGE_NOISE)
    return collapsed or None


def _value_for(pattern: re.Pattern[str], text: str) -> str | None:
    """Return the first match's value, cut off at the next column's label."""
    match = pattern.search(text)
    if match is None:
        return None

    value = match.group(1)
    for stop in _STOP_WORDS:
        value = re.split(rf"\b{re.escape(stop)}\b", value, maxsplit=1,
                         flags=re.IGNORECASE)[0]
    return _clean(value)


#: Characters Tesseract routinely confuses with digits. Applied only to the
#: episode number, never to a name: "Ian" must not become "1an".
_DIGIT_FIXUPS = str.maketrans({"O": "0", "o": "0", "l": "1", "I": "1"})


def split_episode(raw: str) -> tuple[str | None, str | None]:
    """Split an episode number such as 'A10619:2' into base and suffix.

    The base identifies the patient's file and is what the hospital number
    is; the part after the colon counts that patient's admissions. They are
    kept apart rather than run together: '10619' and '2' concatenated would
    read as file 106192, which belongs to somebody else.

    A single leading 'A' is dropped. Only the leading one -- removing every
    'A' would corrupt a number that legitimately contains the letter.
    """
    value = raw.strip()
    if value[:1] in ("A", "a"):
        value = value[1:]
    base, _, suffix = value.partition(":")
    return _clean(base.translate(_DIGIT_FIXUPS)), _clean(suffix)


def title_case(name: str | None) -> str | None:
    """Present an OCR'd name as a person would write it.

    Forms are filled in capitals, so the raw text is shouted. Handles the
    parts of a hyphenated surname and each of several first names.
    """
    if name is None:
        return None
    return _clean(name.title())


def parse_fields(text: str) -> dict[str, str | None]:
    """Pull the patient's details out of the OCR text of an admission form.

    Returns ``hospital_num`` (the episode base), ``episode`` (the number
    exactly as read, for the reviewer to check against the paper),
    ``episode_suffix`` (the admission count after the colon, if any),
    ``surname`` and ``first_names``.

    A pure function over ``text`` -- no file or network access -- so it can
    be tested against captured OCR output without Tesseract installed.
    Values are returned as they were read, including their capitalisation:
    presenting them is the caller's business. Missing fields come back as
    None rather than a placeholder string, so the caller can tell "not
    found" from a value the user should review.
    """
    match = _EPISODE_RE.search(text)
    raw_episode = _clean(match.group(1)) if match else None
    base, suffix = split_episode(raw_episode) if raw_episode else (None, None)

    return {
        "hospital_num": base,
        "episode": raw_episode,
        "episode_suffix": suffix,
        "surname": _value_for(_SURNAME_RE, text),
        "first_names": _value_for(_FIRST_NAMES_RE, text),
    }
