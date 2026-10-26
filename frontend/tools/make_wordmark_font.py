#!/usr/bin/env python3
"""
Makes src/css/02-wordmark-font.css: the font of the "KlippEye" wordmark in the top bar, embedded in the page.

    python3 tools/make_wordmark_font.py Outfit-Regular.ttf Outfit-Bold.ttf        (needs fontTools)

Outfit is released under the SIL Open Font License 1.1 (github.com/Outfitio/Outfit-Fonts). The two files are the
static Regular (400) and Bold (700); their outlines are compatible, so the weight 600 of the logo's wordmark is the
interpolation between them (2/3 of the way to Bold). The font is cut down to the letters, digits and signs a name can have and written
as WOFF (a few KB), so the dashboard stays one file and the name looks the same offline.
"""
import base64
import io
import os
import sys
from fontTools.subset import Options, Subsetter
from fontTools.ttLib import TTFont

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(HERE), "src", "css", "02-wordmark-font.css")
# the name of the brand and the names a printer can be given in the top bar (app/18-printer-brand.js): letters, digits and a few signs
TEXT = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 .-_'"
WEIGHT = 600
CSS = """/* ============================================================================
   The wordmark font: Outfit SemiBold (SIL Open Font License 1.1, (c) 2021 The Outfit Project Authors,
   github.com/Outfitio/Outfit-Fonts), reduced to letters, digits and a few signs (the wordmark "KlippEye" and the name of the printer) so the dashboard
   stays one file and the name looks the same offline. Used only by .app-header__name (20-layout.css).
   Made by tools/make_wordmark_font.py; do not edit the data by hand.
   ========================================================================== */
@font-face {
  font-family: "Outfit";
  font-style: normal;
  font-weight: %d;
  font-display: block;
  src: url("data:font/woff;base64,%s") format("woff");
}
"""


def build(regular_path, bold_path):
    regular, bold = TTFont(regular_path), TTFont(bold_path, recalcTimestamp=False)  # no clock in the file: same input, same output
    t = (WEIGHT - 400) / (700 - 400)
    glyph_of = regular.getBestCmap()
    options = Options()
    options.layout_features = []
    options.hinting = False
    options.notdef_outline = False
    options.name_IDs = [1, 2]
    options.glyph_names = False
    options.drop_tables += ["DSIG", "GDEF", "GPOS", "GSUB", "kern", "gasp", "STAT", "meta"]
    subsetter = Subsetter(options)
    subsetter.populate(text=TEXT)
    subsetter.subset(bold)  # the Bold font, reduced; its outlines are then moved towards the Regular ones
    bold_glyf, regular_glyf = bold["glyf"], regular["glyf"]
    bold_name_of = bold.getBestCmap()
    for char in TEXT:
        nb, nr = bold_name_of[ord(char)], glyph_of[ord(char)]
        glyph, other = bold_glyf[nb], regular_glyf[nr]
        points, other_points = glyph.getCoordinates(bold_glyf)[0], other.getCoordinates(regular_glyf)[0]
        assert len(points) == len(other_points), "the outlines of %r are not compatible" % char
        for i, (x1, y1) in enumerate(other_points):
            x2, y2 = points[i]
            points[i] = (round(x1 + (x2 - x1) * t), round(y1 + (y2 - y1) * t))
        glyph.coordinates = points
        glyph.recalcBounds(bold_glyf)
        advance = round(regular["hmtx"][nr][0] + (bold["hmtx"][nb][0] - regular["hmtx"][nr][0]) * t)
        bold["hmtx"][nb] = (advance, glyph.xMin)
    bold["OS/2"].usWeightClass = WEIGHT
    for record in bold["name"].names:
        if record.nameID == 2:
            record.string = "SemiBold"
    bold.flavor = "woff"
    buffer = io.BytesIO()
    bold.save(buffer)
    return buffer.getvalue()


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    data = build(sys.argv[1], sys.argv[2])
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write(CSS % (WEIGHT, base64.b64encode(data).decode()))
    print("scritto", os.path.relpath(OUT, os.path.dirname(HERE)), len(data), "byte")


if __name__ == "__main__":
    main()
