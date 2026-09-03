import type { ToolCard } from "./data";

const TIER_TAG: Record<ToolCard["tier"], { label: string; netStyle: boolean }> = {
  local: { label: "local tier", netStyle: false },
  lan: { label: "lan tier", netStyle: false },
  net: { label: "net tier", netStyle: true },
};

function buildCard(tool: ToolCard): HTMLElement {
  const card = document.createElement("div");
  const modifier = tool.featured ? " big" : tool.wide ? " wide" : "";
  card.className = `bento-card${modifier}`;

  const mark = document.createElement("div");
  mark.className = `mark c-${tool.color}`;
  mark.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="${tool.iconPath}"/></svg>`;

  const body = document.createElement("div");
  const h3 = document.createElement("h3");
  h3.textContent = tool.name;
  const p = document.createElement("p");
  p.textContent = tool.desc;
  body.append(h3, p);

  if (tool.features?.length) {
    const list = document.createElement("ul");
    list.className = "feature-list";
    for (const feature of tool.features) {
      const li = document.createElement("li");
      li.textContent = feature;
      list.appendChild(li);
    }
    body.appendChild(list);
  }

  const foot = document.createElement("div");
  foot.className = "foot";
  const tierTag = document.createElement("span");
  const tier = TIER_TAG[tool.tier];
  tierTag.className = tier.netStyle ? "tag net" : "tag";
  tierTag.textContent = tier.label;
  foot.appendChild(tierTag);
  if (tool.risk === "confirm") {
    const riskTag = document.createElement("span");
    riskTag.className = "tag";
    riskTag.textContent = "confirm";
    foot.appendChild(riskTag);
  }

  card.append(mark, body, foot);
  return card;
}

export function renderBento(container: HTMLElement, tools: ToolCard[]): void {
  container.innerHTML = "";
  for (const tool of tools) container.appendChild(buildCard(tool));
}
