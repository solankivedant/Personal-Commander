# Market gaps — where Munshiji fits and why nobody has filled it

Companion to [`future-scope.md`](future-scope.md), which describes what
the product could become. **This document is the argument for why it should
exist at all**: the specific, named holes in the current market, who feels
each one, why the incumbents have not closed it, and what Munshiji would have
to ship to close it.

Two honesty rules for this file:

1. **Every gap gets a "why hasn't someone done it" line.** A gap nobody has
   filled is usually either genuinely hard, structurally impossible for the
   incumbents, or not actually a gap. If the answer is "nobody thought of
   it," the gap is probably fake.
2. **Market figures are marked `[verify]` until sourced.** Nothing in this
   file should be quoted at an investor or on the landing page until the
   number behind it has a citation. §9 lists what needs verifying.

---

## 1. The map — four quadrants, one empty

Position every competitor on two axes: **does it actually do things on your
machine**, and **does it run locally**.

```
                    ACTS ON THE MACHINE
                            ▲
                            │
   Open Interpreter         │        (empty)
   AutoHotkey / PowerToys   │
   Windows Voice Access     │   ←── Munshiji targets here
   UI-automation agents     │
                            │
  LOCAL ◄─────────────────── ───────────────────► CLOUD
                            │
   Ollama + a chat UI       │   ChatGPT / Claude desktop
   LM Studio                │   Microsoft 365 Copilot
   Local Whisper dictation  │   Gemini, Alexa+, Siri
                            │   Wispr Flow, Superwhisper
                            │
                        JUST TALKS
```

- **Bottom-left (local, talks):** solved and commoditized. Running a model
  locally is a download now.
- **Bottom-right (cloud, talks):** the most contested market on earth. Do not
  compete here.
- **Top-left (local, acts):** exists but is *developer tooling* — scripts,
  hotkeys, terminal agents. No voice, no Indic, no confirmation discipline,
  no non-technical user.
- **Top-right (cloud, acts):** growing, and structurally limited — a cloud
  agent cannot see your unsaved Excel file or your local folders without
  shipping them to a server first.

**The empty quadrant is "acts on the machine, runs locally, usable by someone
who is not a programmer, in their own language."** That is the whole thesis.

---

## 2. The gaps, ranked

Ranked by *wedge quality*: how sharply the pain is felt, how badly served it
is today, and how hard it is for an incumbent to copy.

---

### GAP 1 — Windows has no assistant that actually operates Windows

**What's missing.** Cortana was retired. Windows Copilot is a sidebar chat
that can toggle a handful of settings and otherwise answers questions. Voice
Access is a literal command mapper — "click Start" — with no intent
understanding at all. Between "a chatbot in a panel" and "write an
AutoHotkey script" there is nothing.

**Who feels it.** Anyone whose work is 40 small mechanical operations a day:
renaming and filing downloads, pulling a number out of a spreadsheet,
attaching the right PDF to the right email, opening the same six apps every
morning.

**Why hasn't someone done it.** Microsoft's incentive is to route you to
M365 and Azure, not to make the OS itself agentic — and their liability
appetite for an assistant with filesystem write access at Windows install
base scale is very low. Startups avoid it because Windows integration work
(COM, pywin32, UI Automation, per-app quirks) is unglamorous, slow, and
doesn't demo well on Twitter.

**What Munshiji ships.** L5 tools over pywin32/pycaw/psutil/win32com, behind
the L3 router — the layers in [`docs/ARCHITECTURE.md`](../docs/ARCHITECTURE.md).
This is the roadmap's Phase 2–5 and it *is* the product.

**Moat durability.** Medium. Microsoft could do this and it would hurt. The
defence is speed, Indic, and being the option for people who won't or can't
send their machine's contents to a cloud.

---

### GAP 2 — Indic voice exists as an API, not as a product anyone uses

**What's missing.** India has genuinely good Indic speech and language
infrastructure — AI4Bharat's models, Bhashini, Sarvam, Krutrim, and a
handful of B2B voice vendors. Almost all of it is sold as an **API to other
businesses**, or shows up in call-centre IVR. There is no consumer desktop
product where a person speaks Hindi or Gujarati to their laptop and the
laptop does the thing.

**Who feels it.** The very large population that operates a computer
competently but composes thought in Hindi/Gujarati/Marathi, not English —
shopkeepers, distributors, clinic staff, small-firm accountants, field
sales, anyone in a tier-2/3 town running a business on a Windows laptop.

**Why hasn't someone done it.** The global players optimize for English
first and treat Indic as a localization ticket. The Indian AI companies
found faster revenue selling APIs and enterprise contracts than building a
consumer desktop app with support costs. And desktop distribution in India
is genuinely hard.

**What Munshiji ships.** The architectural point from
[`CLAUDE.md`](../CLAUDE.md): a **multilingual sentence encoder puts Hindi and
Gujarati phrasings in the same vector space as English examples**, so the
fast non-LLM path is *more* accurate in Indic languages, not less. One
example set covers three languages. That's not a localization pass bolted
on — the language layer is load-bearing in the routing architecture.

**Moat durability.** **High.** This is the gap that ages best. The Indic
example sets, the Hinglish handling, and the golden test set across en/hi/gu
compound with every user. A global competitor adding Hindi later starts from
zero on exactly the asset that takes longest to build.

---

### GAP 3 — Code-mixed speech (Hinglish) breaks every shipped assistant

**What's missing.** Real Indian speech is not Hindi *or* English. It is
"bhai woh **downloads folder** mein jo **invoice** hai usko **desktop** pe
move kar do" — Devanagari grammar, English nouns, sometimes Roman-script
Hindi, all in one sentence. Assistants that force a language selection get
this wrong constantly, and the failure is invisible to their English-speaking
product teams.

**Who feels it.** Effectively every urban Indian user, including ones who
would tell you they "use English."

**Why hasn't someone done it.** Code-mixing is under-represented in training
data, it's hard to benchmark, and the people building the products don't
experience the failure.

**What Munshiji ships.** Script-agnostic handling in the Indic layer, and a
golden test set that contains code-mixed utterances as first-class cases
rather than an edge-case appendix — the mandatory gate in
[`.claude/rules/engineering-standards.md`](../.claude/rules/engineering-standards.md).

**Moat durability.** High, and it's the same asset as GAP 2 compounding.

---

### GAP 4 — Voice assistants are all too slow to actually replace clicking

**What's missing.** Every cloud assistant is a 2–5 second round trip. That is
above the threshold where a person gives up and just does it by hand. The
whole category has quietly accepted latency that makes it a novelty rather
than an interface.

**Who feels it.** Everyone who tried a voice assistant for real work and
stopped after a week.

**Why hasn't someone done it.** Because they routed everything through an
LLM, which is the architecturally obvious choice and the wrong one. Once
your product is "prompt goes to model," sub-second is unreachable.

**What Munshiji ships.** The core decision in
[`.claude/rules/architecture-and-router.md`](../.claude/rules/architecture-and-router.md):
grammar match (<10ms) → embedding match (<20ms) → escalation only for
genuinely compositional requests. ~85% of commands never touch a model at all.
Target is **≈950ms end-to-end on the fast path**.

**The trap this gap sets, and how we avoided it.**
[ADR 0001](../docs/decisions/0001-local-llm-off-the-default-path.md) is worth
reading here, because the obvious way to close the remaining 15% was a local
3B — and it would have reintroduced exactly the latency this gap is about
(~4.4s for a tool call, ~10.6s for a paragraph, at 11.3 tok/s). Beating cloud
assistants on the fast path while shipping a *slower-than-cloud* slow path
would have surrendered the differentiator on the very requests users
remember. Escalation goes to cloud; local stays opt-in.

**Moat durability.** Low as a secret, high as an execution asset — anyone can
copy the idea, few will do the unglamorous grammar and example-curation work
that makes it hold up across three languages, and fewer still will resist
putting a model back on the default path when coverage gets hard.

---

### GAP 5 — Nobody can automate a *running* Office application

**What's missing.** M365 Copilot works on files in the Microsoft cloud.
Google's assistant works on files in Google's cloud. Neither can touch the
Excel workbook open on your screen with three hours of unsaved changes in
it, or the Outlook profile with your firm's PST attached.

**Who feels it.** Accountants, analysts, admin staff, anyone whose real work
lives in a locally-open Office document. In India specifically: the enormous
population of businesses running desktop Office and desktop Tally, not a
cloud suite.

**Why hasn't someone done it.** A cloud product structurally cannot. COM
automation requires code executing on the same machine as the running
application. This is the single most defensible gap in the list, because it
is not a matter of effort — it's a matter of where the code runs.

**What Munshiji ships.** `tools/office.py` via `win32com` into live
Word/Excel/Outlook instances.

**Moat durability.** **Highest in this document.** A cloud-only competitor
cannot cross this line without shipping a local agent — at which point
they're building Munshiji.

---

### GAP 6 — The price gap in India is an order of magnitude

**What's missing.** Per-seat AI assistant pricing is set in dollars for
Western enterprise budgets. `[verify]` M365 Copilot's list price has been
around US$30/user/month — roughly ₹2,500 — on top of an existing M365
licence. For an Indian small business with four staff, that is not an
expensive product; it is a non-product.

**Who feels it.** The entire Indian SMB market, students, individual
professionals, and the price-sensitive tier-2/3 market that will define
volume.

**Why hasn't someone done it.** Cloud-only assistants have real per-query
marginal cost. They cannot price at ₹300/month without losing money on their
heaviest users, so they don't try.

**What Munshiji ships.** The economic asymmetry in
[`future-scope.md`](future-scope.md) §5: **local inference means the
free tier's marginal cost is approximately zero.** The user's laptop, the
user's electricity. That makes a genuinely generous free tier sustainable and
a low-priced paid tier viable — and it's a cost structure a cloud-only
competitor cannot match at any price.

**Moat durability.** High, because it's structural rather than strategic.

---

### GAP 7 — Regulated, air-gapped, and privacy-bound organisations have nothing

**What's missing.** Defence, banking, hospitals, law firms, government
departments, and any company with a client-confidentiality clause cannot put
documents through a third-party cloud model. Their available options are
"no AI assistant" or "an AI assistant we're technically not allowed to use."

**Who feels it.** IT and compliance functions who keep saying no, and the
staff working around them with personal ChatGPT accounts — which is the
actual current state and a live data-leak problem.

**Why hasn't someone done it.** The cloud vendors' entire architecture is the
disqualifier. On-prem LLM deployments exist but are infrastructure projects,
not a thing an individual can install.

**What Munshiji ships.** `network.mode: local_only` **hard-removing every
`net`-tier tool from the registry** — a verifiable claim, not a policy
promise — plus the self-hosted/air-gapped tier in
[`future-scope.md`](future-scope.md) §1.2 with an offline licence file
and no telemetry.

**Moat durability.** High, and it's the segment that pays properly. Also the
segment with the longest sales cycle — treat it as a year-two motion, not a
launch wedge.

---

### GAP 8 — No assistant has a real undo stack or an inspectable audit log

**What's missing.** Across the entire agent category: if it does the wrong
thing, you find out afterwards and you fix it by hand. There is no "undo the
last thing you did," and no complete, human-readable record of what it did
and why.

**Who feels it.** Everyone who has been burned once — and after being burned
once, most people stop granting write access permanently. This is the single
biggest adoption blocker for agents that touch real files.

**Why hasn't someone done it.** Undo is hard and invisible. It doesn't demo.
Every mutating action needs an inverse registered *before* it executes, which
is a discipline you have to impose from the first tool, not retrofit at 200.

**What Munshiji ships.** The rule already in
[`.claude/rules/security-and-privacy.md`](../.claude/rules/security-and-privacy.md):
**every mutating tool registers its inverse before executing, or it isn't
done.** Plus an append-only audit log recording every action, its arguments,
its result, and *which router stage decided it*.

**Moat durability.** Medium as technology, high as positioning. "It can undo
itself and show you its work" is the thing that converts a cautious user, and
it's genuinely hard to bolt on later.

---

### GAP 9 — Voice as an accessibility interface is stuck in 2010

**What's missing.** Dragon NaturallySpeaking was the serious option and its
consumer line has been wound down; what remains is expensive, English-only,
and dictation-shaped. Screen reader users have excellent *reading* tools and
almost no *acting* tools. Nobody has combined modern ASR with an agent that
can operate the machine.

**Who feels it.** Users with motor impairments, RSI, low vision, or temporary
injury. In India, additionally: users who are computer-literate but not
keyboard-literate in English.

**Why hasn't someone done it.** Accessibility is a small, hard-to-reach
market that mainstream product teams treat as a compliance checkbox.

**What Munshiji ships.** The product as designed already is this, with two
additions: NVDA/Narrator interoperability, and push-to-talk plus wake word as
equal first-class entry points (already the case —
[`docs/ROADMAP.md`](../docs/ROADMAP.md) Phase 1 notes push-to-talk as the
reliable path while wake-word reliability is being worked).

**Moat durability.** Medium. High goodwill, real word-of-mouth, modest
revenue. Worth doing on merit; don't build the business case on it.

---

### GAP 10 — Per-app copilots don't cross app boundaries

**What's missing.** There is a copilot in Word, one in Excel, one in your
browser, one in your IDE, one in your CRM. None of them can do "take the
total from this spreadsheet, put it in the invoice template, and email it to
the client." The one thing a human assistant is *for* — moving work between
systems — is exactly what per-app copilots structurally cannot do.

**Who feels it.** Anyone whose actual job is the seams between applications:
office admins, operations staff, solo professionals.

**Why hasn't someone done it.** Each copilot is built by the company that
owns that app, and their integration surface stops at their own product
boundary. Zapier and Power Automate cross the seams but need a person to sit
down and build a flow in a GUI.

**What Munshiji ships.** A single tool registry spanning files, apps, Office,
email, and web — one router, one confirm gate, one undo stack across all of
it. Being outside all of the app vendors is the advantage here, not a
handicap.

**Moat durability.** Medium-high. Structurally unavailable to app vendors.

---

### GAP 11 — Automation still requires you to build the automation

**What's missing.** Every automation tool — Power Automate, Zapier,
AutoHotkey, Shortcuts — asks the user to *become a builder*: open a canvas,
wire nodes, test, save. The number of people willing to do that is a rounding
error next to the number who would happily *describe* what they want once.

**Who feels it.** Every non-technical user with a repetitive weekly routine
they've never automated.

**Why hasn't someone done it.** It requires natural language → reliable
executable steps, which was genuinely not possible until recently, plus a
confirmation model trustworthy enough that a spoken macro isn't terrifying.

**What Munshiji ships.** Teach mode evolved into voice-native macro authoring
(`router/teach.py` → [`future-scope.md`](future-scope.md) §10): *"when
I say 'end of day,' save my open files, email my status update, and lock the
screen"* — defined out loud, confirmed back ("so every time you say 'end of
day,' I should — is that right?"), no editor, in any of three languages.

**Moat durability.** Medium. Also the best organic growth loop the product
has (§3.K of the future scope) — a macro is a file a user can hand a friend.

---

### GAP 12 — "Offline-capable" has been abandoned as a product value

**What's missing.** Assistants assume constant connectivity. Internet in
much of India is intermittent, metered, or absent on a train, in a basement
office, at a client site, on a flight.

**Who feels it.** Field staff, travellers, tier-2/3 users, anyone on a
bad day.

**Why hasn't someone done it.** Cloud assistants would have to ship a local
model, and their whole cost and quality model is built the other way.

**What Munshiji ships.** Everything on the fast path works with the network
off — plus the **offline grace period** rule in
[`future-scope.md`](future-scope.md) §2, so a mandatory account never
becomes an assistant that bricks itself on a plane.

**The honest limit, and say it out loud.** After
[ADR 0001](../docs/decisions/0001-local-llm-off-the-default-path.md) this is
"the ~85% fast path works offline," not "everything works offline."
Compositional requests and knowledge questions need either the network or the
opt-in local model. **This gap is the one most likely to tempt an
overclaim** — resist it. "Most of what you ask works with the wifi off" is
still far more than any competitor can say, and it survives a sceptical user
actually testing it, which the stronger claim would not.

**Moat durability.** Medium, and a strong marketing demo: pull the cable
mid-demo and keep going — with commands, which is what the demo should show
anyway.

---

### GAP 13 — The Indian SMB back office has no voice layer at all

**What's missing.** `[verify]` A very large number of Indian businesses run
their books on desktop Tally, their documents in desktop Office, and their
communication on WhatsApp. There is no AI layer over that stack. Every AI
product for Indian SMBs assumes a cloud SaaS stack those businesses do not
use.

**Who feels it.** Small business owners, their accountants, and CA firms
doing GST filing season by hand.

**Why hasn't someone done it.** It requires local desktop integration with
legacy Windows software — precisely the unglamorous work everyone avoids —
plus domain knowledge of Indian compliance workflows.

**What Munshiji ships.** Not core, but the natural vertical: templates for
GST invoice prep, CA document collation, WhatsApp-for-business triage
([`future-scope.md`](future-scope.md) §3.K). Vertical packs sit on top
of the same registry.

**Moat durability.** High if it works, and it's the clearest path from
"useful tool" to "business people pay for." **Also the biggest unknown** —
validate demand before building a Tally integration.

---

### GAP 14 — Nobody has a local, user-owned memory of your own life

**What's missing.** Cloud assistants either forget everything or remember it
on their servers. The Windows Recall backlash showed the demand *and* the
trust problem simultaneously: people want an assistant with continuity, and
they do not want it held by someone else.

**Who feels it.** Long-term users of any assistant, at the exact moment they
have to re-explain context for the fifth time.

**Why hasn't someone done it.** Cloud vendors have no incentive to make
memory local and portable, and doing it locally means solving storage,
retrieval, and — hardest — making it auditable enough not to be creepy.

**What Munshiji ships.** L7 memory tiers with SQLite + Chroma, entirely
local, plus the design constraint from
[`future-scope.md`](future-scope.md) §10: **"show me everything you
know about X" as a first-class command**, and one-command export and delete.
Legibility is the feature, not the storage.

**Moat durability.** Medium-high, and it compounds per user — a two-year-old
Munshiji is meaningfully harder to switch away from than a two-day-old one.

---

### GAP 15 — Local + cloud in one product, under one trust boundary

**What's missing.** Today you choose: a local tool that can't do the hard
things, or a cloud tool that sees everything. Nobody offers one assistant
where the routine 85% never leaves the laptop and the hard 15% goes to a
cloud agent **only after saying so out loud**.

**Who feels it.** Everyone who wants both and currently runs two products.

**Why hasn't someone done it.** It's two products' worth of engineering, and
neither a local-tool company nor a cloud company has the incentive to build
the other half.

**What Munshiji ships.** The entire hybrid model in
[`future-scope.md`](future-scope.md) §2 — Local / Hybrid / Cloud
agents, one router, one tool contract, one confirm gate, and the hard rule
that **cloud agents can never touch the local machine** (they propose; the
desktop confirms and executes).

**Moat durability.** Medium-high. Hard to copy because it requires being
credibly good at both halves.

---

### GAP 16 — The NPU in millions of new laptops is doing nothing

**What's missing.** `[verify]` Copilot+ class PCs with 40+ TOPS NPUs have
been shipping since 2024, and the installed base is now substantial. Almost
no third-party software uses that silicon. There is idle, paid-for
accelerator hardware in a large and growing number of Windows laptops.

**Who feels it.** Nobody consciously — which is exactly why it's an
opportunity rather than a demand.

**Why hasn't someone done it.** The tooling (DirectML, OpenVINO, ONNX
Runtime + QNN) is fragmented and vendor-specific, and most AI products are
cloud-shaped so on-device acceleration doesn't help them.

**What Munshiji ships.** The repo is already on this path —
`asr/openvino.py` and [`docs/PHASE-0-RESULTS.md`](../docs/PHASE-0-RESULTS.md)
show Iris Xe GPU inference already beating the CPU backend substantially. An
NPU path is the same shape of work.

**Moat durability.** Low-medium as differentiation, **high as a tailwind** —
every year the target hardware gets better and the local-first argument gets
stronger without any work on our part.

---

### GAP 17 — Trust is binary everywhere; nobody offers a ladder

**What's missing.** Every agent product gives you one permissions dialog at
install and then either asks about everything forever or nothing ever again.
There's no product where autonomy is *earned*, *visible*, and *revocable in
one sentence*.

**Who feels it.** Users at both ends: those exhausted by confirmation
fatigue, and those who granted blanket access once and now feel uneasy.

**Why hasn't someone done it.** It requires per-user behavioural history and
a genuine willingness to show the user what you've stopped asking about —
which most products would rather not surface.

**What Munshiji ships.** The trust ladder in
[`future-scope.md`](future-scope.md) §10: broader defaults earned by
demonstrated reliability *on that specific machine*, fully inspectable, and
"be more careful again" puts it right back down.

**Moat durability.** Medium. Speculative, but it's the answer to the
strongest objection the product will face.

---

## 3. Gaps that look real but probably aren't

A gaps document that only lists opportunities is a pitch deck, not analysis.
These are the ones to *not* chase:

- **Dictation.** Crowded and good — Wispr Flow, Superwhisper, and Windows'
  own dictation. Munshiji should dictate well because it has the pipeline
  anyway, but dictation is not a wedge and shouldn't be marketed as one.
- **General chat.** A commodity, given away free by four trillion-dollar
  companies. Never compete here.
- **Coding agents.** Extremely well served, and a completely different user.
  Out of scope.
- **Mac.** Raycast and Shortcuts are strong, Mac users have more options, and
  the Office COM moat doesn't exist there. Windows-only is a feature, not a
  limitation — [`README.md`](../README.md) already commits to this.
- **"Local models are as good as cloud models."** They are not, and claiming
  it will get the product correctly ridiculed. The honest claim is that
  **most commands don't need a model at all**, which is a better claim
  anyway.
- **Smart home.** Home Assistant owns this, is free, and is excellent.
  Integrate with it eventually; don't compete with it.

---

## 4. Structural tailwinds

Forces that make these gaps easier to close over time, independent of
anything the product does:

- **On-device silicon keeps improving** (GAP 16) — the local-first argument
  strengthens annually for free.
- **Small models keep getting better** — the 3B class today does what a 7B
  class did not long ago, and the LLM escalation path gets cheaper and faster
  each generation.
- **Privacy regulation is tightening** — India's DPDP Act, plus the general
  direction of travel, makes "it never left the device" a procurement
  advantage rather than a nerd preference.
- **AI fatigue and trust erosion** — after enough cloud-assistant
  overreach, "auditable, local, undoable" reads as maturity rather than
  paranoia.
- **India's desktop base is not going to the cloud quickly** — desktop Office
  and desktop accounting software will be in use for a long time (GAP 13).

---

## 5. What would close the window

Honest threats, in rough order of severity:

1. **Microsoft ships a genuinely agentic Windows Copilot with real OS
   control.** They have the distribution, the OS, and Office. Mitigation:
   Indic, local-only/air-gapped, price, and being usable by people
   Microsoft's enterprise motion doesn't serve.
2. **An Indian AI company (Sarvam, Krutrim, or similar) launches a consumer
   desktop assistant.** They have the Indic models and local credibility.
   Mitigation: the Windows integration depth and the router architecture are
   the slow parts, and they're what this repo is building.
3. **A cloud assistant ships a good local agent.** Anthropic, OpenAI, or
   Google shipping a real desktop agent that runs locally would compress the
   local/cloud gap. Mitigation: Indic, Office COM, price, and offline.
4. **Local models plateau while cloud accelerates**, making the local path
   feel visibly worse. Mitigation: the router architecture is designed so
   most commands don't depend on model quality at all.
5. **Windows locks down the APIs** this depends on. Low probability, high
   impact. Worth tracking in
   [`docs/RISK-REGISTER.md`](../docs/RISK-REGISTER.md).

---

## 6. If you only chase three

The ranking above is by wedge quality; the *sequence* should be by
defensibility × reachability:

1. **GAP 2 + 3 — Indic and code-mixed voice on the desktop.** Highest
   durability, hardest to copy, largest underserved population, and it's the
   one thing no global competitor will do well soon. This is the identity of
   the product.
2. **GAP 5 — running-Office automation.** The most structurally defensible
   item in this document. A cloud competitor cannot follow.
3. **GAP 6 + 7 — the price and privacy structure.** Free-tier marginal cost
   near zero, and a verifiable `local_only` mode. These are consequences of
   the architecture rather than features to build, which makes them close to
   free to claim — provided the architecture doesn't drift
   ([`future-scope.md`](future-scope.md) §7).

GAP 1 and GAP 4 are the *table stakes* underneath all of it — without a fast
router that actually operates Windows, none of the above matters.

---

## 7. How to falsify this

Every gap here is a hypothesis. Cheapest tests, in order:

- **Ten conversations** with target users (a CA, a shop owner, a clinic
  admin, an ops person at a small firm) about what they do 20 times a day.
  If the answer isn't a list of mechanical Windows chores, GAP 1 is weaker
  than assumed.
- **A landing page with a waitlist**, split-tested on the Indic angle vs the
  privacy angle vs the speed angle. Which one converts tells you which gap
  you're actually selling into. [`landing/`](../landing/) already exists.
- **Watch someone use the Phase 2 build in Hindi** without helping them. The
  router's failure modes in real speech will be different from the golden
  test set's, and that difference is the most valuable data the project can
  get.
- **Price probe** before building billing: ask ten SMB owners what they'd pay
  per month. Do it before S4 in the SaaS sequencing, not after.

---

## 8. Cross-references

| Gap | Where it's being built | Rule that protects it |
|---|---|---|
| 1, 4 | `router/`, roadmap Phase 2–3 | `.claude/rules/architecture-and-router.md` |
| 2, 3 | Indic layer, roadmap Phase 6 | Golden test set across en/hi/gu |
| 5, 10 | `tools/office.py`, Phase 5 | Tool registry contract |
| 6 | future-scope §5 (unit economics) | future-scope §7 invariant 5 |
| 7 | `network.mode: local_only` | `.claude/rules/security-and-privacy.md` |
| 8 | Undo stack + `data/audit.jsonl` | "inverse registered before executing" |
| 11 | `router/teach.py` | Confirmation gating |
| 14 | L7 memory, Phase 7 | Local-only storage, export/delete |
| 15, 17 | future-scope §2, §10 | future-scope §7 invariants |
| 16 | `asr/openvino.py` | `docs/PHASE-0-RESULTS.md` |

---

## 9. Numbers that need sourcing before external use

Marked `[verify]` above. None of these should appear on the landing page, in
a deck, or in a funding conversation until sourced:

- [ ] M365 Copilot list price and whether an M365 licence is a prerequisite
      (GAP 6)
- [ ] Size of the Indian Windows desktop installed base, and the tier-2/3
      share (GAP 2, 12)
- [ ] Number of Indian businesses on desktop accounting software (GAP 13)
- [ ] Copilot+ PC / NPU installed base and shipment share (GAP 16)
- [ ] Current state of Dragon's consumer line and accessibility alternatives
      (GAP 9)
- [ ] Hindi/Gujarati primary-language computer-user population (GAP 2)
- [ ] Whether Bhashini/Sarvam/Krutrim have shipped anything desktop-shaped
      since this was written (GAP 2, §5 threat 2)

**This file goes stale fast.** Re-check §5 (threats) and §9 (numbers) before
using any of it in an external document.

---

*Speculative, like everything under `future-scope/`. If a gap here becomes
the reason for a scheduled piece of work, it graduates to
[`docs/ROADMAP.md`](../docs/ROADMAP.md) with a phase number and a
deliverable.*
