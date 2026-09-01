import type { PhaseSegment } from "./data";

export function renderPhaseTrack(container: HTMLElement, phases: PhaseSegment[]): void {
  container.innerHTML = "";
  for (const phase of phases) {
    const seg = document.createElement("div");
    seg.className = phase.partial ? "phase-seg partial" : "phase-seg";
    seg.title = phase.label;
    container.appendChild(seg);
  }
}
