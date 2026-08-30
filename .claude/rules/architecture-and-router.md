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
   nearest-neighbour at threshold 0.75 against per-intent example utterances.
   ~35% of commands, and generalizes across en/hi/gu because the encoder is
   multilingual — one example set often covers three languages.
3. **LLM escalation** (`brain/`) — only if both above fail.
4. **Teach mode** (`router/teach.py`) — if the LLM is disabled or also fails,
   ask the user what to do and append the utterance to an intent's examples.
   LLM fallback rate should decline over time; if it isn't, that's a signal the
   grammar/embedding layers need more examples, not that the LLM needs to be
   invoked more.

Do not add a shortcut that skips grammar/embeddings and goes straight to the LLM
for convenience during development — it hides regressions the golden test set
exists to catch.

## Prompt assembly is load-bearing (§3.2 L4, §9.2)

Ollama caches the KV state of a stable prefix. Order must always be: system
prompt → tool schemas → *then* volatile context (time, active window, recent
turns) last. Changing anything early in the prompt discards the entire cache and
forces a full re-prefill — seconds on this hardware. When touching
`brain/prompt.py`, never reorder volatile content earlier "for clarity" — it has
a real latency cost.

Other L4 constraints:
- Hard cap **5 iterations** on the propose/validate/execute loop.
- Retrieve top 8–12 relevant tools per query by embedding similarity, not the
  full registry — a 3B model's tool-selection accuracy falls off sharply past
  ~15 options in context.
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
