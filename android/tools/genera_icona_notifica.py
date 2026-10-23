#!/usr/bin/env python3
"""Icona piccola delle notifiche (la sagoma bianca che compare nella barra di stato).

Android vuole un'immagine bianca su fondo trasparente, 24 dp: la sagoma e' quella del logo KlippEye (tools/assets/logo_klippeye_mono.png,
la stessa del logo a colori, con un anello vuoto attorno alla pupilla). Scrive res/drawable-<densita>/ic_stat_klippeye.png.   Uso:  python3 tools/genera_icona_notifica.py
(serve Pillow)
"""
import os
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "..", "app", "src", "main", "res")
SIZES = {"mdpi": 24, "hdpi": 36, "xhdpi": 48, "xxhdpi": 72, "xxxhdpi": 96}
MARGIN = 0.06  # aria attorno alla sagoma, in frazione del lato


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
