"""Draw a synthetic admission form from fixture text.

Used for the scan preview in the screenshots and for the sample form in
``samples/``. Real admission forms carry a named patient's details, so the
repository never holds one: everything drawn here comes from the invented
fixtures under ``tests/fixtures/``.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures"

PAGE = (1000, 1400)
MARGIN = 60
LINE_HEIGHT = 34


def render_form(text: str, path: Path) -> Path:
    """Draw ``text`` as a filled-in paper form and save it to ``path``."""
    image = Image.new("RGB", PAGE, "white")
    draw = ImageDraw.Draw(image)

    try:
        font = ImageFont.truetype("consola.ttf", 19)
        heading = ImageFont.truetype("consolab.ttf", 26)
    except OSError:  # pragma: no cover - font missing on this machine
        font = heading = ImageFont.load_default()

    draw.text((MARGIN, 50), "ADMISSION FORM", font=heading, fill="black")
    draw.line((MARGIN, 95, PAGE[0] - MARGIN, 95), fill="black", width=2)
    for index, line in enumerate(text.splitlines()):
        draw.text((MARGIN, 130 + index * LINE_HEIGHT), line, font=font,
                  fill="#111111")

    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)
    return path


def render_fixture(name: str, path: Path) -> Path:
    """Draw the named fixture from ``tests/fixtures``."""
    return render_form((FIXTURES / f"{name}.txt").read_text(encoding="utf-8"),
                       path)
