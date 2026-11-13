#!/usr/bin/env python3
"""The small icon of the notifications (the white shape in the status bar).

Android wants a white picture on a transparent background, 24 dp: the shape is the KlippEye logo's
(tools/assets/logo_klippeye_mono.png, the same as the colour logo, with an empty ring around the pupil).
Writes res/drawable-<density>/ic_stat_klippeye.png.

    python3 tools/make_notification_icon.py      (needs Pillow)
"""
import os
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "..", "app", "src", "main", "res")
SIZES = {"mdpi": 24, "hdpi": 36, "xhdpi": 48, "xxhdpi": 72, "xxxhdpi": 96}
MARGIN = 0.06  # room around the shape, as a fraction of the side


def main():
    alpha = Image.open(os.path.join(HERE, "assets", "logo_klippeye_mono.png")).convert("RGBA").split()[-1]
    alpha = alpha.crop(alpha.getbbox())
    for density, side in SIZES.items():
        room = side * (1 - 2 * MARGIN)
        scale = min(room / alpha.width, room / alpha.height)
        size = (max(1, round(alpha.width * scale)), max(1, round(alpha.height * scale)))
        shape = alpha.resize(size, Image.LANCZOS)
        icon = Image.new("RGBA", (side, side), (255, 255, 255, 0))
        icon.paste(Image.new("RGBA", size, (255, 255, 255, 255)), ((side - size[0]) // 2, (side - size[1]) // 2), shape)
        folder = os.path.join(RES, "drawable-" + density)
        os.makedirs(folder, exist_ok=True)
        icon.save(os.path.join(folder, "ic_stat_klippeye.png"), optimize=True)
        print(density, side, size)


if __name__ == "__main__":
    main()
