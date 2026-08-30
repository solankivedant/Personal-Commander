# Engineering standards

Source: `munshiji-full-report.md` §5.1–5.2. Applies to all code under `src/`,
`tests/`, and `scripts/`.

## Dependencies

- `uv` for all dependency management, with a committed `uv.lock`.
- Pin Ollama model tags **by digest, not `:latest`** — an upstream retag can
  silently change model behaviour overnight with no code change on our side.
- Model weight licences vary by size within the same family (§13.2). Before
  adding any new model, verify the licence for the exact size being shipped and
  record it in `docs/LICENSING-AUDIT.md`.

## Static checks

- `mypy --strict` on `src/`.
- `ruff` for linting.
- Both run in CI (`.github/workflows/ci.yml`) and should pass locally before
  committing.

## Testing

- `pytest` for unit tests.
- **The golden test set is mandatory**, not optional coverage:
  `tests/golden/utterances.yaml`, 80–120 utterances spanning en/hi/gu, each
  mapped to an expected tool call and router stage.
- Run it after *any* change to a prompt, a model, the grammar files, or the
  embedding index. It takes under two minutes and is the only thing standing
  between you and silent regression — the failure mode here is not a crash, it's
  the model quietly stopping selecting the right tool.
- CI gate: ≥ 92% exact tool match, ≥ 85% args match, **100% on `expect_confirm`
  cases**. A missed confirmation gate is a correctness bug, full stop — never
  relax that threshold to unblock a merge.
- When adding a new intent or tool, add at least one golden-set entry for it in
  the same change. Use `/golden-test` (`.claude/skills/golden-test/`) to run and
  interpret results.

## Configuration

- YAML only, in `config/`. **No behaviour constants in source** — thresholds,
  model names, timeouts, silence durations, etc. all belong in
  `config/default.yaml` or the files it references.
- If you find yourself hardcoding a number that isn't a genuine invariant
  (array index, HTTP status code), move it to config instead.

## Error handling

- Every tool in `tools/` catches its own exceptions and returns a structured,
  readable failure string — e.g. `"Could not find an app matching 'chrom'."`
  Never let an exception reach the LLM loop as a raw traceback; a 3B model
  cannot usefully recover from one and it looks broken to the user.
- Don't add defensive error handling for scenarios that can't happen (see the
  root-level engineering conventions) — this rule is specifically about the
  tool/LLM boundary, not a licence to wrap everything in `try/except`.

## Logging

- `structlog` → rotating JSONL.
- The append-only audit log (`security` cross-cutting concern, `data/audit.jsonl`
  per `config/default.yaml`) must record every action, its arguments, its
  result, a timestamp, and which router stage decided it. This is the only thing
  that will explain "why did it delete that" three days later — treat gaps in it
  as bugs.

## Repo structure discipline

- Keep new modules inside the existing layer boundaries in
  `docs/ARCHITECTURE.md` (L0–L8). A new capability almost always belongs in an
  existing package (`tools/`, `router/`, etc.) rather than a new top-level one.
- Build in roadmap phase order (`docs/ROADMAP.md`, §11 of the report). Don't
  implement a later phase's feature as a shortcut inside an earlier phase's
  module — it breaks the "no LLM required until Phase 4" deliverable.
