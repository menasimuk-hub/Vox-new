"""Generate PWA icons from official icon-black.png (full-bleed) + dark splash screens."""
from __future__ import annotations

from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "dashboard.voxbulk.com" / "dashboard-web" / "public" / "pwa"
ICON_BLACK = ROOT / "voxbulk-api" / "logos" / "icon-black.png"
NAVY = (15, 27, 61, 255)  # #0f1b3d

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


def resize_cover(src: Image.Image, side: int) -> Image.Image:
    """Exact square resize — full-bleed official black icon, no padding."""
    return src.resize((side, side), Image.Resampling.LANCZOS)


def paste_centered(canvas: Image.Image, mark: Image.Image, size: int) -> None:
    icon = mark.copy()
    icon.thumbnail((size, size), Image.Resampling.LANCZOS)
    x = (canvas.width - icon.width) // 2
    y = (canvas.height - icon.height) // 2
    canvas.paste(icon, (x, y), icon if icon.mode == "RGBA" else None)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    black = Image.open(ICON_BLACK).convert("RGBA")

    # Install / home-screen icons = exact official black logo tile.
    for side, name in (
        (180, "apple-touch-icon-180.png"),
        (192, "icon-192.png"),
        (512, "icon-512.png"),
    ):
        resize_cover(black, side).convert("RGB").save(OUT / name, "PNG", optimize=True)
        print(f"wrote {name} (full-bleed icon-black)")

    # Also publish under brand-friendly aliases used by some caches.
    resize_cover(black, 192).convert("RGB").save(OUT / "icon-black-192.png", "PNG", optimize=True)
    resize_cover(black, 512).convert("RGB").save(OUT / "icon-black-512.png", "PNG", optimize=True)

    # Splash: dark navy with full black logo tile centered.
    for w, h, name in SIZES:
        img = Image.new("RGBA", (w, h), NAVY)
        tile = max(180, min(w, h) // 4)
        mark = resize_cover(black, tile).convert("RGBA")
        img.paste(mark, ((w - tile) // 2, (h - tile) // 2))
        img.convert("RGB").save(OUT / f"{name}.png", "PNG", optimize=True)
        print(f"wrote {name}.png ({w}x{h})")

    print(f"done -> {OUT}")


if __name__ == "__main__":
    main()
