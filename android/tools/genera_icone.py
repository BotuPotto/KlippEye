#!/usr/bin/env python3
"""
Genera le immagini dell'app (icona, icona adattiva, splash) nello stile della dashboard One UI 9.

    python3 tools/genera_icone.py            (serve Pillow e numpy)

Il logo VzBot NON viene ridisegnato: è quello di assets/logo_vzbot.png, con i suoi colori. Cambia solo
quello che gli sta intorno: fondo scuro e bagliori sono gli stessi della pagina (src/css/10-base.css della
dashboard: base #040507, blu in alto a sinistra, viola a destra, verde acqua in basso a sinistra).

Scrive in app/src/main/res/:
    drawable-nodpi/ic_launcher_background.png   fondo dell'icona adattiva (432 px = 108 dp a xxxhdpi)
    drawable-nodpi/ic_launcher_foreground.png   logo, nella zona sicura dell'icona adattiva
    drawable-nodpi/ic_launcher_monochrome.png   sagoma del logo (icone tematiche di Android 13)
    drawable-nodpi/ic_splash_icon.png           logo per la splash di sistema (Android 12+)
    drawable-nodpi/splash_logo.png              logo della splash dell'app, della stessa misura di quello di sistema
    drawable-nodpi/splash_bg.png                fondo della splash dell'app
    mipmap-*/ic_launcher.png, ic_launcher_round.png   icone per Android 7.x (senza icone adattive)
"""
import os
import numpy as np
from PIL import Image, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
RES = os.path.join(ROOT, "app", "src", "main", "res")
LOGO = os.path.join(HERE, "assets", "logo_vzbot.png")

BASE = np.array([4, 5, 7], float)  # --oui-bg
BLUE = np.array([62, 145, 255], float)  # --oui-accent
VIOLET = np.array([122, 92, 255], float)
TEAL = np.array([30, 200, 170], float)
RED = np.array([230, 20, 40], float)  # il rosso del logo
rng = np.random.default_rng(7)


def canvas(w, h, top=(10, 12, 18), bottom=(4, 5, 7)):
    """Fondo a gradiente verticale, float RGB."""
    t = np.linspace(0, 1, h)[:, None, None]
    return (np.array(top, float) * (1 - t) + np.array(bottom, float) * t) * np.ones((1, w, 1))


def glow(img, color, cx, cy, rx, ry, alpha, stop=0.7):
    """Come radial-gradient(rx ry at cx cy, color, transparent stop) di CSS; misure in frazioni di larghezza/altezza."""
    h, w, _ = img.shape
    y, x = np.mgrid[0:h, 0:w]
    d = np.sqrt(((x / w - cx) / rx) ** 2 + ((y / h - cy) / ry) ** 2)
    a = np.clip(1 - d / stop, 0, 1)[..., None] * alpha
    img[:] = img * (1 - a) + color * a


def to_image(img, dither=True):
    if dither:
        img = img + rng.uniform(-0.5, 0.5, img.shape)
    return Image.fromarray(np.clip(np.rint(img), 0, 255).astype("uint8"), "RGB")


def load_logo():
    """Il logo con i suoi colori, ritagliato sul contenuto."""
    im = Image.open(LOGO).convert("RGBA")
    return im.crop(im.getchannel("A").getbbox())


def place(logo, size, width_fraction, shadow=True, dy=0.0):
    """Logo largo `width_fraction` della tela quadrata `size`, al centro, con un'ombra morbida sotto."""
    w = int(size * width_fraction)
    h = int(w * logo.height / logo.width)
    mark = logo.resize((w, h), Image.LANCZOS)
    layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    x, y = (size - w) // 2, int((size - h) / 2 + dy * size)
    if shadow:
        sh = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        sh.paste((0, 0, 0, 150), (x, y + int(size * 0.012)), mark.getchannel("A"))
        layer.alpha_composite(sh.filter(ImageFilter.GaussianBlur(size * 0.012)))
    layer.alpha_composite(mark, (x, y))
    return layer


def cropped(logo, content_px, pad_fraction=0.07):
    """Il logo largo `content_px`, con attorno un margine trasparente per l'ombra morbida."""
    w = content_px
    h = int(w * logo.height / logo.width)
    pad = int(w * pad_fraction)
    mark = logo.resize((w, h), Image.LANCZOS)
    layer = Image.new("RGBA", (w + 2 * pad, h + 2 * pad), (0, 0, 0, 0))
    sh = Image.new("RGBA", layer.size, (0, 0, 0, 0))
    sh.paste((0, 0, 0, 150), (pad, pad + int(w * 0.02)), mark.getchannel("A"))
    layer.alpha_composite(sh.filter(ImageFilter.GaussianBlur(w * 0.02)))
    layer.alpha_composite(mark, (pad, pad))
    return layer


def squircle_mask(size, n=5.0, scale=4):
    """Maschera "squircle" (superellisse), come le icone One UI; con anti-alias."""
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
    img = canvas(size, size, top=(13, 16, 24), bottom=(4, 5, 8))
    glow(img, BLUE, 0.12, -0.02, 0.85, 0.85, 0.40)
    glow(img, VIOLET, 1.08, 0.30, 0.65, 0.65, 0.26)
    glow(img, TEAL, -0.05, 1.05, 0.85, 0.80, 0.22)
    glow(img, RED, 0.5, 0.52, 0.40, 0.30, 0.16)  # alone rosso dietro il logo, tiene insieme logo e fondo
    glow(img, np.array([255, 255, 255], float), 0.5, 0.45, 0.55, 0.45, 0.05)
    return to_image(img)


def save(im, *parts):
    path = os.path.join(RES, *parts)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    im.save(path, optimize=True)
    print("scritto", os.path.relpath(path, ROOT), im.size)


def main():
    logo = load_logo()

    # ---- icona adattiva: 108 dp, solo i 66 dp centrali sono sempre visibili; il logo sta in 58 dp ----
    background = icon_background(432)
    foreground = place(logo, 432, 0.54)
    mono = Image.new("RGBA", (432, 432), (255, 255, 255, 0))
    mark = place(logo, 432, 0.54, shadow=False)
    mono.putalpha(mark.getchannel("A"))
    save(background, "drawable-nodpi", "ic_launcher_background.png")
    save(foreground, "drawable-nodpi", "ic_launcher_foreground.png")
    save(mono, "drawable-nodpi", "ic_launcher_monochrome.png")

    # ---- splash di sistema (Android 12+): logo su trasparente, deve stare in un cerchio di 192 dp su una tela di 288 dp
    #      (432 px => 1,5 px per dp). Il logo è largo 0,56 della tela = 161 dp: nell'app il logo ha la stessa misura,
    #      così il passaggio dalla splash di sistema a quella dell'app non "salta". ----
    SPLASH_LOGO_FRACTION = 0.56
    save(place(logo, 432, SPLASH_LOGO_FRACTION, shadow=False), "drawable-nodpi", "ic_splash_icon.png")
    save(cropped(logo, int(432 * SPLASH_LOGO_FRACTION * 2.4)), "drawable-nodpi", "splash_logo.png")  # 2,4 px per px: resta nitido fino a xxxhdpi

    # ---- icone per Android 7.x: stessa composizione, con maschera e un filo di bordo "vetro" ----
    master = 768
    legacy = icon_background(432).convert("RGBA")
    legacy.alpha_composite(foreground)
    legacy = legacy.resize((master, master), Image.LANCZOS)
    zoomed = legacy.crop((int(master * 0.09), int(master * 0.09), int(master * 0.91), int(master * 0.91))).resize((master, master), Image.LANCZOS)  # logo al ~61%
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

    # ---- fondo della splash dell'app: la stessa atmosfera della pagina (10-base.css), 720x1600 ----
    w, h = 720, 1600
    img = canvas(w, h, top=(4, 5, 7), bottom=(4, 5, 7))
    glow(img, BLUE, 0.12, -0.04, 0.75, 0.40, 0.34)  # più decisi che nella pagina: sul display di un telefono i toni bassi si perdono
    glow(img, VIOLET, 1.08, 0.28, 0.60, 0.34, 0.24)
    glow(img, TEAL, -0.08, 1.04, 0.75, 0.38, 0.18)
    glow(img, BLUE, 0.5, 0.44, 0.60, 0.20, 0.08)  # un velo dietro il logo
    glow(img, RED, 0.5, 0.43, 0.40, 0.12, 0.07)
    save(to_image(img), "drawable-nodpi", "splash_bg.png")


if __name__ == "__main__":
    main()
