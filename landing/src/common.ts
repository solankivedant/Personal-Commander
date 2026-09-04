import { initScrollReveal } from "./reveal";
import { initFloatingHeader } from "./header";
import { initBillingToggle } from "./pricing";
import { renderFeatures } from "./features";
import { renderShowcase } from "./carousel";
import { TOOLS, SHOWCASE } from "./data";

/** Entry point for every page that isn't the homepage. The feature grid and
 * the showcase carousel render wherever a page provides their container, so
 * the Features page gets both without a second bundle. */
function main(): void {
  initScrollReveal();
  initFloatingHeader();
  initBillingToggle();

  const grid = document.getElementById("featureGrid");
  if (grid) renderFeatures(grid, TOOLS);

  const showcase = document.getElementById("showcase");
  if (showcase) renderShowcase(showcase, SHOWCASE);
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", main);
} else {
  main();
}
