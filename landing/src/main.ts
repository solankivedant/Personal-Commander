import "./style.css";
import { DEMO_FRAMES, ROADMAP_PHASES, TOOLS } from "./data";
import { CommandDemo } from "./demo";
import { Waveform } from "./waveform";
import { initScrollReveal } from "./reveal";
import { renderBento } from "./bento";
import { renderPhaseTrack } from "./roadmap";

function byId<T extends HTMLElement>(id: string): T {
  const el = document.getElementById(id);
  if (!el) throw new Error(`Expected #${id} in the page`);
  return el as T;
}

function main(): void {
  new CommandDemo(
    {
      utterance: byId("utterance"),
      stageLabel: byId("stageLabel"),
      langTag: byId("langTag"),
      langDots: byId("langDots"),
    },
    DEMO_FRAMES,
  ).start();

  new Waveform(byId<HTMLCanvasElement>("wave")).start();

  renderBento(byId("bentoGrid"), TOOLS);
  renderPhaseTrack(byId("phaseTrack"), ROADMAP_PHASES);

  initScrollReveal();
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", main);
} else {
  main();
}
