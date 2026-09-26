"""Generate the application icon into ``assets/``.

The icon is a neutral placeholder: a record card on the application's
accent colour. It deliberately carries no hospital's branding, so the
project can be published without putting a real organisation's mark on it.

Drawn at 4x and downsampled, which keeps the curves clean at 16px.

    python tools/make_icon.py
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

ASSETS = (Path(__file__).resolve().parents[1]
          / "src" / "records_manager" / "assets")

ACCENT = (0, 95, 184, 255)
WHITE = (255, 255, 255, 255)

#: Sizes Tk wants for the title bar and taskbar, plus 64 for the screens.
SIZES = (16, 32, 48, 64, 256)

MASTER = 1024
SCALE = MASTER // 256


def draw_icon() -> Image.Image:
    """Draw the master icon: a card with ruled lines on a rounded square."""
    image = Image.new("RGBA", (MASTER, MASTER), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    def box(x0: int, y0: int, x1: int, y1: int) -> tuple[int, int, int, int]:
        return (x0 * SCALE, y0 * SCALE, x1 * SCALE, y1 * SCALE)

    # Rounded square background, transparent outside the corners.
    draw.rounded_rectangle(box(0, 0, 256, 256), radius=56 * SCALE, fill=ACCENT)

    # The record card, offset slightly up-left so the stack reads as depth.
    draw.rounded_rectangle(box(74, 62, 196, 178), radius=12 * SCALE,
                           fill=(255, 255, 255, 90))
    draw.rounded_rectangle(box(60, 78, 182, 194), radius=12 * SCALE, fill=WHITE)

    # Ruled lines on the front card.
    for index, (left, right) in enumerate(((78, 150), (78, 164), (78, 136))):
        top = 104 + index * 24
        draw.rounded_rectangle(box(left, top, right, top + 10),
                               radius=5 * SCALE, fill=ACCENT)

    return image


def main() -> None:
    ASSETS.mkdir(exist_ok=True)
    master = draw_icon()
    for size in SIZES:
        resized = master.resize((size, size), Image.LANCZOS)
        path = ASSETS / f"icon-{size}.png"
        resized.save(path)
        print(f"wrote {path.relative_to(ASSETS.parents[2])}  ({size}x{size})")


if __name__ == "__main__":
    main()
