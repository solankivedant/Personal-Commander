# Future Scope

**This is not the roadmap.** `docs/ROADMAP.md` is the committed plan - Phase
0 through 9, each with a concrete deliverable, and CI holds the codebase to
it. This document is the opposite kind of thing on purpose: speculative,
unranked, unscheduled ideas about what Munshiji could become once that
roadmap is done. Nothing here is promised. Some of it may turn out to be a
bad idea on closer look. It's collected here, in one place, instead of
scattered across issues, so the ambition is visible without being mistaken
for a commitment.

Everything below is written to be consistent with the rules that already
govern this codebase (`.claude/rules/`), not an excuse to break them later.
Local-first stays the default. Confirmation gating stays non-negotiable.
Nothing here proposes sending audio off the device, ever - the ideas that
touch the network are opt-in extensions to what already exists
(`config/default.yaml`'s `cloud:` and `network:` sections), not a reversal of
the architecture.

---

## 1. Bring-your-own-key cloud escalation

The config already has the hook: `cloud.enabled` and `cloud.escalate:
never|ask|auto`. The natural extension is letting a user drop in their own
API key (Anthropic, OpenAI, whoever) for the rare request that's genuinely
beyond a local 3B model - a complex multi-document synthesis, a long-form
draft, a hard reasoning problem - while every default stays local. The key
lives in Windows Credential Manager next to the Google OAuth tokens
(`.claude/rules/security-and-privacy.md` already specifies this pattern for
secrets), never in a config file, never transmitted anywhere except directly
to the provider the user chose. Escalating to a cloud model would speak that
intent out loud before it happens ("this needs a bigger model - send it to
Claude?") the same way a confirm-risk tool does, not silently upgrade
mid-request.

## 2. Supervised internet action, not just internet lookup

Today's roadmap gives Munshiji `net`-tier read access: search, weather,
Gmail. The genuinely useful next step is *acting* on the open internet under
the same confirm-gate discipline files and email already get: filling a
form, comparing prices across a few sites, checking a shipment, booking
something. This is a materially bigger attack surface (prompt injection from
a malicious page is the primary threat model in this repo for a reason), so
it would need its own tier above `net` - call it `browse` - with its own
allowlist discipline, its own audit trail, and a hard rule that a page's
content can suggest a next step but never itself trigger a confirm-gated
action. The payoff is real: "find me a flight under 15k next weekend and
hold it" is the kind of request that makes an assistant feel like staff, not
a toy.

## 3. Cowork mode: a standing session, not a single command

Every tool in this repo answers one utterance at a time. The bigger idea is
a *session* - "help me get through this backlog," "sit with me while I clear
my inbox" - where Munshiji holds working context across many turns, proposes
a plan up front (dry-run, same pattern as the multi-step LLM plans in
`brain/loop.py`'s design), and narrates progress as it goes rather than
waiting to be re-invoked for every step. Less "voice command line," more
"someone sitting next to you who happens to only have hands, not judgement
you haven't already approved." The stopping condition is the same
confirm-gate logic already in place - a standing session doesn't mean
standing permission.

## 4. Screen-aware, not just file-aware

Phase 7 already plans `moondream` for screen understanding. Taken further:
Munshiji glancing at what's actually on screen to resolve "no, not that one,
the one on the right" or "summarize this" without needing the content piped
in some other way. This is the single highest-leverage way to make voice
control feel native to a GUI-first OS instead of a workaround for one - and
it's exactly the kind of untrusted-content surface the prompt-injection
rules already exist to handle (a screenshot of a malicious page is still
untrusted content, delimiter-wrapped like any other).

## 5. A personal knowledge graph, built from just living with it

`memory/facts.py` and `memory/documents.py` are already scoped for Phase 7.
The speculative extension: over months of "remind me what I told the
plumber," "what was that restaurant Priya mentioned," Munshiji accumulates a
real, queryable graph of the user's own life - entirely local, entirely
theirs, exportable as a plain file, deletable with one command. Not a
product feature so much as what naturally falls out of a voice assistant
that's actually good at its job for long enough. The interesting design
constraint is making the whole graph legible and auditable to the person it's
about - a "show me everything you know about X" command isn't a nice-to-have
here, it's the thing that keeps this from becoming creepy.

## 6. Teach mode, evolved into voice-native skill authoring

Teach mode already appends unmatched utterances to the router's examples.
The next step up: "when I say 'end of day,' save my open files, email my
status update, and lock the screen" - defining a whole macro by describing
it once, out loud, no config file, no code. This is Munshiji's own version
of a scripting language, except the syntax is spoken English (or Hindi, or
Gujarati) and the compiler is the router plus a confirmation step ("so every
time you say 'end of day,' I should - is that right?"). Power users get
programmability without ever opening a text editor.

## 7. Delegation to specialist sub-agents

Not every request needs the same model or the same tool subset. A research
question, a finance question, and a "draft this email in my voice" request
are different jobs. A longer-term architecture could route genuinely
complex, multi-domain requests to specialist sub-agents (an inbox agent, a
research agent, a scheduling agent) that share the same tool registry,
undo stack, and confirm gate, coordinated by the same router that already
exists - more like a small office than a single assistant, without giving up
the single trust boundary a user actually deals with.

## 8. A trust ladder, not a trust cliff

Right now a tool is `safe`, `confirm`, or `blocked` - fixed at build time.
The more interesting long-run model: a user's own assistant earns broader
defaults over time, visibly and reversibly. Maybe after 20 correctly-executed
file moves, "move the usual downloads" stops asking every single time - but
the ladder only ever goes up by demonstrated reliability on *that specific
user's machine*, is fully visible ("here's what I've stopped asking about and
why"), and one sentence ("be more careful again") puts it right back down.
Autonomy as something earned and inspectable, not a permissions dialog
clicked through once and forgotten.

## 9. Beyond the desktop: a physical bridge

`tools/phone.py`'s KDE Connect bridge is the first crack in the door.
Further out: the same voice, the same router, the same confirm discipline
extended to actual smart-home devices, a dedicated low-power always-listening
puck for rooms without a laptop open, or a car head-unit integration for
"read me that email" on the drive in. None of this needs a different
assistant - it needs the existing one with more `tier: lan` tools and a
speaker who knows which room they're in.

## 10. Meetings as a first-class surface

Munshiji sitting in on a call (locally - transcribing audio it's already
capturing, never uploading it) and turning "let's have Priya send that by
Friday" into an actual drafted follow-up email, or "add that to the roadmap"
into an actual roadmap edit, with the same review-before-send discipline as
everything else. The moat here is the same one `tools/office.py` already
banks on: COM automation into a *running* Office/Outlook instance is a level
of integration a purely cloud-based competitor structurally cannot match
without your credentials.

## 11. Community-taught router, without a community server

Teach mode makes one person's Munshiji faster with use. The speculative
extension is doing that *across* users without breaking the local-first
promise: an opt-in, anonymized, peer-to-peer exchange of router
examples-only (never transcripts, never documents, never anything with
content in it, just "this phrasing means this intent") so that "avaaj kam
karo"-style regional phrasings converge faster for everyone, with no company
in the middle collecting anything. Federated, opt-in, and the default stays
off.

---

## Further out still - the "beyond imagination" list

Genuinely speculative, in the sense that nobody should hold this repo to any
of it. Written down because a few of them might be worth the first
experiment someday, and because a future-scope document that only contains
safe, obvious extrapolations of the current roadmap isn't doing its job.

- **A full audit export of its own life.** One command produces a complete,
  human-readable log of everything Munshiji has ever done on this machine -
  every tool call, every confirmation, every undo - as a single file the
  user owns outright. Not a settings-page feature; a statement that nothing
  it does is meant to be opaque even to the person running it.
- **Tone-aware pacing.** Kokoro/IndicTTS already stream sentence-by-sentence.
  A local, opt-in signal from voice stress or cadence that slows the
  assistant down, shortens its answers, and stops offering suggestions when
  the user sounds rushed or frustrated - the same instinct a good assistant
  has, running entirely on-device, never logged.
- **A dedicated hardware companion.** A small, cheap, dumb microphone/speaker
  puck for rooms without a laptop - all the intelligence still runs on the
  one machine it's paired to over the LAN, so the puck itself has nothing
  worth stealing and nothing worth a subscription.
- **Cross-lingual live interpretation.** The multilingual embedding layer
  and Indic TTS already exist for routing; pointed at a live two-person call
  instead of a command, the same pipeline becomes real-time interpretation
  between English, Hindi, and Gujarati speakers - a very different feature
  built from parts that already have to exist anyway.
- **A morning brief, spoken, no request required.** At an opt-in scheduled
  time, Munshiji synthesizes calendar, overnight email, and yesterday's
  unfinished undo-stack items into a two-minute spoken brief - not a
  dashboard nobody opens, a thing that talks to you once and then gets out
  of the way.
- **Skills as a spoken trade, not a marketplace.** Extending the peer-to-peer
  router-sharing idea (#11) to whole taught macros (#6): a user who taught
  their Munshiji a genuinely good "close out the week" routine can export it
  as a file and hand it to a friend - no app store, no review process, no
  server, just a file that says what it does and asks before it does
  anything unfamiliar on the new machine.
- **The assistant that reads its own risk register.** A reflective loop
  where Munshiji itself flags when a new taught macro or a newly-confirmed
  habit is drifting toward something `docs/RISK-REGISTER.md`-shaped, and
  says so out loud before it becomes a problem instead of after.

---

*If an idea from this list ever gets scheduled, it graduates to
`docs/ROADMAP.md` with a real phase number and a real deliverable. Until
then, it stays here - visible, and clearly not a promise.*
