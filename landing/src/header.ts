/** Floating pill header: dismissible announcement bar, and a nav pill that
 * tightens into a compact floating bar once the page scrolls. Shared by
 * every page (called from both main.ts and common.ts). */
export function initFloatingHeader(): void {
  const header = document.getElementById("siteHeader");
  const topbar = document.getElementById("topbar");
  const closeBtn = document.getElementById("topbarClose");

  closeBtn?.addEventListener("click", () => {
    topbar?.classList.add("dismissed");
  });

  if (!header) return;

  const applyScrollState = () => {
    header.classList.toggle("scrolled", window.scrollY > 24);
  };
  window.addEventListener("scroll", applyScrollState, { passive: true });
  applyScrollState();
}
