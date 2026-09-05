import type { Faq } from "./data";

/** Renders the FAQ accordion. Every row starts closed so the section reads as
 * a scannable index of questions, and at most one answer is open at a time. */
export function renderFaq(container: HTMLElement, items: Faq[]): void {
  container.innerHTML = items.map(itemMarkup).join("");

  const rows = Array.from(container.querySelectorAll<HTMLElement>(".faq-item"));

  rows.forEach((row) => {
    const toggle = row.querySelector<HTMLButtonElement>(".faq-q");
    if (!toggle) return;

    toggle.addEventListener("click", () => {
      const opening = !row.classList.contains("open");
      rows.forEach((other) => setOpen(other, other === row && opening));
    });
  });
}

function setOpen(row: HTMLElement, open: boolean): void {
  row.classList.toggle("open", open);
  row.querySelector(".faq-q")?.setAttribute("aria-expanded", String(open));
}

function itemMarkup(faq: Faq, i: number): string {
  const id = `faq-a-${i}`;
  return `
<div class="faq-item">
  <button type="button" class="faq-q" aria-expanded="false" aria-controls="${id}">
    <span>${faq.q}</span>
    <span class="faq-mark">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 5v14M6 13l6 6 6-6"/></svg>
    </span>
  </button>
  <div class="faq-a" id="${id}" role="region"><p>${faq.a}</p></div>
</div>`;
}
