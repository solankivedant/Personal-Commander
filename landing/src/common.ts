import "./style.css";
import { initScrollReveal } from "./reveal";
import { initFloatingHeader } from "./header";

/** Entry point for every page that isn't the homepage: just the shared
 * styles, the scroll-reveal effect, and the floating header. The
 * homepage-only widgets (waveform, command-demo cycler, bento grid, phase
 * track) live in main.ts because they depend on DOM ids that only exist
 * there. */
function main(): void {
  initScrollReveal();
  initFloatingHeader();
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", main);
} else {
  main();
}
