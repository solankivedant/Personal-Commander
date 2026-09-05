# Architecture & router rules

Source: `munshiji-full-report.md` §3, §9. Full layer detail lives in
`docs/ARCHITECTURE.md` — this file is the set of rules that follow from it.

## The router is the product

`router/` (L3) is the layer that defines this product — everything else is
either integrating a maintained open-source component or wiring Windows APIs.
Cascade order, first match wins:

1. **Grammar** (`router/grammar.py`, hassil) — deterministic YAML templates,
   <10ms, zero RAM. ~50% of daily commands.
2. **Embeddings** (`router/embeddings.py`, multilingual-e5-small) — cosine
   nearest-neighbour at `router.embeddings.threshold` against per-intent
   example utterances. ~35% of commands, and generalizes across en/hi/gu
   because the encoder is multilingual — one example set often covers three
   languages.

   **The threshold is 0.88, not the report's 0.75, and that is measured, not
   preference** (`docs/PHASE-2-RESULTS.md`). e5 is contrastively trained and
   its cosine range is compressed: *unrelated* utterances score 0.78–0.93
   against this index, so at 0.75 the cascade never reached teach mode at
   all — 0 of 18 out-of-domain utterances were refused, and "call my mother"
   resolved to `restart`. It is a property of this encoder's score
   distribution, so re-run `tests/golden/out_of_domain.yaml` and the sweep in
   PHASE-2-RESULTS if the encoder ever changes. Do not tune it down to catch
   one stubborn utterance — add an example instead.

   **An embedding match is evidence about the intent, never about the
   arguments.** The nearest example's stored args describe a *different*
   sentence, so `enrich_slots(..., args_from_example=True)` re-derives every
   re-derivable slot from the actual utterance and drops an `app` the
   utterance doesn't name. Inheriting them shipped "excel kholo" opening
   Chrome and "wifi ko off kar do" turning wifi on.
3. **Escalation** (`router.escalation` in config, default `[cloud]`) — an
   ordered list of targets tried only if both above fail:
   - `cloud` (`brain/cloud.py`) — opt-in, spoken-confirm gated. Handles
     compositional commands *and* knowledge questions.
   - `local` (`brain/ollama.py`) — the 3B model. **Off by default**
     (`llm.enabled: false`); an opt-in privacy mode for users who accept
     ~4.4s in exchange for nothing leaving the machine.
   - empty — no escalation, straight to teach mode.
4. **Teach mode** (`router/teach.py`) — if escalation is disabled, offline, or
   also fails, ask the user what to do and append the utterance to an intent's
   examples. Escalation rate should decline over time; if it isn't, that's a
   signal the grammar/embedding layers need more examples, not that escalation
   needs to be invoked more.

**The local LLM is not the default escalation target** — see
[`docs/decisions/0001-local-llm-off-the-default-path.md`](../../docs/decisions/0001-local-llm-off-the-default-path.md).
At the measured 11.3 tok/s (~88ms/token) a realistic tool-call JSON costs
~4.4s and a paragraph answer ~10.6s, and a 3B model's factual reliability
makes the latter slow *and* wrong. Do not move it back onto the default path
without re-running the benchmark at realistic output lengths.

**Knowledge questions are a route, not an LLM fallback.** "What's the GST rate
on this" is not a command and has no tool. The embedding layer classifies
question-vs-command in <20ms; the answer comes from cloud, or from an honest
refusal when offline ("I can't answer that without the internet"). Never
answer a factual question from the local 3B — a wrong answer delivered slowly
is worse than no answer delivered instantly.

Do not add a shortcut that skips grammar/embeddings and goes straight to
escalation for convenience during development — it hides regressions the
golden test set exists to catch.

## Prompt assembly is load-bearing (§3.2 L4, §9.2)

Ollama caches the KV state of a stable prefix. Order must always be: system
prompt → **stable core tool schemas** → *then* volatile context (per-query
retrieved tools, time, active window, recent turns) last. Changing anything
early in the prompt discards the entire cache and forces a full re-prefill —
seconds on this hardware. When touching `brain/prompt.py`, never reorder
volatile content earlier "for clarity" — it has a real latency cost.

**Note the correction here** (ADR 0001): an earlier version of this rule put
*all* tool schemas in the cached prefix while also requiring per-query tool
retrieval. Those cancel out — schemas that change every request invalidate
the cache at position 2 regardless of ordering, so the prefill cost the rule
exists to avoid was being paid anyway. The fix is the split above: a stable
core set stays cached, query-specific retrieved tools go after the volatile
boundary. Slightly worse tool ordering, a cache that actually survives.

Other L4 constraints:
- Hard cap **5 iterations** on the propose/validate/execute loop.
- Retrieve top 8–12 relevant tools per query by embedding similarity, not the
  full registry — a 3B model's tool-selection accuracy falls off sharply past
  ~15 options in context. These go in the volatile tail, per the split above.
- Prefer **constrained decoding** (GBNF/outlines) over free-form generation
  for tool calls on the opt-in local path — it cuts output tokens and removes
  the malformed-JSON retry below entirely.
- History: 3–5 turns maximum. Long histories confuse small models.
- One retry on malformed JSON with a repair prompt, then fail to teach mode —
  don't retry silently forever.

## Tool registry contract (§3.2 L5)

Every tool carries three orthogonal attributes — see
`security-and-privacy.md` for the rules governing their values:

```python
@tool(tier="local", risk="confirm", tags=["files"])
def move_files(source_dir: str, pattern: str, dest_dir: str) -> str:
    """Move files matching a glob pattern from one folder to another."""
```

Schema is auto-generated from type hints and the docstring — keep both accurate,
they're not just documentation, they're what the LLM sees.

## Memory tiers (§3.2 L7)

Three genuinely distinct tiers — don't collapse them:

| Tier | Store | TTL |
|---|---|---|
| Conversation | in-memory ring, 3–5 turns | session |
| Working state | dict (last file, last app, last result) | session |
| Long-term | SQLite + Chroma | permanent |

Working state is what makes "open it" and "send that to him" resolve — if a
feature needs pronoun/reference resolution, it belongs there, not in the
conversation ring.

## Performance discipline (§9)

- No CUDA on the target hardware — never add a code path, dependency, or
  tutorial-derived pattern that assumes a discrete GPU.
- Keep models warm: `OLLAMA_KEEP_ALIVE=-1`, construct Whisper once at boot, never
  reconstruct per-request.
- VAD silence threshold stays in the 280–320ms band — below ~250ms cuts users
  off mid-thought, above ~500ms adds needless perceived latency.
- Stream everything: ASR during speech, TTS per sentence. Perceived latency is
  time-to-first-audio, not time-to-complete.
- Target latency budget (§9.3): fast path ≈950ms end-to-end, LLM path ≈4.5s.
  Treat regressions against `tests/test_latency.py` as bugs, not noise.

## Cross-cutting

- Layers communicate through the event bus (`bus.py`), not direct calls between
  arbitrary modules — this is what keeps the GUI, audit log, and HTTP API pure
  subscribers instead of coupled to internals.
