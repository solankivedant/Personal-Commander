import type { DemoFrame } from "./data";

export interface CommandDemoEls {
  utterance: HTMLElement;
  stageLabel: HTMLElement;
  langTag: HTMLElement;
  langDots: HTMLElement;
}

/** Cycles the hero's "same intent, three languages" widget. */
export class CommandDemo {
  private index = 0;
  private timer: number | null = null;
  private readonly reduceMotion =
    window.matchMedia?.("(prefers-reduced-motion: reduce)").matches === true;

  constructor(
    private readonly els: CommandDemoEls,
    private readonly frames: DemoFrame[],
    private readonly intervalMs = 2600,
  ) {
    this.buildDots();
  }

  private buildDots(): void {
    this.els.langDots.innerHTML = "";
    for (const frame of this.frames) {
      const dot = document.createElement("span");
      dot.dataset.lang = frame.lang;
      this.els.langDots.appendChild(dot);
    }
  }

  private paint(frame: DemoFrame): void {
    this.els.utterance.dataset.lang = frame.lang;
    this.els.utterance.textContent = frame.text;
    this.els.stageLabel.textContent = frame.stage;
    this.els.langTag.textContent = frame.tag;
    this.els.langDots.querySelectorAll<HTMLElement>("span").forEach((dot) => {
      dot.classList.toggle("on", dot.dataset.lang === frame.lang);
    });
  }

  start(): void {
    const first = this.frames[0];
    if (!first) return;
    this.paint(first);
    if (this.reduceMotion) return;
    this.timer = window.setInterval(() => {
      this.index = (this.index + 1) % this.frames.length;
      const frame = this.frames[this.index];
      if (frame) this.paint(frame);
    }, this.intervalMs);
  }

  stop(): void {
    if (this.timer !== null) window.clearInterval(this.timer);
    this.timer = null;
  }
}
