import type { ShowcaseSlide } from "./data";
import { ICONS } from "./data";
import { icon, mark } from "./graphic";

const TIER_LABEL: Record<ShowcaseSlide["tier"], string> = {
  local: "local tier",
  lan: "lan tier",
  net: "net tier",
};

function slideMarkup(slide: ShowcaseSlide, index: number, total: number): string {
  const tone = slide.amber ? "amber" : "accent";
  const num = String(index + 1).padStart(2, "0");
  const count = String(total).padStart(2, "0");

  return `
<div class="showcase-copy">
  ${mark(slide.icon, tone, "lg")}
  <div class="index mono">${num} / ${count}</div>
  <h3>${slide.name}</h3>
  <p>${slide.desc}</p>
  <div class="chips">
    ${slide.chips.map((c) => `<span class="chip-soft">${c}</span>`).join("")}
  </div>
</div>

<div class="mockup-window showcase-window">
  <div class="mockup-titlebar">
    <span class="mockup-dot"></span><span class="mockup-dot"></span><span class="mockup-dot"></span>
    <span class="mockup-title">${slide.app} · Munshiji</span>
    <span class="mockup-status"><span class="mockup-status-dot"></span>Listening</span>
  </div>
  <div class="mockup-body">
    <div class="mockup-sidebar">
      <span class="mockup-navdot${index % 4 === 0 ? " on" : ""}"></span>
      <span class="mockup-navdot${index % 4 === 1 ? " on" : ""}"></span>
      <span class="mockup-navdot${index % 4 === 2 ? " on" : ""}"></span>
      <span class="mockup-navdot${index % 4 === 3 ? " on" : ""}"></span>
    </div>
    <div class="mockup-main">
      <div class="showcase-said">
        <span class="said-mic">${icon(ICONS.mic, 2)}</span>
        <span class="said-text">${slide.utterance}</span>
      </div>
      <div class="showcase-stage">
        <span class="mono">${slide.stage}</span>
        ${icon("M5 12h14M13 6l6 6-6 6", 2)}
      </div>
      <div class="showcase-call mono"><span class="k">→</span> ${slide.call}</div>
      <div class="showcase-result">
        <span class="ok">${icon("M5 12l4 4L19 6", 2.4)}</span>
        <span>${slide.risk === "confirm" ? "Spoke its intent, waited for a yes" : "Done, and reversible"}</span>
        <span class="undo">undo</span>
      </div>
      <div class="mockup-row showcase-tags">
        <span class="tag${slide.tier === "net" ? " net" : ""}">${TIER_LABEL[slide.tier]}</span>
        ${slide.risk === "confirm" ? '<span class="tag confirm">asks first</span>' : ""}
        <span class="tag">undoable</span>
        <span class="tag">on device</span>
      </div>
    </div>
  </div>
</div>`;
}

/** Full-width showcase: exactly one slide on screen, wrapping forever in both
 * directions, with autoplay that yields to any manual interaction. */
export function renderShowcase(root: HTMLElement, slides: ShowcaseSlide[]): void {
  const viewport = root.querySelector<HTMLElement>(".showcase-viewport");
  const dotsEl = root.querySelector<HTMLElement>(".showcase-dots");
  const prevBtn = root.querySelector<HTMLButtonElement>(".carousel-arrow.prev");
  const nextBtn = root.querySelector<HTMLButtonElement>(".carousel-arrow.next");
  if (!viewport || slides.length === 0) return;

  viewport.innerHTML = "";
  if (dotsEl) dotsEl.innerHTML = "";

  const slideEls = slides.map((slide, i) => {
    const el = document.createElement("div");
    el.className = "showcase-slide";
    el.innerHTML = slideMarkup(slide, i, slides.length);
    el.setAttribute("aria-hidden", "true");
    viewport.appendChild(el);

    if (dotsEl) {
      const dot = document.createElement("span");
      dot.setAttribute("role", "button");
      dot.setAttribute("aria-label", `Show ${slide.name}`);
      dotsEl.appendChild(dot);
    }
    return el;
  });

  const dots = dotsEl ? (Array.from(dotsEl.children) as HTMLElement[]) : [];
  const reduceMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches === true;
  let index = 0;
  let timer: number | null = null;

  function paint(): void {
    slideEls.forEach((el, i) => {
      const on = i === index;
      el.classList.toggle("on", on);
      el.setAttribute("aria-hidden", on ? "false" : "true");
    });
    dots.forEach((d, i) => d.classList.toggle("on", i === index));
  }

  // Wraps in both directions, so the strip never runs out.
  function go(next: number): void {
    const n = slides.length;
    index = ((next % n) + n) % n;
    paint();
  }

  function play(): void {
    if (reduceMotion || timer !== null) return;
    timer = window.setInterval(() => go(index + 1), 5200);
  }

  function pause(): void {
    if (timer !== null) window.clearInterval(timer);
    timer = null;
  }

  function nudge(next: number): void {
    pause();
    go(next);
    play();
  }

  prevBtn?.addEventListener("click", () => nudge(index - 1));
  nextBtn?.addEventListener("click", () => nudge(index + 1));
  dots.forEach((d, i) => d.addEventListener("click", () => nudge(i)));
  root.addEventListener("mouseenter", pause);
  root.addEventListener("mouseleave", play);
  root.addEventListener("focusin", pause);
  root.addEventListener("focusout", play);

  paint();
  play();
}
