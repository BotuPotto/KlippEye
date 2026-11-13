# Printer logos

The dashboard can show the logo of your printer's brand in the top bar and as the icon of the browser tab: **Settings →
Appearance → Logo**. The choices are KlippEye (the default), VzBot, Voron and RatRig.

The KlippEye and VzBot logos are built into the dashboard. The others are read from this folder:

| Brand | File in this folder |
|---|---|
| Voron | `voron.svg` (included) |
| RatRig | `ratrig.png` (included) |
| VzBot | `vzbot.svg`, `vzbot.png` or `vzbot.webp`, only to replace the built-in one |

The file name must be the brand in lower case, with the extension `svg`, `png` or `webp`. If a brand has more than one
file, SVG wins over PNG and PNG over WebP. Each file can be at most 2 MB; a PNG or WebP should have a transparent background
and be at least 256 pixels wide.

Use the official files from each project's website or repository, as they are: the logos are their owners' trademarks.

A new file reaches the printers with the next update (*Settings → Updates → Update KlippEye*); the dashboard reads it at
once, without being rebuilt. Without a file, the bar shows only the brand's name.
