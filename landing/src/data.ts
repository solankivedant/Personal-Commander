/* Content model for the site. Mirrors src/munshiji/tools/ - see
 * docs/ARCHITECTURE.md for the tool registry contract. */

export interface DemoFrame {
  lang: "en" | "hi" | "gu";
  tag: string;
  text: string;
  stage: string;
}

// Mirrors config/examples/{en,hi,gu}.jsonl - one intent, three phrasings.
export const DEMO_FRAMES: DemoFrame[] = [
  { lang: "en", tag: "EN", text: '"turn the volume down"', stage: "grammar match" },
  { lang: "hi", tag: "HI", text: "आवाज़ कम करो", stage: "grammar match" },
  { lang: "gu", tag: "GU", text: "અવાજ ઓછો કરો", stage: "embedding match · 0.81" },
];

export type ToolTier = "local" | "lan" | "net";

/** Line icons, drawn at 24x24 with a 1.8 stroke. */
export const ICONS = {
  office: "M4 4h6v6H4zM14 4h6v6h-6zM14 14h6v6h-6zM4 14h6v6H4z",
  system: "M12 3v10M12 13a4 4 0 0 0 4-4V7a4 4 0 0 0-8 0v2a4 4 0 0 0 4 4Z",
  apps: "M4 5h16v4H4zM4 12h7v7H4zM13 12h7v7h-7z",
  files: "M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7Z",
  web: "M3 12h18M12 3a13 13 0 0 1 0 18 13 13 0 0 1 0-18ZM12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18Z",
  mail: "M4 5h16v14H4zM4 7l8 6 8-6",
  phone: "M7 2h10v20H7zM11 18h2",
  shield: "M12 3 4 6v6c0 4.5 3.4 7.7 8 9 4.6-1.3 8-4.5 8-9V6l-8-3Z",
  shieldCheck: "M9 12l2 2 4-4M12 3l8 3v6c0 4.5-3.4 7.7-8 9-4.6-1.3-8-4.5-8-9V6l8-3Z",
  undo: "M9 14 4 9l5-5M4 9h9a7 7 0 0 1 0 14H8",
  lock: "M6 11h12v10H6zM9 11V8a3 3 0 0 1 6 0v3",
  mic: "M12 2a3 3 0 0 0-3 3v6a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3ZM19 11a7 7 0 0 1-14 0M12 18v4",
  grammar: "M4 19.5A2.5 2.5 0 0 1 6.5 17H20M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2ZM8 7h8M8 11h5",
  vector: "M12 3v4M12 17v4M3 12h4M17 12h4M6.3 6.3l2.8 2.8M14.9 14.9l2.8 2.8M17.7 6.3l-2.8 2.8M9.1 14.9l-2.8 2.8",
  chip: "M9 3h6v2h2a2 2 0 0 1 2 2v2h2v2h-2v2h2v2h-2v2a2 2 0 0 1-2 2h-2v2H9v-2H7a2 2 0 0 1-2-2v-2H3v-2h2v-2H3V9h2V7a2 2 0 0 1 2-2h2ZM9 9h6v6H9Z",
  bulb: "M9 18h6M10 21h4M12 3a6 6 0 0 0-4 10.5c.6.55 1 1.3 1 2.5h6c0-1.2.4-1.95 1-2.5A6 6 0 0 0 12 3Z",
  pulse: "M3 12h4l3 8 4-16 3 8h4",
  bolt: "M13 2 3 14h7v8l10-12h-7z",
  users: "M17 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M9.5 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8ZM22 21v-2a4 4 0 0 0-3-3.85",
  check: "M5 12l4 4L19 6",
  windows: "M3 5.5 10.5 4.4V11H3V5.5ZM11.5 4.3 21 3v8H11.5V4.3ZM3 12h7.5v6.6L3 17.4V12ZM11.5 12H21v9l-9.5-1.3V12Z",
  book: "M4 5a2 2 0 0 1 2-2h12v18H6a2 2 0 0 1-2-2V5ZM8 7h7M8 11h7",
  alert: "M12 8v5M12 16h.01M10.3 3.6 2.7 17a2 2 0 0 0 1.7 3h15.2a2 2 0 0 0 1.7-3L13.7 3.6a2 2 0 0 0-3.4 0Z",
} as const;

export interface ToolCard {
  name: string;
  tier: ToolTier;
  risk?: "confirm";
  desc: string;
  icon: string;
  amber?: boolean;
  chips?: string[];
  span2?: boolean;
}

export const TOOLS: ToolCard[] = [
  {
    name: "Office",
    tier: "local",
    risk: "confirm",
    desc: "Draft an Outlook reply, read a live Excel sheet, format a Word doc - spoken, not clicked.",
    icon: ICONS.office,
    chips: ["Outlook", "Excel", "Word"],
    span2: true,
  },
  { name: "System", tier: "local", desc: "Volume, brightness, power, Wi-Fi.", icon: ICONS.system },
  { name: "Apps", tier: "local", desc: "Launch, focus, and close windows.", icon: ICONS.apps },
  { name: "Files", tier: "local", risk: "confirm", desc: "Search, move, rename - every action undoable.", icon: ICONS.files, amber: true },
  { name: "Web & weather", tier: "net", desc: "Live search and weather lookups.", icon: ICONS.web },
  {
    name: "Gmail & Calendar",
    tier: "net",
    desc: "Read, draft, and search mail; check and create events.",
    icon: ICONS.mail,
    span2: true,
    chips: ["Search mail", "Draft replies", "Create events"],
  },
  { name: "Phone bridge", tier: "lan", desc: "Texts, notifications, find your phone - over your own network.", icon: ICONS.phone },
];

/** One slide per tool pack for the full-width showcase carousel. */
export interface ShowcaseSlide {
  name: string;
  icon: string;
  tier: ToolTier;
  risk?: "confirm";
  amber?: boolean;
  desc: string;
  app: string;
  utterance: string;
  stage: string;
  call: string;
  chips: string[];
}

export const SHOWCASE: ShowcaseSlide[] = [
  {
    name: "Office",
    icon: ICONS.office,
    tier: "local",
    risk: "confirm",
    desc: "Outlook, Excel and Word driven straight from your voice - the document never leaves your machine.",
    app: "Outlook",
    utterance: "reply to Ravi - I'll send the invoice by Friday",
    stage: "llm plan · dry run",
    call: 'office.outlook_reply(to: "Ravi", body: "…")',
    chips: ["Draft & send mail", "Read Excel cells", "Format a doc"],
  },
  {
    name: "System",
    icon: ICONS.system,
    tier: "local",
    desc: "Volume, brightness, power and Wi-Fi, resolved deterministically in under ten milliseconds.",
    app: "System",
    utterance: "turn the volume down",
    stage: "grammar match · 8ms",
    call: "system.set_volume(level: 20)",
    chips: ["Volume", "Brightness", "Wi-Fi", "Power"],
  },
  {
    name: "Apps",
    icon: ICONS.apps,
    tier: "local",
    desc: "Launch, focus and close windows by name - fuzzy matched, so close enough is enough.",
    app: "Windows",
    utterance: "open Chrome and put it on the right",
    stage: "grammar match · 9ms",
    call: 'apps.launch(name: "chrome", snap: "right")',
    chips: ["Launch", "Focus", "Snap", "Close"],
  },
  {
    name: "Files",
    icon: ICONS.files,
    tier: "local",
    risk: "confirm",
    amber: true,
    desc: "Search, move and rename in bulk. It says what it is about to do, then registers the undo first.",
    app: "File Explorer",
    utterance: "move today's PDFs into Invoices",
    stage: "embedding match · 0.86",
    call: 'files.move(pattern: "*.pdf", dest: "Invoices")',
    chips: ["Search", "Move", "Rename", "Undo"],
  },
  {
    name: "Web & weather",
    icon: ICONS.web,
    tier: "net",
    desc: "Live lookups through one allowlisted client - fetched text is quoted to the model, never obeyed.",
    app: "Web",
    utterance: "what's the weather in Ahmedabad tomorrow",
    stage: "grammar match · 7ms",
    call: 'web.weather(city: "Ahmedabad", day: "+1")',
    chips: ["Search", "Weather", "Allowlisted"],
  },
  {
    name: "Gmail & Calendar",
    icon: ICONS.mail,
    tier: "net",
    risk: "confirm",
    desc: "Triage the inbox and the week by voice. Only the query leaves - never the transcript.",
    app: "Gmail",
    utterance: "anything from the bank this week?",
    stage: "embedding match · 0.83",
    call: 'gmail.search(query: "from:bank newer_than:7d")',
    chips: ["Search mail", "Draft replies", "Create events"],
  },
  {
    name: "Phone bridge",
    icon: ICONS.phone,
    tier: "lan",
    risk: "confirm",
    amber: true,
    desc: "Texts, notifications and find-my-phone across your own network - no third-party relay.",
    app: "Phone",
    utterance: "text Meera that I'm on my way",
    stage: "grammar match · 11ms",
    call: 'phone.send_sms(to: "Meera", text: "…")',
    chips: ["Send texts", "Notifications", "Find phone"],
  },
];

export interface Faq {
  q: string;
  a: string;
}

export const FAQS: Faq[] = [
  {
    q: "What is Munshiji?",
    a: "A voice assistant for Windows that runs on your own laptop. It opens apps, sorts files, edits Office documents, reads your inbox and changes system settings - all from a spoken sentence, in English, Hindi or Gujarati.",
  },
  {
    q: "Does anything I say leave my device?",
    a: "No. Speech recognition, routing and speech synthesis all run locally, so audio and transcripts never leave the machine. Only a net-tier tool sends anything out, and then only its arguments - a city name for weather, a search query for mail - never the recording.",
  },
  {
    q: "Do I need an internet connection?",
    a: "Not for the everyday things. Files, apps, Office and system control work fully offline. Turn on local_only mode and the tools that reach the network are removed from the registry entirely.",
  },
  {
    q: "What hardware does it need?",
    a: "A Windows 10 or 11 laptop with 16 GB of RAM and integrated graphics. No discrete GPU - about 85% of commands never touch a language model, so most of the work is a few milliseconds of matching rather than heavy inference.",
  },
  {
    q: "Can it delete or send something by mistake?",
    a: "Anything that deletes, sends, spends or overwrites speaks its intent first and waits for a spoken yes. Every action also registers how to reverse itself before it runs, so \"undo that\" always works.",
  },
  {
    q: "How well does it understand Hindi and Gujarati?",
    a: "As well as English, by design. One multilingual encoder places all three languages in the same vector space, so a single set of examples covers every phrasing - and if it ever mishears you, teach it your wording once and it remembers.",
  },
];
