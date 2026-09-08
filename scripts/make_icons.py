"""Pixel-hinted CaYaScribe icons. Windows taskbar cannot use SVG; it needs a multi-size ICO."""

from __future__ import annotations

import io
import struct
from pathlib import Path

from PIL import Image, ImageDraw

NAVY = (17, 24, 38, 255)
WHITE = (248, 250, 252, 255)
RED = (220, 38, 38, 255)

ROOT = Path(__file__).resolve().parents[1]
ICONS = ROOT / "apps" / "desktop" / "src-tauri" / "icons"
PUBLIC = ROOT / "apps" / "desktop" / "public"


def draw_icon(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), NAVY)
    d = ImageDraw.Draw(img)
    m = max(2, round(size * 0.18))
    bar_w = max(2, round(size * 0.12))
    inner = size - 2 * m
    gap = max(1, round((inner - 3 * bar_w) / 2))
    total_w = 3 * bar_w + 2 * gap
    x0 = (size - total_w) // 2
    red_h = max(2, round(size * 0.055))
    red_y = size - m - red_h
    baseline = red_y - max(2, round(size * 0.08))
    max_h = max(bar_w, baseline - m)
    heights = (0.55, 1.0, 0.42)
    tiny = size <= 32
    for i, hf in enumerate(heights):
        h = max(bar_w, round(max_h * hf))
        x = x0 + i * (bar_w + gap)
        y = baseline - h
        box = [x, y, x + bar_w - 1, y + h - 1]
        if tiny:
            d.rectangle(box, fill=WHITE)
        else:
            d.rounded_rectangle(box, radius=max(1, bar_w // 2), fill=WHITE)
    rx = (size - total_w) // 2
    red_box = [rx, red_y, rx + total_w - 1, red_y + red_h - 1]
    if tiny:
        d.rectangle(red_box, fill=RED)
    else:
        d.rounded_rectangle(red_box, radius=max(1, red_h // 2), fill=RED)
    return img


def save_ico(path: Path, images: list[Image.Image]) -> None:
    entries: list[tuple[int, int, int, int]] = []
    blobs: list[bytes] = []
    offset = 6 + 16 * len(images)
    for im in images:
        buf = io.BytesIO()
        im.save(buf, format="PNG")
        data = buf.getvalue()
        w, h = im.size
        entries.append((w % 256, h % 256, len(data), offset))
        blobs.append(data)
        offset += len(data)
    with path.open("wb") as f:
        f.write(struct.pack("<HHH", 0, 1, len(images)))
        for w, h, nbytes, off in entries:
            f.write(struct.pack("<BBBBHHII", w, h, 0, 0, 1, 32, nbytes, off))
        for blob in blobs:
            f.write(blob)


def main() -> None:
    ICONS.mkdir(parents=True, exist_ok=True)
    PUBLIC.mkdir(parents=True, exist_ok=True)
    sizes = [16, 20, 24, 32, 40, 48, 64, 128, 256, 512, 1024]
    by_size = {s: draw_icon(s) for s in sizes}
    by_size[32].save(ICONS / "32x32.png")
    by_size[128].save(ICONS / "128x128.png")
    by_size[256].save(ICONS / "128x128@2x.png")
    by_size[1024].save(ICONS / "icon.png")
    by_size[512].save(PUBLIC / "logo-icon.png")
    by_size[256].save(PUBLIC / "logo-mark.png")
    ico_sizes = [16, 20, 24, 32, 40, 48, 64, 128, 256]
    save_ico(ICONS / "icon.ico", [by_size[s] for s in ico_sizes])
    print("icons:", ", ".join(str(s) for s in sizes))


if __name__ == "__main__":
    main()
