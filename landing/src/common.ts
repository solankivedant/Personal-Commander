import "./style.css";
import { initScrollReveal } from "./reveal";
import { initFloatingHeader } from "./header";
import { initBillingToggle } from "./pricing";

/** Entry point for every page that isn't the homepage. */
function main(): void {
  initScrollReveal();
  initFloatingHeader();
  initBillingToggle();
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", main);
} else {
  main();
}
