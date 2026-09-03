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

function initMoreMenu(): void {
  const wrap = document.getElementById("navMore");
  const toggle = document.getElementById("moreToggle");
  if (!wrap || !toggle) return;

  const setOpen = (open: boolean) => {
    wrap.classList.toggle("open", open);
    toggle.setAttribute("aria-expanded", String(open));
  };

  toggle.addEventListener("click", (event) => {
    event.stopPropagation();
    setOpen(!wrap.classList.contains("open"));
  });

  // Opens on hover too, the way a desktop nav is expected to behave.
  wrap.addEventListener("mouseenter", () => setOpen(true));
  wrap.addEventListener("mouseleave", () => setOpen(false));

  document.addEventListener("click", (event) => {
    if (!wrap.contains(event.target as Node)) setOpen(false);
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") setOpen(false);
  });
}
