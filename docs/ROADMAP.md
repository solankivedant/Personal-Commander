# Build Roadmap

Source: `munshiji-full-report.md` §11. Total estimated effort: **~560 hours**
(forking Goose instead of building the orchestrator from scratch removes
roughly 100–150h from Phases 4–5).

Check this file before starting new work — build in phase order. A phase's
**Deliverable** is its acceptance test, not just its checklist.

Status legend: `[ ]` not started · `[~]` in progress · `[x]` done

---

## Phase 0 — Spike (1 week, ~20h)

Prove the hardware works before committing to it. **Run on: Dell Inspiron 14
7430 2-in-1, i7-1355U, Iris Xe, 16GB — confirmed to match the report's target
baseline.** Full results: [`docs/PHASE-0-RESULTS.md`](PHASE-0-RESULTS.md).

- [x] Benchmark Whisper `small` int8 on the actual target laptop — **CPU
      backend fails the gate (~2.9s)**; OpenVINO on the Iris Xe GPU gets to
      ~850ms (close, not yet passing — INT8 quantization is the next lever)
- [x] Benchmark Qwen2.5-3B tok/s via Ollama on the actual target laptop —
      **11.3 tok/s median, gate passed**
- [x] Check RAM channel configuration — soldered LPDDR5x @ 6400 MT/s, already
      optimal on this machine; the report's dual-channel-upgrade advice
      doesn't apply here
- [ ] Test openWakeWord false-accept rate in a real room — needs a live mic
      session, deferred to Phase 1 once `wake/detector.py` exists. Note:
      `wake/detector.py` now exists but loads a stock pretrained model
      (`hey_jarvis`) as a placeholder, not a trained "hey munshiji" model —
      see the Phase 1 note below before running this test.

**Gate:** if ASR > 600ms or 3B < 10 tok/s, revise model choices before Phase 1.
**Status: partially open.** LLM path cleared. ASR needs one more iteration
(INT8-quantized Whisper `small` on the Iris Xe GPU, ~30-60 min estimated) —
see `docs/PHASE-0-RESULTS.md` for the concrete next step before treating
`small` as final. Recommend starting Phase 1's non-ASR work now (ring buffer,
wake FSM, TTS) in parallel rather than blocking everything on this.

## Phase 1 — Voice loop (2 weeks, ~50h)

- [x] L0 ring buffer + Silero VAD (`audio/`)
- [x] L1 wake word + FSM + push-to-talk (`wake/`)
- [x] L2 Whisper integration (`asr/whisper.py`) — CTranslate2 CPU backend;
      `asr/openvino.py` stays the Phase 6 stub, see docs/PHASE-0-RESULTS.md
- [x] L8 Kokoro streaming TTS (`tts/kokoro.py`) — requires manually
      downloading Kokoro's weights into `data/models/kokoro/` before first
      run (no bundled/hardcoded-URL auto-download, see the class docstring
      and `.claude/rules/licensing-and-ip.md`)
- [ ] Echo-back test: say something, hear it repeated — code is in place
      (transcript passes straight through to TTS in Phase 1, no router yet).
      Ran `python -m munshiji` live on the target laptop (real mic + real
      speakers): it now starts cleanly and stays up under continuous real
      audio — found and fixed a real crash in doing so (see note below). What
      remains needs an actual human voice and ears (an AI agent has neither):
      say something, confirm it's heard correctly and repeated back at a
      tolerable latency.
- [x] Minimal floating status overlay (`ui/overlay.py`) — a Whisper-Flow/
      Gemini-style pill docked to the bottom of the screen showing
      listen/think/speak state and the last transcript. **Pulled forward from
      Phase 8 by explicit user decision** (user asked for a dashboard +
      floating control UI; Phase 2/3 — the router and tools a real dashboard
      would control — don't exist yet, so scope was cut to a pure status
      subscriber on the event bus, no controls). The full tray icon, control
      dashboard, and onboarding wizard remain Phase 8.

**Note (found on the first live run, now fixed):** `audio/vad.py`'s `SileroVad`
crashed a few seconds into real audio — the installed `silero-vad` model only
accepts fixed 512-sample windows at 16kHz (256 at 8kHz) and raises on
anything else, but `AudioCapture` hands it 1280-sample (80ms) frames sized
for openWakeWord, not Silero. This is exactly the class of bug the "not
verifiable from this dev environment" caveat existed to catch — it only
surfaced by actually running the process with a live mic, not from unit
tests or a read-through. Fixed by sub-chunking each incoming frame into
model-sized windows internally, carrying the remainder to the next call, with
regression coverage in `tests/test_vad.py` (a fake model pinned to reject any
window size other than 512/256, so a regression back to "just pass the frame
through" fails fast without needing real hardware). Verified stable for 20+
seconds of continuous live capture afterward with no crash.

**Note:** no trained "hey munshiji" openWakeWord model exists yet — training
one needs synthetic-TTS data and a training run, tracked as a follow-up, not
done as part of this phase. `wake/detector.py` defaults to the stock
`hey_jarvis` pretrained model (`config/default.yaml`'s `wake.detector_model_id`) as a
placeholder; push-to-talk (`ctrl+alt+space`) is the reliable entry point in
the meantime, per the report's own guidance that wake words fail in noise.

**Deliverable:** a thing that listens and talks. Code-complete and confirmed
running stably on the target laptop with real audio hardware; the one
remaining gate is a human actually speaking to it and confirming the
round-trip sounds and feels right — not something verifiable without a
person present.

## Phase 2 — Router + Tier 0/1 tools (3 weeks, ~70h)

- [x] `@tool` registry with tier/risk/tags (`tools/registry.py`) — schema
      generated from type hints + docstring; `blocked`-risk tools are
      structurally excluded from `ToolRegistry.iter_llm_visible()`, not just
      discouraged by prompt
- [x] hassil grammars for ~25 intents (`config/intents/`) — 24 intents across
      `system.yaml` (14), `apps.yaml` (6), `files.yaml` (4, Phase 3 tools,
      grammar staged ahead of the tools existing)
- [x] Embedding index + teach mode (`router/embeddings.py`, `router/teach.py`)
      — `multilingual-e5-small` via an injectable encoder; teach mode's
      append-example/rebuild-index primitives are implemented and tested,
      but the interactive "ask the user what this should do" voice dialogue
      is deferred — the FSM has no multi-turn dialogue state yet (see note
      below)
- [x] 20 system and app tools (`tools/system.py`, `tools/apps.py`) — 19
      tools, all with real undo paths except the handful with no sensible
      inverse (lock_screen, sleep, read-only getters)
- [x] Golden test set v1 (`tests/golden/utterances.yaml`) — 91 entries across
      en/hi/gu; Phase-2-scoped (grammar + embeddings) pass rate 100%
      exact-tool, 100% args, 100% confirm, verified against **both** the fake
      test encoder and the real `multilingual-e5-small` weights
- [x] Router wired into the voice loop (`wake/fsm.py`'s ROUTING/ACTING
      states, assembled in `__main__.py`) — this was implicit in the
      deliverable but not its own checklist line; a transcript now actually
      resolves to a tool call and executes, rather than echoing
- [x] Held-out semantic test set (`tests/golden/paraphrases.yaml`) — 53
      unseen paraphrases across en/hi/gu, none in `config/examples/` and none
      grammar-matchable. **New**, and the reason the caveats below could be
      closed honestly rather than declared closed
- [x] Out-of-domain refusal set (`tests/golden/out_of_domain.yaml`) — 18
      utterances with no Phase 2 tool, which must reach teach mode. **New**

**Deliverable: genuinely useful daily driver, no LLM required — met.** All
three caveats that were open here are now closed; full numbers, method and
residual limitations in [`docs/PHASE-2-RESULTS.md`](PHASE-2-RESULTS.md).

1. **Real-encoder verification — done, and it changed the answer.** Re-running
   the golden set with real weights returned 100% again, but that number was
   never meaningful: all 62 embedding-stage cases were *verbatim copies* of
   lines in `config/examples/*.jsonl`, so similarity is 1.0 and any encoder
   scores 100%. A genuinely held-out set was added, and on first measurement
   the router scored **75.5% tool / 73.6% args / 66.7% confirm** — a failing
   confirm gate. Three fixes brought it to **92.5% / 100% / 100%** (hi: 61.1%
   → 94.4%):
   - The embedding stage was **inheriting its arguments from the nearest
     example**, so "excel kholo" opened Chrome and "wifi ko off kar do"
     turned wifi on. Args are now re-derived from the utterance
     (`enrich_slots(..., args_from_example=True)`).
   - `router.embeddings.threshold` was recalibrated **0.75 → 0.88**. e5's
     cosine range is compressed, so unrelated text scores 0.78–0.93: at 0.75,
     *zero* of 18 out-of-domain utterances fell through to teach mode
     ("call my mother" → `restart`, caught only by the confirm gate). At 0.88
     in-domain accuracy is unchanged and 14/18 are correctly refused.
   - Example set grown 136 → 294 entries, targeting the observed confusions.
     (Top-k voting was tried as an alternative and is *worse* — see the ADR
     note in PHASE-2-RESULTS.md before re-attempting it.)
2. **Both grammar issues fixed.** `{level}` is now a hassil `RangeSlotList`
   bounded by `config.router.grammar.level_range`, so `"volume {level}"` no
   longer swallows "volume kitna hai"; direction phrasings got their own
   `{direction}` slot sharing `router/slots.py`'s vocabulary. The
   `focus_app`/`sleep` "go to" collision had in fact already been fixed
   during Phase 2 integration — that note was stale.
3. **Cross-script ASR recovery is still unhandled** — unchanged, and still
   correctly Phase 6. `rapidfuzz` fixes Latin-script mangling ("Chrom" →
   "Chrome") but not Devanagari ("क्रोम"); that needs a transliteration step
   before fuzzy-matching, which is Indic-language-specialist work.

Known limitation carried forward: the held-out set has now informed two
rounds of example additions, so 92.5% is an optimistic bound rather than a
clean estimate. Refresh `paraphrases.yaml` with genuinely unseen phrasings
before the next tuning round.

Also out of scope for this phase, deliberately: `router/slots.py` doesn't use
spaCy (nothing in the Phase 2 intent set needs date/time NER — add it when
Phase 3's file tools do), and voice-driven teach mode's "ask the user" loop
(vs. the already-working programmatic `teach()`/`rebuild_index_after_teach()`
primitives) waits on real multi-turn dialogue state, which is closer to
Phase 4/7 territory than a router concern.

## Phase 3 — Files + confirmation + undo (2 weeks, ~50h)

- [x] Everything CLI integration (`tools/files.py`) — `es.exe` when present,
      with a bounded filesystem walk as fallback. The walk also runs when
      Everything returns *nothing*, not just when it's missing: its index
      updates asynchronously, so a file saved seconds ago is routinely absent,
      and "the file I just saved" is what people actually ask about
- [x] File tools with confirm gating (`find_file`, `move_files`,
      `rename_file`, `delete_files`) — every path resolved and checked against
      `tools.files.roots` *after* `resolve()`, so `..` and symlinks can't
      escape; batches capped at `max_batch`; deletion goes to the Recycle Bin,
      never `os.remove`
- [x] Spoken confirmation gate (`security/confirm.py`) + the FSM's CONFIRMING
      state — the first multi-turn state in the voice loop. Only an ASR
      transcript can confirm; pending proposals expire; ambiguity is re-asked
      and then dropped. All three fail closed
- [x] Undo stack (`security/undo.py`) reachable by voice (`undo_last`,
      `what_can_i_undo`) — the safety net is only useful if the user can get
      to it without knowing it exists
- [x] Audit log (`security/audit.py`) — append-only JSONL, attached to the
      event bus as a subscriber rather than called by the FSM, recording the
      action, arguments, result, timestamp and deciding router stage
- [x] `preview=` on the tool registry — a confirm prompt now says "Move 2
      files from Desktop to Documents", which is what §8.2 actually requires;
      an argument dump gives the user nothing to catch a misroute with
- [x] `battery_status` implemented — see the note below

**Deliverable: safe to point at real files — met.** Verified end to end on
this machine against the real router, the real encoder, real tools and a real
audit log, in a temp sandbox configured as the file roots: search, a
confirm-gated move answered "nahi" (nothing moved), the same move answered
"haan" then reversed with "undo that", a delete to the Recycle Bin, and an
out-of-scope question refused.

**Two findings worth carrying forward:**

1. **`battery_status` never existed.** It had a grammar template, examples in
   all three languages and golden cases since Phase 2 — and no tool. Nothing
   caught it because the golden runner graded against a fake registry built
   *from the golden set itself*, so every tool the set named existed by
   construction. The runner now uses the real `REGISTRY`, plus three new
   tests: every golden tool is registered, `expect_confirm` and `risk=` agree
   in both directions, and every confirm-risk tool has a golden case. The
   Phase 2 confirm-gate figure of "100%" held only because the fake registry
   declared confirm exactly the two tools the golden set expected to be
   confirm — it was checking a copy of the answer, not the registry.
2. **Grammar templates for file intents are unusually greedy**, and the golden
   set caught two of mine immediately: `"put {query} in {destination}"` ate
   "put spotify in the background" (minimize_app), and
   `"get rid of {query}"` ate "get rid of chrome" (close_app). Both were
   dropped rather than patched around — those phrasings live as embedding
   examples now, where they compete on similarity instead of claiming the
   utterance outright at Stage 1.

**Deliberately not done, and why:**

- **Undo of a delete is guided, not automatic.** `move_files` and
  `rename_file` register real inverses that run. `delete_files` sends files to
  the Recycle Bin and its undo names them and says where they are. Windows has
  no supported API for restoring a specific item; it can be driven through the
  shell namespace, but items there are identified by an internal `$R…` path and
  the original location is only available as a localized detail column, so
  matching on it breaks on non-English Windows. Building the mutating half of
  undo on that would be worse than not having it. Measured on this machine
  before deciding — see `tools/files.py::_undo_delete_files`.
- **No date filtering.** "find the budget report from last week" stays
  `expect_stage: llm`. `router/slots.py` still has no date NER (spaCy remains
  deliberately absent), so the words would land in the filename pattern and
  match nothing. That is Phase 4 work, not a missing template.
- **Indic file-type vocabulary** ("tasveerein", "gaane") is not in
  `_TYPE_EXTENSIONS` — Phase 6, with the rest of the Indic layer. Hindi and
  Gujarati file commands route to the right *intent* today and are asked for
  specifics, which degrades to "finds less", never to "deletes something
  unexpected".

**One consequence to keep an eye on:** out-of-domain refusal fell 14/18 →
13/18 when the file intents entered the index (`mane ek varta kaho`, "tell me
a story", now sits near the Gujarati find_file examples). The *severity* of a
leak dropped at the same time, which matters more: the embedding stage no
longer inherits free-text args, so a leaked file intent arrives with none and
the assistant asks "which files do you mean?" instead of acting.
"meri maa ko phone lagao" — Phase 2's worst leak, which resolved to `restart`
— now resolves to `find_file` with no arguments, i.e. a question. See
`tests/golden/out_of_domain.yaml`.

## Phase 4 — Escalation (2 weeks, ~50h)

**Re-scoped by [ADR 0001](decisions/0001-local-llm-off-the-default-path.md).**
Was "LLM escalation," built around Ollama as the default target. The local 3B
measured 11.3 tok/s (~88ms/token) on a benchmark that only generated 4–6
tokens — realistically ~4.4s for a tool call, ~10.6s for a paragraph, and
unreliable on facts. It is now an **opt-in privacy mode**, not the default.
The orchestration work below is unchanged; what it points at is now pluggable.

- [ ] Escalation dispatcher honouring `router.escalation` (`brain/loop.py`) —
      ordered targets, bounded loop, hard cap 5 iterations
- [ ] Cloud target (`brain/cloud.py`) — **the default**; spoken-confirm gated
      before anything leaves the machine, BYO-key first
- [ ] Knowledge-question route — embedding-classified question-vs-command,
      answered by cloud or **refused honestly when offline**. New; there is no
      such route in `config/intents/` today.
- [ ] Stable-prefix prompt assembly (`brain/prompt.py`) — stable core tool set
      in the cached prefix, per-query retrieved tools in the volatile tail
      (the KV-cache/tool-retrieval contradiction ADR 0001 corrects)
- [ ] Tool subsetting by embedding
- [ ] Dry-run plan summarization
- [ ] Local target (`brain/ollama.py`) — opt-in, `llm.enabled: false` by
      default; use constrained decoding (GBNF/outlines) for tool-call JSON
- [ ] Re-benchmark the local path at realistic output lengths (50 and 150
      tokens) so the opt-in mode's latency claim is measured, not extrapolated
- [ ] Golden-set entries for escalation and the offline-refusal case

**Deliverable:** handles compositional requests and knowledge questions —
every route either fast and deterministic, or slow and good, or honest. No
route is both slow and unreliable.

## Phase 5 — Office + network (3 weeks, ~70h)

- [ ] COM tools: Outlook, Excel, Word (`tools/office.py`)
- [ ] Allowlisted HTTP client (`net/client.py`)
- [ ] Weather, search, finance (`tools/web.py`)
- [ ] MCP client bridge (`tools/mcp_bridge.py`)
- [ ] Google via app password (`tools/google.py`)

**Deliverable:** does real work.

## Phase 6 — Indic (3 weeks, ~70h)

- [ ] IndicWhisper integration (`asr/`)
- [ ] Multilingual embedding index, hi/gu example sets (`config/examples/`)
- [ ] IndicTTS (`tts/indic.py`)
- [ ] Language auto-routing

**Deliverable:** the differentiator.

## Phase 7 — Memory + RAG (2 weeks, ~45h)

- [ ] SQLite facts, working state (`memory/facts.py`, `memory/working.py`)
- [ ] Chroma document index (`memory/documents.py`)
- [ ] Screen understanding (moondream)
- [ ] Local FastAPI server (`net/api.py`)

## Phase 8 — Packaging + licensing (3 weeks, ~70h)

- [ ] Tray UI, control dashboard, onboarding wizard (`ui/`) — note: a minimal
      status-only overlay (`ui/overlay.py`) already exists, pulled forward
      into Phase 1; this phase still owns the tray icon, the real control
      dashboard wired to the router/tools, and onboarding
- [ ] PyInstaller + Inno Setup (`scripts/package.py`, `installer/`)
- [ ] Code signing
- [ ] Licence verification (`licence/verify.py`)
- [ ] Auto-update

**Deliverable:** shippable installer.

## Phase 9 — Commercial (3 weeks, ~65h)

- [ ] Landing page, docs
- [ ] Licence server
- [ ] Payment integration
- [ ] Support workflow

---

## Immediate next actions (§19.4)

1. Check RAM channel configuration — five seconds, largest cheap speedup
   available.
2. Run Phase 0 benchmarks before writing any product code.
3. Decide fork-vs-build on Goose — moves the timeline by 100–150h and
   determines whether MCP support comes free.
4. Verify the exact licence of the specific model weights intended for
   shipping, at the specific size, on the model card (see
   `docs/LICENSING-AUDIT.md`).
5. Record a 30-second demo as soon as Phase 1 works — it's both motivation and
   the entire early marketing asset.
