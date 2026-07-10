"""Generate PWA install icons (black logo) + dark iOS splash screens."""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "dashboard.voxbulk.com" / "dashboard-web" / "public" / "pwa"
ICON_BLACK = ROOT / "voxbulk-api" / "logos" / "icon-black.png"
ICON_WHITE = ROOT / "voxbulk-api" / "logos" / "icon-white.png"
NAVY = (15, 27, 61, 255)  # #0f1b3d
WHITE = (255, 255, 255, 255)

SIZES = [
    (1290, 2796, "splash-1290x2796"),
    (1179, 2556, "splash-1179x2556"),
    (1170, 2532, "splash-1170x2532"),
    (1284, 2778, "splash-1284x2778"),
    (1125, 2436, "splash-1125x2436"),
    (1242, 2688, "splash-1242x2688"),
    (828, 1792, "splash-828x1792"),
    (750, 1334, "splash-750x1334"),
    (2048, 2732, "splash-2048x2732"),
    (1668, 2388, "splash-1668x2388"),
    (1640, 2360, "splash-1640x2360"),
    (1536, 2048, "splash-1536x2048"),
]


def paste_centered(canvas: Image.Image, mark: Image.Image, size: int) -> None:
    icon = mark.copy()
    icon.thumbnail((size, size), Image.Resampling.LANCZOS)
    x = (canvas.width - icon.width) // 2
    y = (canvas.height - icon.height) // 2
    canvas.paste(icon, (x, y), icon)


def rounded_white_plate(size: int, radius: int) -> Image.Image:
    plate = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(plate)
    draw.rounded_rectangle((0, 0, size - 1, size - 1), radius=radius, fill=WHITE)
    return plate


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    black = Image.open(ICON_BLACK).convert("RGBA")
    white = Image.open(ICON_WHITE).convert("RGBA")

    # Home-screen / install icons: official black mark on white (visible on Android/iOS).
    for side, mark_size, name in (
        (180, 120, "apple-touch-icon-180.png"),
        (192, 128, "icon-192.png"),
        (512, 340, "icon-512.png"),
    ):
        img = Image.new("RGBA", (side, side), WHITE)
        paste_centered(img, black, mark_size)
        img.convert("RGB").save(OUT / name, "PNG", optimize=True)
        print(f"wrote {name}")

    # Splash: dark navy with black logo on a white rounded plate.
    for w, h, name in SIZES:
        img = Image.new("RGBA", (w, h), NAVY)
        plate_size = max(160, min(w, h) // 5)
        plate = rounded_white_plate(plate_size, radius=max(24, plate_size // 6))
        mark = black.copy()
        mark.thumbnail((int(plate_size * 0.62), int(plate_size * 0.62)), Image.Resampling.LANCZOS)
        plate.paste(mark, ((plate_size - mark.width) // 2, (plate_size - mark.height) // 2), mark)
        img.paste(plate, ((w - plate_size) // 2, (h - plate_size) // 2), plate)
        img.convert("RGB").save(OUT / f"{name}.png", "PNG", optimize=True)
        print(f"wrote {name}.png ({w}x{h})")

    # Keep white mark available for in-app dark UI references if needed.
    _ = white
    print(f"done -> {OUT}")


if __name__ == "__main__":
    main()
