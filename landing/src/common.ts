import "./style.css";
import { initScrollReveal } from "./reveal";

/** Entry point for every page that isn't the homepage: just the shared
 * styles and the scroll-reveal effect. The homepage-only widgets (waveform,
 * command-demo cycler, bento grid, phase track) live in main.ts because they
 * depend on DOM ids that only exist there. */
function main(): void {
  initScrollReveal();
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", main);
} else {
  main();
}
