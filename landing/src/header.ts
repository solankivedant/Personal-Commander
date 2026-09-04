/** Floating pill header: dismissible announcement bar, a nav pill that
 * tightens once the page scrolls, and the "More" dropdown. Shared by every
 * page (called from both main.ts and common.ts). */
export function initFloatingHeader(): void {
  const header = document.getElementById("siteHeader");
  const topbar = document.getElementById("topbar");
  const closeBtn = document.getElementById("topbarClose");

  closeBtn?.addEventListener("click", () => {
    topbar?.classList.add("dismissed");
  });

  initMoreMenu();

  if (!header) return;

  const applyScrollState = () => {
    header.classList.toggle("scrolled", window.scrollY > 24);
  };
  window.addEventListener("scroll", applyScrollState, { passive: true });
  applyScrollState();
}

/** Grace period before a hover-opened menu closes, so travelling from the
 * button to the menu - or briefly clipping its edge - doesn't dismiss it. */
const CLOSE_DELAY_MS = 260;

function initMoreMenu(): void {
  const wrap = document.getElementById("navMore");
  const toggle = document.getElementById("moreToggle");
  if (!wrap || !toggle) return;

  let closeTimer: number | null = null;
  // A click pins the menu open, so it survives the pointer leaving entirely.
  let pinned = false;

  const cancelClose = () => {
    if (closeTimer !== null) {
      window.clearTimeout(closeTimer);
      closeTimer = null;
    }
  };

  const setOpen = (open: boolean) => {
    cancelClose();
    wrap.classList.toggle("open", open);
    toggle.setAttribute("aria-expanded", String(open));
  };

  const close = () => {
    pinned = false;
    setOpen(false);
  };

  const closeSoon = () => {
    if (pinned) return;
    cancelClose();
    closeTimer = window.setTimeout(() => setOpen(false), CLOSE_DELAY_MS);
  };

  toggle.addEventListener("click", (event) => {
    event.stopPropagation();
    const isOpen = wrap.classList.contains("open");
    if (!isOpen) {
      pinned = true;
      setOpen(true);
    } else if (pinned) {
      close();
    } else {
      // Already open from hover - a click pins it rather than closing it.
      pinned = true;
      cancelClose();
    }
  });

  // Hover opens for a mouse only (touch has no meaningful hover, and would
  // otherwise open the menu on the same tap that is meant to toggle it).
  wrap.addEventListener("pointerenter", (event) => {
    if ((event as PointerEvent).pointerType === "mouse") setOpen(true);
  });
  wrap.addEventListener("pointerleave", closeSoon);
  wrap.addEventListener("pointermove", cancelClose);
  wrap.addEventListener("focusin", () => setOpen(true));
  wrap.addEventListener("focusout", (event) => {
    const next = event.relatedTarget as Node | null;
    if (!next || !wrap.contains(next)) closeSoon();
  });

  document.addEventListener("click", (event) => {
    if (!wrap.contains(event.target as Node)) close();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") close();
  });
}
