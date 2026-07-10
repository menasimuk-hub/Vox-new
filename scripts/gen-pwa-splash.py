"""Generate dark navy PWA icons + iOS apple-touch-startup-image assets."""
from __future__ import annotations

from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "dashboard.voxbulk.com" / "dashboard-web" / "public" / "pwa"
ICON = ROOT / "voxbulk-api" / "logos" / "icon-white.png"
BG = (15, 27, 61, 255)  # #0f1b3d

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


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    icon = Image.open(ICON).convert("RGBA")

    ati = Image.new("RGBA", (180, 180), BG)
    paste_centered(ati, icon, 112)
    ati.convert("RGB").save(OUT / "apple-touch-icon-180.png", "PNG", optimize=True)

    for side, mark_size, name in ((192, 120, "icon-192.png"), (512, 320, "icon-512.png")):
        img = Image.new("RGBA", (side, side), BG)
        paste_centered(img, icon, mark_size)
        img.convert("RGB").save(OUT / name, "PNG", optimize=True)

    for w, h, name in SIZES:
        img = Image.new("RGBA", (w, h), BG)
        paste_centered(img, icon, max(96, min(w, h) // 6))
        img.convert("RGB").save(OUT / f"{name}.png", "PNG", optimize=True)
        print(f"wrote {name}.png ({w}x{h})")

    print(f"done -> {OUT}")


if __name__ == "__main__":
    main()
