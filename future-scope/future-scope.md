# Future Scope — Munshiji as a SaaS product

**This is not the roadmap.** [`docs/ROADMAP.md`](../docs/ROADMAP.md) is the
committed engineering plan — Phase 0 through 9, each with a concrete
deliverable, enforced by CI. This document is the layer *above* that: what
Munshiji becomes as a **product and a business** once the desktop engine
works, and everything that has to be built to get there.

Nothing here is scheduled. Where an idea would change a rule in
[`.claude/rules/`](../.claude/rules/), that is called out explicitly rather than
quietly assumed.

**Companion document:** [`future-scope/gaps.md`](gaps.md) — the
market gaps this product would fill, why the incumbents haven't filled them,
which ones are worth chasing, and which look like opportunities but aren't.
This file is *what to build*; that one is *why anyone would want it*.

---

## 0. The thesis in one paragraph

Munshiji today is a single-machine application. The product it should become
is an **account-backed hybrid assistant**: the download is free and always
will be, but you sign in to use it. Signed in, the same assistant can run
**entirely on your laptop** (the local-first engine this repo is building),
or hand a job to **cloud AI agents** that keep working when your laptop is
asleep — same voice, same tool registry, same confirmation gate, same undo
stack, different execution venue. The account is what makes "my assistant" a
thing that exists across a laptop, a phone, and a browser instead of a
process on one machine.

**Free download, mandatory account, optional cloud.** That is the shape.

---

## 1. Product model

### 1.1 Why an account at all, when the app runs locally

An account is not a paywall in disguise. It buys four concrete things a
purely local app structurally cannot have:

| What the account enables | Why it can't be local-only |
|---|---|
| Cloud agent execution | Needs an identity to bill, isolate, and rate-limit |
| Multi-device continuity ("continue on my phone") | Needs a rendezvous point between devices |
| Encrypted settings/macro backup and restore | Needs storage that survives a wiped laptop |
| Entitlement + licence enforcement | Needs a server the client can't lie to |

The honest framing for the marketing page ([`landing/`](../landing/)): *"Your
voice, your files, and your transcripts never leave your machine. Your
account holds your settings, your subscription, and — only if you ask — a
cloud agent that can keep working while your laptop is shut."*

### 1.2 The tiers

Illustrative, not final — pricing needs its own exercise (§8).

**Free — "Local"** · ₹0, account required
- Full local engine: wake word, ASR, router, all `local`-tier tools, undo,
  Office/COM automation, Hindi/Gujarati.
- Bring-your-own-key cloud escalation (your Anthropic/OpenAI key, your bill).
- Opt-in local 3B model for users who want escalation without the network and
  will accept the latency (ADR 0001) — off by default, not a paywalled
  feature.
- Settings + taught macros backed up to the account, encrypted.
- 1 device.
- **This tier must stay genuinely useful forever.** The free tier is the
  product's credibility — "it works offline, audit it yourself" stops being
  true the moment the free tier is crippled.

**Pro — "Cloud agents"** · monthly
- Everything in Free, plus a metered pool of **cloud agent credits**.
- Cloud agents run long jobs asynchronously (research, inbox triage,
  multi-document synthesis, scheduled routines) on managed models — no API
  key of your own needed.
- Cross-device: laptop + phone + web.
- Larger models available for LLM escalation without your own key.

**Business / Team** · per seat
- Shared tool packs and taught macros across a team.
- Admin console: which `net`-tier tools are enabled, which domains are
  allowlisted, org-wide `local_only` enforcement.
- SSO, centralized audit log export, invoiced billing.

**Self-hosted / Air-gapped** · annual licence
- For orgs that cannot have an account server in the loop. Offline licence
  file, no telemetry, no cloud tier. This is the version that keeps the
  privacy claim defensible under procurement review.

### 1.3 The hard rule the tiers must not break

**Audio, transcripts, file contents, and screen captures never leave the
device by default in any tier.** Cloud tiers move *specific arguments to
specific tools* the user approved, not the assistant's raw perception. This
is already the rule in
[`.claude/rules/security-and-privacy.md`](../.claude/rules/security-and-privacy.md)
§ "Network boundaries" — SaaS does not get to relax it, it inherits it.

---

## 2. The three execution modes

The existing `network.mode` config (`local_only | hybrid | full` in
[`config/default.yaml`](../config/default.yaml)) already anticipates this. SaaS
adds a second axis: *where the reasoning runs*.

### Mode A — Local (default, offline-capable)

Grammar → embeddings, both sub-20ms, covering ~85% of commands. Exactly what
[`docs/ARCHITECTURE.md`](../docs/ARCHITECTURE.md) describes. Works with the
network cable pulled, after a one-time sign-in. **Sign-in must cache an
offline grace period** (30 days is a reasonable default) — an assistant that
bricks itself on a flight is not local-first, it's DRM wearing a costume.

Note what this no longer includes: the local 3B is **not** part of the default
local path (ADR 0001). Offline, anything the router can't match falls to teach
mode, which is the honest answer and also the mechanism that makes the second
attempt work.

### Mode B — Hybrid (cloud escalation) — *the default escalation target*

The local router still handles ~85% of commands. Only genuinely compositional
requests and knowledge questions escalate — to the user's own API key (Free)
or the managed pool (Pro). Escalation **speaks its intent first** ("this needs
a bigger model — send it to the cloud?"), the same discipline as a
`confirm`-risk tool. Governed by `cloud.escalate: never | ask | auto`, already
in config.

**This is the default now, not an upsell.**
[ADR 0001](../docs/decisions/0001-local-llm-off-the-default-path.md) took the
local 3B off the default path: at the measured 11.3 tok/s it costs ~4.4s for a
tool call and ~10.6s for a paragraph, and on knowledge questions a 3B model is
slow *and* unreliable. That makes the cloud tier's justification honest rather
than commercial — it answers a real limitation of the local engine instead of
a manufactured one. The local 3B stays available as an **opt-in privacy mode**
for users who prefer latency to the network.

**The corollary for marketing: do not claim "fully offline."** The fast path —
the ~85% — works with the network off, and that is a much stronger claim than
any competitor can make. Compositional requests and knowledge questions do
not, unless the user opts into the local model. Say it plainly; overclaiming
here would poison the one thing the product is actually trusted for.

### Mode C — Cloud agents (asynchronous, laptop-independent)

The genuinely new capability. A job is handed to a sandboxed cloud agent
that owns it end to end: "research these five suppliers and draft a
comparison," "watch this inbox and file anything from the CA," "every Friday
5pm compile my week." It runs on managed infrastructure, uses a **cloud-safe
subset of the tool registry** (§3.D), and reports back to the desktop
client, the web app, or a push notification.

**Cloud agents can never touch the local machine.** No filesystem, no COM,
no shell. If a cloud agent's plan needs a local action, it produces a
*proposal* that the desktop client picks up and puts through the normal
local confirm gate. This one boundary is what keeps the SaaS backend from
becoming a remote-code-execution channel into every customer's laptop.

---

## 3. What actually has to be built

The buildout list. Each item names where it lands relative to the existing
layer map (L0–L8 in [`docs/ARCHITECTURE.md`](../docs/ARCHITECTURE.md)).

### A. Identity & accounts — *client side, new `src/munshiji/account/`*

- [ ] Sign-up / sign-in: email + magic link, Google OAuth, and (India-first)
      phone + OTP. Don't build password auth from scratch.
- [ ] **Buy, don't build**: an auth provider (Clerk, Auth0, Supabase Auth;
      WorkOS for SSO later). Rolling your own session handling is where
      small teams lose three months and one breach.
- [ ] Desktop OAuth device flow — the client opens a browser, gets a token,
      stores it in **Windows Credential Manager via `keyring`**, never in a
      config file (the existing rule, already specified for Google tokens).
- [ ] Refresh-token encryption at rest with DPAPI
      (`win32crypt.CryptProtectData`) — the pattern the security rules
      already mandate.
- [ ] Device registration and a per-device identity, so "revoke this laptop"
      is a real button.
- [ ] Offline grace period plus a clear, non-punitive expiry UX.

### B. Entitlements & licence enforcement — *`src/munshiji/account/entitlements.py`*

- [ ] A signed entitlement blob (JWT or similar) the client caches: tier,
      seats, feature flags, expiry. Verified against a public key shipped in
      the binary.
- [ ] Feature gating that **degrades to Free, never to broken** — an expired
      Pro subscription loses cloud agents and keeps every local tool.
- [ ] `network.mode: local_only` must still hard-remove every `net`-tier
      tool regardless of entitlement (existing rule — verify it doesn't
      regress when entitlements land).
- [ ] Anti-piracy posture: accept that a determined user can patch the
      client. Bind value to the *server-side* cloud tier rather than trying
      to make a local binary tamper-proof.

### C. Sync — *client side, new `src/munshiji/sync/`*

What syncs, explicitly:

| Syncs | Never syncs |
|---|---|
| Settings / config overrides | Audio, ever |
| Taught router examples (phrasings only) | Transcripts |
| Taught macros (§10) | File contents |
| Tool allowlists, domain allowlist | Screen captures |
| Entitlement state | The memory graph, unless explicitly exported |

- [ ] **End-to-end encryption with a client-held key** for everything in the
      left column. The server should be architecturally unable to read a
      user's macros. That's a competitive claim, not just hygiene.
- [ ] Conflict resolution — last-write-wins is fine for settings, but taught
      macros need a merge UX ("this macro changed on your other device").
- [ ] Export / delete everything, one command, plain files. Required by DPDP
      anyway (§3.I), and it's what makes the privacy pitch falsifiable.

### D. Cloud agent runtime — *server side, new service*

The biggest single piece of work.

- [ ] **Sandboxed execution per job** — Firecracker microVMs, gVisor, or a
      managed sandbox. Not bare containers sharing a kernel across tenants,
      given these agents fetch attacker-controlled web pages by design.
- [ ] **A cloud-safe tool registry** — the same `@tool` decorator and the
      same `tier`/`risk`/`tags` contract from
      [`.claude/rules/architecture-and-router.md`](../.claude/rules/architecture-and-router.md),
      but a disjoint tool set: web fetch, search, email draft (never send
      without confirmation), document generation, API calls. **Zero** local
      filesystem, shell, registry, or COM tools — enforced structurally by
      the registry the way `blocked`-risk tools already are, not by prompt.
- [ ] **The confirm gate, remoted.** A cloud agent hitting a `confirm`-risk
      step suspends the job and pushes a confirmation to the user's devices.
      A tool result still can never directly trigger a confirm action
      (existing injection-mitigation rule #3) — it routes to a human or it
      does not happen.
- [ ] **Prompt injection at cloud scale.** Today the blast radius of a
      malicious page is one laptop. In a multi-tenant agent runtime it is
      "did that page get one tenant's agent to read another tenant's data."
      Per-job credential scoping, per-tenant egress allowlists, no shared
      caches across tenants.
- [ ] Job model: queue, retries, timeouts, cancellation, and a hard spend cap
      per job and per account. An agent that loops is a bill, not just a bug.
- [ ] Streaming progress back to clients (SSE or WebSocket) so a running job
      is visible, interruptible, and narratable by voice.
- [ ] Scheduled agents ("every Friday 5pm") — cron, plus the misfire
      semantics nobody thinks about until a laptop was off for a week.
- [ ] Server-side model routing: cheap model for triage, expensive model for
      synthesis. Margin lives here.

### E. Billing & payments — *server side*

India-first has specific requirements a Stripe-shaped assumption misses:

- [ ] **Razorpay or Cashfree** for domestic (UPI, cards, netbanking);
      **Stripe/Paddle** for international. Paddle as merchant-of-record
      removes global sales-tax handling entirely — worth the fee early.
- [ ] **RBI e-mandate for recurring UPI/card payments.** Recurring billing in
      India is genuinely harder than elsewhere; the mandate flow, pre-debit
      notification, and failure/retry handling all need building.
- [ ] GST: 18% on SaaS domestically, GSTIN capture for B2B input credit,
      compliant invoices. For exports, LUT filing and zero-rated invoicing.
- [ ] Metering for cloud agent credits — every job's cost attributed to an
      account and visible to the user *before* the bill.
- [ ] Dunning, proration, upgrade/downgrade, refunds, and a self-serve cancel
      that actually works. Cancellation friction is not a growth strategy,
      it's a chargeback generator.

### F. Backend infrastructure — *server side*

- [ ] API: FastAPI (matches the repo's Python and `net/api.py` idiom), or a
      different stack if the team's strength is elsewhere. One API gateway,
      not a service mesh, at this stage.
- [ ] Postgres for accounts/entitlements/jobs; Redis for queues and rate
      limits; object storage for job artifacts (encrypted, TTL'd).
- [ ] **Data residency in India** (ap-south-1 or equivalent) for Indian
      accounts. This will come up in every B2B conversation.
- [ ] Observability: structured logs (the repo already standardizes on
      `structlog`), traces, per-tenant cost dashboards, error tracking.
- [ ] Rate limiting and abuse controls — free accounts running crypto miners
      in your agent sandbox is a when, not an if.
- [ ] Status page, incident process, and a real on-call story before the
      first paying business customer.

### G. Web app & control surfaces — *new, alongside [`landing/`](../landing/)*

- [ ] Web dashboard: account, billing, devices, running jobs, job history,
      **the audit log**. The audit log being visible on the web is what turns
      "trust us" into "check for yourself."
- [ ] A web chat/voice surface — the same assistant, cloud tools only,
      usable from any browser. This is also the funnel: try it in a browser,
      then download it for the local powers.
- [ ] Onboarding that explains local vs cloud honestly. Users will not intuit
      the distinction; if they assume everything is uploaded, the product's
      whole differentiator evaporates.
- [ ] The existing [`desktop-preview/`](../desktop-preview/) Tauri shell is the
      natural home for the signed-in Control Center once the engine is real.

### H. Mobile & cross-device — *further out*

- [ ] A phone client that is *not* a second brain — it's a microphone, a
      confirmation surface, and a notification target for cloud jobs. Local
      inference on a phone is a different product; don't build it twice.
- [ ] "Ask my laptop to do this" — the phone hands a local-tier request to
      the paired desktop over the account's rendezvous channel; the desktop
      confirms and executes locally.
- [ ] Push notifications for suspended cloud jobs awaiting confirmation.
- [ ] The existing `tools/phone.py` KDE Connect bridge is the LAN-only
      version of this and stays valid for users who never sign in to cloud.

### I. Security, privacy & compliance — *the part that gets skipped and shouldn't*

Becoming a SaaS changes the threat model materially. New obligations:

- [ ] **India's DPDP Act 2023**: consent notice, purpose limitation, breach
      notification to the Data Protection Board, a Consent Manager pathway,
      and data-principal rights (access, correction, erasure) with real
      timelines. Build export/delete early; retrofitting them is miserable.
- [ ] **GDPR** if there are any EU users at all — DPA, sub-processor list,
      SCCs for transfers, and the DPO question.
- [ ] **SOC 2 Type II** — unnecessary for consumer, table stakes for the
      Business tier. Start collecting evidence a year before the first
      enterprise asks, not when they ask.
- [ ] Multi-tenancy isolation review — the highest-severity bug class in any
      SaaS, and worse here because tools have side effects.
- [ ] Penetration test, and a public `SECURITY.md` disclosure process (the
      file exists; give it a real inbox and a response SLA).
- [ ] Subprocessor transparency: which model providers see what, published.
      "Local-first" is only meaningful if the exceptions are listed.
- [ ] Extend the audit log (`data/audit.jsonl`) to record *venue* — local vs
      cloud — for every action. The existing rule says gaps in the audit log
      are bugs; venue is now part of a complete record.

### J. Distribution, updates & support

- [ ] Code signing (EV certificate) — without it SmartScreen scares off a
      large fraction of downloads. Already a High risk in
      [`docs/RISK-REGISTER.md`](../docs/RISK-REGISTER.md).
- [ ] Auto-update with a signed appcast, staged rollout, and rollback. A
      broken auto-update on an assistant with shell access is a very bad day.
- [ ] Antivirus false-positive handling — submit to the major vendors
      pre-emptively (also already in the risk register).
- [ ] Crash reporting and **opt-in** anonymous telemetry. Opt-in only; an
      opt-out default would contradict the entire pitch. Instrument the
      router-stage distribution (grammar/embedding/LLM %) — it's the single
      most useful product metric this architecture produces.
- [ ] Support: a docs site, an in-app "send diagnostics" that shows exactly
      what it will send before sending it, and a real response path for
      paying users.

### K. Growth surfaces (cheap, high leverage)

- [ ] Referral: both sides get cloud credits. Credits are marginal-cost
      currency, which makes them the right incentive here.
- [ ] Shareable macros as files (§10) — a user handing a friend a "close out
      the week" routine is organic distribution with no app store.
- [ ] A templates gallery for Indian workflows: GST invoice prep, CA document
      collation, WhatsApp-for-business triage. These are the wedge a global
      assistant won't build.

---

## 4. How this maps onto the existing architecture

The desktop layer map (L0–L8) is not rewritten. It gains **two optional
client layers** and a **separate server side**:

```
L0-L8   unchanged — audio, wake, ASR, router, brain, tools, memory, TTS
        ↑ everything below is opt-in and absent in local_only mode
L9   account/    identity, entitlements, device registration     [client]
L10  sync/       E2EE settings + macro sync                      [client]
        ↕ over the account API
cloud  agents/   sandboxed job runtime, cloud-safe tool registry [server]
       billing/  metering, subscriptions, invoicing              [server]
       web/      dashboard, audit log, web assistant             [server]
```

Rules that carry across the boundary unchanged:

- The router cascade is still grammar → embeddings → LLM. **Cloud does not
  become a shortcut past the local router** — that would break the latency
  budget and hide exactly the regressions the golden test set exists to
  catch.
- The `@tool` contract (`tier`, `risk`, `tags`, a registered inverse, catches
  its own exceptions) applies identically to cloud tools.
- The golden test set gains a cloud-tools section with its own
  `expect_confirm` cases. **100% on confirm cases stays non-negotiable**, in
  both venues.
- Untrusted content stays delimiter-wrapped, whether a laptop or a cloud
  agent fetched it.

---

## 5. Unit economics — the thing that decides whether any of this works

Sketch the numbers before building the runtime, not after.

- **Free tier marginal cost ≈ ₹0** — local inference, the user's hardware,
  the user's electricity. That's a structural advantage over every
  cloud-only assistant, and the reason free can stay generous.
- **Cloud agent cost** is dominated by model tokens plus sandbox seconds. A
  long research job costs materially more than a chat turn; price in
  credits, not "unlimited," or the top 1% of users define the P&L.
- **Gross margin target 70%+ at Pro.** If cloud agents can't clear that after
  model costs, the fix is better local/cloud routing — more work pushed back
  onto the free local engine — not a higher price.
- **The router is a margin lever.** Every command the grammar layer handles
  costs nothing. `router/teach.py` making the assistant faster with use also
  makes it cheaper with use — instrument that.

---

## 6. Sequencing — SaaS phases, stacked after the engine

These are **S-phases**, numbered separately so they can't be confused with
the engineering roadmap's Phase 0–9 and can't be built before it. Building S1
before Phase 4 means selling a subscription to something that doesn't work.

| Phase | Deliverable (the acceptance test, not a task list) |
|---|---|
| **S0 — Account** | The existing local app, with sign-in. Nothing is gated. Proves auth, device registration, and offline grace work before anything depends on them. |
| **S1 — Sync** | Reinstall Windows, sign in, and your settings and taught macros are back — E2EE, server can't read them. |
| **S2 — BYO-key cloud** | Escalation to the user's own API key, spoken-confirm gated. Ships the whole hybrid UX at zero infrastructure cost. |
| **S3 — Cloud agents v1** | One asynchronous job type (research + summarize) runs to completion with the laptop closed, and a suspended job's confirmation reaches the user. |
| **S4 — Billing** | Someone who is not you pays, gets Pro, uses credits, sees the meter, and can cancel without emailing anyone. |
| **S5 — Web + mobile** | The assistant is usable from a browser and a phone, with local powers still exclusive to the desktop. |
| **S6 — Business tier** | An admin can enforce `local_only` org-wide and export the audit log for a whole team. |

**Gate before S0:** roadmap Phase 4 done. The local product has to be
something people would use for free before it's something with an account
attached.

---

## 7. What does not change

True in every tier. Any proposal that breaks one of these is a different
product, not a version of this one.

1. **Audio never leaves the device.** Not for training, not for quality, not
   for debugging.
2. **The fast path works offline** after sign-in, within the grace period —
   grammar and embeddings, the ~85%. Not "everything works offline"; state
   the limit rather than overclaiming (ADR 0001).
3. **Confirmation gating is not a setting.** Delete/send/spend/overwrite
   speaks its intent and blocks on a human, in both venues.
4. **Cloud agents cannot touch the local machine.** They propose; the desktop
   confirms and executes.
5. **The free tier stays genuinely useful.** Crippling it to sell Pro
   destroys the credibility that is the entire differentiator.
6. **Nothing in the user's data is readable by the server** except what they
   explicitly send to a cloud tool.
7. **The audit log is complete and exportable**, covering local and cloud
   actions alike.

---

## 8. Open decisions

Real forks, not rhetorical ones. Each needs an owner and a date before S0.

- **Licence model.** [`docs/LICENSING-AUDIT.md`](../docs/LICENSING-AUDIT.md)
  still lists this as open, and SaaS sharpens it: **open-core** (engine under
  AGPL-3.0, cloud + Indic + Office layers proprietary) makes "audit the
  privacy claim yourself" literally checkable and is the stronger story here;
  fully proprietary is simpler but forces the privacy claim to be taken on
  trust — which is exactly what this product argues against.
- **Pricing.** Credit-metered vs flat-rate Pro; INR-first vs USD-first; what
  a student/individual tier costs in India specifically.
- **Cloud model provider.** Own inference vs API providers. API first,
  obviously — but the margin math in §5 eventually forces the question, and
  ADR 0001 makes it more urgent: cloud is now the *default* escalation
  target, so its cost is on the critical path rather than an edge case.
- **~~Whether the local 3B is the default escalation target.~~ Resolved** by
  [ADR 0001](../docs/decisions/0001-local-llm-off-the-default-path.md) — it
  isn't. Left here as a pointer because it changes §5's economics: more
  escalations reach paid infrastructure than the original architecture
  assumed. Re-check the free-tier credit allowance against real escalation
  rates once Phase 2 telemetry exists.
- **Whether the free tier gets any cloud escalation at all.** ADR 0001 makes
  this sharper. BYO-key covers technical users; a non-technical free user with
  no API key now has *no* escalation path unless they enable the local model.
  Options: a small monthly free credit allowance, a "bring a key or enable the
  local model" prompt at onboarding, or accepting that free = fast path only.
- **Whether the free tier truly requires an account.** Genuinely contested:
  mandatory sign-in for a local-first tool will lose some of exactly the
  privacy-motivated users this is for. Consider a "local-only, no account"
  mode that trades away sync and cloud entirely — it costs little and defuses
  the loudest objection.
- **Where cloud agents' credentials live** when acting on a user's behalf
  (Gmail, Drive). Delegated OAuth with narrow scopes, plus a hard answer to
  "what can a compromised agent runtime read."
- **Self-hosted tier** — real demand or a distraction? It's the only version
  procurement at a regulated company can buy.

---

## 9. New risks this creates

To be merged into [`docs/RISK-REGISTER.md`](../docs/RISK-REGISTER.md) if any of
this gets scheduled.

| Risk | Likelihood | Why it matters here specifically |
|---|---|---|
| Multi-tenant isolation break in the agent runtime | Medium | Agents execute tools with side effects, not just generate text |
| Prompt injection escalating across tenants | Medium | The runtime is a shared surface a single laptop never had |
| Runaway job cost | High | An agent loop is a bill; needs hard caps, not alerts |
| "Local-first" claim erodes feature by feature | High | Each individual cloud convenience is defensible; the tenth one isn't |
| Recurring-payment failure in India (e-mandate) | High | Involuntary churn from mandate failures is a known, large tax |
| Auth or payment provider outage | Medium | Must not take the *local* app down — offline grace is the mitigation |
| DPDP / GDPR non-compliance | Medium | Fines aside, this product's whole pitch is privacy competence |

---

## 10. Beyond the buildout — the speculative list

Kept from the earlier version of this document, because a future-scope file
containing only safe extrapolations isn't doing its job. Several of these get
*better* with an account and a cloud tier behind them.

- **Supervised internet action, not just lookup.** Filling a form, comparing
  prices, checking a shipment — under the same confirm gate. Needs its own
  tier above `net` (call it `browse`) with its own allowlist and audit trail.
  This is the natural home for cloud agents: the risky browsing happens in a
  disposable sandbox, not on your laptop.
- **Cowork mode.** A standing session — "sit with me while I clear my inbox"
  — holding working context across many turns, proposing a plan up front,
  narrating progress. A standing session is not standing permission.
- **Screen-aware.** Resolving "no, not that one, the one on the right" from
  what's actually on screen. Stays local — a screenshot is the most sensitive
  thing on the machine.
- **A personal knowledge graph** built from months of ordinary use, entirely
  local, exportable as a plain file, with "show me everything you know about
  X" as a first-class command rather than a settings page.
- **Voice-native skill authoring.** "When I say 'end of day,' save my open
  files, email my status update, and lock the screen" — a macro defined by
  describing it once, out loud, in any of three languages. Under SaaS these
  become the shareable unit (§3.K) and a real reason to have an account.
- **Specialist sub-agents.** An inbox agent, a research agent, a scheduling
  agent, sharing one tool registry, one undo stack, one confirm gate — a
  small office rather than a single assistant, behind a single trust
  boundary. Cloud is where this stops being a memory-budget problem.
- **A trust ladder, not a trust cliff.** Autonomy earned per-machine through
  demonstrated reliability, fully visible, reversible with one sentence.
- **Meetings as a first-class surface.** Local transcription of a call
  turning "let's have Priya send that by Friday" into a drafted follow-up.
  COM automation into a *running* Outlook is a moat a cloud-only competitor
  structurally cannot cross.
- **Community-taught router, without a company in the middle.** Opt-in,
  anonymized, phrasings-only exchange so regional Hindi and Gujarati
  phrasings converge faster for everyone. Federated; default off.
- **Cross-lingual live interpretation.** The multilingual encoder and Indic
  TTS already have to exist for routing; pointed at a two-person call, the
  same parts become real-time en↔hi↔gu interpretation.
- **A morning brief, spoken.** Calendar, overnight email, and yesterday's
  loose ends as a two-minute spoken brief at an opt-in time — a natural first
  scheduled cloud agent.
- **A dedicated hardware puck.** A cheap microphone/speaker for rooms without
  a laptop; all intelligence stays on the paired machine, so the puck holds
  nothing worth stealing.
- **A full audit export of its own life.** One command, one human-readable
  file, everything it has ever done. Not a settings feature — a statement.

---

*If an idea from this document ever gets scheduled, it graduates to
[`docs/ROADMAP.md`](../docs/ROADMAP.md) with a real phase number and a real
deliverable. Until then it stays here — visible, and clearly not a promise.*
