#!/usr/bin/env python3
"""
Makes the app's pictures (icon, adaptive icon, splash) in the style of the dashboard.

    python3 tools/make_icons.py            (needs Pillow and numpy)

The KlippEye logo is NOT redrawn: it is assets/logo_klippeye.png (source: assets/klippeye_g4.svg), with its own
colours; the shape for the one-colour icons is assets/logo_klippeye_mono.png (source: assets/klippeye_g4_mono.svg;
the pupil has an empty ring around it). Only what surrounds it is made here:
    icon         the dark violet tile fading to black (the icon's background)
    splash       the dashboard's background (src/css/10-base.css: #040507 with the violet at the top), without a tile

Writes in app/src/main/res/:
    drawable-nodpi/ic_launcher_background.png   background of the adaptive icon (432 px = 108 dp at xxxhdpi)
    drawable-nodpi/ic_launcher_foreground.png   the logo, inside the adaptive icon's safe zone
    drawable-nodpi/ic_launcher_monochrome.png   the logo's shape (themed icons of Android 13)
    drawable-nodpi/ic_splash_icon.png           the logo of the system splash (Android 12+)
    drawable-nodpi/splash_logo.png              the logo of the app's splash, the same size as the system's
    drawable-nodpi/splash_bg.png                the background of the app's splash
    mipmap-*/ic_launcher.png, ic_launcher_round.png   icons for Android 7.x (no adaptive icons)
"""
import os
import numpy as np
from PIL import Image, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
RES = os.path.join(ROOT, "app", "src", "main", "res")
LOGO = os.path.join(HERE, "assets", "logo_klippeye.png")
LOGO_MONO = os.path.join(HERE, "assets", "logo_klippeye_mono.png")

BASE = np.array([4, 5, 7], float)  # --oui-bg, the dashboard's background
TILE_BASE = np.array([8, 11, 17], float)  # #080b11, the black of the tile
VIOLET = np.array([122, 92, 255], float)  # #7a5cff, the dark violet of the tile and of the background
rng = np.random.default_rng(7)


def to_image(img, dither=True):
    if dither:
        img = img + rng.uniform(-0.5, 0.5, img.shape)
    return Image.fromarray(np.clip(np.rint(img), 0, 255).astype("uint8"), "RGB")


def load_logo(path=LOGO):
    """The logo with its colours, cropped to its content."""
    im = Image.open(path).convert("RGBA")
    return im.crop(im.getchannel("A").getbbox())


def place(logo, size, width_fraction):
    """The logo, `width_fraction` of the square canvas `size` wide, in the middle."""
    w = int(size * width_fraction)
    h = int(w * logo.height / logo.width)
    layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    layer.alpha_composite(logo.resize((w, h), Image.LANCZOS), ((size - w) // 2, (size - h) // 2))
    return layer


def cropped(logo, content_px, pad_fraction=0.07):
    """The logo `content_px` wide, with a transparent margin around it (so its size in the layout stays that of the system splash)."""
    w = content_px
    h = int(w * logo.height / logo.width)
    pad = int(w * pad_fraction)
    layer = Image.new("RGBA", (w + 2 * pad, h + 2 * pad), (0, 0, 0, 0))
    layer.alpha_composite(logo.resize((w, h), Image.LANCZOS), (pad, pad))
    return layer


def squircle_mask(size, n=5.0, scale=4):
    """A "squircle" mask (superellipse), anti-aliased."""
    s = size * scale
    y, x = np.mgrid[0:s, 0:s]
    u = (x + 0.5) / s * 2 - 1
    v = (y + 0.5) / s * 2 - 1
    m = (np.abs(u) ** n + np.abs(v) ** n <= 1).astype("uint8") * 255
    return Image.fromarray(m, "L").resize((size, size), Image.LANCZOS)


def circle_mask(size, scale=4):
    s = size * scale
    y, x = np.mgrid[0:s, 0:s]
    m = (((x + 0.5) / s * 2 - 1) ** 2 + ((y + 0.5) / s * 2 - 1) ** 2 <= 1).astype("uint8") * 255
    return Image.fromarray(m, "L").resize((size, size), Image.LANCZOS)


def icon_background(size=432):
    """The tile: dark violet fading to black, like CSS radial-gradient(circle at 50% 36%, rgba(122,92,255,.42), transparent 64%) on #080b11."""
    y, x = np.mgrid[0:size, 0:size]
    d = np.hypot((x + 0.5) / size - 0.5, (y + 0.5) / size - 0.36) / np.hypot(0.5, 0.64)  # "circle": up to the farthest corner
    a = (np.clip(1 - d / 0.64, 0, 1) * 0.42)[..., None]
    return to_image(TILE_BASE * (1 - a) + VIOLET * a)


def glow(img, color, cx, cy, rx, ry, alpha, stop=0.7):
    """Like CSS radial-gradient(rx ry at cx cy, color, transparent stop); sizes as fractions of the width/height."""
    h, w, _ = img.shape
    y, x = np.mgrid[0:h, 0:w]
    d = np.sqrt(((x / w - cx) / rx) ** 2 + ((y / h - cy) / ry) ** 2)
    a = np.clip(1 - d / stop, 0, 1)[..., None] * alpha
    img[:] = img * (1 - a) + color * a


def save(im, *parts):
    path = os.path.join(RES, *parts)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    im.save(path, optimize=True)
    print("written", os.path.relpath(path, ROOT), im.size)


def main():
    logo = load_logo()
    mono_logo = load_logo(LOGO_MONO)

    # ---- adaptive icon: 108 dp, only the 66 dp in the middle are always visible; the logo (60 dp wide) fits in them ----
    background = icon_background(432)
    foreground = place(logo, 432, 0.56)
    mono = Image.new("RGBA", (432, 432), (255, 255, 255, 0))
    mono.putalpha(place(mono_logo, 432, 0.56).getchannel("A"))
    save(background, "drawable-nodpi", "ic_launcher_background.png")
    save(foreground, "drawable-nodpi", "ic_launcher_foreground.png")
    save(mono, "drawable-nodpi", "ic_launcher_monochrome.png")

    # ---- system splash (Android 12+): the logo on transparent, inside a 192 dp circle on a 288 dp canvas
    #      (432 px => 1.5 px per dp). The logo is 0.56 of the canvas = 161 dp wide: the app's splash uses the same size,
    #      so going from the system splash to the app's does not "jump". ----
    SPLASH_LOGO_FRACTION = 0.56
    save(place(logo, 432, SPLASH_LOGO_FRACTION), "drawable-nodpi", "ic_splash_icon.png")
    save(cropped(logo, int(432 * SPLASH_LOGO_FRACTION * 2.4)), "drawable-nodpi", "splash_logo.png")  # 2.4 px per px: sharp up to xxxhdpi

    # ---- icons for Android 7.x: the same picture, with a mask and a thin "glass" rim ----
    master = 768
    legacy = icon_background(432).convert("RGBA")
    legacy.alpha_composite(foreground)
    legacy = legacy.resize((master, master), Image.LANCZOS)
    zoomed = legacy.crop((int(master * 0.09), int(master * 0.09), int(master * 0.91), int(master * 0.91))).resize((master, master), Image.LANCZOS)  # logo at about 68%
    for density, px in (("mdpi", 48), ("hdpi", 72), ("xhdpi", 96), ("xxhdpi", 144), ("xxxhdpi", 192)):
        for name, mask_fn, base in (("ic_launcher.png", squircle_mask, zoomed), ("ic_launcher_round.png", circle_mask, zoomed)):
            out = base.resize((px, px), Image.LANCZOS)
            mask = mask_fn(px)
            edge = mask.filter(ImageFilter.MinFilter(3 if px < 96 else 5))
            ring = np.clip(np.asarray(mask, int) - np.asarray(edge, int), 0, 255)
            rim = Image.new("RGBA", (px, px), (255, 255, 255, 0))
            rim.putalpha(Image.fromarray((ring * 0.22).astype("uint8"), "L"))
            out.alpha_composite(rim)
            out.putalpha(mask)
            save(out, "mipmap-" + density, name)

    # ---- background of the app's splash: the dashboard's (10-base.css: violet at the top on #040507), 720x1600 ----
    w, h = 720, 1600
    img = np.ones((h, w, 3)) * BASE
    glow(img, VIOLET, 0.5, -0.04, 0.95, 0.46, 0.34)  # stronger than on the page: dark tones get lost on a phone's display
    glow(img, VIOLET, 0.5, 1.08, 0.80, 0.34, 0.14)
    glow(img, VIOLET, 0.5, 0.44, 0.60, 0.20, 0.14)  # a veil behind the logo
    save(to_image(img), "drawable-nodpi", "splash_bg.png")


if __name__ == "__main__":
    main()
