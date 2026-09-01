export interface DemoFrame {
  lang: "en" | "hi" | "gu";
  tag: string;
  text: string;
  stage: string;
}

// Mirrors config/examples/{en,hi,gu}.jsonl — one intent, three phrasings.
export const DEMO_FRAMES: DemoFrame[] = [
  { lang: "en", tag: "EN", text: '"turn the volume down"', stage: "grammar match" },
  { lang: "hi", tag: "HI", text: "आवाज़ कम करो", stage: "grammar match" },
  { lang: "gu", tag: "GU", text: "અવાજ ઓછો કરો", stage: "embedding match · 0.81" },
];

export type ToolTier = "local" | "lan" | "net";

export interface ToolCard {
  name: string;
  tier: ToolTier;
  risk?: "confirm";
  desc: string;
  iconPath: string;
  featured?: boolean;
}

// Mirrors src/munshiji/tools/ — see docs/ARCHITECTURE.md for the tool registry contract.
export const TOOLS: ToolCard[] = [
  {
    name: "Office",
    tier: "local",
    risk: "confirm",
    desc: "Outlook, Excel, Word via COM automation — the strongest technical moat, and the reason this exists at all.",
    iconPath: "M4 4h6v6H4zM14 4h6v6h-6zM14 14h6v6h-6zM4 14h6v6H4z",
    featured: true,
  },
  {
    name: "System",
    tier: "local",
    desc: "Volume, brightness, power, Wi-Fi.",
    iconPath: "M12 3v10M12 13a4 4 0 0 0 4-4V7a4 4 0 0 0-8 0v2a4 4 0 0 0 4 4Z",
  },
  {
    name: "Apps",
    tier: "local",
    desc: "Launch, focus, close windows.",
    iconPath: "M4 4h16v4H4zM4 10h16v10H4z",
  },
  {
    name: "Files",
    tier: "local",
    risk: "confirm",
    desc: "Search, move, rename — confirm-gated and undoable.",
    iconPath: "M14.7 6.3a4 4 0 0 1-5.4 5.4L4 17l3 3 5.3-5.3a4 4 0 0 1 5.4-5.4l-3 3-2-2 3-3Z",
  },
  {
    name: "Web & weather",
    tier: "net",
    desc: "Search and Open-Meteo lookups.",
    iconPath: "M3 12h18M12 3a13 13 0 0 1 0 18 13 13 0 0 1 0-18Z",
  },
  {
    name: "Gmail & Calendar",
    tier: "net",
    desc: "App-password or OAuth2.",
    iconPath: "M4 4h16v16H4z M4 6l8 7 8-7",
  },
  {
    name: "Phone bridge",
    tier: "lan",
    desc: "Via the KDE Connect CLI.",
    iconPath: "M7 2h10v20H7z M11 18h2",
  },
];

export interface PhaseSegment {
  label: string;
  partial: boolean;
}

// Mirrors docs/ROADMAP.md — kept in sync by hand, same as the desktop-preview build.
export const ROADMAP_PHASES: PhaseSegment[] = [
  { label: "Phase 0 — Spike", partial: true },
  { label: "Phase 1 — Voice loop", partial: true },
  { label: "Phase 2 — Router", partial: false },
  { label: "Phase 3 — Files", partial: false },
  { label: "Phase 4 — LLM", partial: false },
  { label: "Phase 5 — Office", partial: false },
  { label: "Phase 6 — Indic", partial: false },
  { label: "Phase 7 — Memory", partial: false },
  { label: "Phase 8 — Packaging", partial: false },
  { label: "Phase 9 — Commercial", partial: false },
];
