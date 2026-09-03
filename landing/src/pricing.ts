/** Monthly / annual billing toggle. Prices live in the markup as data
 * attributes so the page still reads correctly with JS disabled. */
export function initBillingToggle(): void {
  const toggle = document.getElementById("billingToggle");
  if (!toggle) return;

  const buttons = Array.from(toggle.querySelectorAll<HTMLButtonElement>("button"));
  const amounts = Array.from(document.querySelectorAll<HTMLElement>("[data-monthly]"));
  const notes = Array.from(document.querySelectorAll<HTMLElement>("[data-note-monthly]"));

  function apply(cycle: "monthly" | "annual"): void {
    buttons.forEach((b) => b.classList.toggle("on", b.dataset.cycle === cycle));
    for (const el of amounts) {
      const next = cycle === "annual" ? el.dataset.annual : el.dataset.monthly;
      if (next) el.textContent = next;
    }
    for (const el of notes) {
      const next = cycle === "annual" ? el.dataset.noteAnnual : el.dataset.noteMonthly;
      if (next) el.textContent = next;
    }
  }

  buttons.forEach((b) =>
    b.addEventListener("click", () => {
      const cycle = b.dataset.cycle === "annual" ? "annual" : "monthly";
      apply(cycle);
    }),
  );

  apply("annual");
}
