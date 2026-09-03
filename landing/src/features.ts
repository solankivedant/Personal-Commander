import type { ToolCard } from "./data";
import { mark } from "./graphic";

const TIER_LABEL: Record<ToolCard["tier"], string> = {
  local: "local tier",
  lan: "lan tier",
  net: "net tier",
};

function cardMarkup(tool: ToolCard): string {
  const chips = tool.chips?.length
    ? `<div class="chips">${tool.chips.map((c) => `<span class="chip-soft">${c}</span>`).join("")}</div>`
    : "";

  return `
${mark(tool.icon, tool.amber ? "amber" : "accent")}
<h3>${tool.name}</h3>
<p>${tool.desc}</p>
${chips}
<div class="foot">
  <span class="tag${tool.tier === "net" ? " net" : ""}">${TIER_LABEL[tool.tier]}</span>
  ${tool.risk === "confirm" ? '<span class="tag confirm">asks first</span>' : ""}
</div>`;
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
