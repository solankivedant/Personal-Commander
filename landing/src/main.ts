import { DEMO_FRAMES, TOOLS, SHOWCASE, FAQS } from "./data";
import { CommandDemo } from "./demo";
import { Waveform } from "./waveform";
import { VoiceDial } from "./dial";
import { initScrollReveal } from "./reveal";
import { renderFeatures } from "./features";
import { renderShowcase } from "./carousel";
import { initFloatingHeader } from "./header";
import { renderFaq } from "./faq";

function byId<T extends HTMLElement>(id: string): T {
  const el = document.getElementById(id);
  if (!el) throw new Error(`Expected #${id} in the page`);
  return el as T;
}

/** getElementById is typed to HTMLElement, which the dial's <svg> is not. */
function bySelector<T extends Element>(selector: string): T {
  const el = document.querySelector<T>(selector);
  if (!el) throw new Error(`Expected ${selector} in the page`);
  return el;
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

  const waveform = new Waveform(byId<HTMLCanvasElement>("wave"));
  waveform.start();

  // The dial owns the dashboard's listening state; the bars just follow it.
  const dial = new VoiceDial({
    root: byId("dash"),
    button: byId<HTMLButtonElement>("voiceDial"),
    svg: bySelector<SVGSVGElement>("#dialSvg"),
    label: byId("dialLabel"),
    hint: byId("dialHint"),
    status: byId("dashStatusText"),
  });
  dial.onChange((paused) => waveform.setActive(!paused));
  dial.start();

  renderFeatures(byId("featureGrid"), TOOLS);
  renderShowcase(byId("showcase"), SHOWCASE);
  renderFaq(byId("faqList"), FAQS);

  initScrollReveal();
  initFloatingHeader();
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", main);
} else {
  main();
}
