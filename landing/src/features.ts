import type { ToolCard } from "./data";
import { mark } from "./graphic";

const TIER_LABEL: Record<ToolCard["tier"], string> = {
  local: "local tier",
  lan: "lan tier",
  net: "net tier",
};

function chipsMarkup(tool: ToolCard): string {
  if (!tool.chips?.length) return "";
  return `<div class="chips">${tool.chips.map((c) => `<span class="chip-soft">${c}</span>`).join("")}</div>`;
}

function footMarkup(tool: ToolCard): string {
  return `<div class="foot">
  <span class="tag${tool.tier === "net" ? " net" : ""}">${TIER_LABEL[tool.tier]}</span>
  ${tool.risk === "confirm" ? '<span class="tag confirm">asks first</span>' : ""}
</div>`;
}

function cardMarkup(tool: ToolCard): string {
  // A double-width card puts its labels alongside the copy, so the extra
  // width is used instead of sitting empty.
  if (tool.span2) {
    return `
<div class="fc-main">
  ${mark(tool.icon, tool.amber ? "amber" : "accent")}
  <h3>${tool.name}</h3>
  <p>${tool.desc}</p>
</div>
<div class="fc-aside">
  ${chipsMarkup(tool)}
  ${footMarkup(tool)}
</div>`;
  }

  return `
${mark(tool.icon, tool.amber ? "amber" : "accent")}
<h3>${tool.name}</h3>
<p>${tool.desc}</p>
${chipsMarkup(tool)}
${footMarkup(tool)}`;
}

export function renderFeatures(container: HTMLElement, tools: ToolCard[]): void {
  container.innerHTML = "";
  for (const tool of tools) {
    const card = document.createElement("div");
    card.className = `feature-card${tool.span2 ? " span-2" : ""}`;
    card.innerHTML = cardMarkup(tool);
    container.appendChild(card);
  }
}
