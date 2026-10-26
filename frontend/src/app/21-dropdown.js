/* ============================================================================
   21 · DROPDOWN MENU
   A small glass menu that opens under its trigger button, or above it when
   the screen has no room below (the floating tab bar is never covered). A tap
   outside, Escape or scrolling the page closes it.
     const menu = useDropdown();
     h("button", { ref: menu.anchorRef, onClick: menu.toggle }, "Open")
     h(DropdownMenu, { menu }, h(MenuItem, { ... }))
   ========================================================================== */

const MENU_GAP_PX = 8; // between trigger and menu
const MENU_EDGE_PX = 12; // minimum distance from the left and right screen edges
const MENU_TOP_CLEARANCE_PX = 76; // the fixed top bar
const MENU_BOTTOM_CLEARANCE_PX = 100; // the floating tab bar and its margin
const MENU_MIN_WIDTH_PX = 280;
const MENU_SCROLL_GUARD_MS = 250; // a browser that scrolls the trigger into view reports it just after the tap opened the menu

function useDropdown() {
  const [open, setOpen] = useState(false);
  const anchorRef = useRef(null);
  return { open, anchorRef, toggle: () => setOpen((value) => !value), close: () => setOpen(false) };
}

/** Where the menu goes: left or right aligned with the trigger, below it or above it, whichever fits. */
function placeMenu(anchor, menu) {
  const trigger = anchor.getBoundingClientRect();
  const width = Math.min(Math.max(trigger.width, MENU_MIN_WIDTH_PX), window.innerWidth - 2 * MENU_EDGE_PX);
  const alignRight = trigger.left + trigger.width / 2 > window.innerWidth / 2;
  const left = clamp(alignRight ? trigger.right - width : trigger.left, MENU_EDGE_PX, window.innerWidth - width - MENU_EDGE_PX);

  const roomBelow = window.innerHeight - trigger.bottom - MENU_GAP_PX - MENU_BOTTOM_CLEARANCE_PX;
  const roomAbove = trigger.top - MENU_GAP_PX - MENU_TOP_CLEARANCE_PX;
  const below = menu.scrollHeight <= roomBelow || roomBelow >= roomAbove;
  const room = Math.max(120, below ? roomBelow : roomAbove);
  const height = Math.min(menu.scrollHeight, room);
  return {
    left,
    width,
    top: below ? trigger.bottom + MENU_GAP_PX : trigger.top - MENU_GAP_PX - height,
    maxHeight: room,
    transformOrigin: (alignRight ? "right " : "left ") + (below ? "top" : "bottom"),
  };
}

function DropdownMenu({ menu, children }) {
  const { open, anchorRef, close } = menu;
  const menuRef = useRef(null);
  const [position, setPosition] = useState(null);

  useLayoutEffect(() => {
    if (!open || !anchorRef.current || !menuRef.current) {
      setPosition(null);
      return;
    }
    setPosition(placeMenu(anchorRef.current, menuRef.current));
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const openedAt = Date.now();
    const closeOnEscape = (event) => event.key === "Escape" && close();
    const closeOnPageScroll = (event) => Date.now() - openedAt > MENU_SCROLL_GUARD_MS && !(menuRef.current && menuRef.current.contains(event.target)) && close();
    document.addEventListener("keydown", closeOnEscape);
    window.addEventListener("scroll", closeOnPageScroll, true);
    window.addEventListener("resize", close);
    return () => {
      document.removeEventListener("keydown", closeOnEscape);
      window.removeEventListener("scroll", closeOnPageScroll, true);
      window.removeEventListener("resize", close);
    };
  }, [open]);

  return h(
    Presence,
    null,
    open &&
      h(
        React.Fragment,
        null,
        h("div", { className: "oui-menu-scrim", onClick: close, onContextMenu: (event) => event.preventDefault() }),
        h("div", { ref: menuRef, className: "oui-menu", role: "menu", style: position || { visibility: "hidden" } }, children),
      ),
  );
}

/** One choice of a menu: round icon, title, a line of explanation. `disabled` greys it out (say why in `subtitle`). */
function MenuItem({ icon, title, subtitle, disabled, onClick }) {
  return h(
    "button",
    { className: "oui-menu__item", role: "menuitem", disabled, onClick },
    h("span", { className: "oui-menu__icon" }, icon),
    h("span", { className: "oui-menu__text" }, h("span", { className: "oui-menu__title" }, title), subtitle && h("span", { className: "oui-menu__sub" }, subtitle)),
  );
}

/** Small caption that groups the items under it. */
const MenuLabel = ({ children }) => h("div", { className: "oui-menu__label" }, children);
