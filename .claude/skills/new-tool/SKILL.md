---
name: new-tool
description: Scaffold a new @tool in src/munshiji/tools/ following the registry contract (tier, risk, tags, undo, error handling) and add a matching golden-test entry. Use when the user asks to add a new capability/command/action to Munshiji, e.g. "add a tool for muting the mic" or "let it lock the screen by voice".
---

# Adding a new tool

Follow this sequence for every new tool. Don't skip steps to save time — a tool
missing any of these is not done, per `.claude/rules/security-and-privacy.md`.

## 1. Classify it first

Before writing code, answer:

- **Which module** does it belong in? `tools/system.py` (volume/power/
  brightness), `apps.py` (launch/focus/close), `files.py` (search/move/batch),
  `office.py` (COM: Outlook/Excel/Word), `web.py` (search/weather), `google.py`
  (Gmail/Calendar), `phone.py` (KDE Connect), or `mcp_bridge.py` (MCP-sourced).
- **`tier`**: `local` (never touches network), `lan` (this network only), or
  `net` (leaves the machine). Judge by what it actually does, not intent.
- **`risk`**: `safe` by default. `confirm` if it deletes, sends, spends, or
  overwrites anything. `blocked` if it touches credentials, the registry, or
  mass deletion — and a `blocked` tool must not be reachable from the LLM loop.
- **Does it mutate state?** If yes, it needs an inverse for the undo stack.

## 2. Write the tool

```python
from munshiji.tools.registry import tool

@tool(tier="local", risk="confirm", tags=["files"], undo="move_files_inverse")
def move_files(source_dir: str, pattern: str, dest_dir: str) -> str:
    """Move files matching a glob pattern from one folder to another.

    Args:
        source_dir: Absolute path to the source folder.
        pattern: Glob pattern, e.g. '*.pdf'.
        dest_dir: Absolute path to the destination folder.
    """
```

The registry decorator generates the JSON schema the LLM sees from the type
hints and docstring — keep both precise, not just readable.

Requirements:
- Catch every exception internally; return a short, readable failure string.
  Never let an exception propagate to the LLM loop as a traceback.
- If `risk="confirm"`, the caller (`security/confirm.py`) is what speaks the
  intent and blocks on a yes — the tool itself just executes once approved.
  Don't build a second confirmation inside the tool function.
- If `risk="confirm"` **and the effect can't be read off the arguments**, pass
  `preview=` too: a function taking the same arguments that returns what the
  tool *would* do, without doing it. §8.2 wants "I'll move 14 PDFs from Desktop
  to Documents/Invoices. Proceed?" — only the tool can turn "all the PDFs" into
  a count and a folder, and a prompt that just names arguments gives the user
  nothing to catch a misroute with. See `tools/files.py::_preview_move_files`.
- Anything with a free-text slot the embedding stage can't re-derive (a
  filename, a folder, a message body) belongs in
  `router/slots.py::_UNDERIVABLE_TEXT_SLOTS`, so an embedding match arrives
  with the slot missing rather than inheriting the nearest example's value.
- If it mutates state, implement and register the inverse function alongside
  it, in the same file, before the tool is considered complete.
- If it's `net` tier, call out through `net/client.py`'s shared allowlisted
  client — never a fresh `httpx`/`requests` instance — and add the target
  domain to `config/default.yaml`'s `network.allowlist` if it isn't already
  there.

## 3. Add routing so the tool is reachable

Pick one or both:
- **Grammar**: add a hassil template to the matching file in `config/intents/`
  for the common phrasing(s).
- **Embeddings**: add 3–5+ example utterances per language (en, and hi/gu where
  the vocabulary is shared — see `.claude/agents/indic-language-specialist.md`)
  to `config/examples/{en,hi,gu}.jsonl`.

Then rebuild the index: `python scripts/build_index.py` (once implemented per
`docs/ROADMAP.md` Phase 2).

## 4. Add a golden-test entry

In `tests/golden/utterances.yaml`:

```yaml
- text: "move all pdfs from desktop to documents"
  lang: en
  expect_tool: move_files
  expect_args: {source_dir: "Desktop", pattern: "*.pdf", dest_dir: "Documents"}
  expect_stage: grammar        # or embeddings / llm
  expect_confirm: true         # required if risk="confirm"
```

Add at least one entry per language you added examples for.

## 5. Verify

Run the golden test set (`.claude/skills/golden-test/`) and confirm:
- the new case matches the intended tool and stage
- overall accuracy is still ≥92% exact tool match, ≥85% args match
- `expect_confirm` cases are 100% — this one never gets a pass

The runner grades against the **real** registry, so three further tests will
fail on an incomplete change, and each is telling you something specific:
- `test_every_golden_tool_is_registered` — the golden set names a tool that
  doesn't exist. (This is how `battery_status` was found in Phase 3: grammar,
  examples and golden cases since Phase 2, no tool behind any of them.)
- `test_confirm_risk_matches_golden_expectations` — `expect_confirm` and
  `risk=` disagree, in either direction.
- `test_every_confirm_tool_has_a_golden_case` — a destructive tool with no
  case exercising its gate.

Watch for grammar templates that are too greedy, especially for free-text
slots. `"put {query} in {destination}"` looks harmless and silently swallowed
"put spotify in the background". The golden set catches these — read a failure
on an *unrelated* intent as your new template stealing it.

If touching anything in `tools/`, `net/`, or `security/`, consider invoking the
`security-auditor` agent before merging.
