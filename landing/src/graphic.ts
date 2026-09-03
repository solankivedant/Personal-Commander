/** Shared icon + mark helpers. One crisp line-icon language across the whole
 * site - no glows, no gradients, no decorative filler. */

export function icon(path: string, stroke = 1.8): string {
  return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="${stroke}" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="${path}"/></svg>`;
}

export type MarkTone = "accent" | "amber" | "slate";

export function mark(path: string, tone: MarkTone = "accent", size: "" | "lg" = ""): string {
  const cls = ["mark", tone === "accent" ? "" : tone, size].filter(Boolean).join(" ");
  return `<div class="${cls}">${icon(path)}</div>`;
}
