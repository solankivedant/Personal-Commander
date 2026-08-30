## What this changes

## Which roadmap phase

See `docs/ROADMAP.md` — confirm this doesn't skip ahead of the current phase's
gate (e.g. don't ship Phase 5 tools before Phase 2's router is solid).

## Checklist

- [ ] `ruff check` and `mypy --strict` pass locally
- [ ] Golden test set run (`.claude/skills/golden-test/`) — pass rate stated
      below, no regression below the CI gate (92% tool / 85% args / 100%
      `expect_confirm`)
- [ ] If a new `@tool` was added: tier/risk/tags set honestly, undo registered
      if it mutates state, exceptions caught internally
      (`.claude/skills/new-tool/SKILL.md`)
- [ ] If `tools/`, `net/`, or `security/` changed: reviewed against
      `.claude/rules/security-and-privacy.md` (consider running the
      `security-auditor` agent)
- [ ] If a new dependency or model was added: licence recorded in
      `docs/LICENSING-AUDIT.md`
- [ ] `docs/ROADMAP.md` checkboxes updated if this completes or advances a
      phase item

## Golden test set result

Before: `__%` tool match / `__%` args match
After: `__%` tool match / `__%` args match
