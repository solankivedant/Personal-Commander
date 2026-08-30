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
- If `risk="confirm"`, the caller (loop/confirm gate) is what speaks the intent
  and blocks on a yes — the tool itself just executes once approved. Don't
  build a second confirmation inside the tool function.
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

If touching anything in `tools/`, `net/`, or `security/`, consider invoking the
`security-auditor` agent before merging.
