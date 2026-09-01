const PREFERS_REDUCED_MOTION =
  typeof window !== "undefined" &&
  window.matchMedia?.("(prefers-reduced-motion: reduce)").matches === true;

function cssVar(name: string, fallback: string): string {
  const v = getComputedStyle(document.documentElement).getPropertyValue(name);
  return v.trim() || fallback;
}

function hexToRgb(hex: string): [number, number, number] {
  let h = hex.replace("#", "");
  if (h.length === 3) h = h.split("").map((c) => c + c).join("");
  const n = parseInt(h, 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

function mix(a: string, b: string, t: number): string {
  const [ar, ag, ab] = hexToRgb(a);
  const [br, bg, bb] = hexToRgb(b);
  const r = Math.round(ar + (br - ar) * t);
  const g = Math.round(ag + (bg - ag) * t);
  const bl = Math.round(ab + (bb - ab) * t);
  return `rgb(${r},${g},${bl})`;
}

/** Ambient bar waveform, purely decorative — evokes the assistant "listening". */
export class Waveform {
  private ctx: CanvasRenderingContext2D;
  private dpr = Math.max(1, Math.min(2, window.devicePixelRatio || 1));
  private width = 0;
  private height = 0;
  private barWidth = 3 * this.dpr;
  private gap = 5 * this.dpr;
  private rafId: number | null = null;

  constructor(private canvas: HTMLCanvasElement) {
    const ctx = canvas.getContext("2d");
    if (!ctx) throw new Error("2D canvas context unavailable");
    this.ctx = ctx;
    window.addEventListener("resize", () => this.resize());
    this.resize();
  }

  private resize(): void {
    const rect = this.canvas.getBoundingClientRect();
    this.width = Math.max(1, Math.round(rect.width * this.dpr));
    this.height = Math.max(1, Math.round(rect.height * this.dpr));
    this.canvas.width = this.width;
    this.canvas.height = this.height;
  }

  private renderFrame(t: number): void {
    const accentStrong = cssVar("--accent-strong", "#103e38");
    const accent = cssVar("--accent", "#1f7a6c");
    const gold = cssVar("--gold", "#9c6a1e");
    const rose = cssVar("--rose", "#a14f3c");

    this.ctx.clearRect(0, 0, this.width, this.height);
    const count = Math.floor(this.width / (this.barWidth + this.gap));
    const mid = this.height / 2;

    for (let i = 0; i < count; i++) {
      const x = i * (this.barWidth + this.gap);
      const phase = i * 0.32;
      const amp = Math.abs(
        Math.sin(t * 0.0011 + phase) * 0.45 +
          Math.sin(t * 0.0006 + phase * 1.8) * 0.35 +
          Math.sin(phase * 2.6) * 0.2,
      );
      const barH = Math.max(3 * this.dpr, amp * this.height * 0.72);
      const frac = i / count;
      const color =
        frac < 0.4
          ? mix(accentStrong, accent, frac / 0.4)
          : frac < 0.7
            ? mix(accent, gold, (frac - 0.4) / 0.3)
            : mix(gold, rose, (frac - 0.7) / 0.3);
      this.ctx.fillStyle = color;
      this.ctx.fillRect(x, mid - barH / 2, this.barWidth, barH);
    }
  }

  start(): void {
    if (PREFERS_REDUCED_MOTION) {
      this.renderFrame(0);
      return;
    }
    const loop = (t: number) => {
      this.renderFrame(t);
      this.rafId = requestAnimationFrame(loop);
    };
    this.rafId = requestAnimationFrame(loop);
  }

  stop(): void {
    if (this.rafId !== null) cancelAnimationFrame(this.rafId);
    this.rafId = null;
  }
}
