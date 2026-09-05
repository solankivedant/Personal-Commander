import { initScrollReveal } from "./reveal";
import { initFloatingHeader } from "./header";
import { initBillingToggle } from "./pricing";
import { renderFeatures } from "./features";
import { renderShowcase } from "./carousel";
import { renderFaq } from "./faq";
import { initDownload } from "./release";
import { TOOLS, SHOWCASE, FAQS } from "./data";

/** Entry point for every page that isn't the homepage. The feature grid and
 * the showcase carousel render wherever a page provides their container, so
 * the Features page gets both without a second bundle. */
function main(): void {
  initScrollReveal();
  initFloatingHeader();
  initBillingToggle();
  // No-op on pages with no download card.
  initDownload();

  const grid = document.getElementById("featureGrid");
  if (grid) renderFeatures(grid, TOOLS);

  const showcase = document.getElementById("showcase");
  if (showcase) renderShowcase(showcase, SHOWCASE);

  const faq = document.getElementById("faqList");
  if (faq) renderFaq(faq, FAQS);
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", main);
} else {
  main();
}
