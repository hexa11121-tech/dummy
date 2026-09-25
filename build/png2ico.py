#!/usr/bin/env python3
"""Convert a PNG to a Windows .ico file.

Uses Pillow when available (multi-size icon); otherwise falls back to
embedding the PNG as a single 256px PNG-compressed icon entry (Vista+),
which Windows scales as needed.

Usage: python build/png2ico.py assets/icon.png assets/icon.ico
"""
from __future__ import annotations

import struct
import sys


def with_pillow(png_path: str, ico_path: str) -> bool:
    try:
        from PIL import Image
    except ImportError:
        return False
    img = Image.open(png_path).convert("RGBA")
    sizes = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)]
    img.save(ico_path, format="ICO", sizes=sizes)
    return True


def with_raw_png(png_path: str, ico_path: str) -> None:
    with open(png_path, "rb") as f:
        png = f.read()
    if png[:8] != b"\x89PNG\r\n\x1a\n":
        raise SystemExit(f"{png_path} is not a PNG")
    # read width/height from IHDR
    w, h = struct.unpack(">II", png[16:24])
    if w > 256 or h > 256:
        # ICO entries cap at 256; embed anyway, Windows downscales
        pass
    w_b = 0 if w >= 256 else w
    h_b = 0 if h >= 256 else h

    icondir = struct.pack("<HHH", 0, 1, 1)          # reserved, type=icon, count
    entry = struct.pack("<BBBBHHII", w_b, h_b, 0, 0, 1, 32,
                        len(png), 6 + 16)
    with open(ico_path, "wb") as f:
        f.write(icondir + entry + png)


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    png_path, ico_path = sys.argv[1], sys.argv[2]
    if with_pillow(png_path, ico_path):
        print(f"wrote {ico_path} (Pillow, multi-size)")
    else:
        with_raw_png(png_path, ico_path)
        print(f"wrote {ico_path} (raw PNG entry)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
