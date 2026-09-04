import { DEMO_FRAMES, TOOLS, SHOWCASE } from "./data";
import { CommandDemo } from "./demo";
import { Waveform } from "./waveform";
import { initScrollReveal } from "./reveal";
import { renderFeatures } from "./features";
import { renderShowcase } from "./carousel";
import { initFloatingHeader } from "./header";

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

  renderFeatures(byId("featureGrid"), TOOLS);
  renderShowcase(byId("showcase"), SHOWCASE);

  initScrollReveal();
  initFloatingHeader();
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", main);
} else {
  main();
}
