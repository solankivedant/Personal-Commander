# ADR 0001 — The local LLM comes off the default path

**Date:** 2026-09-04
**Status:** Accepted
**Supersedes:** the "escalate to the local 3B" step as described in
`munshiji-full-report.md` §3.2 L4 and the original cascade in
`.claude/rules/architecture-and-router.md`

---

## Context

The architecture has always said the LLM is not the primary reasoning path —
grammar and embeddings handle ~85% of commands in under 20ms, and only
genuinely compositional requests escalate to a local 3B model. That part
holds and is not in question here.

What was never examined is whether the *escalation target itself* is worth
having on the default path. Two things forced the question:

### 1. The Phase 0 benchmark measured the wrong workload

[`PHASE-0-RESULTS.md`](../PHASE-0-RESULTS.md) recorded **11.3 tok/s median**
for `qwen2.5:3b-instruct-q4_K_M` on the target machine and marked the gate
passed. But the same document notes the caveat plainly: *"Each generation was
short (4-6 tokens) because the benchmark prompt asks for a single tool
name."*

11.3 tok/s is **~88ms per token**. Extrapolated — and this is extrapolation,
not measurement:

| Output | Tokens | Decode time |
|---|---|---|
| Single tool name (what was benchmarked) | 4–6 | ~0.5s |
| Full tool-call JSON with arguments | ~50 | ~4.4s |
| One spoken sentence | ~40 | ~3.5s |
| A short paragraph | ~120 | ~10.6s |

The gate was cleared by a benchmark that never produced a realistic output
length. The 4.5s LLM-path budget in the rules is achievable for tool-call
JSON and nothing else.

### 2. Two different jobs were conflated under "the LLM"

- **Compositional command parsing** — turning *"move the PDFs from downloads
  into the invoices folder"* into tool calls when grammar and embeddings both
  miss. Short structured output. Genuinely within a 3B model's ability.
- **Knowledge question answering** — *"what's the GST rate on this,"*
  *"explain what this error means,"* *"draft a reply to this."* Long output,
  and a 3B model's factual reliability is poor.

The second job is **slow and wrong simultaneously** — ~10s to produce an
answer that may be confidently false. That is the worst possible combination
for a voice product, where the user cannot skim and has no visible source to
check.

There is currently **no route for knowledge questions anywhere in the
codebase** — `config/intents/` has none, the router has none. Today such a
question would fall through the cascade and land on exactly this path.

### 3. A contradiction in the existing prompt-assembly rules

The router rules require both of the following, and they cancel each other
out:

> Order must always be: system prompt → tool schemas → *then* volatile
> context (time, active window, recent turns) last.

> Retrieve top 8–12 relevant tools per query by embedding similarity, not the
> full registry.

If the tool schemas sit early in the prompt *and* change per query, the KV
cache is invalidated on nearly every request — only the system prompt stays
warm. The prefill cost the ordering rule exists to avoid is paid anyway.

---

## Decision

**The local LLM is removed from the default path.** It becomes an opt-in
privacy mode (`llm.enabled: false` by default in `config/default.yaml`),
not the standard escalation target.

The cascade becomes:

1. **Grammar** (hassil) — <10ms, unchanged
2. **Embeddings** (multilingual-e5-small) — <20ms, unchanged
3. **Escalation**, per `router.escalation` — an ordered list, default
   `[cloud]`:
   - `cloud` — opt-in, spoken-confirm gated, for compositional commands and
     knowledge questions alike
   - `local` — the 3B model, for users who enable it and accept the latency
     in exchange for never leaving the machine
   - empty — no escalation; go straight to teach mode
4. **Teach mode** — unchanged, and now the honest offline answer

**Knowledge questions become an explicit route**, classified by the embedding
layer (a question is not a command — that's a 20ms decision, not a 10s one)
and answered by cloud, or refused honestly when offline: *"I can't answer
that without the internet."* A wrong answer delivered slowly is worse than no
answer delivered instantly.

### Prompt assembly, corrected

For whichever escalation target is in use, the cached prefix holds a **stable
core tool set**; per-query retrieved tools go *after* the volatile boundary.
Slightly worse tool ordering in exchange for a KV cache that actually
survives a request.

---

## Consequences

### Good

- **The default install gets faster and smaller.** No Ollama dependency, no
  1.9GB of weights, ~2GB less RAM in the working set. First-run download
  drops substantially, which matters on Indian bandwidth.
- **No path in the product is both slow and unreliable.** Every route is
  either fast and deterministic (grammar/embeddings), or slow and good
  (cloud), or honest (teach mode / "I can't do that offline").
- **Phase 2's deliverable is unchanged and now literally true** — *"genuinely
  useful daily driver, no LLM required."*
- **The cloud tier's justification becomes honest.** It's not an upsell
  bolted onto a complete product; it's the answer to a real limitation the
  local engine has. See [`../../future-scope.md`](../../future-scope.md) §2.
- **Licensing simplifies.** One less model family to audit and one less
  weights download to gate at first run.

### Bad — and accepted

- **Offline compositional commands regress to teach mode.** With no network
  and no local LLM, *"move the PDFs from downloads to invoices"* fails to
  teach mode rather than being parsed. Mitigation: this is exactly the
  pressure that should push coverage into grammar and embeddings, which is
  where the architecture always wanted it. Teach mode makes the second
  attempt work.
- **The pure-offline story weakens for users who don't enable the local
  model.** Accepted deliberately: the fast path — the ~85% — still works with
  the network off. It is not "offline for everything," and the marketing must
  not claim otherwise.
- **Privacy-absolutist users must opt in and accept ~4.4s.** Better than
  imposing it on everyone by default.

### Neutral

- Phase 4 doesn't disappear, it re-scopes: the orchestrator, bounded loop,
  dry-run summarization, and tool subsetting are all still needed — they now
  sit in front of a pluggable escalation target rather than hardcoded Ollama.

---

## What this does not change

- Grammar → embeddings ordering, thresholds, and the sub-20ms fast path.
- The golden test set and its gates. Escalation cases need their own entries.
- Every security invariant. A cloud escalation is still spoken-confirm
  gated, still cannot be triggered directly by a tool result, and still
  never sends audio.
- `network.mode: local_only` still hard-removes every `net`-tier tool — and
  in that mode `local` is the only escalation target available.

---

## Follow-ups

- [ ] Re-run the LLM benchmark at realistic output lengths (50 and 150
      tokens) so the opt-in mode's latency claim is measured rather than
      extrapolated from a 4–6 token run.
- [ ] Test constrained decoding (GBNF / outlines) for the opt-in local path —
      forcing valid tool-call JSON cuts output tokens and removes the
      malformed-JSON retry the rules currently budget for. A constrained 1.5B
      likely beats an unconstrained 3B at this specific job.
- [ ] Add knowledge-question examples to the embedding index so the
      "question, not command" classification is a fast-path decision.
- [ ] Add golden-set entries for the offline-refusal case.
