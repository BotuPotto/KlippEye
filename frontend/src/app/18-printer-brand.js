/* ============================================================================
   18 · PRINTER BRAND
   Which name and which logo the top bar shows, and the title and icon of the browser tab: KlippEye (the default), or the
   brand of the printer itself (VzBot, Voron, RatRig), optionally with a name of the owner's choice ("VzBot.287").
   The choice is part of the settings (settings.printer = { brand, name }, app/16-settings.js), so it is the same on every device.

   Where a logo comes from, in this order:
     · a file in the logos/ folder of the repository (logos/voron.svg, .png or .webp), which the backend lists in /api/logos:
       this is how the official logo of a brand is put in, without rebuilding the dashboard (see logos/README.md);
     · the logo embedded in the page (src/logos/, embedded by build.py): KlippEye's own and VzBot's;
     · none: the bar then shows the name alone, and the tab keeps KlippEye's icon. A logo is never drawn here.
   ========================================================================== */

const PRINTER_BRANDS = [
  { id: "klippeye", label: "KlippEye", detail: tx("The program's logo (default)") },
  { id: "vzbot", label: "VzBot", detail: tx("{brand} logo and name", { brand: "VzBot" }) },
  { id: "voron", label: "Voron", detail: tx("{brand} logo and name", { brand: "Voron" }) },
  { id: "ratrig", label: "RatRig", detail: tx("{brand} logo and name", { brand: "RatRig" }) },
];
const printerBrand = (id) => PRINTER_BRANDS.find((brand) => brand.id === id) || PRINTER_BRANDS[0];

/** The name shown in the bar and in the tab: the one typed in the settings, else the brand's. */
const printerName = (printer) => printer.name || printerBrand(printer.brand).label;
/** True when the bar shows the KlippEye wordmark ("Klipp" and "Eye" in two colours). */
const isKlippEyeWordmark = (printer) => printer.brand === "klippeye" && !printer.name;

/* ---------------------------------------------------------------------------
   Logos
   ------------------------------------------------------------------------- */
const LOGO_FILE_PATTERN = /^[a-z0-9_-]{1,32}\.(svg|png|webp)$/;
let logoFiles = null; // { brand id: address } of the files the backend has; null until asked
let logoFilesAsking = null;
const logoListeners = new Set();

/** The logos folder of the repository as the backend lists it: { voron: "/logos/voron.svg", ... } ({} when there are none or the backend is older). */
async function readLogoFiles() {
  try {
    const response = await fetchFresh("/api/logos", { timeout: BRAIN_READ_TIMEOUT_MS });
    if (!response.ok) return {};
    const data = await response.json();
    const found = {};
    (isPlainObject(data) && Array.isArray(data.files) ? data.files : []).forEach((file) => {
      const name = typeof file === "string" ? file : "";
      const id = name.replace(/\.[a-z0-9]+$/, "");
      if (LOGO_FILE_PATTERN.test(name) && PRINTER_BRANDS.some((brand) => brand.id === id) && !found[id]) found[id] = "/logos/" + name + "?r=" + encodeURIComponent(dashboardRelease());
    });
    return found;
  } catch (error) {
    return {};
  }
}

/** Asks the backend once (and again when `again`); everyone using logos is told when the answer is there. */
function loadLogoFiles(again = false) {
  if (logoFilesAsking) return logoFilesAsking;
  if (logoFiles && !again) return Promise.resolve(logoFiles);
  logoFilesAsking = readLogoFiles().then((found) => {
    logoFilesAsking = null;
    if (JSON.stringify(found) !== JSON.stringify(logoFiles)) {
      logoFiles = found;
      logoListeners.forEach((listener) => listener());
    } else logoFiles = found;
    return found;
  });
  return logoFilesAsking;
}

/** The logo to show for a brand: a file of the repository, else the one embedded in the page, else "". */
function logoSource(id) {
  if (id === "klippeye") return LOGO_SVG;
  return (logoFiles && logoFiles[id]) || EMBEDDED_LOGOS[id] || "";
}

/** { brand id: logo address or "" } for every brand; re-renders when the list of files arrives. */
function usePrinterLogos() {
  const [, setTick] = useState(0);
  useEffect(() => {
    const listener = () => setTick((tick) => tick + 1);
    logoListeners.add(listener);
    loadLogoFiles();
    return () => logoListeners.delete(listener);
  }, []);
  return Object.fromEntries(PRINTER_BRANDS.map((brand) => [brand.id, logoSource(brand.id)]));
}

/** The logo of a brand as an image; nothing when there is none. */
function PrinterLogo({ id, className }) {
  const src = usePrinterLogos()[id];
  return src ? h("img", { src, alt: "", className: cx(className, id !== "klippeye" && "is-brand") }) : null;
}

/* ---------------------------------------------------------------------------
   Tab title and icon
   ------------------------------------------------------------------------- */
const TAB_ICON_SIZES = { "32x32": 32, "64x64": 64, "180x180": 180 };
let originalTabIcons = null; // the <link> hrefs of the page as built (KlippEye's icon), to go back to
const tabIconCache = new Map();

const tabIconLinks = () => Array.from(document.querySelectorAll('link[rel="icon"], link[rel="apple-touch-icon"]'));

/** The icon of the page drawn like KlippEye's (the logo on a dark violet tile, tools/make_favicon.py), for another brand's logo. */
function drawTabIcon(src, size, rounded) {
  return new Promise((resolve) => {
    const image = new Image();
    image.onload = () => {
      try {
        const canvas = document.createElement("canvas");
        canvas.width = canvas.height = size;
        const ctx = canvas.getContext("2d");
        if (rounded) {
          ctx.beginPath();
          ctx.moveTo(size * 0.225, 0);
          ctx.arcTo(size, 0, size, size, size * 0.225);
          ctx.arcTo(size, size, 0, size, size * 0.225);
          ctx.arcTo(0, size, 0, 0, size * 0.225);
          ctx.arcTo(0, 0, size, 0, size * 0.225);
          ctx.closePath();
          ctx.clip();
        }
        ctx.fillStyle = "#080b11";
        ctx.fillRect(0, 0, size, size);
        const glow = ctx.createRadialGradient(size * 0.5, size * 0.36, 0, size * 0.5, size * 0.36, Math.hypot(0.5, 0.64) * size * 0.64);
        glow.addColorStop(0, "rgba(122,92,255,0.42)");
        glow.addColorStop(1, "rgba(122,92,255,0)");
        ctx.fillStyle = glow;
        ctx.fillRect(0, 0, size, size);
        const naturalWidth = image.naturalWidth || 100;
        const naturalHeight = image.naturalHeight || 100;
        const scale = Math.min((size * 0.76) / naturalWidth, (size * 0.76) / naturalHeight);
        const width = naturalWidth * scale;
        const height = naturalHeight * scale;
        ctx.drawImage(image, (size - width) / 2, (size - height) / 2, width, height);
        resolve(canvas.toDataURL("image/png"));
      } catch (error) {
        resolve("");
      }
    };
    image.onerror = () => resolve("");
    image.src = src;
  });
}

let tabIconToken = 0; // a newer choice cancels the drawing of an older one

async function applyTabIcon(brand, src) {
  const token = ++tabIconToken;
  const links = tabIconLinks();
  if (!originalTabIcons) originalTabIcons = links.map((link) => link.getAttribute("href"));
  const restore = () => links.forEach((link, index) => link.setAttribute("href", originalTabIcons[index] || link.getAttribute("href")));
  if (brand === "klippeye" || !src) return restore();
  const drawn = await Promise.all(
    links.map(async (link) => {
      const size = TAB_ICON_SIZES[link.getAttribute("sizes")] || 64;
      const key = brand + "|" + src + "|" + size;
      if (!tabIconCache.has(key)) tabIconCache.set(key, await drawTabIcon(src, size, link.getAttribute("rel") === "icon"));
      return tabIconCache.get(key);
    }),
  );
  if (token !== tabIconToken) return;
  if (drawn.some((href) => !href)) return restore(); // a logo that cannot be drawn: the page's own icon stays
  links.forEach((link, index) => link.setAttribute("href", drawn[index]));
}

/** Keeps the title and the icon of the browser tab in step with the chosen printer; called once by the application. */
function usePrinterIdentity() {
  const { settings } = useSettings();
  const logos = usePrinterLogos();
  const { brand } = settings.printer;
  const title = printerName(settings.printer);
  const src = logos[brand];
  useEffect(() => {
    document.title = title;
  }, [title]);
  useEffect(() => {
    applyTabIcon(brand, src).catch(noop);
  }, [brand, src]);
}
