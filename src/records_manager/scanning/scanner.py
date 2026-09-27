"""Thin wrapper around the vendored ``wia_scan`` package.

WIA is a Windows-only API, so scanning is optional: the application runs
without a scanner and on other platforms. Call :func:`is_available` before
offering the feature.

The wrapper deliberately does three things the old ``segment.py`` did not:
it scans exactly one page per call rather than looping a fixed number of
times, it returns the image instead of writing files into the working
directory, and it raises instead of showing message boxes, leaving all user
interaction to the UI layer.
"""
from __future__ import annotations

import os
import sys

from PIL import Image

#: Set to any non-empty value to make the application behave as though no
#: scanner were attached, the same switch as RECORDS_DISABLE_OCR.
DISABLE_ENV = "RECORDS_DISABLE_SCANNER"


def _disabled() -> bool:
    return bool(os.environ.get(DISABLE_ENV))


class ScannerUnavailableError(RuntimeError):
    """No scanner support: wrong platform, missing package, or no device."""


_DISABLED_MESSAGE = (
    "Scanning is switched off: unset RECORDS_DISABLE_SCANNER to use it.")


def is_available() -> bool:
    """True when this machine can drive a WIA scanner."""
    if _disabled():
        return False
    if sys.platform != "win32":
        return False
    try:
        from . import wia_scan  # noqa: F401
    except ImportError:
        return False
    return True


def _require_wia_scan():
    """Import the vendored package, or explain why scanning is unavailable."""
    if _disabled():
        raise ScannerUnavailableError(_DISABLED_MESSAGE)
    if sys.platform != "win32":
        raise ScannerUnavailableError(
            "Scanning uses Windows Image Acquisition and is only available "
            "on Windows. Open an image file instead.")
    try:
        from . import wia_scan
    except ImportError as error:
        raise ScannerUnavailableError(
            "Scanner support is not installed. Install the scan extra: "
            'pip install "records-manager[scan]"'
        ) from error
    return wia_scan


def list_devices() -> list[tuple[str, str]]:
    """Return the connected scanners as ``(device_id, name)`` pairs."""
    wia_scan = _require_wia_scan()
    manager = wia_scan.get_device_manager()

    devices: list[tuple[str, str]] = []
    for index in range(1, manager.DeviceInfos.Count + 1):
        info = manager.DeviceInfos(index)
        name = info.DeviceID
        for property_ in info.Properties:
            if property_.Name == "Name":
                name = property_.Value
                break
        devices.append((info.DeviceID, name))
    return devices


def scan_page(device_uid: str | None = None) -> Image.Image | None:
    """Scan a single page and return it, or None if no scanner is connected.

    Pass ``device_uid`` to choose a scanner; with no id the first connected
    device is used. One call scans one page — the caller decides whether to
    ask for another, so a mis-scan costs one page rather than a fixed batch.
    """
    wia_scan = _require_wia_scan()

    if device_uid is None:
        devices = list_devices()
        if not devices:
            return None
        device_uid = devices[0][0]

    # connect_to_device_by_uid prompts on stdin when quiet is False, which
    # would hang a GUI with no console attached.
    device = wia_scan.connect_to_device_by_uid(device_uid, quiet=True)
    return wia_scan.scan_side(device=device, quiet=True)
