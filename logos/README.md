# Printer logos

In **Settings → Printer** the dashboard can show, in its top bar and as the browser tab icon, the logo of **KlippEye**
(default), **VzBot**, **Voron** or **RatRig**.

The KlippEye and VzBot logos are already inside the dashboard. For **Voron** and **RatRig** (and to replace the VzBot one)
put the **official** logo file here, in this folder, with one of these exact names (all lower case):

| Brand  | Accepted names                          |
|--------|-----------------------------------------|
| VzBot  | `vzbot.svg`  `vzbot.png`  `vzbot.webp`  |
| Voron  | `voron.svg`  `voron.png`  `voron.webp`  |
| RatRig | `ratrig.svg` `ratrig.png` `ratrig.webp` |

* **SVG** is the best format; for PNG or WebP use a transparent background and at least 256 pixels of width.
* At most 2 MB per file. When a brand has several formats, svg wins over png, png over webp.
* Take the files from each project's official pages (website or repository) and use them as they are, without redrawing them:
  the logos are their owners' trademarks.
* Once the file is in the repository: dashboard → Settings → Updates → Check → Update KlippEye. The logo appears at once in
  the Printer page (nothing is rebuilt). Until a file is there, the bar shows only the name for that brand.
