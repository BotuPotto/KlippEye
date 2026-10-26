#!/usr/bin/env python3
"""
Draws the icon of the browser tab: the same look as the app icon (the KlippEye logo on its dark violet tile) in three
sizes. build.py embeds the files of src/icons/ in the page, so the dashboard stays one file.

    python3 tools/make_favicon.py            (needs Pillow and numpy)

    src/icons/favicon-32.png         tab icon, rounded corners
    src/icons/favicon-64.png         the same for high-density screens
    src/icons/apple-touch-icon.png   180 px, full square (iOS and Android round it themselves): "add to home screen"

The logo is tools/assets/logo_klippeye.png (source: klippeye_g4.svg next to it); it is not redrawn here.
"""
import os
import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(HERE), "src", "icons")
MASTER = 720  # drawn large, then reduced: sharper small sizes
LOGO_WIDTH = 0.74  # of the icon's side: at 16-32 px every pixel counts
BASE = np.array((8, 11, 17), float)  # #080b11
VIOLET = np.array((122, 92, 255), float)  # #7a5cff


def background(size):
    """The tile: dark violet fading to black, i.e. CSS radial-gradient(circle at 50% 36%, rgba(122,92,255,.42), transparent 64%) on #080b11."""
    y, x = np.mgrid[0:size, 0:size]
    d = np.hypot(x / size - 0.5, y / size - 0.36) / np.hypot(0.5, 0.64)  # "circle" reaches the farthest corner
    a = (np.clip(1 - d / 0.64, 0, 1) * 0.42)[..., None]
    img = BASE * (1 - a) + VIOLET * a
    return Image.fromarray(np.clip(np.rint(img), 0, 255).astype("uint8"), "RGB").convert("RGBA")


def logo():
    im = Image.open(os.path.join(HERE, "assets", "logo_klippeye.png")).convert("RGBA")
    return im.crop(im.getbbox())


def master(rounded):
    icon = background(MASTER)
    mark = logo()
    width = round(MASTER * LOGO_WIDTH)
    mark = mark.resize((width, round(mark.height * width / mark.width)), Image.LANCZOS)
    icon.alpha_composite(mark, ((MASTER - mark.width) // 2, (MASTER - mark.height) // 2))
    if rounded:
        mask = Image.new("L", (MASTER * 2, MASTER * 2), 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, MASTER * 2 - 1, MASTER * 2 - 1), radius=round(MASTER * 2 * 0.225), fill=255)
        icon.putalpha(mask.resize((MASTER, MASTER), Image.LANCZOS))
    return icon


def main():
    os.makedirs(OUT, exist_ok=True)
    for name, size, rounded in (("favicon-32.png", 32, True), ("favicon-64.png", 64, True), ("apple-touch-icon.png", 180, False)):
        master(rounded).resize((size, size), Image.LANCZOS).save(os.path.join(OUT, name), optimize=True)
        print(name, size)


if __name__ == "__main__":
    main()
