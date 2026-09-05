/** The hero dashboard's voice dial - a semicircular level meter that doubles
 * as the pause/resume control. One click (or Space/Enter) toggles listening,
 * and the whole dashboard follows: bars settle, arc drains, status pill
 * flips, mic glyph becomes a play glyph.
 *
 * Colour is done entirely in SVG/CSS - the ticks stroke a userSpaceOnUse
 * gradient built from the theme's own custom properties, so light/dark
 * switching needs no per-frame JS. The animation loop only moves geometry. */

const SVG_NS = "http://www.w3.org/2000/svg";

const PREFERS_REDUCED_MOTION =
  typeof window !== "undefined" &&
  window.matchMedia?.("(prefers-reduced-motion: reduce)").matches === true;

// Geometry, in the 300x168 viewBox the markup declares. The dial's centre sits
// on the flat edge at y=150, leaving 18 units below it for round caps.
const CX = 150;
const CY = 150;
const ARC_R = 132;
const TICK_R = 100;
const TICK_MIN = 4;
const TICK_MAX = 24;
const TICKS = 46;
const ARC_LEN = Math.PI * ARC_R;

// Paused drains the arc completely; the knob fades with it in CSS, so the
// track is left empty rather than holding a stray stub.
const PAUSED_LEVEL = 0;
const EASE = 0.07;
const SETTLED = 0.005;

function polar(angleDeg: number, r: number): [number, number] {
  const a = (angleDeg * Math.PI) / 180;
  return [CX + r * Math.cos(a), CY - r * Math.sin(a)];
}

/** Tick index to its angle, sweeping left (180deg) to right (0deg). */
function tickAngle(i: number): number {
  return 180 - (i * 180) / (TICKS - 1);
}

const SVG_MARKUP = `
<defs>
  <linearGradient id="dialGrad" gradientUnits="userSpaceOnUse" x1="18" y1="0" x2="282" y2="0">
    <stop offset="0" stop-color="var(--accent-strong)"/>
    <stop offset="0.52" stop-color="var(--accent)"/>
    <stop offset="1" stop-color="var(--amber)"/>
  </linearGradient>
</defs>
<path class="dial-hair" d="M 58 150 A 92 92 0 0 1 242 150"/>
<path class="dial-track" d="M 18 150 A 132 132 0 0 1 282 150"/>
<path class="dial-arc" d="M 18 150 A 132 132 0 0 1 282 150"/>
<g class="dial-ticks"></g>
<circle class="dial-knob" cx="18" cy="150" r="6"/>
`;

export interface VoiceDialEls {
  /** The dashboard shell - carries `.is-paused` for every dependent style. */
  root: HTMLElement;
  button: HTMLButtonElement;
  svg: SVGSVGElement;
  label: HTMLElement;
  hint: HTMLElement;
  /** Text node of the titlebar status pill, beside its pulsing dot. */
  status: HTMLElement;
}

function must<T extends Element>(parent: ParentNode, selector: string): T {
  const el = parent.querySelector<T>(selector);
  if (!el) throw new Error(`Expected ${selector} in the voice dial`);
  return el;
}

export class VoiceDial {
  private readonly ticks: SVGLineElement[] = [];
  private readonly arc: SVGPathElement;
  private readonly knob: SVGCircleElement;
  private rafId: number | null = null;
  private paused = false;
  private energy = 1;
  private energyTarget = 1;
  private level = PAUSED_LEVEL;
  private listener: ((paused: boolean) => void) | null = null;

  constructor(private readonly els: VoiceDialEls) {
    els.svg.innerHTML = SVG_MARKUP;
    this.arc = must<SVGPathElement>(els.svg, ".dial-arc");
    this.knob = must<SVGCircleElement>(els.svg, ".dial-knob");
    this.arc.setAttribute("stroke-dasharray", ARC_LEN.toFixed(2));

    const group = must<SVGGElement>(els.svg, ".dial-ticks");
    for (let i = 0; i < TICKS; i++) {
      const [x1, y1] = polar(tickAngle(i), TICK_R);
      const tick = document.createElementNS(SVG_NS, "line");
      tick.setAttribute("class", "dial-tick");
      tick.setAttribute("x1", x1.toFixed(2));
      tick.setAttribute("y1", y1.toFixed(2));
      tick.setAttribute("x2", x1.toFixed(2));
      tick.setAttribute("y2", y1.toFixed(2));
      tick.setAttribute("stroke", "url(#dialGrad)");
      group.appendChild(tick);
      this.ticks.push(tick);
    }

    els.button.addEventListener("click", () => this.toggle());
  }

  /** Called with the new paused state after every toggle. */
  onChange(fn: (paused: boolean) => void): void {
    this.listener = fn;
  }

  get isPaused(): boolean {
    return this.paused;
  }

  toggle(): void {
    this.setPaused(!this.paused);
  }

  setPaused(paused: boolean): void {
    if (paused === this.paused) return;
    this.paused = paused;
    this.energyTarget = paused ? 0 : 1;

    this.els.root.classList.toggle("is-paused", paused);
    this.els.button.setAttribute("aria-pressed", String(paused));
    this.els.button.setAttribute(
      "aria-label",
      paused ? "Resume listening" : "Pause listening",
    );
    this.els.label.textContent = paused ? "Paused" : "Listening";
    this.els.hint.textContent = paused ? "Click to resume" : "Click to pause";
    this.els.status.textContent = paused ? "Paused" : "Listening";
    this.listener?.(paused);

    if (PREFERS_REDUCED_MOTION) {
      this.snap();
      return;
    }
    if (this.rafId === null) this.rafId = requestAnimationFrame(this.loop);
  }

  start(): void {
    if (PREFERS_REDUCED_MOTION) {
      this.snap();
      return;
    }
    this.rafId = requestAnimationFrame(this.loop);
  }

  stop(): void {
    if (this.rafId !== null) cancelAnimationFrame(this.rafId);
    this.rafId = null;
  }

  /** Jump straight to the resting shape - reduced-motion path, no animation. */
  private snap(): void {
    this.energy = this.energyTarget;
    this.level = this.paused ? PAUSED_LEVEL : 0.62;
    this.paint(0, false);
  }

  private readonly loop = (t: number): void => {
    this.paint(t, true);
    // Once paused and fully settled there is nothing left to move, so give the
    // frame budget back instead of spinning on a static picture.
    const done =
      this.paused &&
      this.energy < SETTLED &&
      Math.abs(this.level - PAUSED_LEVEL) < SETTLED;
    this.rafId = done ? null : requestAnimationFrame(this.loop);
  };

  private paint(t: number, ease: boolean): void {
    if (ease) {
      this.energy += (this.energyTarget - this.energy) * EASE;
      const live = 0.34 + 0.42 * (0.5 + 0.5 * Math.sin(t * 0.0007));
      const target = this.paused ? PAUSED_LEVEL : live;
      this.level += (target - this.level) * EASE;
    }

    for (const [i, tick] of this.ticks.entries()) {
      const phase = i * 0.42;
      const amp = Math.abs(
        Math.sin(t * 0.0016 + phase * 0.9) * 0.5 +
          Math.sin(t * 0.0009 + phase * 2.1) * 0.3 +
          Math.sin(phase * 1.7) * 0.2,
      );
      // Bell weighting: loudest through the middle of the arc, tapering at the
      // ends, so it reads as a voice meter rather than a noise field.
      const bell = 0.4 + 0.6 * Math.sin((Math.PI * i) / (TICKS - 1));
      const h = TICK_MIN + amp * bell * (TICK_MAX - TICK_MIN) * this.energy;
      const [x2, y2] = polar(tickAngle(i), TICK_R + h);
      tick.setAttribute("x2", x2.toFixed(2));
      tick.setAttribute("y2", y2.toFixed(2));
    }

    this.arc.setAttribute(
      "stroke-dashoffset",
      (ARC_LEN * (1 - this.level)).toFixed(2),
    );
    const [kx, ky] = polar(180 - 180 * this.level, ARC_R);
    this.knob.setAttribute("cx", kx.toFixed(2));
    this.knob.setAttribute("cy", ky.toFixed(2));
  }
}
